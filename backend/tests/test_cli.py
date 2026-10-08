"""CLI output is Rich markup: literal [brackets] in messages and user data must survive printing."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from job_seeker.cli import app
from tests.conftest import SAMPLE_CV, make_pdf

runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1"})


def test_help_shows_preset_section_header() -> None:
    result = runner.invoke(app, ["searches", "--help"])
    assert result.exit_code == 0
    assert "[searches.<nazwa>]" in result.output

    result = runner.invoke(app, ["match", "--help"])
    assert "[searches.<nazwa>]" in result.output


def test_searches_without_presets_names_the_section(tmp_path: Path) -> None:
    result = runner.invoke(app, ["searches", "--config", str(tmp_path / "config.toml")])
    assert result.exit_code == 0
    assert "Dodaj np. [searches.cpp] w config.toml" in result.output


def test_cv_file_name_with_brackets(tmp_path: Path) -> None:
    (tmp_path / "cv").mkdir()
    (tmp_path / "cv" / "CV [final].pdf").write_bytes(make_pdf(SAMPLE_CV))
    result = runner.invoke(app, ["profile", "show", "--config", str(tmp_path / "config.toml")])
    assert result.exit_code == 0, result.output
    assert "CV: CV [final].pdf" in result.output
    assert "Profil przebudowany z CV [final].pdf" in result.output
