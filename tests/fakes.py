"""Test doubles for job sources and AI scorers (no network)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from job_seeker.domain.models import AIAssessment, AIResult, AssessmentContext, CandidateProfile, JobOffer
from job_seeker.matching.ai.base import AIConfigurationError, AIScoringError
from job_seeker.sources.base import CategoryInfo, SourceQuery


class FakeSource:
    name = "justjoin"

    def __init__(self, offers: list[JobOffer]) -> None:
        self.offers = offers
        self.detail_calls: list[str] = []
        self.closed = False

    async def fetch_offers(self, query: SourceQuery) -> AsyncIterator[JobOffer]:
        for offer in self.offers:
            if not query.categories or offer.category in query.categories:
                yield offer

    async def fetch_details(self, offer: JobOffer) -> JobOffer:
        self.detail_calls.append(offer.id)
        return offer.model_copy(update={"description": f"Opis oferty {offer.title}"})

    async def list_categories(self) -> list[CategoryInfo]:
        return [CategoryInfo(key="javascript", count=len(self.offers))]

    async def aclose(self) -> None:
        self.closed = True


class FakeScorer:
    provider = "fake"

    def __init__(
        self,
        model: str = "fake-model",
        score: int = 90,
        fail_ids: set[str] | None = None,
        config_error: bool = False,
    ) -> None:
        self.model = model
        self.score = score
        self.fail_ids = fail_ids or set()
        self.config_error = config_error
        self.calls: list[str] = []
        self.descriptions: list[str | None] = []
        self.contexts: list[AssessmentContext] = []

    async def assess(self, profile: CandidateProfile, offer: JobOffer, context: AssessmentContext) -> AIResult:
        if self.config_error:
            raise AIConfigurationError("Brak klucza API")
        self.calls.append(offer.id)
        self.descriptions.append(offer.description)
        self.contexts.append(context)
        if offer.id in self.fail_ids:
            raise AIScoringError(f"refusal for {offer.id}")
        assessment = AIAssessment(score=self.score, summary="Pasuje", pros=["Node.js"], cons=[], missing_skills=[])
        return AIResult(
            provider=self.provider, model=self.model, assessment=assessment, input_tokens=100, output_tokens=20
        )

    async def aclose(self) -> None:
        return None
