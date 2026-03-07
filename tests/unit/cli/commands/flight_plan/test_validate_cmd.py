"""Unit tests for ``maverick plan validate`` CLI subcommand.

T009: Write tests for validate subcommand (TDD -- written before T011 implementation).
Tests must FAIL before T011 implementation.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from click.testing import CliRunner

from maverick.main import cli

from .conftest import VALID_FLIGHT_PLAN_CONTENT

# ---------------------------------------------------------------------------
# Helper -- invalid content (no name field)
# ---------------------------------------------------------------------------

_INVALID_CONTENT_NO_NAME = """\
---
version: "1.0"
created: 2026-02-28
---

## Objective

Text.

## Success Criteria

- [ ] Criterion one

## Scope

### In

- In scope item
"""


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


class TestValidateSubcommandRegistered:
    """validate subcommand is registered under flight-plan."""

    def test_validate_in_flight_plan_help(self, cli_runner: CliRunner) -> None:
        """'validate' appears in 'maverick plan --help' output."""
        result = cli_runner.invoke(cli, ["plan", "--help"])
        assert result.exit_code == 0
        assert "validate" in result.output

    def test_validate_help_shows_file_path_argument(
        self, cli_runner: CliRunner
    ) -> None:
        """'maverick plan validate --help' shows FILE_PATH argument."""
        result = cli_runner.invoke(cli, ["plan", "validate", "--help"])
        assert result.exit_code == 0
        # The argument should appear in the help text
        assert "FILE_PATH" in result.output or "file" in result.output.lower()


# ---------------------------------------------------------------------------
# Happy path -- valid file
# ---------------------------------------------------------------------------


class TestValidateHappyPath:
    """Valid file exits with code 0 and prints success message."""

    def test_valid_file_exits_zero(
        self,
        cli_runner: CliRunner,
        write_flight_plan: Callable[..., Path],
    ) -> None:
        """validate exits 0 for a valid flight plan file."""
        path = write_flight_plan(VALID_FLIGHT_PLAN_CONTENT)
        result = cli_runner.invoke(cli, ["plan", "validate", str(path)])
        assert result.exit_code == 0, (
            f"Expected 0, got {result.exit_code}. Output: {result.output}"
        )

    def test_valid_file_prints_success_message(
        self,
        cli_runner: CliRunner,
        write_flight_plan: Callable[..., Path],
    ) -> None:
        """validate prints a success-like message for a valid flight plan."""
        path = write_flight_plan(VALID_FLIGHT_PLAN_CONTENT)
        result = cli_runner.invoke(cli, ["plan", "validate", str(path)])
        # Should contain something indicating success
        assert any(
            word in result.output.lower()
            for word in ("valid", "ok", "passed", "success", "no issue")
        ), f"Expected success message, got: {result.output!r}"


# ---------------------------------------------------------------------------
# Validation failures -- exit code 1, issue list
# ---------------------------------------------------------------------------


class TestValidateFailures:
    """Validation failures exit with code 1 and print issues."""

    def test_invalid_file_exits_one(
        self,
        cli_runner: CliRunner,
        write_flight_plan: Callable[..., Path],
    ) -> None:
        """validate exits 1 when the file has validation issues."""
        path = write_flight_plan(_INVALID_CONTENT_NO_NAME)
        result = cli_runner.invoke(cli, ["plan", "validate", str(path)])
        assert result.exit_code == 1, (
            f"Expected 1, got {result.exit_code}. Output: {result.output}"
        )

    def test_invalid_file_prints_issues(
        self,
        cli_runner: CliRunner,
        write_flight_plan: Callable[..., Path],
    ) -> None:
        """validate prints a list of issues for an invalid flight plan."""
        path = write_flight_plan(_INVALID_CONTENT_NO_NAME)
        result = cli_runner.invoke(cli, ["plan", "validate", str(path)])
        # Output should contain some reference to the issue (name field)
        assert "name" in result.output.lower() or "V4" in result.output, (
            f"Expected issue mentioning 'name', got: {result.output!r}"
        )

    def test_issue_location_shown_in_output(
        self,
        cli_runner: CliRunner,
        write_flight_plan: Callable[..., Path],
    ) -> None:
        """Each issue's location field appears in the validate output."""
        path = write_flight_plan(_INVALID_CONTENT_NO_NAME)
        result = cli_runner.invoke(cli, ["plan", "validate", str(path)])
        # The location should appear somewhere in the output
        # (validator uses "frontmatter.name" or similar)
        out_lower = result.output.lower()
        in_output = "frontmatter" in out_lower or "name" in out_lower
        assert in_output, f"Expected location in output, got: {result.output!r}"

    def test_missing_objective_shown_in_output(
        self,
        cli_runner: CliRunner,
        write_flight_plan: Callable[..., Path],
    ) -> None:
        """Missing ## Objective section causes issue to appear in output."""
        content = VALID_FLIGHT_PLAN_CONTENT.replace(
            "## Objective\n\nThis is the objective text.\n", ""
        )
        path = write_flight_plan(content)
        result = cli_runner.invoke(cli, ["plan", "validate", str(path)])
        assert result.exit_code == 1
        assert "objective" in result.output.lower(), (
            f"Expected 'objective' in output, got: {result.output!r}"
        )

    def test_missing_scope_shown_in_output(
        self,
        cli_runner: CliRunner,
        write_flight_plan: Callable[..., Path],
    ) -> None:
        """Missing ## Scope section causes issue to appear in output."""
        content = VALID_FLIGHT_PLAN_CONTENT.split("## Scope")[0]
        path = write_flight_plan(content)
        result = cli_runner.invoke(cli, ["plan", "validate", str(path)])
        assert result.exit_code == 1
        assert "scope" in result.output.lower(), (
            f"Expected 'scope' in output, got: {result.output!r}"
        )

    def test_multiple_issues_all_shown(
        self,
        cli_runner: CliRunner,
        write_flight_plan: Callable[..., Path],
    ) -> None:
        """When multiple issues exist, all are shown in output."""
        # Remove name AND objective
        content = _INVALID_CONTENT_NO_NAME.replace("## Objective\n\nText.\n", "")
        path = write_flight_plan(content)
        result = cli_runner.invoke(cli, ["plan", "validate", str(path)])
        assert result.exit_code == 1
        # Both name-related and objective-related issues should appear
        assert "name" in result.output.lower() or "V4" in result.output
        assert "objective" in result.output.lower()


