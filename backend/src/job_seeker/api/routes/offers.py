from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import Field

from job_seeker.api.deps import ServiceDep
from job_seeker.domain.models import JobOffer, MatchResult, Model

router = APIRouter(tags=["offers"])


class OfferStatusUpdate(Model):
    status: Literal["saved", "hidden"] | None


class OfferActivityUpdate(Model):
    visited: bool | None = Field(
        default=None, description="true stamps a visit now; false forgets visit and application"
    )
    applied: bool | None = Field(default=None, description="Mark (true) or unmark (false) the offer as applied")


class OfferActivity(Model):
    visited_at: datetime | None
    applied_at: datetime | None


@router.get("/offers/{offer_id}", response_model=JobOffer)
async def get_offer(offer_id: str, service: ServiceDep) -> JobOffer:
    """Offer from the local database (``source:external_id``), with its description fetched on demand."""
    offer = await service.offer_with_details(offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail=f"Offer {offer_id} not found")
    return offer


@router.put("/offers/{offer_id}/status", status_code=status.HTTP_204_NO_CONTENT)
def set_offer_status(offer_id: str, update: OfferStatusUpdate, service: ServiceDep) -> Response:
    """Mark an offer as saved or hidden (hidden offers are left out of /matches); null clears the mark."""
    service.set_offer_status(offer_id, update.status)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/offers/{offer_id}/activity", response_model=OfferActivity)
def set_offer_activity(offer_id: str, update: OfferActivityUpdate, service: ServiceDep) -> OfferActivity:
    """Record that the user opened the offer on the job board and/or applied to it; omitted fields stay as they are."""
    marks = service.set_offer_activity(offer_id, visited=update.visited, applied=update.applied)
    return OfferActivity(visited_at=marks.visited_at, applied_at=marks.applied_at)


@router.post("/offers/{offer_id}/assess", response_model=MatchResult)
async def assess_offer(
    offer_id: str,
    service: ServiceDep,
    search: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> MatchResult:
    """AI-assess one offer, e.g. one outside the top N rated in /matches?mode=ai."""
    return await service.assess_offer(offer_id, search, provider, model)
