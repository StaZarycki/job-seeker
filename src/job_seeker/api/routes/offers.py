from __future__ import annotations

from fastapi import APIRouter, HTTPException

from job_seeker.api.deps import ServiceDep
from job_seeker.domain.models import JobOffer

router = APIRouter(tags=["offers"])


@router.get("/offers/{offer_id}", response_model=JobOffer)
async def get_offer(offer_id: str, service: ServiceDep) -> JobOffer:
    """Offer from the local database (``source:external_id``), with its description fetched on demand."""
    offer = await service.offer_with_details(offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail=f"Offer {offer_id} not found")
    return offer
