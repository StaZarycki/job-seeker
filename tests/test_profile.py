from __future__ import annotations

import os
import time
from datetime import date
from pathlib import Path

import pytest

from job_seeker.domain.models import Seniority
from job_seeker.profile import cv_reader
from job_seeker.profile.service import CVNotFoundError, ProfileOverrides, ProfileService
from job_seeker.profile.skills import canonical_skill, find_skills_in_text
from tests.conftest import SAMPLE_CV, make_pdf


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("NodeJS", "node.js"),
        ("Node.js", "node.js"),
        ("TS", "typescript"),
        ("Postgres", "postgresql"),
        ("Golang", "go"),
        ("REST API", "rest"),
        ("Kraków-specific tool", "krakow-specific tool"),
        ("Optimizely (Episerver)", "optimizely"),
    ],
)
def test_canonical_skill(raw: str, expected: str) -> None:
    assert canonical_skill(raw) == expected


def test_find_skills_counts_each_mention_once() -> None:
    found = find_skills_in_text("Express.js and Node.js services. JavaScript/TypeScript. SOLID. Go, Terraform.")
    assert found["express"] == 1
    assert found["node.js"] == 1
    assert {"javascript", "typescript", "solid", "go", "terraform"} <= found.keys()
    assert "java" not in found  # 'JavaScript' must not count as Java


def test_words_are_not_mistaken_for_skills() -> None:
    found = find_skills_in_text("I like to go hiking and rest. Solid results, nest of birds.")
    assert not found.keys() & {"go", "rest", "solid", "nestjs"}


def test_years_prefers_stated_value() -> None:
    assert cv_reader.years_of_experience("Developer with 4+ years of commercial experience") == 4


def test_years_sums_merged_ranges() -> None:
    text = "Experience\nA 2019 - 2020\nB 2021 - 2022\nC 2022 - 2025\nD 2026 - Present\nEducation\nUni 2010 - 2015"
    years = cv_reader.years_of_experience(text, today=date(2026, 7, 1))
    assert years == pytest.approx(1 + 4 + 0.5, abs=0.01)


def test_languages() -> None:
    langs = cv_reader.spoken_languages("Spoken Languages Polish - Native, English - B2, German - A2, Japanese - N3")
    assert langs == {"pl": "C2", "en": "B2", "de": "A2", "ja": "B1"}


def test_sanitize_removes_contacts_and_consent() -> None:
    text = "\n".join(SAMPLE_CV)
    clean = cv_reader.sanitize(text)
    assert "jan@example.com" not in clean
    assert "600 700 800" not in clean
    assert "Jan Kowalski" not in clean
    assert "I agree" not in clean
    assert "Node.js" in clean


# --- ProfileService: CV replacement ----------------------------------------------------------------


def _service(tmp_path: Path) -> ProfileService:
    return ProfileService(
        cv_dir=tmp_path / "cv",
        profile_path=tmp_path / "data" / "profile.json",
        overrides_path=tmp_path / "profile.overrides.toml",
    )


def _write_cv(directory: Path, name: str, lines: list[str], mtime_offset: float = 0) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(make_pdf(lines))
    ts = time.time() + mtime_offset
    os.utime(path, (ts, ts))
    return path


def test_builds_profile_from_pdf(tmp_path: Path) -> None:
    _write_cv(tmp_path / "cv", "moje cv.pdf", SAMPLE_CV)
    state = _service(tmp_path).load()

    assert state.rebuilt
    p = state.profile
    assert p.source_file == "moje cv.pdf"
    assert p.years_of_experience == 3
    assert p.seniority is Seniority.MID
    assert {"node.js", "typescript", "postgresql", "docker", "kafka"} <= set(p.skill_weights())
    assert p.languages == {"pl": "C2", "en": "B2"}
    assert "jan@example.com" not in p.cv_text


def test_same_cv_is_not_rebuilt(tmp_path: Path) -> None:
    _write_cv(tmp_path / "cv", "cv.pdf", SAMPLE_CV)
    service = _service(tmp_path)
    first = service.load()
    second = service.load()
    assert first.rebuilt and not second.rebuilt
    assert first.profile_hash == second.profile_hash


def test_new_cv_with_different_name_triggers_rebuild(tmp_path: Path) -> None:
    old = _write_cv(tmp_path / "cv", "stare.pdf", SAMPLE_CV, mtime_offset=-100)
    service = _service(tmp_path)
    first = service.load()

    old.unlink()
    _write_cv(tmp_path / "cv", "nowe CV 2027.pdf", [*SAMPLE_CV[:-3], "Skills", "Python, FastAPI, Rust"])
    second = service.load()

    assert second.rebuilt
    assert second.profile.source_file == "nowe CV 2027.pdf"
    assert "rust" in second.profile.skill_weights()
    assert second.profile_hash != first.profile_hash


