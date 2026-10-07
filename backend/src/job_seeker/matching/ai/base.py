"""Contract for AI scorers - any model provider that can rate one offer against the candidate profile."""

from __future__ import annotations

from typing import Protocol

from job_seeker.domain.models import AIResult, AssessmentContext, CandidateProfile, JobOffer


class AIConfigurationError(RuntimeError):
    """The AI provider cannot be used at all (missing key, unknown provider, bad model). Aborts the run."""


class AIScoringError(RuntimeError):
    """Scoring a single offer failed (refusal, malformed output, transient API error). Skips that offer."""


class AIScorer(Protocol):
    provider: str
    model: str

    async def assess(self, profile: CandidateProfile, offer: JobOffer, context: AssessmentContext) -> AIResult: ...

    async def aclose(self) -> None: ...
