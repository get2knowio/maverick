"""Tests for runway CLI commands."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from maverick.cli.commands.runway._group import runway


class TestRunwayInit:
    """Tests for `maverick runway init`."""

    def test_init_creates_structure(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            result = runner.invoke(runway, ["init"])
            assert result.exit_code == 0
            assert "initialized" in result.output.lower()
            runway_path = Path(td) / ".maverick" / "runway"
            assert runway_path.is_dir()
            assert (runway_path / "index.json").is_file()

    def test_init_idempotent(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(runway, ["init"])
            result = runner.invoke(runway, ["init"])
            assert result.exit_code == 0
            assert "already initialized" in result.output.lower()


class TestRunwayStatus:
    """Tests for `maverick runway status`."""

    def test_status_not_initialized(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(runway, ["status"])
            assert result.exit_code == 0
            assert "not initialized" in result.output.lower()

    def test_status_initialized(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(runway, ["init"])
            result = runner.invoke(runway, ["status"])
            assert result.exit_code == 0
            assert "Bead outcomes" in result.output or "bead" in result.output.lower()


class TestRunwayGroup:
    """Tests for the runway command group."""

    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(runway, ["--help"])
        assert result.exit_code == 0
        assert "runway" in result.output.lower()

    def test_no_subcommand_shows_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(runway, [])
        assert result.exit_code == 0
        assert "init" in result.output
        assert "status" in result.output
