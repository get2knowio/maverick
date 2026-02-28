"""Unit tests for ``maverick flight-plan generate`` CLI subcommand."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from maverick.main import cli


class TestFlightPlanGenerateRegistered:
    """Test that generate subcommand is registered under flight-plan."""

    def test_generate_in_flight_plan_help(
        self,
        cli_runner: CliRunner,
    ) -> None:
        """'generate' subcommand appears in 'maverick flight-plan --help'."""
        result = cli_runner.invoke(cli, ["flight-plan", "--help"])
        assert result.exit_code == 0
        assert "generate" in result.output

    def test_generate_help_shows_options(
        self,
        cli_runner: CliRunner,
    ) -> None:
        """'maverick flight-plan generate --help' shows NAME and options."""
        result = cli_runner.invoke(cli, ["flight-plan", "generate", "--help"])
        assert result.exit_code == 0
        assert "--from-prd" in result.output
        assert "--output-dir" in result.output
        assert "--interactive" in result.output
        assert "--session-log" in result.output


class TestFlightPlanGenerateNameValidation:
    """Tests for kebab-case name validation."""

    @pytest.mark.parametrize(
        "invalid_name",
        [
            "My-Feature",
            "MY-PLAN",
            "my feature",
            "1-leading-digit",
            "my-feature-",
            "plan_v1",
        ],
    )
    def test_invalid_names_rejected(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
        invalid_name: str,
    ) -> None:
        """Invalid names are rejected with exit code 1."""
        result = cli_runner.invoke(
            cli,
            [
                "flight-plan",
                "generate",
                invalid_name,
                "--from-prd",
                "-",
            ],
            input="Some PRD content",
        )
        assert result.exit_code == 1

    def test_invalid_name_shows_error(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Invalid name produces an error message."""
        result = cli_runner.invoke(
            cli,
            ["flight-plan", "generate", "Bad Name", "--from-prd", "-"],
            input="PRD content",
        )
        assert result.exit_code == 1
        output_lower = result.output.lower()
        assert "invalid" in output_lower or "kebab" in output_lower


class TestFlightPlanGeneratePrdInput:
    """Tests for PRD input reading."""

    def test_missing_prd_file_exits_with_error(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Non-existent PRD file produces exit code 1."""
        result = cli_runner.invoke(
            cli,
            [
                "flight-plan",
                "generate",
                "my-plan",
                "--from-prd",
                "nonexistent.md",
            ],
        )
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_empty_stdin_prd_exits_with_error(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Empty STDIN PRD produces exit code 1."""
        result = cli_runner.invoke(
            cli,
            ["flight-plan", "generate", "my-plan", "--from-prd", "-"],
            input="",
        )
        assert result.exit_code == 1
        assert "empty" in result.output.lower()

    def test_empty_file_prd_exits_with_error(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Empty PRD file produces exit code 1."""
        prd_file = flight_plan_env / "empty.md"
        prd_file.write_text("", encoding="utf-8")
        result = cli_runner.invoke(
            cli,
            [
                "flight-plan",
                "generate",
                "my-plan",
                "--from-prd",
                str(prd_file),
            ],
        )
        assert result.exit_code == 1


class TestFlightPlanGenerateOverwriteGuard:
    """Tests for the overwrite protection mechanism."""

    def test_refuses_to_overwrite_existing_file(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Command refuses with exit code 1 if the target file already exists."""
        output_dir = flight_plan_env / ".maverick" / "flight-plans"
        output_dir.mkdir(parents=True)
        existing_file = output_dir / "my-plan.md"
        existing_file.write_text("existing content")

        result = cli_runner.invoke(
            cli,
            ["flight-plan", "generate", "my-plan", "--from-prd", "-"],
            input="Some PRD content",
        )
        assert result.exit_code == 1
        assert "exist" in result.output.lower() or "my-plan" in result.output.lower()

    def test_overwrite_guard_does_not_modify_existing_file(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Existing file content is not modified when overwrite is refused."""
        output_dir = flight_plan_env / ".maverick" / "flight-plans"
        output_dir.mkdir(parents=True)
        existing_file = output_dir / "my-plan.md"
        original = "original content that must not change"
        existing_file.write_text(original)

        cli_runner.invoke(
            cli,
            ["flight-plan", "generate", "my-plan", "--from-prd", "-"],
            input="Some PRD",
        )
        assert existing_file.read_text() == original


class TestFlightPlanGenerateOutputDir:
    """Tests for output directory handling."""

    def test_output_dir_is_file_exits_with_error(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """If --output-dir is an existing file, command fails with exit code 1."""
        file_not_dir = flight_plan_env / "not-a-dir"
        file_not_dir.write_text("I am a file")

        result = cli_runner.invoke(
            cli,
            [
                "flight-plan",
                "generate",
                "my-plan",
                "--from-prd",
                "-",
                "--output-dir",
                str(file_not_dir),
            ],
            input="PRD content",
        )
        assert result.exit_code == 1
