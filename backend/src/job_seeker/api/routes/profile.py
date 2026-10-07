from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile

from job_seeker.api.deps import ServiceDep
from job_seeker.domain.models import CandidateProfile, Model
from job_seeker.profile.service import ProfileOverrides, ProfileState

router = APIRouter(prefix="/profile", tags=["profile"])

MAX_CV_BYTES = 10 * 1024 * 1024


class ProfileResponse(Model):
    profile: CandidateProfile
    profile_hash: str
    rebuilt: bool
    warning: str | None


def _response(state: ProfileState) -> ProfileResponse:
    return ProfileResponse(
        profile=state.profile, profile_hash=state.profile_hash, rebuilt=state.rebuilt, warning=state.warning
    )


@router.get("", response_model=ProfileResponse)
def get_profile(service: ServiceDep) -> ProfileResponse:
    """Current profile; rebuilt automatically when the CV file changed."""
    return _response(service.load_profile())


@router.post("/rebuild", response_model=ProfileResponse)
def rebuild_profile(service: ServiceDep) -> ProfileResponse:
    return _response(service.load_profile(force_rebuild=True))


@router.post("/cv", response_model=ProfileResponse)
async def upload_cv(file: UploadFile, service: ServiceDep) -> ProfileResponse:
    """Upload a new CV (PDF). It becomes the newest file in the CV folder and the profile is rebuilt."""
    content = await file.read(MAX_CV_BYTES + 1)
    if len(content) > MAX_CV_BYTES:
        raise HTTPException(status_code=413, detail="CV is larger than 10 MB")
    try:
        state = service.profiles.save_uploaded_cv(file.filename or "cv.pdf", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _response(state)


@router.get("/overrides", response_model=ProfileOverrides)
def get_overrides(service: ServiceDep) -> ProfileOverrides:
    try:
        return service.profiles.read_overrides()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/overrides", response_model=ProfileResponse)
def put_overrides(overrides: ProfileOverrides, service: ServiceDep) -> ProfileResponse:
    """Replace manual profile corrections (kept across CV changes) and return the resulting profile."""
    service.profiles.write_overrides(overrides)
    return _response(service.load_profile())
