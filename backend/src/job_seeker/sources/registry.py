"""Name -> factory registry of job sources. Adding a job board = one module + one ``register`` call."""

from __future__ import annotations

from collections.abc import Callable

from job_seeker.config import AppConfig
from job_seeker.sources.base import JobSource

SourceFactory = Callable[[AppConfig], JobSource]

_FACTORIES: dict[str, SourceFactory] = {}


def register(name: str, factory: SourceFactory) -> None:
    _FACTORIES[name] = factory


def available_sources() -> list[str]:
    _ensure_builtins()
    return sorted(_FACTORIES)


def create_source(name: str, config: AppConfig) -> JobSource:
    _ensure_builtins()
    try:
        factory = _FACTORIES[name]
    except KeyError:
        raise ValueError(f"Unknown source '{name}'. Available: {', '.join(available_sources())}") from None
    return factory(config)


def _ensure_builtins() -> None:
    if "justjoin" not in _FACTORIES:
        from job_seeker.sources.justjoin.client import JustJoinSource

        register("justjoin", lambda cfg: JustJoinSource.from_config(cfg.justjoin))
