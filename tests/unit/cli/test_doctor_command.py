"""Unit tests for the ``maverick doctor`` CLI command."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from maverick.cli.commands.doctor import doctor
from maverick.library.actions.preflight import PreflightCheckResult


def _make_result(*, success: bool, **kwargs: object) -> PreflightCheckResult:
    """Build a PreflightCheckResult for tests."""
    return PreflightCheckResult(success=success, **kwargs)  # type: ignore[arg-type]


def test_help_lists_options() -> None:
    runner = CliRunner()
    result = runner.invoke(doctor, ["--help"])
    assert result.exit_code == 0
    assert "providers-only" in result.output
    assert "Validate the local environment" in result.output


def test_passes_when_all_checks_succeed() -> None:
    """All green → exit 0, friendly summary line."""
    runner = CliRunner()
    success_result = _make_result(success=True)

    with patch(
        "maverick.library.actions.preflight.run_preflight_checks",
        new=AsyncMock(return_value=success_result),
    ):
        result = runner.invoke(doctor, [])

    assert result.exit_code == 0
    assert "All checks passed" in result.output
    assert "ACP providers" in result.output
    assert "git" in result.output


def test_fails_with_nonzero_exit_when_check_fails() -> None:
    """Any failed check → exit 1, errors enumerated."""
    runner = CliRunner()
    bad_result = _make_result(
        success=False,
        providers_available=False,
        errors=("Provider 'gemini' returned no content. Set GEMINI_API_KEY.",),
    )

    with patch(
        "maverick.library.actions.preflight.run_preflight_checks",
        new=AsyncMock(return_value=bad_result),
    ):
        result = runner.invoke(doctor, [])

    assert result.exit_code != 0
    assert "GEMINI_API_KEY" in result.output
    assert "One or more checks failed" in result.output


def test_providers_only_skips_other_checks() -> None:
    """``--providers-only`` should only print the ACP providers row."""
    runner = CliRunner()
    success_result = _make_result(success=True)
    captured_kwargs: dict[str, object] = {}

    async def fake_run(**kwargs: object) -> PreflightCheckResult:
        captured_kwargs.update(kwargs)
        return success_result

    with patch(
        "maverick.library.actions.preflight.run_preflight_checks",
        new=fake_run,
    ):
        result = runner.invoke(doctor, ["--providers-only"])

    assert result.exit_code == 0
    # check_providers stays on; the rest were turned off.
    assert captured_kwargs["check_providers"] is True
    assert captured_kwargs["check_git"] is False
    assert captured_kwargs["check_github"] is False
    assert captured_kwargs["check_bd"] is False
    assert captured_kwargs["check_jj"] is False
    # Output omits the rows for the skipped checks.
    assert "ACP providers" in result.output
    assert "GitHub CLI" not in result.output


def test_warnings_are_displayed() -> None:
    runner = CliRunner()
    result_with_warnings = _make_result(
        success=True,
        warnings=("optional tool 'jj' missing; some workflows degraded",),
    )

    with patch(
        "maverick.library.actions.preflight.run_preflight_checks",
        new=AsyncMock(return_value=result_with_warnings),
    ):
        result = runner.invoke(doctor, [])

    assert result.exit_code == 0
    assert "Warnings" in result.output
    assert "jj" in result.output
