from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from job_seeker.api.deps import ServiceDep
from job_seeker.config import MatchingMode, SearchPreferences
from job_seeker.domain.models import MatchResult
from job_seeker.services.job_seeker import MatchRequest

router = APIRouter(tags=["matches"])


class AIUsage(BaseModel):
    provider: str | None
    model: str | None
    calls: int
    cached: int
    failed: int
    input_tokens: int
    output_tokens: int
    errors: list[str]


class MatchResponse(BaseModel):
    mode: MatchingMode
    considered: int
    filtered_out: int
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
    top: Annotated[int, Query(ge=1, le=500)] = 20,
    provider: str | None = None,
    model: str | None = None,
    min_score: Annotated[float | None, Query(ge=0, le=100)] = None,
    search: Annotated[str | None, Query(description="Named search preset, see GET /searches")] = None,
    category: Annotated[list[str] | None, Query(description="Override search.categories")] = None,
    city: Annotated[list[str] | None, Query(description="Override search.preferred_cities")] = None,
    min_salary: Annotated[float | None, Query(description="Override search.min_salary_pln_month")] = None,
) -> MatchResponse:
    """Offers ranked by fit. ``mode=basic`` uses rules only; ``mode=ai`` also asks the configured model."""
    preferences = {"categories": category, "preferred_cities": city, "min_salary_pln_month": min_salary}
    request = MatchRequest(mode=mode, top=top, provider=provider, model=model, min_score=min_score, search=search,
                           preferences={k: v for k, v in preferences.items() if v is not None})  # fmt: skip
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
        profile_hash=outcome.profile.profile_hash,
        profile_rebuilt=outcome.profile.rebuilt,
        warning=outcome.profile.warning,
        preferences=outcome.preferences,
        ai=ai,
        results=report.results,
    )
