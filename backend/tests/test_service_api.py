from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from job_seeker.api.app import create_app
from job_seeker.config import AIConfig, AppConfig, MatchingMode
from job_seeker.domain.models import JobOffer
from job_seeker.services.job_seeker import JobSeekerService, MatchRequest
from tests.conftest import SAMPLE_CV, make_pdf
from tests.fakes import FakeScorer, FakeSource


def sync_via_api(client: TestClient, **body: Any) -> dict[str, Any]:
    """Start a background sync through the API and wait until it finishes."""
    response = client.post("/sync", json=body)
    assert response.status_code == 202, response.text
    for _ in range(200):
        status: dict[str, Any] = client.get("/sync/status").json()
        if not status["running"]:
            return status
        time.sleep(0.01)
    raise AssertionError("sync did not finish")


@pytest.fixture
def stable_offers(offers: list[JobOffer]) -> list[JobOffer]:
    """Fixture offers with dates pinned to 'now', so tests don't depend on when they run."""
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
    searches = {"cpp": {"categories": ["javascript"], "target_skills": ["C++"], "title_keywords": ["c++"]}}
    return app_config.model_copy(update={"search": search, "ai": AIConfig(top_n=2), "searches": searches})


@pytest.fixture
def source(stable_offers: list[JobOffer]) -> FakeSource:
    return FakeSource(stable_offers)


@pytest.fixture
def scorer() -> FakeScorer:
    return FakeScorer(score=95)


@pytest.fixture
def service(config: AppConfig, source: FakeSource, scorer: FakeScorer) -> JobSeekerService:
    return JobSeekerService(config, source_factory=lambda name, cfg: source, scorer_factory=lambda cfg: scorer)


async def test_sync_then_match_basic(service: JobSeekerService, stable_offers: list[JobOffer]) -> None:
    [result] = await service.sync()
    assert result.fetched == len(stable_offers) and result.new == len(stable_offers) and result.error is None
    [again] = await service.sync()
    assert again.new == 0

    outcome = await service.match(MatchRequest(top=5))
    assert outcome.report.mode is MatchingMode.BASIC
    assert len(outcome.report.results) == 5
    assert outcome.profile.rebuilt  # first load builds from cv/cv.pdf


async def test_match_ai_fetches_descriptions_and_persists_them(
    service: JobSeekerService, source: FakeSource, scorer: FakeScorer
) -> None:
    await service.sync()
    outcome = await service.match(MatchRequest(mode=MatchingMode.AI, top=5))

    assert len(scorer.calls) == 2
    assert all(d and d.startswith("Opis oferty") for d in scorer.descriptions)
    assert len(source.detail_calls) == 2
    assert outcome.report.results[0].ai is not None
    stored = service.db.get_offer(scorer.calls[0])
    assert stored is not None and stored.description

    await service.sync()  # re-sync must not wipe fetched descriptions
    stored = service.db.get_offer(scorer.calls[0])
    assert stored is not None and stored.description


async def test_preference_overrides(service: JobSeekerService) -> None:
    await service.sync()
    outcome = await service.match(MatchRequest(top=50, preferences={"exclude_keywords": ["React", "Angular"]}))
    for r in outcome.report.results:
        assert "react" not in r.offer.title.lower()
    assert outcome.preferences.exclude_keywords == ["React", "Angular"]


def test_api_end_to_end(service: JobSeekerService, config: AppConfig) -> None:
    with TestClient(create_app(service=service)) as client:
        assert client.get("/health").json() == {"status": "ok"}

        sync = sync_via_api(client)
        assert sync["results"][0]["fetched"] > 0 and sync["error"] is None

        sources = client.get("/sources").json()
        assert sources[0]["name"] == "justjoin" and sources[0]["offers_in_db"] > 0

        matches = client.get("/matches", params={"top": 3}).json()
        assert matches["mode"] == "basic" and len(matches["results"]) == 3
        first = matches["results"][0]
        assert first["offer"]["url"].startswith("https://") and first["rule"]["breakdown"]

        ai = client.get("/matches", params={"top": 3, "mode": "ai"}).json()
        assert ai["ai"]["calls"] == 2 and ai["results"][0]["ai"]["assessment"]["score"] == 95

        offer = client.get(f"/offers/{first['offer']['source']}:{first['offer']['external_id']}")
        assert offer.status_code == 200 and offer.json()["description"]
        assert client.get("/offers/justjoin:missing").status_code == 404

        profile = client.get("/profile").json()
        assert "node.js" in {s["name"] for s in profile["profile"]["skills"]}

        updated = client.put("/profile/overrides", json={"add_skills": ["Rust"]}).json()
        assert updated["profile_hash"] != profile["profile_hash"]
        assert client.get("/profile/overrides").json()["add_skills"] == ["Rust"]

        upload = client.post(
            "/profile/cv", files={"file": ("nowe.pdf", make_pdf([*SAMPLE_CV, "Skills", "Elixir"]), "application/pdf")}
        )
        assert upload.status_code == 200 and upload.json()["profile"]["source_file"] == "nowe.pdf"
        bad = client.post("/profile/cv", files={"file": ("x.pdf", b"not a pdf", "application/pdf")})
        assert bad.status_code == 400

        assert client.get("/sources/justjoin/categories").json() == [
            {"key": "javascript", "count": len(service.db.list_offers())}
        ]


def test_api_reports_missing_cv(config: AppConfig, source: FakeSource) -> None:
    for pdf in Path(config.base_dir / "cv").glob("*.pdf"):
        pdf.unlink()
    service = JobSeekerService(config, source_factory=lambda name, cfg: source)
    with TestClient(create_app(service=service)) as client:
        response = client.get("/profile")
        assert response.status_code == 404 and "Nie znaleziono CV" in response.json()["detail"]


async def test_search_preset_is_applied(service: JobSeekerService) -> None:
    await service.sync(search="cpp")
    prefs = service.preferences("cpp")
    assert prefs.target_skills == ["C++"] and prefs.title_keywords == ["c++"]
    assert prefs.preferred_cities == service.config.search.preferred_cities  # inherited from [search]
    with pytest.raises(ValueError, match="Nieznany profil"):
        service.preferences("nope")


async def test_ai_cache_is_separate_per_preset(service: JobSeekerService, scorer: FakeScorer) -> None:
    await service.sync()
    await service.match(MatchRequest(mode=MatchingMode.AI, top=5))
    assert len(scorer.calls) == 2
    await service.match(MatchRequest(mode=MatchingMode.AI, top=5))
    assert len(scorer.calls) == 2  # cached
    await service.match(MatchRequest(mode=MatchingMode.AI, top=5, search="cpp"))
    assert len(scorer.calls) == 4  # different target skills -> fresh assessments
    assert scorer.contexts[-1].target_skills == ["C++"]
    assert scorer.contexts[-1].effective_years is not None


def test_api_search_presets(service: JobSeekerService) -> None:
    with TestClient(create_app(service=service)) as client:
        sync_via_api(client, search="cpp")
        searches = {s["name"]: s for s in client.get("/searches").json()}
        assert searches["cpp"]["preferences"]["target_skills"] == ["C++"]
        assert searches[None]["passed"] > 0 and not searches["cpp"]["needs_sync"]
        response = client.get("/matches", params={"search": "cpp", "top": 3})
        assert response.status_code == 200
        assert response.json()["preferences"]["target_skills"] == ["C++"]
        unknown = client.get("/matches", params={"search": "nope"})
        assert unknown.status_code == 400 and "Nieznany profil" in unknown.json()["detail"]
