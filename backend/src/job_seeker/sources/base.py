"""Contract every job board integration implements."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from job_seeker.domain.models import JobOffer, Seniority


class SourceQuery(BaseModel):
    """Server-side filters a source should apply when it can; the rest is filtered locally."""

    categories: list[str] = Field(default_factory=list, description="Empty means all categories")
    experience_levels: list[Seniority] = Field(default_factory=list)
    keywords: str | None = None
    limit: int | None = Field(default=None, description="Stop after this many offers (useful for testing)")


class CategoryInfo(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    key: str
    count: int | None = None


@dataclass(frozen=True)
class FetchProgress:
    """Reported by a source while it downloads; ``total`` is the category's offer count if known."""

    category: str | None
    category_index: int
    category_count: int
    fetched: int
    total: int | None


ProgressCallback = Callable[[FetchProgress], None]


class SourceError(RuntimeError):
    """Raised when a job board cannot be reached or returns unexpected data."""


@runtime_checkable
class JobSource(Protocol):
    name: str

    def fetch_offers(self, query: SourceQuery, on_progress: ProgressCallback | None = None) -> AsyncIterator[JobOffer]:
        """Yield offers matching ``query``; each offer is yielded once even if listed in many places."""
        ...

    async def fetch_details(self, offer: JobOffer) -> JobOffer:
        """Return ``offer`` enriched with fields only available on the detail page (e.g. description)."""
        ...

    async def list_categories(self) -> list[CategoryInfo]: ...

    async def aclose(self) -> None: ...
