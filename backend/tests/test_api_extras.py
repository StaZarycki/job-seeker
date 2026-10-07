"""Endpoints added for the web frontend: offer marks, single-offer AI, background sync, settings, error codes."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from job_seeker.api.app import create_app
from job_seeker.config import AIConfig, AppConfig
from job_seeker.domain.models import JobOffer
from job_seeker.services.job_seeker import JobSeekerService, MatchRequest, SyncInProgressError
from job_seeker.sources.base import FetchProgress, ProgressCallback, SourceQuery
from job_seeker.storage.db import Database
from tests.conftest import SAMPLE_CV, make_pdf
from tests.fakes import FakeScorer, FakeSource


class SlowSource(FakeSource):
    """Yields one offer every 20 ms so a sync can be observed and cancelled midway."""

    async def fetch_offers(
        self, query: SourceQuery, on_progress: ProgressCallback | None = None
    ) -> AsyncIterator[JobOffer]:
        for i, offer in enumerate(self.offers, 1):
            await asyncio.sleep(0.02)
            yield offer
            if on_progress:
                on_progress(FetchProgress("javascript", 1, 1, i, len(self.offers)))


@pytest.fixture
def offers_now(offers: list[JobOffer]) -> list[JobOffer]:
    now = datetime.now(UTC)
    return [o.model_copy(update={"published_at": now, "expires_at": None}) for o in offers]


@pytest.fixture
def config(app_config: AppConfig) -> AppConfig:
    search = app_config.search.model_copy(
        update={"categories": ["javascript"], "onsite_only_in_preferred_cities": False, "max_offer_age_days": None}
    )
    cv_dir = app_config.base_dir / "cv"
    cv_dir.mkdir()
    (cv_dir / "cv.pdf").write_bytes(make_pdf(SAMPLE_CV))
    return app_config.model_copy(update={"search": search, "ai": AIConfig(top_n=2)})


@pytest.fixture
def scorer() -> FakeScorer:
    return FakeScorer(score=77)


@pytest.fixture
def service(config: AppConfig, offers_now: list[JobOffer], scorer: FakeScorer) -> JobSeekerService:
    source = FakeSource(offers_now)
    return JobSeekerService(config, source_factory=lambda name, cfg: source, scorer_factory=lambda cfg: scorer)


async def test_hidden_offers_are_left_out_and_saved_can_be_listed(service: JobSeekerService) -> None:
    await service.sync()
    first = (await service.match(MatchRequest(top=50))).report.results
    hidden_id, saved_id = first[0].offer.id, first[1].offer.id
    service.set_offer_status(hidden_id, "hidden")
    service.set_offer_status(saved_id, "saved")

    results = (await service.match(MatchRequest(top=50))).report.results
    assert hidden_id not in {r.offer.id for r in results}
    assert next(r for r in results if r.offer.id == saved_id).status == "saved"
    saved = (await service.match(MatchRequest(top=50, status="saved"))).report.results
    assert [r.offer.id for r in saved] == [saved_id]

    service.set_offer_status(hidden_id, None)
    assert hidden_id in {r.offer.id for r in (await service.match(MatchRequest(top=50))).report.results}


async def test_assess_single_offer_uses_cache(service: JobSeekerService, scorer: FakeScorer) -> None:
    await service.sync()
    offer_id = (await service.match(MatchRequest(top=50))).report.results[-1].offer.id

    result = await service.assess_offer(offer_id)
    assert result.ai is not None and result.ai.assessment.score == 77
    assert result.final_score == round(0.7 * 77 + 0.3 * result.rule.score, 1)
    assert scorer.descriptions[-1]  # description fetched before asking the model

    await service.assess_offer(offer_id)
    assert scorer.calls.count(offer_id) == 1  # second call served from cache


async def test_background_sync_reports_progress_and_history(service: JobSeekerService) -> None:
    state = service.start_sync_job()
    assert state.running
    with pytest.raises(SyncInProgressError):
        service.start_sync_job()
    await service.wait_for_sync()

    done = service.sync_status()
    assert not done.running and done.error is None and not done.cancelled
    assert done.fetched == done.total and done.results[0].new == done.fetched
    [run] = service.db.sync_history()
    assert run.categories == ["javascript"] and run.fetched == done.fetched


async def test_cancelled_sync_keeps_downloaded_offers(config: AppConfig, offers_now: list[JobOffer]) -> None:
    service = JobSeekerService(config, source_factory=lambda name, cfg: SlowSource(offers_now))
    service.start_sync_job()
    await asyncio.sleep(0.09)
    assert service.cancel_sync()
    await service.wait_for_sync()

    state = service.sync_status()
    assert state.cancelled and not state.running
    kept = len(service.db.list_offers())
    assert 0 < kept < len(offers_now)
    [run] = service.db.sync_history()
    assert run.error == "Synchronizacja przerwana" and run.fetched == kept


def test_old_database_gets_categories_column(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE sync_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, started_at TEXT "
            "NOT NULL, finished_at TEXT, fetched INTEGER NOT NULL DEFAULT 0, new_offers INTEGER NOT NULL DEFAULT 0, "
            "error TEXT)"
        )
        conn.execute("INSERT INTO sync_runs (source, started_at) VALUES ('justjoin', '2026-10-07T18:00:00+00:00')")
    db = Database(path)
    [run] = db.sync_history()
    assert run.categories is None


def test_api_endpoints_for_frontend(service: JobSeekerService) -> None:
    with TestClient(create_app(service=service)) as client:
        assert client.post("/sync", json={}).status_code == 202
        for _ in range(200):
            if not client.get("/sync/status").json()["running"]:
                break
        status = client.get("/sync/status").json()
        assert status["results"][0]["fetched"] > 0
        assert client.delete("/sync").status_code == 409  # nothing running any more

        history = client.get("/syncs").json()
        assert history[0]["categories"] == ["javascript"]

        offer_id = client.get("/matches", params={"top": 1}).json()["results"][0]["offer"]["id"]
        assert client.put(f"/offers/{offer_id}/status", json={"status": "saved"}).status_code == 204
        saved = client.get("/matches", params={"status": "saved"}).json()["results"]
        assert [r["offer"]["id"] for r in saved] == [offer_id] and saved[0]["status"] == "saved"
        missing = client.put("/offers/justjoin:nope/status", json={"status": "saved"})
        assert missing.status_code == 404 and missing.json()["code"] == "offer_not_found"

        assessed = client.post(f"/offers/{offer_id}/assess").json()
        assert assessed["ai"]["assessment"]["score"] == 77

        settings = client.get("/settings").json()
        assert settings["experience"]["transfer_ratio"] == 0.35 and settings["ai"]["top_n"] == 2

        unknown = client.get("/matches", params={"search": "nope"}).json()
        assert unknown["code"] == "invalid_request"

        cors = client.get("/health", headers={"Origin": "http://localhost:5173"})
        assert cors.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_error_codes(config: AppConfig, offers_now: list[JobOffer]) -> None:
    from job_seeker.matching.ai.base import AIConfigurationError

    class NoKeyScorer(FakeScorer):
        def __init__(self) -> None:
            super().__init__(config_error=True)

    for pdf in (config.base_dir / "cv").glob("*.pdf"):
        pdf.unlink()
    service = JobSeekerService(
        config, source_factory=lambda name, cfg: FakeSource(offers_now), scorer_factory=lambda cfg: NoKeyScorer()
    )
    with TestClient(create_app(service=service)) as client:
        assert client.get("/profile").json()["code"] == "cv_not_found"
        (config.base_dir / "cv" / "cv.pdf").write_bytes(make_pdf(SAMPLE_CV))
        client.post("/sync", json={})
        for _ in range(200):
            if not client.get("/sync/status").json()["running"]:
                break
        response = client.get("/matches", params={"mode": "ai"})
        assert response.status_code == 400 and response.json()["code"] == "ai_not_configured"
    assert issubclass(AIConfigurationError, RuntimeError)
