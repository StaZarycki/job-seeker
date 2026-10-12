"""Edit ``config.toml`` and ``.env`` from the API, keeping the user's comments and layout.

Every write is guarded by the file's version (a hash of its content), so an edit made in a text editor
meanwhile is never silently overwritten, and the new file is validated as an ``AppConfig`` before it
replaces the old one.
"""

from __future__ import annotations

import hashlib
import os
import re
import tomllib
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomlkit
from dotenv import dotenv_values, set_key, unset_key
from pydantic import BaseModel, ValidationError
from tomlkit.items import Table
from tomlkit.toml_document import TOMLDocument

from job_seeker.config import AppConfig, SearchPreferences, config_from_toml

PRESET_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
RESERVED_PRESET_NAMES = {"default", "new"}  # used by the web app's URLs (/searches/default, /searches/new)

# Fields whose "unset" value can't be written as a missing key, because a missing key means the default.
_NONE_AS = {"max_offer_age_days": 0}


class ConfigConflictError(RuntimeError):
    """config.toml changed since the client read it."""


class ConfigWriteError(RuntimeError):
    """config.toml or .env could not be written."""


class SettingsValidationError(ValueError):
    """The edited config is invalid; ``fields`` maps dotted paths (``ai.top_n``) to Polish messages."""

    def __init__(self, fields: dict[str, str]) -> None:
        self.fields = fields
        summary = "; ".join(f"{path}: {message}" for path, message in fields.items())
        super().__init__(f"Nie zapisano – popraw wartości: {summary}")


class PresetNotFoundError(LookupError):
    pass