def test_newest_pdf_wins_when_several_exist(tmp_path: Path) -> None:
    _write_cv(tmp_path / "cv", "a.pdf", SAMPLE_CV, mtime_offset=-100)
    _write_cv(tmp_path / "cv", "b.pdf", SAMPLE_CV, mtime_offset=0)
    assert _service(tmp_path).find_cv().name == "b.pdf"


def test_missing_cv_gives_clear_error(tmp_path: Path) -> None:
    with pytest.raises(CVNotFoundError, match="Nie znaleziono CV"):
        _service(tmp_path).load()


def test_missing_cv_falls_back_to_stored_profile(tmp_path: Path) -> None:
    cv = _write_cv(tmp_path / "cv", "cv.pdf", SAMPLE_CV)
    service = _service(tmp_path)
    first = service.load()
    cv.unlink()

    state = service.load()
    assert not state.rebuilt
    assert state.warning and "Nie znaleziono CV" in state.warning
    assert state.profile_hash == first.profile_hash


def test_overrides_survive_cv_change(tmp_path: Path) -> None:
    _write_cv(tmp_path / "cv", "a.pdf", SAMPLE_CV, mtime_offset=-100)
    service = _service(tmp_path)
    service.write_overrides(
        ProfileOverrides(
            add_skills=["Kubernetes"], remove_skills=["docker"], years_of_experience=6, extra_notes="Tylko backend"
        )
    )
    first = service.load()
    _write_cv(tmp_path / "cv", "b.pdf", [*SAMPLE_CV, "Also Redis"])
    second = service.load()

    for state in (first, second):
        weights = state.profile.skill_weights()
        assert weights["kubernetes"] == 1.0
        assert "docker" not in weights
        assert state.profile.years_of_experience == 6
        assert state.profile.seniority is Seniority.SENIOR
        assert "Tylko backend" in state.profile.cv_text
    assert second.rebuilt and "redis" in second.profile.skill_weights()


def test_overrides_change_profile_hash(tmp_path: Path) -> None:
    _write_cv(tmp_path / "cv", "cv.pdf", SAMPLE_CV)
    service = _service(tmp_path)
    before = service.load().profile_hash
    service.write_overrides(ProfileOverrides(add_skills=["Rust"]))
    assert service.load().profile_hash != before


def test_overrides_toml_roundtrip(tmp_path: Path) -> None:
    service = _service(tmp_path)
    overrides = ProfileOverrides(
        add_skills=['C# "quoted"'], skill_weights={"go": 0.3}, languages={"de": "A2"}, seniority=Seniority.MID
    )
    service.write_overrides(overrides)
    assert service.read_overrides() == overrides


def test_uploaded_cv_becomes_active(tmp_path: Path) -> None:
    _write_cv(tmp_path / "cv", "old.pdf", SAMPLE_CV, mtime_offset=-100)
    service = _service(tmp_path)
    service.load()
    state = service.save_uploaded_cv("../../evil name.pdf", make_pdf([*SAMPLE_CV, "Skills", "Elixir, Rust"]))
    assert state.rebuilt
    assert state.profile.source_file == "evil name.pdf"
    assert (tmp_path / "cv" / "evil name.pdf").is_file()


def test_upload_rejects_non_pdf(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="PDF"):
        _service(tmp_path).save_uploaded_cv("cv.pdf", b"hello")


def test_skill_years_override_survives_cv_change(tmp_path: Path) -> None:
    _write_cv(tmp_path / "cv", "a.pdf", SAMPLE_CV, mtime_offset=-100)
    service = _service(tmp_path)
    assert service.load().profile.skill_years["node.js"] == 3  # 2022 - Present, capped by stated 3 years
    service.write_overrides(ProfileOverrides(skill_years={"Python": 2, "C++": 0.5}))
    _write_cv(tmp_path / "cv", "b.pdf", [*SAMPLE_CV, "Also Redis"])
    state = service.load()
    assert state.rebuilt
    assert state.profile.skill_years["python"] == 2
    assert state.profile.skill_years["c++"] == 0.5
    assert "c++" in state.profile.skill_weights()  # a skill with years is a known skill


def test_profile_from_older_parser_is_rebuilt(tmp_path: Path) -> None:
    _write_cv(tmp_path / "cv", "cv.pdf", SAMPLE_CV)
    service = _service(tmp_path)
    stored = service.load().profile.model_copy(update={"parser_version": 1, "skill_years": {}})
    service.profile_path.write_text(stored.model_dump_json(), encoding="utf-8")

    state = service.load()
    assert state.rebuilt
    assert state.profile.skill_years
