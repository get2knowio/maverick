"""Unit tests for ``maverick plan validate`` CLI subcommand.

T009: Write tests for validate subcommand (TDD -- written before T011 implementation).
Tests must FAIL before T011 implementation.
"""

from __future__ import annotations

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


def _write_plan(
    base: Path,
    name: str,
    content: str,
) -> None:
    """Write content into the plans directory structure for the given name."""
    plan_dir = base / ".maverick" / "plans" / name
    plan_dir.mkdir(parents=True, exist_ok=True)
    (plan_dir / "flight-plan.md").write_text(content, encoding="utf-8")


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

    def test_validate_help_shows_name_argument(self, cli_runner: CliRunner) -> None:
        """'maverick plan validate --help' shows NAME argument."""
        result = cli_runner.invoke(cli, ["plan", "validate", "--help"])
        assert result.exit_code == 0
        assert "NAME" in result.output


# ---------------------------------------------------------------------------
# Happy path -- valid file
# ---------------------------------------------------------------------------


class TestValidateHappyPath:
    """Valid file exits with code 0 and prints success message."""

    def test_valid_file_exits_zero(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """validate exits 0 for a valid flight plan file."""
        _write_plan(flight_plan_env, "test-plan", VALID_FLIGHT_PLAN_CONTENT)
        result = cli_runner.invoke(cli, ["plan", "validate", "test-plan"])
        assert result.exit_code == 0, (
            f"Expected 0, got {result.exit_code}. Output: {result.output}"
        )

    def test_valid_file_prints_success_message(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """validate prints a success-like message for a valid flight plan."""
        _write_plan(flight_plan_env, "test-plan", VALID_FLIGHT_PLAN_CONTENT)
        result = cli_runner.invoke(cli, ["plan", "validate", "test-plan"])
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
        flight_plan_env: Path,
    ) -> None:
        """validate exits 1 when the file has validation issues."""
        _write_plan(flight_plan_env, "bad-plan", _INVALID_CONTENT_NO_NAME)
        result = cli_runner.invoke(cli, ["plan", "validate", "bad-plan"])
        assert result.exit_code == 1, (
            f"Expected 1, got {result.exit_code}. Output: {result.output}"
        )

    def test_invalid_file_prints_issues(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """validate prints a list of issues for an invalid flight plan."""
        _write_plan(flight_plan_env, "bad-plan", _INVALID_CONTENT_NO_NAME)
        result = cli_runner.invoke(cli, ["plan", "validate", "bad-plan"])
        # Output should contain some reference to the issue (name field)
        assert "name" in result.output.lower() or "V4" in result.output, (
            f"Expected issue mentioning 'name', got: {result.output!r}"
        )

    def test_issue_location_shown_in_output(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Each issue's location field appears in the validate output."""
        _write_plan(flight_plan_env, "bad-plan", _INVALID_CONTENT_NO_NAME)
        result = cli_runner.invoke(cli, ["plan", "validate", "bad-plan"])
        # The location should appear somewhere in the output
        # (validator uses "frontmatter.name" or similar)
        out_lower = result.output.lower()
        in_output = "frontmatter" in out_lower or "name" in out_lower
        assert in_output, f"Expected location in output, got: {result.output!r}"

    def test_missing_objective_shown_in_output(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Missing ## Objective section causes issue to appear in output."""
        content = VALID_FLIGHT_PLAN_CONTENT.replace(
            "## Objective\n\nThis is the objective text.\n", ""
        )
        _write_plan(flight_plan_env, "no-obj", content)
        result = cli_runner.invoke(cli, ["plan", "validate", "no-obj"])
        assert result.exit_code == 1
        assert "objective" in result.output.lower(), (
            f"Expected 'objective' in output, got: {result.output!r}"
        )

    def test_missing_scope_shown_in_output(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """Missing ## Scope section causes issue to appear in output."""
        content = VALID_FLIGHT_PLAN_CONTENT.split("## Scope")[0]
        _write_plan(flight_plan_env, "no-scope", content)
        result = cli_runner.invoke(cli, ["plan", "validate", "no-scope"])
        assert result.exit_code == 1
        assert "scope" in result.output.lower(), (
            f"Expected 'scope' in output, got: {result.output!r}"
        )

    def test_multiple_issues_all_shown(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """When multiple issues exist, all are shown in output."""
        # Remove name AND objective
        content = _INVALID_CONTENT_NO_NAME.replace("## Objective\n\nText.\n", "")
        _write_plan(flight_plan_env, "multi-bad", content)
        result = cli_runner.invoke(cli, ["plan", "validate", "multi-bad"])
        assert result.exit_code == 1
        # Both name-related and objective-related issues should appear
        assert "name" in result.output.lower() or "V4" in result.output
        assert "objective" in result.output.lower()


# ---------------------------------------------------------------------------
# File-not-found error
# ---------------------------------------------------------------------------


class TestValidateFileNotFound:
    """Non-existent plan name prints error and exits with code 1."""

    def test_missing_file_exits_one(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """validate exits 1 when given a non-existent plan name."""
        result = cli_runner.invoke(cli, ["plan", "validate", "does-not-exist"])
        assert result.exit_code == 1, (
            f"Expected 1, got {result.exit_code}. Output: {result.output}"
        )

    def test_missing_file_prints_error_message(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """validate prints an error message for a non-existent plan name."""
        result = cli_runner.invoke(cli, ["plan", "validate", "does-not-exist"])
        assert any(
            word in result.output.lower()
            for word in ("not found", "does not exist", "no such file", "error")
        ), f"Expected error message, got: {result.output!r}"

    def test_missing_file_output_contains_path(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """validate error output includes the plan name in the path."""
        result = cli_runner.invoke(cli, ["plan", "validate", "does-not-exist"])
        joined = "".join(result.output.splitlines())
        assert "does-not-exist" in joined, (
            f"Expected plan name in output, got: {result.output!r}"
        )

    def test_custom_plans_dir(
        self,
        cli_runner: CliRunner,
        flight_plan_env: Path,
    ) -> None:
        """validate with --plans-dir resolves from the custom directory."""
        custom = flight_plan_env / "custom-plans"
        plan_dir = custom / "my-plan"
        plan_dir.mkdir(parents=True)
        (plan_dir / "flight-plan.md").write_text(
            VALID_FLIGHT_PLAN_CONTENT, encoding="utf-8"
        )
        result = cli_runner.invoke(
            cli,
            ["plan", "validate", "my-plan", "--plans-dir", str(custom)],
        )
        assert result.exit_code == 0, (
            f"Expected 0, got {result.exit_code}. Output: {result.output}"
        )