def file_version(path: Path) -> str:
    """Short content hash; "" when the file doesn't exist yet."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except FileNotFoundError:
        return ""


class ConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def version(self) -> str:
        return file_version(self.path)

    # --- sections -------------------------------------------------------------------------------------

    def update_sections(
        self, version: str, sections: dict[str, BaseModel], *, current: AppConfig, force: bool = False
    ) -> AppConfig:
        """Write the fields of whole sections (``{"ai": AIConfig(...), "matching": ...}``) that differ from
        ``current``; untouched keys and comments stay as they are."""

        def edit(doc: TOMLDocument) -> None:
            for name, model in sections.items():
                _write_model(doc, [name], model, getattr(current, name))

        return self._update(version, edit, force)

    def update_default_search(
        self, version: str, preferences: SearchPreferences, *, current: AppConfig, force: bool = False
    ) -> AppConfig:
        return self._update(version, lambda doc: _write_model(doc, ["search"], preferences, current.search), force)

    def save_preset(
        self,
        version: str,
        name: str,
        overrides: dict[str, Any],
        *,
        create: bool = False,
        rename_to: str | None = None,
        force: bool = False,
    ) -> AppConfig:
        """Create or replace ``[searches.<name>]`` with exactly ``overrides`` (other keys inherit [search])."""
        new_name = rename_to or name
        _check_preset_name(new_name)

        def edit(doc: TOMLDocument) -> None:
            searches = _searches_table(doc)
            exists = name in searches
            if create and exists:
                raise SettingsValidationError({"name": "Profil o tej nazwie już istnieje."})
            if not create and not exists:
                raise PresetNotFoundError(name)
            if new_name != name and new_name in searches:
                raise SettingsValidationError({"name": "Profil o tej nazwie już istnieje."})
            table = searches[name] if exists else tomlkit.table()
            assert isinstance(table, Table)
            for key in [k for k in table if k not in overrides]:
                del table[key]
            for key, value in overrides.items():
                plain = _toml_value(key, _plain(value))
                if key not in table or table[key] != plain:
                    table[key] = plain
            if new_name != name:
                del searches[name]
            searches[new_name] = table

        return self._update(version, edit, force)

    def delete_preset(self, version: str, name: str, *, force: bool = False) -> AppConfig:
        def edit(doc: TOMLDocument) -> None:
            searches = _searches_table(doc)
            if name not in searches:
                raise PresetNotFoundError(name)
            del searches[name]
            if not searches:
                del doc["searches"]

        return self._update(version, edit, force)

    # --- internals ------------------------------------------------------------------------------------

    def _update(self, version: str, edit: Callable[[TOMLDocument], None], force: bool) -> AppConfig:
        try:
            raw = self.path.read_bytes().decode("utf-8")
        except FileNotFoundError:
            raw = ""
        if not force and version != file_version(self.path):
            raise ConfigConflictError(
                "Plik config.toml zmienił się od otwarcia strony. Wczytaj go ponownie albo nadpisz."
            )
        newline = "\r\n" if "\r\n" in raw else "\n"  # keep the file's line endings (Windows editors use CRLF)
        doc = tomlkit.parse(raw.replace("\r\n", "\n"))
        edit(doc)
        new_text = _space_tables(tomlkit.dumps(doc))
        config = _validate(new_text, self.path)
        _atomic_write(self.path, new_text.replace("\n", newline))
        return config


@dataclass(frozen=True)
class EnvKey:
    name: str
    label: str
    is_set: bool
    hint: str | None  # last characters of the value, never the value itself


ENV_KEYS = {
    "ANTHROPIC_API_KEY": "Anthropic",
    "ANTHROPIC_WORKSPACE_ID": "Workspace Anthropic",
    "OPENAI_API_KEY": "Zgodny z OpenAI",
}
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


class EnvStore:
    """API keys in ``.env``. Values are written, never read back to the client."""

    def __init__(self, path: Path, extra_key: str | None = None) -> None:
        self.path = path
        self.names = dict(ENV_KEYS)
        if extra_key and extra_key not in self.names and ENV_NAME.match(extra_key):
            self.names[extra_key] = f"Klucz z ai.api_key_env ({extra_key})"

    def statuses(self) -> list[EnvKey]:
        stored = dotenv_values(self.path) if self.path.is_file() else {}
        result = []
        for name, label in self.names.items():
            value = stored.get(name) or os.environ.get(name)
            result.append(EnvKey(name, label, bool(value), _hint(value)))
        return result

    def set(self, name: str, value: str) -> EnvKey:
        self._check(name)
        value = value.strip()
        if not value or any(c in value for c in "\r\n'\""):
            raise SettingsValidationError({"value": "Wklej sam klucz – bez cudzysłowów i nowych linii."})
        try:
            self.path.touch(exist_ok=True)
            set_key(self.path, name, value, quote_mode="always")
        except OSError as exc:
            raise ConfigWriteError(f"Nie można zapisać pliku {self.path.name}: {exc.strerror or exc}") from exc
        os.environ[name] = value  # takes effect without a restart
        return EnvKey(name, self.names[name], True, _hint(value))

    def remove(self, name: str) -> EnvKey:
        self._check(name)
        if self.path.is_file():
            try:
                unset_key(self.path, name)
            except OSError as exc:
                raise ConfigWriteError(f"Nie można zapisać pliku {self.path.name}: {exc.strerror or exc}") from exc
        os.environ.pop(name, None)
        return EnvKey(name, self.names[name], False, None)

    def _check(self, name: str) -> None:
        if name not in self.names:
            raise SettingsValidationError({"name": f"Nieobsługiwana zmienna {name}."})


# --- helpers -------------------------------------------------------------------------------------------


def _hint(value: str | None) -> str | None:
    return f"…{value[-4:]}" if value and len(value) >= 8 else None


def _check_preset_name(name: str) -> None:
    if not PRESET_NAME.match(name):
        raise SettingsValidationError({"name": "Nazwa: małe litery, cyfry, - i _ (do 40 znaków)."})
    if name in RESERVED_PRESET_NAMES:
        raise SettingsValidationError({"name": f"Nazwa „{name}” jest zarezerwowana."})


def _searches_table(doc: TOMLDocument) -> Table:
    if "searches" not in doc:
        doc.add("searches", tomlkit.table(is_super_table=True))
    table = doc["searches"]
    assert isinstance(table, Table)
    return table


def _table(doc: TOMLDocument, path: list[str]) -> Table:
    node: Any = doc
    for key in path:
        if key not in node:
            node[key] = tomlkit.table()
        node = node[key]
    assert isinstance(node, Table)
    return node


def _write_model(doc: TOMLDocument, path: list[str], new: BaseModel, old: BaseModel) -> None:
    """Write fields of ``new`` that differ from ``old`` into the table at ``path`` (nested models recurse)."""
    old_values = old.model_dump(mode="json")
    for key, field_value in new:
        if isinstance(field_value, BaseModel):
            _write_model(doc, [*path, key], field_value, getattr(old, key))
            continue
        value = _plain(field_value)
        if value == old_values.get(key):
            continue
        table = _table(doc, path)
        if value is None and key not in _NONE_AS:
            table.pop(key, None)
        else:
            table[key] = _toml_value(key, value)


def _plain(value: Any) -> Any:
    """What TOML can hold: enums -> their values, paths -> strings, lists element-wise."""
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, float) and value.is_integer() and abs(value) >= 1:
        return int(value)  # 18000, not 18000.0
    return getattr(value, "value", value)


_HEADER = re.compile(r"^\[[^\[\]]+\]\s*(#.*)?$")


def _space_tables(text: str) -> str:
    """tomlkit appends new tables without a blank line; keep one before every header (or its comment)."""
    out: list[str] = []
    for line in text.split("\n"):
        if _HEADER.match(line) and out and out[-1].strip() and not out[-1].lstrip().startswith("#"):
            out.append("")
        out.append(line)
    return "\n".join(out)


def _toml_value(key: str, value: Any) -> Any:
    return _NONE_AS.get(key, value) if value is None else value


def _validate(text: str, path: Path) -> AppConfig:
    data = tomllib.loads(text)
    errors: dict[str, str] = {}
    try:
        base = SearchPreferences.model_validate(data.get("search", {})).model_dump()
    except ValidationError as exc:
        errors.update(_field_errors(exc, "search"))
        base = SearchPreferences().model_dump()
    # Presets are checked here, field by field: AppConfig would only report "invalid preset".
    for name, overrides in (data.get("searches") or {}).items():
        try:
            SearchPreferences.model_validate({**base, **overrides})
        except ValidationError as exc:
            errors.update(_field_errors(exc, f"searches.{name}"))
    if not errors:
        try:
            return config_from_toml(data, path)
        except ValidationError as exc:
            errors.update(_field_errors(exc))
    raise SettingsValidationError(errors)


def _field_errors(exc: ValidationError, prefix: str = "") -> Iterator[tuple[str, str]]:
    yield from field_messages(exc.errors(), prefix).items()


def field_messages(errors: Iterable[Any], prefix: str = "", drop: int = 0) -> dict[str, str]:
    """Pydantic errors -> {"ai.top_n": "Minimum 1."}; ``drop`` skips leading loc parts (FastAPI's "body")."""
    messages = {}
    for error in errors:
        parts = [str(part) for part in error["loc"][drop:]]
        messages[".".join([prefix, *parts] if prefix else parts) or "body"] = _polish(error)
    return messages


def _polish(error: Any) -> str:
    ctx = error.get("ctx") or {}
    kind = error["type"]
    if kind in ("less_than_equal", "less_than"):
        return f"Maksymalnie {ctx.get('le', ctx.get('lt'))}."
    if kind in ("greater_than_equal", "greater_than"):
        return f"Minimum {ctx.get('ge', ctx.get('gt'))}."
    if kind in ("int_parsing", "int_from_float", "float_parsing"):
        return "Wpisz liczbę."
    if kind in ("enum", "literal_error"):
        return "Niedozwolona wartość."
    if kind == "extra_forbidden":
        return "Nieznane pole."
    if kind in ("string_type", "list_type", "bool_type", "bool_parsing"):
        return "Zły typ wartości."
    return str(error.get("msg", "Błędna wartość."))


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8", newline="")
        os.replace(tmp, path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise ConfigWriteError(f"Nie można zapisać pliku {path.name}: {exc.strerror or exc}") from exc
