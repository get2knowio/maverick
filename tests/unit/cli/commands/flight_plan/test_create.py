"""Unit tests for ``maverick plan create`` CLI subcommand."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from maverick.main import cli


class TestFlightPlanCreateRegistered:
    """Test that create subcommand is registered under plan."""

    def test_create_in_flight_plan_help(
        self,
        cli_runner: CliRunner,
    ) -> None:
        """'create' subcommand appears in 'maverick plan --help'."""
        result = cli_runner.invoke(cli, ["plan", "--help"])
        assert result.exit_code == 0
        assert "create" in result.output

    def test_create_help_shows_options(
        self,
        cli_runner: CliRunner,
    ) -> None:
        """'maverick plan create --help' shows NAME argument and options."""
        result = cli_runner.invoke(cli, ["plan", "create", "--help"])
        assert result.exit_code == 0
        assert "--plans-dir" in result.output


class TestFlightPlanCreateHappyPath:
    """Tests for successful file creation."""

    def test_creates_file_in_default_output_dir(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Command creates a .md file in the default .maverick/plans/ dir."""
        result = cli_runner.invoke(cli, ["plan", "create", "my-feature"])

        assert result.exit_code == 0, f"Unexpected exit: {result.output}"
        expected_file = flight_plan_env / ".maverick" / "plans" / "my-feature" / "flight-plan.md"
        assert expected_file.exists(), f"Expected file not found: {expected_file}"

    def test_created_file_contains_name_in_frontmatter(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """The created file's YAML frontmatter contains the correct name."""
        import yaml

        cli_runner.invoke(cli, ["plan", "create", "my-feature"])

        file_path = flight_plan_env / ".maverick" / "plans" / "my-feature" / "flight-plan.md"
        content = file_path.read_text()
        parts = content.split("---", 2)
        fm = yaml.safe_load(parts[1])
        assert fm["name"] == "my-feature"

    def test_created_file_has_required_sections(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """The created file contains all required Markdown sections."""
        cli_runner.invoke(cli, ["plan", "create", "my-feature"])

        file_path = flight_plan_env / ".maverick" / "plans" / "my-feature" / "flight-plan.md"
        content = file_path.read_text()
        assert "## Objective" in content
        assert "## Success Criteria" in content
        assert "## Scope" in content
        assert "### In" in content
        assert "### Out" in content
        assert "### Boundaries" in content
        assert "## Context" in content
        assert "## Constraints" in content
        assert "## Notes" in content

    def test_output_shows_success_message(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Command prints a success message on successful creation."""
        result = cli_runner.invoke(cli, ["plan", "create", "my-feature"])

        assert result.exit_code == 0
        # Should mention the file was created
        assert "my-feature" in result.output

    def test_custom_output_dir_creates_file_there(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """With --plans-dir, file is created in the specified directory."""
        custom_dir = flight_plan_env / "custom" / "plans"
        result = cli_runner.invoke(
            cli,
            ["plan", "create", "my-feature", "--plans-dir", str(custom_dir)],
        )

        assert result.exit_code == 0, f"Unexpected exit: {result.output}"
        expected_file = custom_dir / "my-feature" / "flight-plan.md"
        assert expected_file.exists(), f"Expected file not found: {expected_file}"

    def test_custom_output_dir_file_content(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """File created in custom dir has correct content."""
        import yaml

        custom_dir = flight_plan_env / "plans"
        cli_runner.invoke(
            cli,
            ["plan", "create", "api-setup", "--plans-dir", str(custom_dir)],
        )

        file_path = custom_dir / "api-setup" / "flight-plan.md"
        content = file_path.read_text()
        parts = content.split("---", 2)
        fm = yaml.safe_load(parts[1])
        assert fm["name"] == "api-setup"


class TestFlightPlanCreateDirectoryCreation:
    """Tests for automatic directory creation."""

    def test_auto_creates_default_output_dir(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Default output directory is created if it doesn't exist."""
        default_dir = flight_plan_env / ".maverick" / "plans"
        assert not default_dir.exists(), "Directory should not exist before command"

        result = cli_runner.invoke(cli, ["plan", "create", "my-plan"])

        assert result.exit_code == 0
        assert default_dir.exists()

    def test_auto_creates_nested_output_dir(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Nested custom output directory is auto-created including parents."""
        nested_dir = flight_plan_env / "a" / "b" / "c" / "plans"
        assert not nested_dir.exists()

        result = cli_runner.invoke(
            cli,
            ["plan", "create", "my-plan", "--plans-dir", str(nested_dir)],
        )

        assert result.exit_code == 0, f"Unexpected exit: {result.output}"
        assert nested_dir.exists()
        assert (nested_dir / "my-plan" / "flight-plan.md").exists()

    def test_existing_output_dir_is_ok(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Command succeeds if the output directory already exists."""
        existing_dir = flight_plan_env / "plans"
        existing_dir.mkdir(parents=True)

        result = cli_runner.invoke(
            cli,
            ["plan", "create", "my-plan", "--plans-dir", str(existing_dir)],
        )

        assert result.exit_code == 0


class TestFlightPlanCreateOverwriteGuard:
    """Tests for the overwrite protection mechanism."""

    def test_refuses_to_overwrite_existing_file(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Command refuses with exit code 1 if the target file already exists."""
        # Create the file first
        output_dir = flight_plan_env / ".maverick" / "plans" / "my-feature"
        output_dir.mkdir(parents=True)
        existing_file = output_dir / "flight-plan.md"
        existing_file.write_text("existing content")

        result = cli_runner.invoke(cli, ["plan", "create", "my-feature"])

        assert result.exit_code == 1

    def test_overwrite_guard_shows_error_message(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Error message is shown when file already exists."""
        output_dir = flight_plan_env / ".maverick" / "plans" / "my-feature"
        output_dir.mkdir(parents=True)
        existing_file = output_dir / "flight-plan.md"
        existing_file.write_text("existing content")

        result = cli_runner.invoke(cli, ["plan", "create", "my-feature"])

        assert result.exit_code == 1
        # Should mention the file already exists or similar
        assert "my-feature" in result.output.lower() or "exist" in result.output.lower()

    def test_overwrite_guard_does_not_modify_existing_file(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Existing file content is not modified when overwrite is refused."""
        output_dir = flight_plan_env / ".maverick" / "plans" / "my-feature"
        output_dir.mkdir(parents=True)
        existing_file = output_dir / "flight-plan.md"
        original_content = "original content that must not change"
        existing_file.write_text(original_content)

        cli_runner.invoke(cli, ["plan", "create", "my-feature"])

        assert existing_file.read_text() == original_content

    def test_custom_dir_overwrite_guard(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Overwrite guard also applies when --plans-dir is specified."""
        custom_dir = flight_plan_env / "plans"
        custom_dir.mkdir(parents=True)
        existing_file = custom_dir / "my-plan" / "flight-plan.md"
        (custom_dir / "my-plan").mkdir(parents=True)
        existing_file.write_text("existing")

        result = cli_runner.invoke(
            cli,
            ["plan", "create", "my-plan", "--plans-dir", str(custom_dir)],
        )

        assert result.exit_code == 1


class TestFlightPlanCreateNameValidation:
    """Tests for kebab-case name validation."""

    @pytest.mark.parametrize(
        "valid_name",
        [
            "my-feature",
            "api",
            "setup-auth-flow",
            "a",
            "abc123",
            "my-feature-v2",
            "x1",
            "my--feature",  # consecutive hyphens are intentionally allowed by the regex
        ],
    )
    def test_valid_kebab_case_names_accepted(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
        valid_name: str,
    ) -> None:
        """Valid kebab-case names are accepted without error."""
        result = cli_runner.invoke(cli, ["plan", "create", valid_name])
        assert result.exit_code == 0, (
            f"Expected success for name '{valid_name}', got: {result.output}"
        )

    @pytest.mark.parametrize(
        "invalid_name",
        [
            "My-Feature",  # uppercase letter
            "MY-PLAN",  # all uppercase
            "my feature",  # space
            "1-leading-digit",  # leading digit
            "my-feature-",  # trailing hyphen
            "my/feature",  # slash
            "plan_v1",  # underscore
            "café",  # unicode
        ],
    )
    def test_invalid_names_rejected_with_exit_code_1(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
        invalid_name: str,
    ) -> None:
        """Invalid names are rejected with exit code 1."""
        result = cli_runner.invoke(cli, ["plan", "create", invalid_name])
        assert result.exit_code == 1, (
            f"Expected failure for name '{invalid_name}', "
            f"got exit={result.exit_code}: {result.output}"
        )

    def test_leading_hyphen_name_rejected(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Name starting with a hyphen is rejected (non-zero exit code)."""
        # Pass '--' to separate options from the positional argument so Click
        # doesn't parse the leading hyphen as an option flag.
        result = cli_runner.invoke(cli, ["plan", "create", "--", "-starts-with-hyphen"])
        assert result.exit_code != 0, (
            f"Expected failure for name '-starts-with-hyphen', got exit=0: {result.output}"
        )

    def test_invalid_name_shows_error_message(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Invalid name produces an informative error message."""
        result = cli_runner.invoke(cli, ["plan", "create", "Invalid Name"])

        assert result.exit_code == 1
        # Should mention the name or kebab-case requirement
        output_lower = result.output.lower()
        assert "invalid" in output_lower or "kebab" in output_lower or "name" in output_lower

    def test_invalid_name_does_not_create_file(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """An invalid name does not create any file."""
        cli_runner.invoke(cli, ["plan", "create", "Bad Name!"])

        default_dir = flight_plan_env / ".maverick" / "plans"
        if default_dir.exists():
            files = list(default_dir.glob("*/flight-plan.md"))
            assert len(files) == 0, "No files should be created for invalid names"


class TestFlightPlanCreateOutputDirIsFile:
    """Tests for when --plans-dir points to an existing file (not a directory)."""

    def test_output_dir_is_file_exits_with_code_1(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """If --plans-dir is an existing file, command fails with exit code 1."""
        # Create a regular file where a directory is expected
        file_not_dir = flight_plan_env / "not-a-dir"
        file_not_dir.write_text("I am a file, not a directory")

        result = cli_runner.invoke(
            cli,
            ["plan", "create", "my-plan", "--plans-dir", str(file_not_dir)],
        )

        assert result.exit_code == 1

    def test_output_dir_is_file_shows_error(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """If --plans-dir is a file, error message is shown."""
        file_not_dir = flight_plan_env / "not-a-dir"
        file_not_dir.write_text("I am a file")

        result = cli_runner.invoke(
            cli,
            ["plan", "create", "my-plan", "--plans-dir", str(file_not_dir)],
        )

        assert result.exit_code == 1
        # Should mention the path or the issue
        assert (
            str(file_not_dir) in result.output
            or "not a directory" in result.output.lower()
            or "exist" in result.output.lower()
        )
