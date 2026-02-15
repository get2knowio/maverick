"""Unit tests for the ``maverick land`` CLI command."""

from __future__ import annotations

from click.testing import CliRunner

from maverick.cli.commands.land import land


class TestLandCommand:
    """Tests for the land command (curate + push)."""

    def test_land_in_cli(self) -> None:
        """land command is registered and shows in help."""
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        assert result.exit_code == 0
        assert "curate" in result.output.lower()

    def test_land_help(self) -> None:
        """Help output shows all options."""
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        assert result.exit_code == 0
        assert "--no-curate" in result.output
        assert "--dry-run" in result.output
        assert "--yes" in result.output
        assert "--base" in result.output
        assert "--heuristic-only" in result.output

    def test_land_no_curate_option(self) -> None:
        """--no-curate is a recognized flag."""
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        assert result.exit_code == 0
        assert "--no-curate" in result.output
        assert "skip curation" in result.output.lower()

    def test_land_dry_run_option(self) -> None:
        """--dry-run is a recognized flag."""
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        assert result.exit_code == 0
        assert "--dry-run" in result.output

    def test_land_yes_option(self) -> None:
        """--yes / -y is a recognized flag."""
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        assert result.exit_code == 0
        assert "--yes" in result.output
        assert "-y" in result.output

    def test_land_base_option(self) -> None:
        """--base defaults to 'main'."""
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        assert result.exit_code == 0
        assert "--base" in result.output
        assert "main" in result.output  # default shown

    def test_land_heuristic_only_option(self) -> None:
        """--heuristic-only is a recognized flag."""
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        assert result.exit_code == 0
        assert "--heuristic-only" in result.output

    def test_land_is_command_not_group(self) -> None:
        """land should be a direct command, not a group with subcommands."""
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        assert result.exit_code == 0
        assert "Commands:" not in result.output
