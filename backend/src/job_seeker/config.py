"""Application configuration loaded from ``config.toml`` (all keys optional)."""

from __future__ import annotations

import os
import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from job_seeker.domain.models import Seniority, WorkplaceType

CONFIG_ENV_VAR = "JOBSEEKER_CONFIG"
DEFAULT_CONFIG_NAME = "config.toml"


class MatchingMode(StrEnum):
    BASIC = "basic"
    AI = "ai"


class PathsConfig(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    cv_dir: Path = Path("cv")
    cv_path: Path | None = Field(
        default=None, description="Explicit CV file; overrides picking the newest PDF in cv_dir"
    )
    data_dir: Path = Path("data")
    overrides: Path = Path("profile.overrides.toml")

    @property
    def database(self) -> Path:
        return self.data_dir / "jobseeker.db"

    @property
    def profile(self) -> Path:
        return self.data_dir / "profile.json"


class SearchPreferences(BaseModel):
    """What the user is looking for. Every field can be overridden per request (CLI flags / API params)."""

    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)  # forbid: catch typos

    sources: list[str] = Field(default_factory=lambda: ["justjoin"])
    categories: list[str] = Field(default_factory=lambda: ["javascript", "python", "architecture", "devops"])
    experience_levels: list[Seniority] | Literal["auto"] = Field(
        default="auto",
        description="'auto' = your level in the offer's technologies plus one level up; or an explicit list",
    )
    workplace: list[WorkplaceType] = Field(default_factory=lambda: [WorkplaceType.REMOTE, WorkplaceType.HYBRID])
    preferred_cities: list[str] = Field(default_factory=lambda: ["Katowice", "Kraków", "Gliwice"])
    onsite_only_in_preferred_cities: bool = Field(
        default=True, description="Drop hybrid/office offers that are not located in one of preferred_cities"
    )
    min_salary_pln_month: float | None = Field(default=None, ge=0)
    exclude_keywords: list[str] = Field(default_factory=list, description="Whole words matched in title and skills")
    title_keywords: list[str] = Field(
        default_factory=lambda: ["backend", "back-end", "full stack", "fullstack", "full-stack"],
        description="Words that make a job title attractive (core skills from the CV count automatically)",
    )
    avoid_title_keywords: list[str] = Field(
        default_factory=list, description="Words that make a job title unattractive (soft penalty, not a filter)"
    )
    target_skills: list[str] = Field(
        default_factory=list,
        description="Skills you are moving towards (e.g. C++): partial credit in matching, told to the AI scorer",
    )
    max_offer_age_days: int | None = Field(default=45, ge=0, description="0 or null: no age limit")

    @field_validator("max_offer_age_days")
    @classmethod
    def _no_limit(cls, value: int | None) -> int | None:
        return value or None  # TOML has no null, so config.toml spells "no limit" as 0


class RuleWeights(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    skills: float = Field(default=0.45, ge=0)
    title: float = Field(default=0.10, ge=0)
    seniority: float = Field(default=0.15, ge=0)
    location: float = Field(default=0.10, ge=0)
    salary: float = Field(default=0.10, ge=0)
    languages: float = Field(default=0.05, ge=0)
    freshness: float = Field(default=0.05, ge=0)


class ExperienceConfig(BaseModel):
    """How experience in one technology carries over to another (see matching/experience.py)."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    transfer_ratio: float = Field(
        default=0.35, ge=0, le=1, description="Share of general experience that counts in an unfamiliar technology"
    )
    declared_ratio: float = Field(
        default=0.5,
        ge=0,
        le=1,
        description="Share of general experience assumed for skills listed in the CV but not tied to a position",
    )


class MatchingConfig(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    mode: MatchingMode = MatchingMode.BASIC
    weights: RuleWeights = Field(default_factory=RuleWeights)
    experience: ExperienceConfig = Field(default_factory=ExperienceConfig)


class AIConfig(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    provider: str = "anthropic"
    model: str = "claude-haiku-4-5"
    top_n: int = Field(default=20, ge=1)
    weight: float = Field(default=0.7, ge=0, le=1, description="Share of the AI score in the final score")
    base_url: str | None = Field(default=None, description="For openai_compatible providers, e.g. Ollama")
    api_key_env: str | None = Field(default=None, description="Env var holding the API key; provider default if empty")
    max_concurrency: int = Field(default=4, ge=1)


class JustJoinConfig(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    page_size: int = Field(default=100, ge=1, le=100)
    request_delay_s: float = Field(default=0.5, ge=0)
    max_retries: int = Field(default=3, ge=0)


class ApiConfig(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Origins allowed to call the REST API from a browser (the web frontend's dev server)",
    )


class AppConfig(BaseModel):
    base_dir: Path = Field(default_factory=Path.cwd, exclude=True)
    config_path: Path | None = Field(default=None, exclude=True, description="The config.toml it was loaded from")
    paths: PathsConfig = Field(default_factory=PathsConfig)
    search: SearchPreferences = Field(default_factory=SearchPreferences)
    matching: MatchingConfig = Field(default_factory=MatchingConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    justjoin: JustJoinConfig = Field(default_factory=JustJoinConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    searches: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Named search presets: partial [search] overrides, e.g. [searches.cpp] categories = ['c']",
    )

    @model_validator(mode="after")
    def _validate_searches(self) -> AppConfig:
        for name in self.searches:
            try:
                self.preferences(name)
            except ValidationError as exc:
                raise ValueError(f"Błąd w [searches.{name}]: {exc}") from exc
        return self

    @property
    def file(self) -> Path:
        """config.toml to edit: the loaded file, or the default name in base_dir when built in code."""
        return self.config_path or self.base_dir / DEFAULT_CONFIG_NAME

    def resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else self.base_dir / path

    def preferences(self, search: str | None = None, overrides: dict[str, Any] | None = None) -> SearchPreferences:
        """Effective preferences: [search] <- [searches.<search>] <- per-request overrides."""
        merged = self.search.model_dump()
        if search:
            if search not in self.searches:
                available = ", ".join(sorted(self.searches)) or "brak - dodaj [searches.<nazwa>] w config.toml"
                raise ValueError(f"Nieznany profil wyszukiwania '{search}'. Dostępne: {available}")
            merged.update(self.searches[search])
        merged.update({k: v for k, v in (overrides or {}).items() if v is not None})
        return SearchPreferences.model_validate(merged)


def load_config(path: Path | None = None) -> AppConfig:
    """Load config from ``path``, ``$JOBSEEKER_CONFIG`` or ``./config.toml``; missing file means defaults."""
    if path is None:
        env_path = os.environ.get(CONFIG_ENV_VAR)
        path = Path(env_path) if env_path else Path.cwd() / DEFAULT_CONFIG_NAME
    base_dir = path.parent.resolve()
    load_dotenv(base_dir / ".env")

    data: dict[str, Any] = {}
    if path.is_file():
        with path.open("rb") as f:
            data = tomllib.load(f)
    return config_from_toml(data, path)


def config_from_toml(data: dict[str, Any], path: Path) -> AppConfig:
    """Validate parsed TOML as the config stored at ``path`` (relative paths resolve next to it)."""
    data = dict(data)
    paths = data.get("paths")
    if isinstance(paths, dict) and not paths.get("cv_path"):
        data["paths"] = {k: v for k, v in paths.items() if k != "cv_path"}  # TOML has no null; "" means unset
    return AppConfig.model_validate({**data, "base_dir": path.parent.resolve(), "config_path": path})
