"""Settings endpoints: config.toml sections, search presets, API keys in .env."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from job_seeker.api.app import create_app
from job_seeker.config import AppConfig
from job_seeker.services.job_seeker import JobSeekerService
from tests.conftest import SAMPLE_CV, make_pdf
from tests.fakes import FakeSource


@pytest.fixture
def client(app_config: AppConfig, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_WORKSPACE_ID", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    (app_config.base_dir / "cv").mkdir()
    (app_config.base_dir / "cv" / "cv.pdf").write_bytes(make_pdf(SAMPLE_CV))
    service = JobSeekerService(app_config, source_factory=lambda name, cfg: FakeSource([]))
    return TestClient(create_app(service=service))


def config_file(client: TestClient) -> Path:
    return Path(client.get("/config").json()["config_file"])


def test_global_settings_are_saved_and_used(client: TestClient) -> None:
    config = client.get("/config").json()
    assert config["version"] == "" and config["ai"]["top_n"] == 20 and not config["restart_required"]

    ai = {**config["ai"], "top_n": 30, "model": "claude-sonnet-5-5"}
    saved = client.put("/config", json={"version": "", "ai": ai})
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] and not saved.json()["restart_required"]
    assert "top_n = 30" in config_file(client).read_text(encoding="utf-8")
    assert client.get("/settings").json()["ai"]["top_n"] == 30  # applied without a restart

    stale = client.put("/config", json={"version": "", "ai": ai})
    assert stale.status_code == 409 and stale.json()["code"] == "config_conflict"
    forced = client.put("/config", json={"version": "", "force": True, "ai": {**ai, "top_n": 31}})
    assert forced.status_code == 200 and forced.json()["ai"]["top_n"] == 31

    paths = {**config["paths"], "data_dir": "other-data"}
    moved = client.put("/config", json={"version": forced.json()["version"], "paths": paths}).json()
    assert moved["restart_required"] and moved["paths"]["data_dir"] == "other-data"


def test_invalid_values_come_back_per_field(client: TestClient) -> None:
    config = client.get("/config").json()
    bad = client.put("/config", json={"version": "", "justjoin": {**config["justjoin"], "page_size": 150}})
    assert bad.status_code == 400 and bad.json()["code"] == "invalid_request"
    assert bad.json()["fields"] == {"justjoin.page_size": "Maksymalnie 100."}
    assert config_file(client).exists() is False


def test_search_presets(client: TestClient) -> None:
    version = client.get("/config").json()["version"]
    prefs = client.get("/preferences").json()
    saved = client.put("/searches/default", json={"version": version, "preferences": {**prefs, "categories": ["go"]}})
    assert saved.status_code == 200, saved.text
    assert client.get("/preferences").json()["categories"] == ["go"]

    version = saved.json()["version"]
    created = client.put(
        "/searches/cpp",
        json={"version": version, "create": True, "overrides": {"categories": ["c"], "target_skills": ["C++"]}},
    )
    assert created.status_code == 200, created.text
    cpp = next(s for s in client.get("/searches").json() if s["name"] == "cpp")
    assert cpp["overridden"] == ["categories", "target_skills"] and cpp["preferences"]["target_skills"] == ["C++"]
    assert cpp["preferences"]["exclude_keywords"] == prefs["exclude_keywords"]  # inherited

    version = created.json()["version"]
    renamed = client.put(
        "/searches/cpp", json={"version": version, "overrides": {"categories": ["c"]}, "rename_to": "cplus"}
    )
    assert renamed.status_code == 200
    assert [s["name"] for s in client.get("/searches").json()] == [None, "cplus"]

    reserved = client.put("/searches/new", json={"version": renamed.json()["version"], "create": True, "overrides": {}})
    assert reserved.status_code == 400 and "name" in reserved.json()["fields"]
    missing = client.delete("/searches/nope", params={"version": renamed.json()["version"]})
    assert missing.status_code == 404 and missing.json()["code"] == "search_not_found"

    deleted = client.delete("/searches/cplus", params={"version": renamed.json()["version"]})
    assert deleted.status_code == 200 and [s["name"] for s in client.get("/searches").json()] == [None]


def test_api_keys_are_never_returned(client: TestClient) -> None:
    keys = client.get("/env-keys").json()
    assert [k["name"] for k in keys] == ["ANTHROPIC_API_KEY", "ANTHROPIC_WORKSPACE_ID", "OPENAI_API_KEY"]
    assert not any(k["set"] for k in keys)

    saved = client.put("/env-keys/ANTHROPIC_API_KEY", json={"value": "sk-ant-test-1234a3F9"})
    assert saved.json() == {"name": "ANTHROPIC_API_KEY", "label": "Anthropic", "set": True, "hint": "…a3F9"}
    assert "sk-ant-test-1234a3F9" not in client.get("/env-keys").text

    assert client.delete("/env-keys/ANTHROPIC_API_KEY").json()["set"] is False
    assert client.put("/env-keys/PATH", json={"value": "x"}).status_code == 400
