"""Application service shared by the CLI and the REST API."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from job_seeker.config import AIConfig, AppConfig, MatchingMode, SearchPreferences
from job_seeker.domain.models import JobOffer
from job_seeker.matching.ai.base import AIScorer
from job_seeker.matching.ai.registry import create_scorer
from job_seeker.matching.pipeline import AIPlanCallback, MatchReport, run_matching
from job_seeker.profile.service import ProfileService, ProfileState
from job_seeker.sources.base import CategoryInfo, JobSource, SourceError, SourceQuery
from job_seeker.sources.registry import create_source
from job_seeker.storage.db import Database, UpsertStats

log = logging.getLogger(__name__)

SourceFactory = Callable[[str, AppConfig], JobSource]
ScorerFactory = Callable[[AIConfig], AIScorer]


class MatchRequest(BaseModel):
    """Per-request overrides of the configured defaults."""

    mode: MatchingMode | None = None
    top: int = Field(default=20, ge=1, le=500)
    provider: str | None = None
    model: str | None = None
    min_score: float | None = Field(default=None, ge=0, le=100)
    search: str | None = Field(default=None, description="Named search preset from [searches.<name>]")
    preferences: dict[str, Any] = Field(default_factory=dict, description="Overrides of SearchPreferences fields")


@dataclass(frozen=True)
class SyncResult:
    source: str
    fetched: int
    new: int
    error: str | None = None


@dataclass
class MatchOutcome:
    report: MatchReport
    profile: ProfileState
    preferences: SearchPreferences


class JobSeekerService:
    def __init__(
        self,
        config: AppConfig,
        *,
        db: Database | None = None,
        profiles: ProfileService | None = None,
        source_factory: SourceFactory = create_source,
        scorer_factory: ScorerFactory = create_scorer,
    ) -> None:
        self.config = config
        self.db = db or Database(config.resolve(config.paths.database))
        self.profiles = profiles or ProfileService.from_config(config)
        self._source_factory = source_factory
        self._scorer_factory = scorer_factory

    def load_profile(self, force_rebuild: bool = False) -> ProfileState:
        return self.profiles.load(force_rebuild=force_rebuild)

    def preferences(self, search: str | None = None, overrides: dict[str, Any] | None = None) -> SearchPreferences:
        """[search] from config <- named preset ``search`` <- per-request ``overrides``."""
        return self.config.preferences(search, overrides)

    async def sync(
        self,
        sources: list[str] | None = None,
        categories: list[str] | None = None,
        limit: int | None = None,
        on_source_done: Callable[[SyncResult], None] | None = None,
        search: str | None = None,
    ) -> list[SyncResult]:
        """Download offers into the local database. Offers are stored unfiltered (beyond category), so
        changing preferences later doesn't require another sync. ``search`` takes sources/categories from
        a named preset."""
        prefs = self.preferences(search)
        query = SourceQuery(categories=categories if categories is not None else prefs.categories, limit=limit)
        results = []
        for name in sources or prefs.sources:
            run_id = self.db.start_sync(name)
            offers: list[JobOffer] = []
            error = None
            source = self._source_factory(name, self.config)
            try:
                async for offer in source.fetch_offers(query):
                    offers.append(offer)
            except SourceError as exc:
                error = str(exc)
                log.warning("Sync of %s failed: %s", name, exc)
            finally:
                await source.aclose()
            stats = self.db.upsert_offers(offers) if offers else UpsertStats()
            self.db.finish_sync(run_id, stats, error)
            result = SyncResult(source=name, fetched=stats.fetched, new=stats.new, error=error)
            results.append(result)
            if on_source_done:
                on_source_done(result)
        return results

    async def match(self, request: MatchRequest, on_ai_plan: AIPlanCallback | None = None) -> MatchOutcome:
        profile_state = self.load_profile()
        prefs = self.preferences(request.search, request.preferences)
        mode = request.mode or self.config.matching.mode
        offers = self.db.list_offers(
            sources=prefs.sources, categories=prefs.categories, max_age_days=prefs.max_offer_age_days
        )

        ai_config = self.config.ai.model_copy(
            update={k: v for k, v in {"provider": request.provider, "model": request.model}.items() if v}
        )
        scorer = self._scorer_factory(ai_config) if mode is MatchingMode.AI else None
        sources: dict[str, JobSource] = {}

        async def enrich(offer: JobOffer) -> JobOffer:
            if offer.source not in sources:
                sources[offer.source] = self._source_factory(offer.source, self.config)
            detailed = await sources[offer.source].fetch_details(offer)
            self.db.save_offer(detailed)
            return detailed

        try:
            report = await run_matching(
                offers,
                profile_state.profile,
                profile_state.profile_hash,
                prefs=prefs,
                weights=self.config.matching.weights,
                mode=mode,
                top=request.top,
                db=self.db,
                ai_config=ai_config,
                scorer=scorer,
                enrich=enrich,
                on_ai_plan=on_ai_plan,
                experience_config=self.config.matching.experience,
            )
        finally:
            for source in sources.values():
                await source.aclose()
            if scorer is not None:
                await scorer.aclose()
        if request.min_score is not None:
            report.results = [r for r in report.results if r.final_score >= request.min_score]
        return MatchOutcome(report=report, profile=profile_state, preferences=prefs)

    async def offer_with_details(self, offer_id: str) -> JobOffer | None:
        offer = self.db.get_offer(offer_id)
        if offer is None or offer.description is not None:
            return offer
        source = self._source_factory(offer.source, self.config)
        try:
            offer = await source.fetch_details(offer)
        finally:
            await source.aclose()
        self.db.save_offer(offer)
        return offer

    async def list_categories(self, source_name: str) -> list[CategoryInfo]:
        source = self._source_factory(source_name, self.config)
        try:
            return await source.list_categories()
        finally:
            await source.aclose()
