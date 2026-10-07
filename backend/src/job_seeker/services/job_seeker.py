"""Application service shared by the CLI and the REST API."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from job_seeker.config import AIConfig, AppConfig, MatchingMode, SearchPreferences
from job_seeker.domain.models import JobOffer, MatchResult
from job_seeker.matching.ai.base import AIScorer
from job_seeker.matching.ai.registry import create_scorer
from job_seeker.matching.experience import offer_experience
from job_seeker.matching.pipeline import (
    AIPlanCallback,
    MatchReport,
    OfferEnricher,
    assess_one,
    rank_by_rules,
    run_matching,
)
from job_seeker.matching.rules import score_offer
from job_seeker.profile.service import ProfileService, ProfileState
from job_seeker.sources.base import CategoryInfo, FetchProgress, JobSource, SourceError, SourceQuery
from job_seeker.sources.registry import create_source
from job_seeker.storage.db import Database, OfferActivity, OfferStatus, UpsertStats

log = logging.getLogger(__name__)

SourceFactory = Callable[[str, AppConfig], JobSource]
ScorerFactory = Callable[[AIConfig], AIScorer]
SyncProgressCallback = Callable[[str, FetchProgress], None]


class MatchRequest(BaseModel):
    """Per-request overrides of the configured defaults."""

    mode: MatchingMode | None = None
    top: int = Field(default=20, ge=1, le=500)
    provider: str | None = None
    model: str | None = None
    min_score: float | None = Field(default=None, ge=0, le=100)
    search: str | None = Field(default=None, description="Named search preset from [searches.<name>]")
    status: Literal["saved", "hidden"] | None = Field(
        default=None, description="Only offers with this mark; by default hidden offers are left out"
    )
    activity: Literal["unvisited", "applied"] | None = Field(
        default=None, description="Only offers never opened on the job board / only offers marked as applied"
    )
    preferences: dict[str, Any] = Field(default_factory=dict, description="Overrides of SearchPreferences fields")


@dataclass(frozen=True)
class SyncResult:
    source: str
    fetched: int
    new: int
    error: str | None = None


@dataclass(frozen=True)
class SyncJobState:
    """Snapshot of the background sync started from the API."""

    running: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None
    source: str | None = None
    category: str | None = None
    category_index: int = 0
    category_count: int = 0
    fetched: int = 0
    total: int | None = None
    cancelled: bool = False
    error: str | None = None
    results: list[SyncResult] = field(default_factory=list)


@dataclass(frozen=True)
class SearchSummary:
    name: str | None  # None = the default [search] section
    preferences: SearchPreferences
    considered: int
    passed: int
    needs_sync: bool


@dataclass
class MatchOutcome:
    report: MatchReport
    profile: ProfileState
    preferences: SearchPreferences


class SyncInProgressError(RuntimeError):
    pass


class OfferNotFoundError(LookupError):
    pass


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
        self._sync_state = SyncJobState()
        self._sync_task: asyncio.Task[list[SyncResult]] | None = None

    def load_profile(self, force_rebuild: bool = False) -> ProfileState:
        return self.profiles.load(force_rebuild=force_rebuild)

    def preferences(self, search: str | None = None, overrides: dict[str, Any] | None = None) -> SearchPreferences:
        """[search] from config <- named preset ``search`` <- per-request ``overrides``."""
        return self.config.preferences(search, overrides)

    # --- synchronization --------------------------------------------------------------------------------

    async def sync(
        self,
        sources: list[str] | None = None,
        categories: list[str] | None = None,
        limit: int | None = None,
        on_source_done: Callable[[SyncResult], None] | None = None,
        search: str | None = None,
        on_progress: SyncProgressCallback | None = None,
    ) -> list[SyncResult]:
        """Download offers into the local database. Offers are stored unfiltered (beyond category), so
        changing preferences later doesn't require another sync. ``search`` takes sources/categories from
        a named preset. Cancelling keeps everything downloaded so far."""
        prefs = self.preferences(search)
        query = SourceQuery(categories=categories if categories is not None else prefs.categories, limit=limit)
        results = []
        for name in sources or prefs.sources:
            run_id = self.db.start_sync(name, query.categories)
            offers: list[JobOffer] = []
            error = None
            cancelled = False
            source = self._source_factory(name, self.config)
            progress = (lambda p, n=name: on_progress(n, p)) if on_progress else None
            try:
                async for offer in source.fetch_offers(query, on_progress=progress):
                    offers.append(offer)
            except SourceError as exc:
                error = str(exc)
                log.warning("Sync of %s failed: %s", name, exc)
            except asyncio.CancelledError:
                cancelled = True
                error = "Synchronizacja przerwana"
            finally:
                await source.aclose()
            stats = self.db.upsert_offers(offers) if offers else UpsertStats()
            self.db.finish_sync(run_id, stats, error)
            result = SyncResult(source=name, fetched=stats.fetched, new=stats.new, error=error)
            results.append(result)
            if on_source_done:
                on_source_done(result)
            if cancelled:
                raise asyncio.CancelledError
        return results

    def start_sync_job(
        self,
        sources: list[str] | None = None,
        categories: list[str] | None = None,
        limit: int | None = None,
        search: str | None = None,
    ) -> SyncJobState:
        """Start a sync in the background (API). Poll ``sync_status``; ``cancel_sync`` stops it."""
        if self._sync_task is not None and not self._sync_task.done():
            raise SyncInProgressError("Synchronizacja już trwa.")
        self.preferences(search)  # fail fast on an unknown preset
        self._sync_state = SyncJobState(running=True, started_at=datetime.now(UTC))

        def progress(source: str, p: FetchProgress) -> None:
            self._sync_state = replace(
                self._sync_state,
                source=source,
                category=p.category,
                category_index=p.category_index,
                category_count=p.category_count,
                fetched=p.fetched,
                total=p.total,
            )

        def source_done(result: SyncResult) -> None:
            self._sync_state = replace(self._sync_state, results=[*self._sync_state.results, result])

        async def run() -> list[SyncResult]:
            try:
                results = await self.sync(sources, categories, limit, source_done, search, progress)
            except asyncio.CancelledError:
                self._sync_state = replace(
                    self._sync_state, running=False, cancelled=True, finished_at=datetime.now(UTC)
                )
                raise
            except Exception as exc:
                log.exception("Background sync failed")
                self._sync_state = replace(
                    self._sync_state, running=False, error=str(exc), finished_at=datetime.now(UTC)
                )
                raise
            errors = [r.error for r in results if r.error]
            self._sync_state = replace(
                self._sync_state,
                running=False,
                finished_at=datetime.now(UTC),
                error="; ".join(errors) or None,
            )
            return results

        self._sync_task = asyncio.create_task(run())
        return self._sync_state

    def sync_status(self) -> SyncJobState:
        return self._sync_state

    def cancel_sync(self) -> bool:
        if self._sync_task is None or self._sync_task.done():
            return False
        self._sync_task.cancel()
        return True

    async def wait_for_sync(self) -> None:
        """Wait until the background sync (if any) finishes; used by tests and shutdown."""
        if self._sync_task is not None:
            await asyncio.gather(self._sync_task, return_exceptions=True)

    # --- matching ---------------------------------------------------------------------------------------

    async def match(self, request: MatchRequest, on_ai_plan: AIPlanCallback | None = None) -> MatchOutcome:
        profile_state = self.load_profile()
        prefs = self.preferences(request.search, request.preferences)
        mode = request.mode or self.config.matching.mode
        statuses = self.db.offer_statuses()
        activity = self.db.offer_activity()
        offers = [
            o
            for o in self.db.list_offers(
                sources=prefs.sources, categories=prefs.categories, max_age_days=prefs.max_offer_age_days
            )
            if (statuses.get(o.id) == request.status if request.status else statuses.get(o.id) != "hidden")
            and _activity_matches(activity.get(o.id), request.activity)
        ]

        ai_config = self._ai_config(request.provider, request.model)
        scorer = self._scorer_factory(ai_config) if mode is MatchingMode.AI else None
        enrich, close_sources = self._enricher()
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
            await close_sources()
            if scorer is not None:
                await scorer.aclose()
        if request.min_score is not None:
            report.results = [r for r in report.results if r.final_score >= request.min_score]
        self._attach_marks(report.results, statuses, activity)
        return MatchOutcome(report=report, profile=profile_state, preferences=prefs)

    async def assess_offer(
        self, offer_id: str, search: str | None = None, provider: str | None = None, model: str | None = None
    ) -> MatchResult:
        """Rule-score one offer and ask the AI model about it (cached like the batch assessments)."""
        offer = self.db.get_offer(offer_id)
        if offer is None:
            raise OfferNotFoundError(offer_id)
        profile_state = self.load_profile()
        prefs = self.preferences(search)
        experience = offer_experience(
            offer, profile_state.profile, self.config.matching.experience, prefs.target_skills
        )
        rule = score_offer(offer, profile_state.profile, prefs, self.config.matching.weights, experience=experience)
        result = MatchResult(offer=offer, rule=rule, final_score=rule.score)
        self._attach_marks([result], self.db.offer_statuses(), self.db.offer_activity())
        ai_config = self._ai_config(provider, model)
        scorer = self._scorer_factory(ai_config)
        enrich, close_sources = self._enricher()
        try:
            return await assess_one(
                result,
                profile_state.profile,
                profile_state.profile_hash,
                prefs=prefs,
                experience_config=self.config.matching.experience,
                ai_config=ai_config,
                scorer=scorer,
                db=self.db,
                enrich=enrich,
            )
        finally:
            await close_sources()
            await scorer.aclose()

    def set_offer_status(self, offer_id: str, status: OfferStatus | None) -> None:
        if self.db.get_offer(offer_id) is None:
            raise OfferNotFoundError(offer_id)
        self.db.set_offer_status(offer_id, status)

    def set_offer_activity(
        self, offer_id: str, visited: bool | None = None, applied: bool | None = None
    ) -> OfferActivity:
        """Record a visit on the job board and/or an application; returns the offer's marks afterwards."""
        if self.db.get_offer(offer_id) is None:
            raise OfferNotFoundError(offer_id)
        self.db.set_offer_activity(offer_id, visited=visited, applied=applied)
        return self.db.offer_activity().get(offer_id, OfferActivity())

    @staticmethod
    def _attach_marks(
        results: list[MatchResult], statuses: dict[str, OfferStatus], activity: dict[str, OfferActivity]
    ) -> None:
        for result in results:
            marks = activity.get(result.offer.id, OfferActivity())
            result.status = statuses.get(result.offer.id)
            result.visited_at = marks.visited_at
            result.applied_at = marks.applied_at

    def search_summaries(self) -> list[SearchSummary]:
        """The default search plus every [searches.<name>] preset, with how many offers pass its filters."""
        profile = self.load_profile().profile
        summaries = []
        for name in [None, *sorted(self.config.searches)]:
            prefs = self.preferences(name)
            offers = self.db.list_offers(
                sources=prefs.sources, categories=prefs.categories, max_age_days=prefs.max_offer_age_days
            )
            ranked, _ = rank_by_rules(
                offers, profile, prefs, self.config.matching.weights, experience_config=self.config.matching.experience
            )
            needs_sync = bool(prefs.categories) and not self.db.list_offers(
                sources=prefs.sources, categories=prefs.categories, include_expired=True
            )
            summaries.append(SearchSummary(name, prefs, len(offers), len(ranked), needs_sync))
        return summaries

    # --- offers and sources -----------------------------------------------------------------------------

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

    # --- helpers ----------------------------------------------------------------------------------------

    def _ai_config(self, provider: str | None, model: str | None) -> AIConfig:
        return self.config.ai.model_copy(update={k: v for k, v in {"provider": provider, "model": model}.items() if v})

    def _enricher(self) -> tuple[OfferEnricher, Callable[[], Awaitable[None]]]:
        """An ``enrich`` callback that fetches offer descriptions (and saves them), plus its cleanup."""
        sources: dict[str, JobSource] = {}

        async def enrich(offer: JobOffer) -> JobOffer:
            if offer.source not in sources:
                sources[offer.source] = self._source_factory(offer.source, self.config)
            detailed = await sources[offer.source].fetch_details(offer)
            self.db.save_offer(detailed)
            return detailed

        async def close() -> None:
            for source in sources.values():
                await source.aclose()

        return enrich, close


def _activity_matches(marks: OfferActivity | None, wanted: Literal["unvisited", "applied"] | None) -> bool:
    if wanted == "unvisited":
        return marks is None or (marks.visited_at is None and marks.applied_at is None)
    if wanted == "applied":
        return marks is not None and marks.applied_at is not None
    return True
