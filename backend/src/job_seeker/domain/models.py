"""Source-agnostic domain models shared by every layer of the application."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class Model(BaseModel):
    """Base for domain models: fields with defaults are always present in responses, so the OpenAPI
    schema marks them required (the web frontend's generated types then need no undefined checks)."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class Seniority(StrEnum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    MANAGER = "manager"
    C_LEVEL = "c_level"


class WorkplaceType(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    OFFICE = "office"


class Skill(Model):
    name: str
    level: int | None = Field(default=None, description="Required proficiency, 1 (basic) to 5 (expert)")


class Location(Model):
    city: str
    street: str | None = None


class LanguageRequirement(Model):
    code: str = Field(description="ISO 639-1 language code, e.g. 'en'")
    level: str | None = Field(default=None, description="CEFR level, e.g. 'B2'")


class Salary(Model):
    """Salary range normalized to PLN per month."""

    contract: str = Field(description="b2b, permanent, mandate_contract, internship or any")
    min_pln_month: float | None = None
    max_pln_month: float | None = None
    gross: bool | None = None
    original_currency: str | None = None
    original_unit: str | None = None
    original_min: float | None = None
    original_max: float | None = None


class JobOffer(Model):
    source: str
    external_id: str
    url: str
    title: str
    company: str
    category: str | None = None
    seniority: Seniority | None = None
    workplace_type: WorkplaceType | None = None
    working_time: str | None = None
    locations: list[Location] = Field(default_factory=list)
    required_skills: list[Skill] = Field(default_factory=list)
    nice_to_have_skills: list[Skill] = Field(default_factory=list)
    languages: list[LanguageRequirement] = Field(default_factory=list)
    salaries: list[Salary] = Field(default_factory=list)
    published_at: datetime | None = None
    expires_at: datetime | None = None
    apply_url: str | None = None
    description: str | None = Field(default=None, description="Plain-text description, filled by fetch_details")
    extra: dict[str, str] = Field(default_factory=dict, description="Source-specific identifiers, e.g. slug")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def id(self) -> str:
        """Globally unique id: ``source:external_id``."""
        return f"{self.source}:{self.external_id}"

    @property
    def best_salary(self) -> Salary | None:
        """The salary entry with the highest upper bound, if any range is known."""
        known = [s for s in self.salaries if s.max_pln_month or s.min_pln_month]
        if not known:
            return None
        return max(known, key=lambda s: s.max_pln_month or s.min_pln_month or 0)


class CandidateSkill(Model):
    name: str = Field(description="Canonical skill name, see profile.skill_extractor")
    weight: float = Field(default=1.0, ge=0, le=1, description="1.0 = core skill, lower = secondary")


class CandidateProfile(Model):
    parser_version: int = Field(default=0, description="Version of the CV parser that built this profile")
    source_file: str | None = None
    source_hash: str | None = Field(default=None, description="SHA-256 of the CV file the profile was built from")
    built_at: datetime | None = None
    headline: str | None = None
    location: str | None = None
    years_of_experience: float = 0
    seniority: Seniority = Seniority.MID
    skills: list[CandidateSkill] = Field(default_factory=list)
    skill_years: dict[str, float] = Field(
        default_factory=dict, description="Canonical skill -> years used in positions listed in the CV"
    )
    languages: dict[str, str] = Field(default_factory=dict, description="ISO code -> CEFR level")
    cv_text: str = Field(default="", description="CV text with contact data removed; sent to AI scorers")

    def skill_weights(self) -> dict[str, float]:
        return {s.name: s.weight for s in self.skills}


class RuleScore(Model):
    score: float = Field(ge=0, le=100)
    breakdown: dict[str, float] = Field(default_factory=dict, description="Component -> 0..1")
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    effective_years: float | None = Field(
        default=None, description="Candidate's experience in this offer's main technologies"
    )
    effective_level: Seniority | None = None
    main_skills: list[str] = Field(default_factory=list, description="Offer skills used for effective_years")


class AssessmentContext(Model):
    """Per-offer facts computed by the rules that AI scorers receive alongside the offer."""

    effective_years: float | None = None
    effective_level: Seniority | None = None
    main_skills: list[str] = Field(default_factory=list)
    target_skills: list[str] = Field(default_factory=list)


class AIAssessment(Model):
    """Structured answer every AI scorer must return."""

    score: int = Field(ge=0, le=100, description="Overall fit of the candidate for the offer")
    summary: str = Field(description="Two or three sentences in Polish explaining the score")
    pros: list[str] = Field(description="Reasons the candidate fits, in Polish")
    cons: list[str] = Field(description="Gaps or risks, in Polish")
    missing_skills: list[str] = Field(description="Skills the offer needs that the candidate lacks")


class AIResult(Model):
    provider: str
    model: str
    assessment: AIAssessment
    input_tokens: int = 0
    output_tokens: int = 0
    cached: bool = False


class MatchResult(Model):
    offer: JobOffer
    rule: RuleScore
    ai: AIResult | None = None
    final_score: float
    status: Literal["saved", "hidden"] | None = Field(default=None, description="The user's mark on the offer")
