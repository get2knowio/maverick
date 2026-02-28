"""Unit tests for ``maverick refuel flight-plan`` CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from maverick.main import cli

_PATCH_EXECUTE = "maverick.cli.commands.refuel._shared.execute_python_workflow"


class TestRefuelFlightPlanRegistered:
    """Test that flight-plan subcommand is registered under refuel."""

    def test_flight_plan_in_refuel_help(
        self,
        cli_runner: CliRunner,
    ) -> None:
        result = cli_runner.invoke(cli, ["refuel", "--help"])
        assert result.exit_code == 0
        assert "flight-plan" in result.output


class TestRefuelFlightPlanCommand:
    """Tests for 'maverick refuel flight-plan' command."""

    def test_missing_flight_plan_arg(
        self,
        cli_runner: CliRunner,
    ) -> None:
        """flight-plan-path argument is required."""
        result = cli_runner.invoke(cli, ["refuel", "flight-plan"])
        assert result.exit_code != 0

    def test_list_steps_prints_step_names_and_exits(
        self,
        cli_runner: CliRunner,
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

        result = cli_runner.invoke(
            cli,
            ["refuel", "flight-plan", "some-path.md", "--list-steps"],
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
    ) -> None:
        """Normal execution delegates to RefuelMaverickWorkflow."""
        from maverick.workflows.refuel_maverick import RefuelMaverickWorkflow

        result = cli_runner.invoke(
            cli,
            ["refuel", "flight-plan", "my-plan.md"],
        )

        assert result.exit_code == 0
        assert result.exception is None
        mock_execute.assert_called_once()
        run_config = mock_execute.call_args[0][1]
        assert run_config.workflow_class is RefuelMaverickWorkflow

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_flight_plan_path_passed_as_string(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
    ) -> None:
        """flight_plan_path is passed as a string in inputs."""
        result = cli_runner.invoke(
            cli,
            ["refuel", "flight-plan", "my-plan.md"],
        )

        assert result.exit_code == 0
        assert result.exception is None
        mock_execute.assert_called_once()
        run_config = mock_execute.call_args[0][1]
        assert "flight_plan_path" in run_config.inputs
        assert run_config.inputs["flight_plan_path"] == "my-plan.md"

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_dry_run_flag_passed_to_workflow(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
    ) -> None:
        """--dry-run flag is passed as input to the workflow."""
        result = cli_runner.invoke(
            cli,
            ["refuel", "flight-plan", "my-plan.md", "--dry-run"],
        )

        assert result.exit_code == 0
        assert result.exception is None
        mock_execute.assert_called_once()
        run_config = mock_execute.call_args[0][1]
        assert run_config.inputs["dry_run"] is True

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_dry_run_is_false_by_default(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
    ) -> None:
        """--dry-run defaults to False when not specified."""
        result = cli_runner.invoke(
            cli,
            ["refuel", "flight-plan", "my-plan.md"],
        )

        assert result.exit_code == 0
        assert result.exception is None
        mock_execute.assert_called_once()
        run_config = mock_execute.call_args[0][1]
        assert run_config.inputs["dry_run"] is False

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_session_log_passed_to_run_config(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        refuel_env: Path,
    ) -> None:
        """--session-log path is passed to PythonWorkflowRunConfig."""
        log_path = refuel_env / "session.log"

        result = cli_runner.invoke(
            cli,
            ["refuel", "flight-plan", "my-plan.md", "--session-log", str(log_path)],
        )

        assert result.exit_code == 0
        assert result.exception is None
        mock_execute.assert_called_once()
        run_config = mock_execute.call_args[0][1]
        assert run_config.session_log_path == log_path

    def test_help_shows_correct_options(
        self,
        cli_runner: CliRunner,
    ) -> None:
        """Help text shows --dry-run, --list-steps, --session-log options."""
        result = cli_runner.invoke(cli, ["refuel", "flight-plan", "--help"])

        assert result.exit_code == 0
        assert "--dry-run" in result.output
        assert "--list-steps" in result.output
        assert "--session-log" in result.output

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_flight_plan_path_with_spaces(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
    ) -> None:
        """Verify paths with spaces are handled correctly."""
        result = cli_runner.invoke(
            cli,
            ["refuel", "flight-plan", "sub dir/my plan.md"],
        )

        assert result.exit_code == 0
        assert result.exception is None
        mock_execute.assert_called_once()
        run_config = mock_execute.call_args[0][1]
        assert run_config.inputs["flight_plan_path"] == "sub dir/my plan.md"
