from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from job_seeker.services.job_seeker import JobSeekerService


def get_service(request: Request) -> JobSeekerService:
    service: JobSeekerService = request.app.state.service
    return service


ServiceDep = Annotated[JobSeekerService, Depends(get_service)]
