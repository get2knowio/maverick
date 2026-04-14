"""Unit tests for ``maverick refuel`` CLI command."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from maverick.main import cli


class TestRefuelGroupRegistered:
    """Test that refuel command is registered."""

    def test_refuel_in_cli(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(cli, ["--help"])
        assert "refuel" in result.output

    def test_refuel_help(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        result = cli_runner.invoke(cli, ["refuel", "--help"])
        assert result.exit_code == 0
        assert "--dry-run" in result.output
        assert "--skip-briefing" in result.output
