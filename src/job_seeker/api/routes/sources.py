from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from job_seeker.api.deps import ServiceDep
from job_seeker.config import SearchPreferences
from job_seeker.sources.base import CategoryInfo
from job_seeker.sources.registry import available_sources

router = APIRouter(tags=["sources"])


class SourceStatus(BaseModel):
    name: str
    offers_in_db: int
    last_sync_started: datetime | None = None
    last_sync_finished: datetime | None = None
    last_sync_fetched: int | None = None
    last_sync_error: str | None = None


class SyncRequest(BaseModel):
    sources: list[str] | None = Field(default=None, description="Default: search.sources from config")
    categories: list[str] | None = Field(default=None, description="Default: search.categories from config")
    search: str | None = Field(default=None, description="Take sources/categories from a named search preset")
    limit: int | None = Field(default=None, ge=1)


class SyncResponseItem(BaseModel):
    source: str
    fetched: int
    new: int
    error: str | None


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
                last_sync_error=run.error if run else None,
            )
        )
    return statuses


@router.get("/sources/{source}/categories", response_model=list[CategoryInfo])
async def list_categories(source: str, service: ServiceDep) -> list[CategoryInfo]:
    if source not in available_sources():
        raise HTTPException(status_code=404, detail=f"Unknown source '{source}'")
    return await service.list_categories(source)


@router.post("/sync", response_model=list[SyncResponseItem])
async def sync(request: SyncRequest, service: ServiceDep) -> list[SyncResponseItem]:
    """Download fresh offers into the local database (may take a minute for many categories)."""
    unknown = set(request.sources or []) - set(available_sources())
    if unknown:
        raise HTTPException(status_code=404, detail=f"Unknown sources: {', '.join(sorted(unknown))}")
    results = await service.sync(request.sources, request.categories, request.limit, search=request.search)
    return [SyncResponseItem(source=r.source, fetched=r.fetched, new=r.new, error=r.error) for r in results]


@router.get("/preferences", response_model=SearchPreferences, tags=["meta"])
def preferences(service: ServiceDep, search: str | None = None) -> SearchPreferences:
    """Effective search preferences: config.toml [search], optionally with a named preset applied."""
    return service.preferences(search)


@router.get("/searches", response_model=dict[str, SearchPreferences], tags=["meta"])
def searches(service: ServiceDep) -> dict[str, SearchPreferences]:
    """Named search presets ([searches.<name>] in config.toml) with their effective preferences."""
    return {name: service.preferences(name) for name in sorted(service.config.searches)}
