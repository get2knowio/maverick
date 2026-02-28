"""Unit tests for ``maverick refuel maverick`` CLI command."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from maverick.main import cli

_PATCH_EXECUTE = "maverick.cli.commands.refuel.maverick_cmd.execute_python_workflow"


class TestRefuelMaverickRegistered:
    """Test that maverick subcommand is registered under refuel."""

    def test_maverick_in_refuel_help(
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
        assert "maverick" in result.output


class TestRefuelMaverickCommand:
    """Tests for 'maverick refuel maverick' command."""

    def test_missing_flight_plan_arg(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """flight-plan-path argument is required."""
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        result = cli_runner.invoke(cli, ["refuel", "maverick"])
        assert result.exit_code != 0

    def test_list_steps_prints_step_names_and_exits(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--list-steps prints workflow step names and exits with code 0."""
        from maverick.workflows.refuel_maverick.constants import (
            CREATE_BEADS,
            DECOMPOSE,
            GATHER_CONTEXT,
            PARSE_FLIGHT_PLAN,
            VALIDATE,
            WIRE_DEPS,
            WRITE_WORK_UNITS,
        )

        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        result = cli_runner.invoke(
            cli,
            ["refuel", "maverick", "some-path.md", "--list-steps"],
        )

        assert result.exit_code == 0
        assert PARSE_FLIGHT_PLAN in result.output
        assert GATHER_CONTEXT in result.output
        assert DECOMPOSE in result.output
        assert VALIDATE in result.output
        assert WRITE_WORK_UNITS in result.output
        assert CREATE_BEADS in result.output
        assert WIRE_DEPS in result.output

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_delegates_to_refuel_maverick_workflow(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Normal execution delegates to RefuelMaverickWorkflow."""
        from maverick.workflows.refuel_maverick import RefuelMaverickWorkflow

        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        cli_runner.invoke(
            cli,
            ["refuel", "maverick", "my-plan.md"],
        )

        mock_execute.assert_called_once()
        run_config = mock_execute.call_args[0][1]
        assert run_config.workflow_class is RefuelMaverickWorkflow

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_dry_run_flag_passed_to_workflow(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--dry-run flag is passed as input to the workflow."""
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        cli_runner.invoke(
            cli,
            ["refuel", "maverick", "my-plan.md", "--dry-run"],
        )

        mock_execute.assert_called_once()
        run_config = mock_execute.call_args[0][1]
        assert run_config.inputs["dry_run"] is True

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_dry_run_is_false_by_default(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--dry-run defaults to False when not specified."""
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        cli_runner.invoke(
            cli,
            ["refuel", "maverick", "my-plan.md"],
        )

        mock_execute.assert_called_once()
        run_config = mock_execute.call_args[0][1]
        assert run_config.inputs["dry_run"] is False

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_flight_plan_path_passed_as_string(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """flight_plan_path is passed as a string in inputs."""
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        cli_runner.invoke(
            cli,
            ["refuel", "maverick", "my-plan.md"],
        )

        mock_execute.assert_called_once()
        run_config = mock_execute.call_args[0][1]
        assert "flight_plan_path" in run_config.inputs
        assert run_config.inputs["flight_plan_path"] == "my-plan.md"

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_session_log_passed_to_run_config(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--session-log path is passed to PythonWorkflowRunConfig."""
        log_path = temp_dir / "session.log"
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        cli_runner.invoke(
            cli,
            ["refuel", "maverick", "my-plan.md", "--session-log", str(log_path)],
        )

        mock_execute.assert_called_once()
        run_config = mock_execute.call_args[0][1]
        assert run_config.session_log_path == log_path

    def test_maverick_help_shows_correct_options(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Help text shows --dry-run, --list-steps, --session-log options."""
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        result = cli_runner.invoke(cli, ["refuel", "maverick", "--help"])

        assert result.exit_code == 0
        assert "--dry-run" in result.output
        assert "--list-steps" in result.output
        assert "--session-log" in result.output
