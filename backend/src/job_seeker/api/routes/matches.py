from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import Field

from job_seeker.api.deps import ServiceDep
from job_seeker.config import MatchingMode, SearchPreferences
from job_seeker.domain.models import MatchResult, Model
from job_seeker.services.job_seeker import MatchRequest

router = APIRouter(tags=["matches"])


class AIUsage(Model):
    provider: str | None
    model: str | None
    calls: int
    cached: int
    failed: int
    input_tokens: int
    output_tokens: int
    errors: list[str]


class MatchResponse(Model):
    mode: MatchingMode
    considered: int
    filtered_out: int
    passed: int
    total: int = Field(description="Ranked offers available for paging (passed, minus those below min_score)")
    offset: int = Field(description="Position of results[0] in the whole ranking")
    profile_hash: str
    profile_rebuilt: bool
    warning: str | None
    preferences: SearchPreferences
    ai: AIUsage | None
    results: list[MatchResult]


@router.get("/matches", response_model=MatchResponse)
async def get_matches(
    service: ServiceDep,
    mode: MatchingMode | None = None,
    top: Annotated[int, Query(ge=1, le=500, description="Page size")] = 20,
    offset: Annotated[int, Query(ge=0, description="Skip this many ranked offers (page * top)")] = 0,
    provider: str | None = None,
    model: str | None = None,
    min_score: Annotated[float | None, Query(ge=0, le=100)] = None,
    search: Annotated[str | None, Query(description="Named search preset, see GET /searches")] = None,
    status: Annotated[
        Literal["saved", "hidden"] | None,
        Query(description="Only saved / only hidden offers (default: all but hidden)"),
    ] = None,
    activity: Annotated[
        Literal["unvisited", "applied"] | None,
        Query(description="Only offers never opened on the job board / only offers marked as applied"),
    ] = None,
    category: Annotated[list[str] | None, Query(description="Override search.categories")] = None,
    city: Annotated[list[str] | None, Query(description="Override search.preferred_cities")] = None,
    min_salary: Annotated[float | None, Query(description="Override search.min_salary_pln_month")] = None,
) -> MatchResponse:
    """Offers ranked by fit. ``mode=basic`` uses rules only; ``mode=ai`` also asks the configured model."""
    preferences = {"categories": category, "preferred_cities": city, "min_salary_pln_month": min_salary}
    request = MatchRequest(
        mode=mode,
        top=top,
        offset=offset,
        provider=provider,
        model=model,
        min_score=min_score,
        search=search,
        status=status,
        activity=activity,
        preferences={k: v for k, v in preferences.items() if v is not None},
    )
    outcome = await service.match(request)
    report = outcome.report
    ai = None
    if report.mode is MatchingMode.AI:
        ai = AIUsage(
            provider=report.ai_provider,
            model=report.ai_model,
            calls=report.ai_calls,
            cached=report.ai_cached,
            failed=report.ai_failed,
            input_tokens=report.input_tokens,
            output_tokens=report.output_tokens,
            errors=report.errors,
        )
    return MatchResponse(
        mode=report.mode,
        considered=report.considered,
        filtered_out=report.filtered_out,
        passed=report.passed,
        total=report.total,
        offset=report.offset,
        profile_hash=outcome.profile.profile_hash,
        profile_rebuilt=outcome.profile.rebuilt,
        warning=outcome.profile.warning,
        preferences=outcome.preferences,
        ai=ai,
        results=report.results,
    )
