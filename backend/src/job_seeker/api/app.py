"""FastAPI application. Run with ``uv run jobseeker serve``; OpenAPI docs at ``/docs``.

Errors are returned as ``{"detail": "<message in Polish>", "code": "<machine-readable code>"}`` so the web
frontend can show the right state (e.g. ``cv_not_found`` -> "upload your CV").
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from job_seeker.api.routes import matches, offers, profile, sources
from job_seeker.config import AppConfig, load_config
from job_seeker.matching.ai.base import AIConfigurationError, AIScoringError
from job_seeker.profile.service import CVNotFoundError
from job_seeker.services.job_seeker import JobSeekerService, OfferNotFoundError, SyncInProgressError
from job_seeker.sources.base import SourceError

log = logging.getLogger(__name__)

ERRORS: list[tuple[type[Exception], int, str]] = [
    (CVNotFoundError, 404, "cv_not_found"),
    (OfferNotFoundError, 404, "offer_not_found"),
    (AIConfigurationError, 400, "ai_not_configured"),
    (AIScoringError, 502, "ai_failed"),
    (SourceError, 502, "source_unavailable"),
    (SyncInProgressError, 409, "sync_in_progress"),
    (ValueError, 400, "invalid_request"),
]


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
        service.cancel_sync()
        await service.wait_for_sync()

    app = FastAPI(
        title="Job Seeker API",
        version="0.2.0",
        description="Dopasowuje oferty pracy z serwisów (na razie JustJoin.it) do CV kandydata.",
        lifespan=lifespan,
    )
    app.state.service = service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=service.config.api.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for exc_type, status_code, code in ERRORS:
        app.add_exception_handler(exc_type, _error_handler(status_code, code))

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for module in (matches, offers, profile, sources):
        app.include_router(module.router)
    return app


def _error_handler(status_code: int, code: str) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handler(_: Request, exc: Exception) -> JSONResponse:
        detail = str(exc) if code != "offer_not_found" else f"Nie ma oferty {exc} w bazie."
        return JSONResponse(status_code=status_code, content={"detail": detail, "code": code})

    return handler
