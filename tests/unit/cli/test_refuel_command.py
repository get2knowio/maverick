"""Unit tests for ``maverick refuel speckit`` CLI command."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from maverick.main import cli

# Patch target for the workflow execution
_PATCH_EXECUTE = "maverick.cli.commands.refuel.speckit.execute_workflow_run"


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
        assert "SPEC" in result.output
        assert "--dry-run" in result.output
        assert "--list-steps" in result.output


class TestRefuelSpeckitCommand:
    """Tests for 'maverick refuel speckit' command."""

    def test_missing_spec_arg(
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
            ["refuel", "speckit"],
        )
        assert result.exit_code != 0

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_delegates_to_workflow_run(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        cli_runner.invoke(
            cli,
            ["refuel", "speckit", "001-test"],
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
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        cli_runner.invoke(
            cli,
            ["refuel", "speckit", "001-test", "--dry-run"],
        )

        mock_execute.assert_called_once()
        args = mock_execute.call_args[0]
        # args[2] = inputs tuple (workflow-level dry_run input)
        inputs_tuple = args[2]
        assert any("dry_run=true" in i for i in inputs_tuple)
        # args[4] = CLI-level dry_run flag (skips preflight/executor)
        assert args[4] is True

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_cli_dry_run_is_false_by_default(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        cli_runner.invoke(
            cli,
            ["refuel", "speckit", "001-test"],
        )

        mock_execute.assert_called_once()
        args = mock_execute.call_args[0]
        # args[4] = CLI-level dry_run flag
        assert args[4] is False

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_passes_spec_as_input(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        cli_runner.invoke(
            cli,
            ["refuel", "speckit", "001-test"],
        )

        mock_execute.assert_called_once()
        args = mock_execute.call_args[0]
        inputs_tuple = args[2]
        assert any("spec=001-test" in i for i in inputs_tuple)

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_passes_list_steps_flag(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        cli_runner.invoke(
            cli,
            ["refuel", "speckit", "001-test", "--list-steps"],
        )

        mock_execute.assert_called_once()
        args = mock_execute.call_args[0]
        # args[7] = list_steps
        assert args[7] is True
