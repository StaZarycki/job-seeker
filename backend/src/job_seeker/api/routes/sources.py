from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import Field

from job_seeker.api.deps import ServiceDep
from job_seeker.config import MatchingMode, RuleWeights, SearchPreferences
from job_seeker.domain.models import Model
from job_seeker.services.job_seeker import SyncJobState
from job_seeker.sources.base import CategoryInfo
from job_seeker.sources.registry import available_sources
from job_seeker.storage.db import SyncRun

router = APIRouter(tags=["sources"])


class SourceStatus(Model):
    name: str
    offers_in_db: int
    last_sync_started: datetime | None = None
    last_sync_finished: datetime | None = None
    last_sync_fetched: int | None = None
    last_sync_new: int | None = None
    last_sync_error: str | None = None


class SyncRequest(Model):
    sources: list[str] | None = Field(default=None, description="Default: search.sources from config")
    categories: list[str] | None = Field(default=None, description="Default: search.categories from config")
    search: str | None = Field(default=None, description="Take sources/categories from a named search preset")
    limit: int | None = Field(default=None, ge=1)


class SyncResultItem(Model):
    source: str
    fetched: int
    new: int
    error: str | None


class SyncStatus(Model):
    running: bool
    started_at: datetime | None
    finished_at: datetime | None
    source: str | None
    category: str | None
    category_index: int
    category_count: int
    fetched: int
    total: int | None
    cancelled: bool
    error: str | None
    results: list[SyncResultItem]


class SyncHistoryItem(Model):
    id: int
    source: str
    started_at: datetime
    finished_at: datetime | None
    categories: list[str] | None = Field(description="Empty: all categories; null: not recorded (older runs)")
    fetched: int
    new: int
    error: str | None


class SearchSummaryItem(Model):
    name: str | None = Field(description="Preset name; null for the default [search] section")
    preferences: SearchPreferences
    considered: int = Field(description="Offers in the database for this search")
    passed: int = Field(description="Offers that pass the hard filters (after merging duplicates)")
    needs_sync: bool = Field(description="No offers of this search's categories have been downloaded yet")


class ExperienceSettings(Model):
    transfer_ratio: float
    declared_ratio: float


class AISettings(Model):
    provider: str
    model: str
    top_n: int
    weight: float


class Settings(Model):
    """Read-only configuration the UI uses for labels and explanations."""

    default_mode: MatchingMode
    weights: RuleWeights
    experience: ExperienceSettings
    ai: AISettings


@router.get("/sources", response_model=list[SourceStatus])
def list_sources(service: ServiceDep) -> list[SourceStatus]:
    counts = service.db.count_offers()
    syncs = {run.source: run for run in service.db.last_syncs()}
    statuses = []
    for name in available_sources():
        run = syncs.get(name)
        statuses.append(
            SourceStatus(
                name=name,
                offers_in_db=counts.get(name, 0),
                last_sync_started=run.started_at if run else None,
                last_sync_finished=run.finished_at if run else None,
                last_sync_fetched=run.fetched if run else None,
                last_sync_new=run.new_offers if run else None,
                last_sync_error=run.error if run else None,
            )
        )
    return statuses


@router.get("/sources/{source}/categories", response_model=list[CategoryInfo])
async def list_categories(source: str, service: ServiceDep) -> list[CategoryInfo]:
    if source not in available_sources():
        raise HTTPException(status_code=404, detail=f"Unknown source '{source}'")
    return await service.list_categories(source)


@router.post("/sync", response_model=SyncStatus, status_code=status.HTTP_202_ACCEPTED)
async def start_sync(request: SyncRequest, service: ServiceDep) -> SyncStatus:
    """Start downloading offers in the background; poll GET /sync/status for progress."""
    unknown = set(request.sources or []) - set(available_sources())
    if unknown:
        raise HTTPException(status_code=404, detail=f"Unknown sources: {', '.join(sorted(unknown))}")
    state = service.start_sync_job(request.sources, request.categories, request.limit, request.search)
    return _sync_status(state)


@router.get("/sync/status", response_model=SyncStatus)
def sync_status(service: ServiceDep) -> SyncStatus:
    return _sync_status(service.sync_status())


@router.delete("/sync", status_code=status.HTTP_204_NO_CONTENT)
def cancel_sync(service: ServiceDep) -> Response:
    """Stop the running sync; offers downloaded so far are kept."""
    if not service.cancel_sync():
        raise HTTPException(status_code=409, detail="Żadna synchronizacja nie trwa.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/syncs", response_model=list[SyncHistoryItem])
def sync_history(service: ServiceDep, limit: int = Query(default=10, ge=1, le=100)) -> list[SyncHistoryItem]:
    return [_history_item(run) for run in service.db.sync_history(limit)]


@router.get("/searches", response_model=list[SearchSummaryItem], tags=["meta"])
def searches(service: ServiceDep) -> list[SearchSummaryItem]:
    """The default search and every [searches.<name>] preset from config.toml, with offer counts."""
    return [
        SearchSummaryItem(
            name=s.name, preferences=s.preferences, considered=s.considered, passed=s.passed, needs_sync=s.needs_sync
        )
        for s in service.search_summaries()
    ]


@router.get("/preferences", response_model=SearchPreferences, tags=["meta"])
def preferences(service: ServiceDep, search: str | None = None) -> SearchPreferences:
    """Effective search preferences: config.toml [search], optionally with a named preset applied."""
    return service.preferences(search)


@router.get("/settings", response_model=Settings, tags=["meta"])
def settings(service: ServiceDep) -> Settings:
    config = service.config
    return Settings(
        default_mode=config.matching.mode,
        weights=config.matching.weights,
        experience=ExperienceSettings(**config.matching.experience.model_dump()),
        ai=AISettings(
            provider=config.ai.provider, model=config.ai.model, top_n=config.ai.top_n, weight=config.ai.weight
        ),
    )


def _sync_status(state: SyncJobState) -> SyncStatus:
    return SyncStatus(
        running=state.running,
        started_at=state.started_at,
        finished_at=state.finished_at,
        source=state.source,
        category=state.category,
        category_index=state.category_index,
        category_count=state.category_count,
        fetched=state.fetched,
        total=state.total,
        cancelled=state.cancelled,
        error=state.error,
        results=[SyncResultItem(source=r.source, fetched=r.fetched, new=r.new, error=r.error) for r in state.results],
    )


def _history_item(run: SyncRun) -> SyncHistoryItem:
    return SyncHistoryItem(
        id=run.id,
        source=run.source,
        started_at=run.started_at,
        finished_at=run.finished_at,
        categories=run.categories,
        fetched=run.fetched,
        new=run.new_offers,
        error=run.error,
    )
