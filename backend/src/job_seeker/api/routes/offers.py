from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status

from job_seeker.api.deps import ServiceDep
from job_seeker.domain.models import JobOffer, MatchResult, Model

router = APIRouter(tags=["offers"])


class OfferStatusUpdate(Model):
    status: Literal["saved", "hidden"] | None


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
