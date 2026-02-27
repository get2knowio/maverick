"""Unit tests for ``maverick refuel speckit`` CLI command."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from maverick.main import cli

# Patch target for the Python workflow execution
_PATCH_EXECUTE = "maverick.cli.commands.refuel.speckit.execute_python_workflow"


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
    def test_delegates_to_python_workflow(
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
        # First positional arg is the click context
        call_args = mock_execute.call_args
        # Second positional arg is PythonWorkflowRunConfig
        run_config = call_args[0][1]
        from maverick.workflows.refuel_speckit import RefuelSpeckitWorkflow

        assert run_config.workflow_class is RefuelSpeckitWorkflow

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
        run_config = mock_execute.call_args[0][1]
        assert run_config.inputs.get("dry_run") is True

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
        run_config = mock_execute.call_args[0][1]
        assert run_config.inputs.get("dry_run") is False

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
        run_config = mock_execute.call_args[0][1]
        assert run_config.inputs.get("spec") == "001-test"

    def test_list_steps_flag_exits_without_executing(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--list-steps should print steps and exit without running the workflow."""
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        result = cli_runner.invoke(
            cli,
            ["refuel", "speckit", "001-test", "--list-steps"],
        )

        # Should exit cleanly (SystemExit(0))
        assert result.exit_code == 0
        # Should show at least one step name
        assert "parse_spec" in result.output or "checkout" in result.output
