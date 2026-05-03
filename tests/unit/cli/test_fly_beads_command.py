"""Unit tests for the ``maverick fly`` CLI command."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from maverick.cli.commands.fly._group import fly
from maverick.main import cli

# Patch target for the Python workflow execution
_PATCH_EXECUTE = "maverick.cli.commands.fly._group.execute_python_workflow"


class TestFlyCommand:
    """Tests for the fly command (bead-driven workflow)."""

    def test_help_shows_bead_driven_description(self) -> None:
        runner = CliRunner()
        result = runner.invoke(fly, ["--help"])
        assert result.exit_code == 0
        assert "bead-driven" in result.output.lower()

    def test_help_shows_epic_option(self) -> None:
        runner = CliRunner()
        result = runner.invoke(fly, ["--help"])
        assert result.exit_code == 0
        assert "--epic" in result.output

    def test_help_shows_max_beads_option(self) -> None:
        runner = CliRunner()
        result = runner.invoke(fly, ["--help"])
        assert result.exit_code == 0
        assert "--max-beads" in result.output

    def test_help_shows_list_steps_option(self) -> None:
        runner = CliRunner()
        result = runner.invoke(fly, ["--help"])
        assert result.exit_code == 0
        assert "--list-steps" in result.output

    def test_help_shows_session_log_option(self) -> None:
        runner = CliRunner()
        result = runner.invoke(fly, ["--help"])
        assert result.exit_code == 0
        assert "--session-log" in result.output

    def test_no_branch_option(self) -> None:
        """fly should NOT have a --branch option."""
        runner = CliRunner()
        result = runner.invoke(fly, ["--help"])
        assert result.exit_code == 0
        assert "--branch" not in result.output

    def test_epic_is_optional(self) -> None:
        """fly should work without --epic (it's optional)."""
        runner = CliRunner()
        result = runner.invoke(fly, ["--help"])
        assert result.exit_code == 0
        # --epic should not be marked as required
        # Click shows "[required]" for required options
        help_text = result.output
        epic_idx = help_text.find("--epic")
        assert epic_idx != -1
        # Check that "required" doesn't appear near --epic
        epic_section = help_text[epic_idx : epic_idx + 100]
        assert "required" not in epic_section.lower()

    def test_fly_is_command_not_group(self) -> None:
        """fly should be a direct command, not a group with subcommands."""
        runner = CliRunner()
        result = runner.invoke(fly, ["--help"])
        assert result.exit_code == 0
        # Should NOT show subcommands like "beads" or "run"
        assert "beads" not in result.output.lower().split("options")[0]
        assert "Commands:" not in result.output


class TestFlyCommandDelegation:
    """Tests that fly CLI delegates to the correct Python workflow."""

    @pytest.fixture(autouse=True)
    def _mock_bd_ready(self):
        """Skip the bd-on-PATH + .beads-initialized preflight — these
        tests verify the CLI's delegation surface, not its preflight."""
        with (
            patch("shutil.which", return_value="/usr/bin/bd"),
            patch(
                "maverick.beads.client.BeadClient.is_initialized",
                return_value=True,
            ),
        ):
            yield

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_delegates_to_python_workflow(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
        maverick_yaml: Path,
    ) -> None:
        """fly command delegates to execute_python_workflow with FlyBeadsWorkflow."""
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        cli_runner.invoke(cli, ["fly"])

        mock_execute.assert_called_once()
        # First positional arg is the click context; second is PythonWorkflowRunConfig
        call_args = mock_execute.call_args
        run_config = call_args[0][1]
        from maverick.workflows.fly_beads import FlyBeadsWorkflow

        assert run_config.workflow_class is FlyBeadsWorkflow
