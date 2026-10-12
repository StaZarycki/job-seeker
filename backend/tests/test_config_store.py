"""Editing config.toml / .env from the web app: comments survive, conflicts and bad values are refused."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from job_seeker.config import AIConfig, JustJoinConfig, MatchingMode, SearchPreferences, load_config
from job_seeker.config_store import (
    ConfigConflictError,
    ConfigStore,
    EnvStore,
    PresetNotFoundError,
    SettingsValidationError,
    file_version,
)
from job_seeker.domain.models import WorkplaceType

CONFIG = """\
# My job search
[search]
categories = ["javascript", "python"]   # keys from `jobseeker categories`
exclude_keywords = ["Java"]

[matching]
mode = "basic"

[ai]
model = "claude-haiku-4-5"    # cheap
top_n = 20

# C++ switch
[searches.cpp]
categories = ["c"]   # JustJoin key for C/C++
target_skills = ["C++"]
"""


@pytest.fixture
def path(tmp_path: Path) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(CONFIG, encoding="utf-8")
    return p


def test_section_update_writes_only_changed_keys_and_keeps_comments(path: Path) -> None:
    store = ConfigStore(path)
    current = load_config(path)
    ai = current.ai.model_copy(update={"top_n": 30})
    matching = current.matching.model_copy(update={"mode": MatchingMode.AI})
    config = store.update_sections(store.version(), {"ai": ai, "matching": matching}, current=current)

    text = path.read_text(encoding="utf-8")
    assert "top_n = 30" in text and 'mode = "ai"' in text
    assert 'model = "claude-haiku-4-5"    # cheap' in text  # untouched line, comment kept
    assert "# My job search" in text and "# JustJoin key for C/C++" in text
    assert "provider" not in text and "max_concurrency" not in text  # unchanged defaults are not written
    assert config.ai.top_n == 30 and config.matching.mode is MatchingMode.AI


def test_new_section_and_nested_table_are_created(path: Path) -> None:
    store = ConfigStore(path)
    current = load_config(path)
    justjoin = JustJoinConfig(page_size=50)
    weights = current.matching.weights.model_copy(update={"skills": 0.6})
    matching = current.matching.model_copy(update={"weights": weights})
    config = store.update_sections(store.version(), {"justjoin": justjoin, "matching": matching}, current=current)
    assert config.justjoin.page_size == 50 and config.matching.weights.skills == 0.6
    assert load_config(path).matching.weights.skills == 0.6


def test_stale_version_is_refused_unless_forced(path: Path) -> None:
    store = ConfigStore(path)
    version = store.version()
    current = load_config(path)
    path.write_text(CONFIG + "\n# edited by hand\n", encoding="utf-8")
    with pytest.raises(ConfigConflictError):
        store.update_sections(version, {"ai": AIConfig(top_n=5)}, current=current)
    store.update_sections(version, {"ai": AIConfig(top_n=5)}, current=current, force=True)
    assert "# edited by hand" in path.read_text(encoding="utf-8")


def test_invalid_values_are_reported_per_field_and_nothing_is_written(path: Path) -> None:
    store = ConfigStore(path)
    current = load_config(path)
    bad = JustJoinConfig.model_construct(page_size=150, request_delay_s=0.5, max_retries=3)
    with pytest.raises(SettingsValidationError) as info:
        store.update_sections(store.version(), {"justjoin": bad}, current=current)
    assert info.value.fields == {"justjoin.page_size": "Maksymalnie 100."}
    assert path.read_text(encoding="utf-8") == CONFIG


def test_default_search_and_no_age_limit(path: Path) -> None:
    store = ConfigStore(path)
    current = load_config(path)
    prefs = current.search.model_copy(
        update={"max_offer_age_days": None, "min_salary_pln_month": 18000.0, "workplace": [WorkplaceType.REMOTE]}
    )
    config = store.update_default_search(store.version(), prefs, current=current)
    text = path.read_text(encoding="utf-8")
    assert "max_offer_age_days = 0" in text and 'workplace = ["remote"]' in text
    assert config.search.max_offer_age_days is None and config.search.min_salary_pln_month == 18000

    cleared = config.search.model_copy(update={"min_salary_pln_month": None})
    store.update_default_search(store.version(), cleared, current=config)
    assert "min_salary_pln_month" not in path.read_text(encoding="utf-8")


def test_presets_create_replace_rename_delete(path: Path) -> None:
    store = ConfigStore(path)
    config = store.save_preset(store.version(), "go", {"categories": ["go"], "target_skills": ["Go"]}, create=True)
    assert config.searches["go"] == {"categories": ["go"], "target_skills": ["Go"]}

    with pytest.raises(SettingsValidationError) as info:
        store.save_preset(store.version(), "go", {}, create=True)
    assert info.value.fields == {"name": "Profil o tej nazwie już istnieje."}

    config = store.save_preset(store.version(), "cpp", {"categories": ["c"]}, rename_to="cplus")
    assert "cpp" not in config.searches and config.searches["cplus"] == {"categories": ["c"]}
    assert "# JustJoin key for C/C++" in path.read_text(encoding="utf-8")  # kept for the kept key

    config = store.delete_preset(store.version(), "cplus")
    config = store.delete_preset(store.version(), "go")
    assert config.searches == {} and "[searches" not in path.read_text(encoding="utf-8")
    with pytest.raises(PresetNotFoundError):
        store.delete_preset(store.version(), "go")


def test_preset_validation(path: Path) -> None:
    store = ConfigStore(path)
    for name in ("C++", "", "default", "new"):
        with pytest.raises(SettingsValidationError):
            store.save_preset(store.version(), name, {}, create=True)
    with pytest.raises(SettingsValidationError) as info:
        store.save_preset(store.version(), "cpp", {"workplace": ["moon"]})
    assert info.value.fields == {"searches.cpp.workplace.0": "Niedozwolona wartość."}


def test_windows_line_endings_are_kept(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_bytes(CONFIG.replace("\n", "\r\n").encode("utf-8"))
    store = ConfigStore(path)
    current = load_config(path)
    store.update_sections(store.version(), {"ai": current.ai.model_copy(update={"top_n": 9})}, current=current)
    data = path.read_bytes()
    assert b"top_n = 9\r\n" in data and data.count(b"\r\n") == data.count(b"\n")


def test_missing_file_is_created(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    store = ConfigStore(path)
    assert store.version() == ""
    current = load_config(path)
    store.update_sections("", {"ai": AIConfig(top_n=7)}, current=current)
    assert load_config(path).ai.top_n == 7 and file_version(path) != ""


def test_search_preferences_round_trip_through_example_config() -> None:
    example = Path(__file__).parents[1] / "config.example.toml"
    config = load_config(example)
    assert isinstance(config.search, SearchPreferences) and set(config.searches) == {"cpp", "python"}


def test_env_keys_are_written_but_never_returned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("# keys\nOTHER=1\n", encoding="utf-8")
    store = EnvStore(env)
    assert {k.name: k.is_set for k in store.statuses()}["ANTHROPIC_API_KEY"] is False

    key = store.set("ANTHROPIC_API_KEY", "  sk-ant-secret-a3F9 ")
    assert key.is_set and key.hint == "…a3F9"
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-secret-a3F9"
    text = env.read_text(encoding="utf-8")
    assert "OTHER=1" in text and "# keys" in text and "sk-ant-secret-a3F9" in text

    store.remove("ANTHROPIC_API_KEY")
    assert "ANTHROPIC_API_KEY" not in env.read_text(encoding="utf-8") and "ANTHROPIC_API_KEY" not in os.environ
    with pytest.raises(SettingsValidationError):
        store.set("PATH", "x")
    with pytest.raises(SettingsValidationError):
        store.set("OPENAI_API_KEY", "two\nlines")
