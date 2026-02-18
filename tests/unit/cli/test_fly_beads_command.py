"""Unit tests for the ``maverick fly`` CLI command."""

from __future__ import annotations

from click.testing import CliRunner

from maverick.cli.commands.fly._group import fly


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

    def test_help_shows_dry_run_option(self) -> None:
        runner = CliRunner()
        result = runner.invoke(fly, ["--help"])
        assert result.exit_code == 0
        assert "--dry-run" in result.output

    def test_help_shows_skip_review_option(self) -> None:
        runner = CliRunner()
        result = runner.invoke(fly, ["--help"])
        assert result.exit_code == 0
        assert "--skip-review" in result.output

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
