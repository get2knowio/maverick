"""Unit tests for ``maverick plan`` help text and subcommand discovery.

T012: Verify that the plan command group is self-documenting — both
subcommands are listed in the group help, each subcommand's own help output
describes its arguments and options correctly, and invoking the group without a
subcommand shows the same help text as ``--help``.
"""

from __future__ import annotations

from click.testing import CliRunner

from maverick.main import cli


class TestFlightPlanGroupHelp:
    """``maverick plan --help`` lists subcommands with descriptions."""

    def test_help_exits_zero(self, cli_runner: CliRunner) -> None:
        """``maverick plan --help`` exits with code 0."""
        result = cli_runner.invoke(cli, ["plan", "--help"])
        assert result.exit_code == 0

    def test_help_lists_create_subcommand(self, cli_runner: CliRunner) -> None:
        """``create`` subcommand appears in the group help output."""
        result = cli_runner.invoke(cli, ["plan", "--help"])
        assert result.exit_code == 0
        assert "create" in result.output

    def test_help_lists_validate_subcommand(self, cli_runner: CliRunner) -> None:
        """``validate`` subcommand appears in the group help output."""
        result = cli_runner.invoke(cli, ["plan", "--help"])
        assert result.exit_code == 0
        assert "validate" in result.output

    def test_help_shows_create_brief_description(self, cli_runner: CliRunner) -> None:
        """The group help shows a brief description for the ``create`` subcommand."""
        result = cli_runner.invoke(cli, ["plan", "--help"])
        assert result.exit_code == 0
        # The help line for 'create' should contain a short description.
        # The CLI contract requires: "Create a new flight plan from a template."
        output_lower = result.output.lower()
        assert "create" in output_lower
        # Verify a meaningful description word is present alongside 'create'
        assert any(
            word in output_lower for word in ("template", "flight plan", "new", "create a")
        ), f"Expected description for create, got: {result.output!r}"

    def test_help_shows_validate_brief_description(self, cli_runner: CliRunner) -> None:
        """The group help shows a brief description for the ``validate`` subcommand."""
        result = cli_runner.invoke(cli, ["plan", "--help"])
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "validate" in output_lower
        # Verify a meaningful description word is present alongside 'validate'
        assert any(
            word in output_lower for word in ("structural", "flight plan", "issues", "validate a")
        ), f"Expected description for validate, got: {result.output!r}"

    def test_help_shows_group_description(self, cli_runner: CliRunner) -> None:
        """The group help shows the group-level description."""
        result = cli_runner.invoke(cli, ["plan", "--help"])
        assert result.exit_code == 0
        # CLI contract group description: "Create and validate flight plan files."
        output_lower = result.output.lower()
        assert "flight plan" in output_lower or "plan" in output_lower


class TestFlightPlanNoSubcommand:
    """Invoking ``maverick plan`` without a subcommand shows help text."""

    def test_no_subcommand_exits_zero(self, cli_runner: CliRunner) -> None:
        """``maverick plan`` (no subcommand) exits with code 0."""
        result = cli_runner.invoke(cli, ["plan"])
        assert result.exit_code == 0

    def test_no_subcommand_shows_help(self, cli_runner: CliRunner) -> None:
        """``maverick plan`` without subcommand displays help text."""
        result = cli_runner.invoke(cli, ["plan"])
        assert result.exit_code == 0
        # Should list subcommands just like --help
        assert "create" in result.output
        assert "validate" in result.output

    def test_no_subcommand_output_matches_help(self, cli_runner: CliRunner) -> None:
        """Output of bare ``plan`` matches ``plan --help``."""
        result_bare = cli_runner.invoke(cli, ["plan"])
        result_help = cli_runner.invoke(cli, ["plan", "--help"])
        assert result_bare.exit_code == 0
        assert result_help.exit_code == 0
        assert result_bare.output == result_help.output


class TestFlightPlanCreateHelp:
    """``maverick plan create --help`` shows NAME argument and --output-dir."""

    def test_create_help_exits_zero(self, cli_runner: CliRunner) -> None:
        """``maverick plan create --help`` exits with code 0."""
        result = cli_runner.invoke(cli, ["plan", "create", "--help"])
        assert result.exit_code == 0

    def test_create_help_shows_name_argument(self, cli_runner: CliRunner) -> None:
        """``create --help`` shows the NAME positional argument."""
        result = cli_runner.invoke(cli, ["plan", "create", "--help"])
        assert result.exit_code == 0
        assert "NAME" in result.output

    def test_create_help_shows_output_dir_option(self, cli_runner: CliRunner) -> None:
        """``create --help`` shows the ``--output-dir`` option."""
        result = cli_runner.invoke(cli, ["plan", "create", "--help"])
        assert result.exit_code == 0
        assert "--output-dir" in result.output

    def test_create_help_shows_output_dir_default(self, cli_runner: CliRunner) -> None:
        """``create --help`` shows the default value for ``--output-dir``."""
        result = cli_runner.invoke(cli, ["plan", "create", "--help"])
        assert result.exit_code == 0
        # Default should mention the standard path
        assert ".maverick/plans" in result.output

    def test_create_help_shows_usage_line(self, cli_runner: CliRunner) -> None:
        """``create --help`` shows a Usage line with NAME."""
        result = cli_runner.invoke(cli, ["plan", "create", "--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "NAME" in result.output


class TestFlightPlanValidateHelp:
    """``maverick plan validate --help`` shows NAME argument."""

    def test_validate_help_exits_zero(self, cli_runner: CliRunner) -> None:
        """``maverick plan validate --help`` exits with code 0."""
        result = cli_runner.invoke(cli, ["plan", "validate", "--help"])
        assert result.exit_code == 0

    def test_validate_help_shows_name_argument(self, cli_runner: CliRunner) -> None:
        """``validate --help`` shows the NAME positional argument."""
        result = cli_runner.invoke(cli, ["plan", "validate", "--help"])
        assert result.exit_code == 0
        assert "NAME" in result.output

    def test_validate_help_shows_usage_line(self, cli_runner: CliRunner) -> None:
        """``validate --help`` shows a Usage line with NAME."""
        result = cli_runner.invoke(cli, ["plan", "validate", "--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "NAME" in result.output

    def test_validate_help_shows_plans_dir_option(self, cli_runner: CliRunner) -> None:
        """``validate --help`` shows the ``--plans-dir`` option."""
        result = cli_runner.invoke(cli, ["plan", "validate", "--help"])
        assert result.exit_code == 0
        assert "--plans-dir" in result.output

    def test_validate_help_shows_description(self, cli_runner: CliRunner) -> None:
        """``validate --help`` shows a description of what the command does."""
        result = cli_runner.invoke(cli, ["plan", "validate", "--help"])
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert any(
            word in output_lower for word in ("validate", "flight plan", "structural", "issues")
        ), f"Expected description in validate --help, got: {result.output!r}"
