"""Editing config.toml and the API keys in .env from the web app (screens Ustawienia and Wyszukiwania)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from job_seeker.api.deps import ServiceDep
from job_seeker.config import (
    AIConfig,
    ApiConfig,
    AppConfig,
    JustJoinConfig,
    MatchingConfig,
    PathsConfig,
    SearchPreferences,
)
from job_seeker.config_store import EnvKey
from job_seeker.domain.models import Model
from job_seeker.services.job_seeker import JobSeekerService

router = APIRouter(tags=["settings"])


class Versioned(Model):
    version: str = Field(description="config.toml version from the last read; a stale one is refused with 409")
    force: bool = Field(default=False, description="Overwrite even if config.toml changed meanwhile")


class ConfigResponse(Model):
    version: str = Field(description="Content hash of config.toml; empty when the file doesn't exist yet")
    config_file: str
    restart_required: bool = Field(description="Saved paths or CORS origins differ from the running server's")
    matching: MatchingConfig
    ai: AIConfig
    justjoin: JustJoinConfig
    paths: PathsConfig
    api: ApiConfig


class ConfigUpdate(Versioned):
    """Sections to save; each is sent whole, only fields that changed are written."""

    matching: MatchingConfig | None = None
    ai: AIConfig | None = None
    justjoin: JustJoinConfig | None = None
    paths: PathsConfig | None = None
    api: ApiConfig | None = None


class SavedConfig(Model):
    version: str
    restart_required: bool


class DefaultSearchUpdate(Versioned):
    preferences: SearchPreferences


class PresetUpdate(Versioned):
    overrides: dict[str, Any] = Field(description="Fields of [search] this preset changes; the rest inherit")
    create: bool = Field(default=False, description="Fail if a preset with this name already exists")
    rename_to: str | None = None


class EnvKeyStatus(Model):
    name: str
    label: str
    set: bool
    hint: str | None = Field(description="Last characters of the value, e.g. '…a3F9'; the value is never returned")


class EnvKeyValue(Model):
    value: str


@router.get("/config", response_model=ConfigResponse)
def get_config(service: ServiceDep) -> ConfigResponse:
    """Global settings from config.toml (search settings: GET /searches)."""
    return _config_response(service)


@router.put("/config", response_model=ConfigResponse)
def update_config(update: ConfigUpdate, service: ServiceDep) -> ConfigResponse:
    sections: dict[str, BaseModel] = {
        name: section
        for name in ("matching", "ai", "justjoin", "paths", "api")
        if (section := getattr(update, name)) is not None
    }
    config = service.config_store.update_sections(update.version, sections, current=service.config, force=update.force)
    service.apply_config(config)
    return _config_response(service)


@router.put("/searches/default", response_model=SavedConfig)
def update_default_search(update: DefaultSearchUpdate, service: ServiceDep) -> SavedConfig:
    """Save the [search] section, the base every preset inherits from."""
    config = service.config_store.update_default_search(
        update.version, update.preferences, current=service.config, force=update.force
    )
    return _saved(service, config)


@router.put("/searches/{name}", response_model=SavedConfig)
def save_preset(name: str, update: PresetUpdate, service: ServiceDep) -> SavedConfig:
    """Create (``create: true``), replace or rename the ``[searches.<name>]`` preset."""
    config = service.config_store.save_preset(
        update.version, name, update.overrides, create=update.create, rename_to=update.rename_to, force=update.force
    )
    return _saved(service, config)


@router.delete("/searches/{name}", response_model=SavedConfig)
def delete_preset(name: str, version: str, service: ServiceDep, force: bool = False) -> SavedConfig:
    config = service.config_store.delete_preset(version, name, force=force)
    return _saved(service, config)


@router.get("/env-keys", response_model=list[EnvKeyStatus])
def env_keys(service: ServiceDep) -> list[EnvKeyStatus]:
    """Which API keys are set in .env. Values are never returned."""
    return [_key_status(key) for key in service.env_store.statuses()]


@router.put("/env-keys/{name}", response_model=EnvKeyStatus)
def set_env_key(name: str, body: EnvKeyValue, service: ServiceDep) -> EnvKeyStatus:
    return _key_status(service.env_store.set(name, body.value))


@router.delete("/env-keys/{name}", response_model=EnvKeyStatus)
def remove_env_key(name: str, service: ServiceDep) -> EnvKeyStatus:
    return _key_status(service.env_store.remove(name))


def _config_response(service: JobSeekerService) -> ConfigResponse:
    config = service.config
    return ConfigResponse(
        version=service.config_store.version(),
        config_file=str(config.file),
        restart_required=service.restart_required(),
        matching=config.matching,
        ai=config.ai,
        justjoin=config.justjoin,
        paths=config.paths,
        api=config.api,
    )


def _saved(service: JobSeekerService, config: AppConfig) -> SavedConfig:
    service.apply_config(config)
    return SavedConfig(version=service.config_store.version(), restart_required=service.restart_required())


def _key_status(key: EnvKey) -> EnvKeyStatus:
    return EnvKeyStatus(name=key.name, label=key.label, set=key.is_set, hint=key.hint)