# ---------------------------------------------------------------------------
# File-not-found error
# ---------------------------------------------------------------------------


class TestValidateFileNotFound:
    """Non-existent file path prints error and exits with code 1."""

    def test_missing_file_exits_one(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """validate exits 1 when given a non-existent file path."""
        missing = tmp_path / "does-not-exist.md"
        result = cli_runner.invoke(cli, ["plan", "validate", str(missing)])
        assert result.exit_code == 1, (
            f"Expected 1, got {result.exit_code}. Output: {result.output}"
        )

    def test_missing_file_prints_error_message(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """validate prints an error message when given a non-existent file path."""
        missing = tmp_path / "does-not-exist.md"
        result = cli_runner.invoke(cli, ["plan", "validate", str(missing)])
        assert any(
            word in result.output.lower()
            for word in ("not found", "does not exist", "no such file", "error")
        ), f"Expected error message, got: {result.output!r}"

    def test_missing_file_output_contains_path(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """validate error output includes (part of) the missing file path."""
        missing = tmp_path / "does-not-exist.md"
        result = cli_runner.invoke(cli, ["plan", "validate", str(missing)])
        # Rich may wrap long paths across lines, so join output lines and check
        # for the filename stem which is short enough not to be split.
        joined = "".join(result.output.splitlines())
        assert "does-not-exist" in joined or "does-not-exist.md" in result.output, (
            f"Expected file path in output, got: {result.output!r}"
        )
