"""FastAPI application. Run with ``uv run jobseeker serve``; OpenAPI docs at ``/docs``."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from job_seeker.api.routes import matches, offers, profile, sources
from job_seeker.config import AppConfig, load_config
from job_seeker.matching.ai.base import AIConfigurationError
from job_seeker.profile.service import CVNotFoundError
from job_seeker.services.job_seeker import JobSeekerService
from job_seeker.sources.base import SourceError

log = logging.getLogger(__name__)


def create_app(config: AppConfig | None = None, service: JobSeekerService | None = None) -> FastAPI:
    service = service or JobSeekerService(config or load_config())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            state = service.load_profile()
            if state.rebuilt:
                log.warning("Wykryto nowe CV (%s) - profil przebudowany", state.profile.source_file)
        except CVNotFoundError as exc:
            log.warning("%s", exc)
        yield

    app = FastAPI(
        title="Job Seeker API",
        version="0.1.0",
        description="Dopasowuje oferty pracy z serwisów (na razie JustJoin.it) do CV kandydata.",
        lifespan=lifespan,
    )
    app.state.service = service

    @app.exception_handler(CVNotFoundError)
    async def cv_not_found(_: Request, exc: CVNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(AIConfigurationError)
    async def ai_config_error(_: Request, exc: AIConfigurationError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(SourceError)
    async def source_error(_: Request, exc: SourceError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def value_error(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for module in (matches, offers, profile, sources):
        app.include_router(module.router)
    return app
