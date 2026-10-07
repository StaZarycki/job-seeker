"""Builds the candidate profile from the CV and keeps it in sync when the CV file changes.

- The CV is the newest ``*.pdf`` in ``cv_dir`` (or an explicit ``cv_path``), so file names don't matter.
- ``data/profile.json`` caches the profile built from the CV, keyed by the CV's SHA-256; a different
  hash triggers an automatic rebuild.
- Manual corrections live in ``profile.overrides.toml`` and are applied on every load, so they survive
  CV changes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from job_seeker.config import AppConfig
from job_seeker.domain.models import CandidateProfile, CandidateSkill, Seniority
from job_seeker.profile import cv_reader
from job_seeker.profile.skills import IMPLIED_WEIGHT, IMPLIES, canonical_skill, find_skills_in_text

log = logging.getLogger(__name__)

# Bump when CV parsing changes, so profiles stored by an older version are rebuilt automatically.
PARSER_VERSION = 2
CORE_WEIGHT = 1.0
SECONDARY_WEIGHT = 0.75
_SUMMARY_SECTIONS = ("about me", "summary", "profile", "o mnie", "podsumowanie")


class CVNotFoundError(FileNotFoundError):
    pass


class ProfileOverrides(BaseModel):
    """Manual corrections applied on top of the profile parsed from the CV."""

    add_skills: list[str] = Field(default_factory=list, description="Added as core skills")
    remove_skills: list[str] = Field(default_factory=list)
    skill_weights: dict[str, float] = Field(default_factory=dict, description="Skill -> weight 0..1")
    skill_years: dict[str, float] = Field(
        default_factory=dict, description="Skill -> years of commercial use, e.g. {'python': 2}"
    )
    years_of_experience: float | None = None
    seniority: Seniority | None = None
    languages: dict[str, str] = Field(default_factory=dict, description="ISO code -> CEFR level")
    extra_notes: str | None = Field(default=None, description="Extra context for AI scoring, e.g. what you want")


@dataclass(frozen=True)
class ProfileState:
    profile: CandidateProfile
    profile_hash: str
    rebuilt: bool = False
    warning: str | None = None


class ProfileService:
    def __init__(self, cv_dir: Path, profile_path: Path, overrides_path: Path, cv_path: Path | None = None) -> None:
        self.cv_dir = cv_dir
        self.cv_path = cv_path
        self.profile_path = profile_path
        self.overrides_path = overrides_path

    @classmethod
    def from_config(cls, config: AppConfig) -> ProfileService:
        paths = config.paths
        return cls(
            cv_dir=config.resolve(paths.cv_dir),
            cv_path=config.resolve(paths.cv_path) if paths.cv_path else None,
            profile_path=config.resolve(paths.profile),
            overrides_path=config.resolve(paths.overrides),
        )

    def find_cv(self) -> Path:
        if self.cv_path is not None:
            if not self.cv_path.is_file():
                raise CVNotFoundError(f"Nie znaleziono CV: {self.cv_path} (ustawione jako paths.cv_path)")
            return self.cv_path
        pdfs = [p for p in self.cv_dir.glob("*.pdf") if p.is_file()] if self.cv_dir.is_dir() else []
        if not pdfs:
            raise CVNotFoundError(f"Nie znaleziono CV w folderze '{self.cv_dir}'. Wrzuć tam plik PDF.")
        return max(pdfs, key=lambda p: p.stat().st_mtime)

    def load(self, force_rebuild: bool = False) -> ProfileState:
        """Return the current profile, rebuilding it if the CV changed (or ``force_rebuild``)."""
        stored = self._read_stored()
        try:
            cv = self.find_cv()
        except CVNotFoundError as exc:
            if stored is None:
                raise
            warning = f"{exc} Używam ostatnio zapisanego profilu (z pliku {stored.source_file})."
            return self._state(stored, rebuilt=False, warning=warning)

        cv_hash = file_sha256(cv)
        if (
            force_rebuild
            or stored is None
            or stored.source_hash != cv_hash
            or stored.parser_version != PARSER_VERSION  # built by an older version of the CV parser
        ):
            stored = build_profile(cv, cv_hash)
            self._write_stored(stored)
            log.info("Profile rebuilt from %s", cv.name)
            return self._state(stored, rebuilt=True)
        return self._state(stored, rebuilt=False)

    def save_uploaded_cv(self, filename: str, content: bytes) -> ProfileState:
        if not content.startswith(b"%PDF"):
            raise ValueError("Przesłany plik nie jest PDF-em.")
        if self.cv_path is not None:
            raise ValueError("W configu ustawiono paths.cv_path - podmień ten plik zamiast przesyłać nowy.")
        safe_name = re.sub(r"[^\w.\- ]", "_", Path(filename).name) or "cv.pdf"
        if not safe_name.lower().endswith(".pdf"):
            safe_name += ".pdf"
        self.cv_dir.mkdir(parents=True, exist_ok=True)
        (self.cv_dir / safe_name).write_bytes(content)
        return self.load(force_rebuild=True)

    def read_overrides(self) -> ProfileOverrides:
        if not self.overrides_path.is_file():
            return ProfileOverrides()
        try:
            with self.overrides_path.open("rb") as f:
                return ProfileOverrides.model_validate(tomllib.load(f))
        except (tomllib.TOMLDecodeError, ValidationError) as exc:
            raise ValueError(f"Błędny plik {self.overrides_path.name}: {exc}") from exc

    def write_overrides(self, overrides: ProfileOverrides) -> None:
        self.overrides_path.parent.mkdir(parents=True, exist_ok=True)
        self.overrides_path.write_text(_overrides_to_toml(overrides), encoding="utf-8")

    def _state(self, raw: CandidateProfile, *, rebuilt: bool, warning: str | None = None) -> ProfileState:
        profile = apply_overrides(raw, self.read_overrides())
        return ProfileState(profile=profile, profile_hash=profile_hash(profile), rebuilt=rebuilt, warning=warning)

    def _read_stored(self) -> CandidateProfile | None:
        if not self.profile_path.is_file():
            return None
        try:
            return CandidateProfile.model_validate_json(self.profile_path.read_text(encoding="utf-8"))
        except ValidationError:
            log.warning("Ignoring corrupt %s; it will be rebuilt", self.profile_path)
            return None

    def _write_stored(self, profile: CandidateProfile) -> None:
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.profile_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")


def build_profile(cv: Path, cv_hash: str | None = None) -> CandidateProfile:
    text = cv_reader.extract_text(cv)
    sections = cv_reader.split_sections(text)
    summary = " ".join(sections.get(name, "") for name in _SUMMARY_SECTIONS)
    in_summary = find_skills_in_text(summary)

    weights: dict[str, float] = {}
    for skill, mentions in find_skills_in_text(text).items():
        weights[skill] = CORE_WEIGHT if mentions >= 2 or skill in in_summary else SECONDARY_WEIGHT
    for skill, weight in list(weights.items()):
        for implied in IMPLIES.get(skill, ()):
            weights[implied] = max(weights.get(implied, 0.0), round(weight * IMPLIED_WEIGHT, 2))

    years = cv_reader.years_of_experience(text)
    skill_years = _skill_years(text, cap=years)
    for skill in skill_years:  # skills implied by a position (e.g. JavaScript via Node.js) are known skills too
        weights.setdefault(skill, round(SECONDARY_WEIGHT * IMPLIED_WEIGHT, 2))
    headline, location = cv_reader.headline_and_location(text)
    return CandidateProfile(
        parser_version=PARSER_VERSION,
        source_file=cv.name,
        source_hash=cv_hash or file_sha256(cv),
        built_at=datetime.now(UTC),
        headline=headline,
        location=location,
        years_of_experience=years,
        seniority=cv_reader.seniority_for_years(years),
        skills=sorted(
            (CandidateSkill(name=n, weight=w) for n, w in weights.items()), key=lambda s: (-s.weight, s.name)
        ),
        skill_years=skill_years,
        languages=cv_reader.spoken_languages(text),
        cv_text=cv_reader.sanitize(text),
    )


def _skill_years(text: str, cap: float) -> dict[str, float]:
    """Years per skill: union of the periods of CV positions whose text mentions the skill (or implies it)."""
    intervals: dict[str, list[tuple[float, float]]] = {}
    for entry in cv_reader.experience_entries(text):
        for skill in _with_implied(find_skills_in_text(entry.text)):
            intervals.setdefault(skill, []).append((entry.start, entry.end))
    limit = cap if cap > 0 else float("inf")
    return {skill: min(limit, cv_reader.merged_years(periods)) for skill, periods in sorted(intervals.items())}


def _with_implied(skills: Iterable[str]) -> set[str]:
    result = set(skills)
    pending = list(result)
    while pending:
        for implied in IMPLIES.get(pending.pop(), ()):
            if implied not in result:
                result.add(implied)
                pending.append(implied)
    return result


def apply_overrides(profile: CandidateProfile, overrides: ProfileOverrides) -> CandidateProfile:
    weights = profile.skill_weights()
    for name in overrides.remove_skills:
        weights.pop(canonical_skill(name), None)
    for name in overrides.add_skills:
        weights[canonical_skill(name)] = CORE_WEIGHT
    for name, weight in overrides.skill_weights.items():
        weights[canonical_skill(name)] = max(0.0, min(1.0, weight))
    skill_years = {k: v for k, v in profile.skill_years.items() if k in weights}
    for name, value in overrides.skill_years.items():
        skill = canonical_skill(name)
        skill_years[skill] = max(0.0, value)
        weights.setdefault(skill, SECONDARY_WEIGHT)

    years = overrides.years_of_experience if overrides.years_of_experience is not None else profile.years_of_experience
    seniority = overrides.seniority or (
        cv_reader.seniority_for_years(years) if overrides.years_of_experience is not None else profile.seniority
    )
    cv_text = profile.cv_text
    if overrides.extra_notes:
        cv_text = f"{cv_text}\n\nDodatkowe informacje od kandydata:\n{overrides.extra_notes.strip()}"
    return profile.model_copy(
        update={
            "skills": sorted(
                (CandidateSkill(name=n, weight=w) for n, w in weights.items() if w > 0),
                key=lambda s: (-s.weight, s.name),
            ),
            "skill_years": dict(sorted(skill_years.items())),
            "years_of_experience": years,
            "seniority": seniority,
            "languages": {**profile.languages, **overrides.languages},
            "cv_text": cv_text,
        }
    )


def profile_hash(profile: CandidateProfile) -> str:
    """Identity of the profile *content*; changes when the CV or overrides change."""
    payload = profile.model_dump_json(exclude={"built_at", "source_file"})
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _overrides_to_toml(overrides: ProfileOverrides) -> str:
    def value(v: object) -> str:
        return json.dumps(v, ensure_ascii=False)  # JSON strings/numbers/arrays are valid TOML values

    lines = ["# Ręczne poprawki profilu - przetrwają podmianę CV.", ""]
    lines.append(f"add_skills = {value(overrides.add_skills)}")
    lines.append(f"remove_skills = {value(overrides.remove_skills)}")
    if overrides.years_of_experience is not None:
        lines.append(f"years_of_experience = {value(overrides.years_of_experience)}")
    if overrides.seniority is not None:
        lines.append(f"seniority = {value(overrides.seniority.value)}")
    if overrides.extra_notes:
        lines.append(f"extra_notes = {value(overrides.extra_notes)}")
    for table in ("skill_weights", "skill_years", "languages"):
        entries: dict[str, object] = getattr(overrides, table)
        if entries:
            lines += ["", f"[{table}]"] + [f"{value(k)} = {value(v)}" for k, v in entries.items()]
    return "\n".join(lines) + "\n"
