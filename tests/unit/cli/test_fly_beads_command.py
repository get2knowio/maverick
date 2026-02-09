"""Unit tests for the ``maverick fly beads`` CLI command."""

from __future__ import annotations

from click.testing import CliRunner

from maverick.cli.commands.fly._group import fly


class TestFlyBeadsCommand:
    """Tests for the fly beads subcommand."""

    def test_help_shows_beads_subcommand(self) -> None:
        runner = CliRunner()
        result = runner.invoke(fly, ["beads", "--help"])
        assert result.exit_code == 0
        assert "bead-driven" in result.output.lower()

    def test_missing_epic_option_errors(self) -> None:
        runner = CliRunner()
        result = runner.invoke(fly, ["beads", "--branch", "test-branch"])
        assert result.exit_code != 0
        assert "epic" in result.output.lower() or "required" in result.output.lower()

    def test_missing_branch_option_errors(self) -> None:
        runner = CliRunner()
        result = runner.invoke(fly, ["beads", "--epic", "test-epic"])
        assert result.exit_code != 0
        assert "branch" in result.output.lower() or "required" in result.output.lower()

    def test_fly_group_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(fly, ["--help"])
        assert result.exit_code == 0
        assert "beads" in result.output


class TestFlyRunCommand:
    """Tests for the fly run subcommand."""

    def test_help_shows_run_subcommand(self) -> None:
        runner = CliRunner()
        result = runner.invoke(fly, ["run", "--help"])
        assert result.exit_code == 0
        assert "name_or_file" in result.output.lower()

    def test_fly_group_lists_run(self) -> None:
        runner = CliRunner()
        result = runner.invoke(fly, ["--help"])
        assert result.exit_code == 0
        assert "run" in result.output


class TestFlyGroupNoArgs:
    """Tests that 'maverick fly' without arguments shows help."""

    def test_fly_no_args_shows_help(self) -> None:
        """Fly with no args should show usage/help."""
        runner = CliRunner()
        result = runner.invoke(fly, [])
        assert result.exit_code == 0
        assert "beads" in result.output or "run" in result.output
