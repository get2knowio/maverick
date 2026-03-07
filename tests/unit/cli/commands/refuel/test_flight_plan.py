"""Unit tests for ``maverick refuel`` CLI command (plan source)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from maverick.main import cli

_PATCH_EXECUTE = "maverick.cli.workflow_executor.execute_python_workflow"


class TestRefuelHelp:
    """Test refuel help and registration."""

    def test_refuel_in_top_level_help(
        self,
        cli_runner: CliRunner,
    ) -> None:
        result = cli_runner.invoke(cli, ["refuel", "--help"])
        assert result.exit_code == 0
        assert "--from" in result.output
        assert "plan" in result.output
        assert "speckit" in result.output

    def test_help_shows_correct_options(
        self,
        cli_runner: CliRunner,
    ) -> None:
        """Help text shows --dry-run, --list-steps, --session-log, --from options."""
        result = cli_runner.invoke(cli, ["refuel", "--help"])

        assert result.exit_code == 0
        assert "--dry-run" in result.output
        assert "--list-steps" in result.output
        assert "--session-log" in result.output
        assert "--from" in result.output
        assert "--skip-briefing" in result.output


class TestRefuelFromPlan:
    """Tests for 'maverick refuel <name>' (default --from plan)."""

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
            ["refuel", "my-feature", "--list-steps"],
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
            ["refuel", "my-feature"],
        )

        assert result.exit_code == 0
        assert result.exception is None
        mock_execute.assert_called_once()
        run_config = mock_execute.call_args[0][1]
        assert run_config.workflow_class is RefuelMaverickWorkflow

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_flight_plan_path_resolved_from_name(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
    ) -> None:
        """Plan name is resolved to .maverick/plans/<name>/flight-plan.md."""
        result = cli_runner.invoke(
            cli,
            ["refuel", "my-feature"],
        )

        assert result.exit_code == 0
        assert result.exception is None
        mock_execute.assert_called_once()
        run_config = mock_execute.call_args[0][1]
        assert "flight_plan_path" in run_config.inputs
        assert run_config.inputs["flight_plan_path"] == str(
            Path(".maverick/plans/my-feature/flight-plan.md")
        )

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_dry_run_flag_passed_to_workflow(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
    ) -> None:
        """--dry-run flag is passed as input to the workflow."""
        result = cli_runner.invoke(
            cli,
            ["refuel", "my-feature", "--dry-run"],
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
            ["refuel", "my-feature"],
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
            ["refuel", "my-feature", "--session-log", str(log_path)],
        )

        assert result.exit_code == 0
        assert result.exception is None
        mock_execute.assert_called_once()
        run_config = mock_execute.call_args[0][1]
        assert run_config.session_log_path == log_path

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_skip_briefing_passed_to_workflow(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
    ) -> None:
        """--skip-briefing flag is passed as input to the workflow."""
        result = cli_runner.invoke(
            cli,
            ["refuel", "my-feature", "--skip-briefing"],
        )

        assert result.exit_code == 0
        assert result.exception is None
        mock_execute.assert_called_once()
        run_config = mock_execute.call_args[0][1]
        assert run_config.inputs["skip_briefing"] is True


class TestRefuelFromSpeckit:
    """Tests for 'maverick refuel --from speckit <spec>'."""

    def test_list_steps_speckit(
        self,
        cli_runner: CliRunner,
    ) -> None:
        """--list-steps with --from speckit prints speckit workflow steps."""
        result = cli_runner.invoke(
            cli,
            ["refuel", "--from", "speckit", "001-greet-cli", "--list-steps"],
        )

        assert result.exit_code == 0
        assert "parse_spec" in result.output

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_delegates_to_refuel_speckit_workflow(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
    ) -> None:
        """--from speckit delegates to RefuelSpeckitWorkflow."""
        from maverick.workflows.refuel_speckit import RefuelSpeckitWorkflow

        result = cli_runner.invoke(
            cli,
            ["refuel", "--from", "speckit", "001-greet-cli"],
        )

        assert result.exit_code == 0
        assert result.exception is None
        mock_execute.assert_called_once()
        run_config = mock_execute.call_args[0][1]
        assert run_config.workflow_class is RefuelSpeckitWorkflow
        assert run_config.inputs["spec"] == "001-greet-cli"

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_speckit_dry_run(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
    ) -> None:
        """--dry-run with --from speckit is passed through."""
        result = cli_runner.invoke(
            cli,
            ["refuel", "--from", "speckit", "001-greet-cli", "--dry-run"],
        )

        assert result.exit_code == 0
        assert result.exception is None
        mock_execute.assert_called_once()
        run_config = mock_execute.call_args[0][1]
        assert run_config.inputs["dry_run"] is True
