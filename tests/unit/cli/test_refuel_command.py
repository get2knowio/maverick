"""Unit tests for ``maverick refuel speckit`` CLI command."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from maverick.main import cli

# Patch target for the workflow execution
_PATCH_EXECUTE = "maverick.cli.commands.refuel.speckit._execute_workflow_run"


@pytest.fixture
def spec_dir_for_cli(temp_dir: Path) -> Path:
    """Create a spec directory with tasks.md for CLI testing."""
    spec_dir = temp_dir / "specs" / "001-test"
    spec_dir.mkdir(parents=True)
    (spec_dir / "tasks.md").write_text("## Phase 1: Setup\n\n- [ ] T001 Init project\n")
    return spec_dir


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
        assert "speckit" in result.output

    def test_refuel_speckit_help(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        result = cli_runner.invoke(cli, ["refuel", "speckit", "--help"])
        assert result.exit_code == 0
        assert "SPEC_DIR" in result.output
        assert "--dry-run" in result.output
        assert "--list-steps" in result.output


class TestRefuelSpeckitCommand:
    """Tests for 'maverick refuel speckit' command."""

    def test_missing_spec_dir(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        result = cli_runner.invoke(
            cli,
            ["refuel", "speckit", str(temp_dir / "nonexistent")],
        )
        assert result.exit_code != 0

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_delegates_to_workflow_run(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        spec_dir_for_cli: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        cli_runner.invoke(
            cli,
            ["refuel", "speckit", str(spec_dir_for_cli)],
        )

        mock_execute.assert_called_once()
        args = mock_execute.call_args[0]
        # args[0] = ctx, args[1] = workflow name
        assert args[1] == "refuel-speckit"

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_passes_dry_run_as_input(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        spec_dir_for_cli: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        cli_runner.invoke(
            cli,
            ["refuel", "speckit", str(spec_dir_for_cli), "--dry-run"],
        )

        mock_execute.assert_called_once()
        args = mock_execute.call_args[0]
        # args[2] = inputs tuple
        inputs_tuple = args[2]
        assert any("dry_run=True" in i for i in inputs_tuple)

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_passes_spec_dir_as_input(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        spec_dir_for_cli: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        cli_runner.invoke(
            cli,
            ["refuel", "speckit", str(spec_dir_for_cli)],
        )

        mock_execute.assert_called_once()
        args = mock_execute.call_args[0]
        inputs_tuple = args[2]
        assert any("spec_dir=" in i for i in inputs_tuple)

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_passes_list_steps_flag(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        spec_dir_for_cli: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        cli_runner.invoke(
            cli,
            ["refuel", "speckit", str(spec_dir_for_cli), "--list-steps"],
        )

        mock_execute.assert_called_once()
        args = mock_execute.call_args[0]
        # args[7] = list_steps
        assert args[7] is True
