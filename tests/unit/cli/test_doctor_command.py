"""Unit tests for the ``maverick doctor`` CLI command."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from maverick.cli.commands.doctor import doctor
from maverick.library.actions.preflight import PreflightCheckResult
from maverick.runners.preflight import ValidationResult


def _make_other_result(*, success: bool, **kwargs: object) -> PreflightCheckResult:
    """Build a PreflightCheckResult for the non-provider checks."""
    return PreflightCheckResult(success=success, **kwargs)  # type: ignore[arg-type]


def _make_health_check(name: str, *, success: bool, errors: tuple[str, ...] = ()) -> Any:
    """Stand-in for ``AcpProviderHealthCheck`` — just needs ``provider_name``
    and an awaitable ``validate()``."""
    hc = MagicMock()
    hc.provider_name = name
    hc.validate = AsyncMock(
        return_value=ValidationResult(
            success=success,
            component=f"ACP:{name}",
            errors=errors,
            duration_ms=10,
        )
    )
    return hc


def test_help_lists_options() -> None:
    runner = CliRunner()
    result = runner.invoke(doctor, ["--help"])
    assert result.exit_code == 0
    assert "Validate the local environment" in result.output


def test_passes_when_all_checks_succeed() -> None:
    """All providers + non-provider checks green → exit 0."""
    runner = CliRunner()
    fake_config = MagicMock()
    health_checks = [
        _make_health_check("claude", success=True),
        _make_health_check("copilot", success=True),
    ]

    other = _make_other_result(success=True)
    with (
        patch.dict("os.environ", {"NO_COLOR": "1"}),
        patch(
            "maverick.cli.commands.doctor.build_provider_health_checks",
            return_value=health_checks,
        ),
        patch(
            "maverick.cli.commands.doctor.run_preflight_checks",
            new=AsyncMock(return_value=other),
        ),
    ):
        result = runner.invoke(doctor, [], obj={"config": fake_config})

    assert result.exit_code == 0
    assert "All checks passed" in result.output


def test_runs_every_provider_even_when_one_fails() -> None:
    """Failure in one provider must NOT short-circuit the others.

    All three validates should be awaited, and all three rows should
    appear in the post-run output.
    """
    runner = CliRunner()
    fake_config = MagicMock()
    hc_a = _make_health_check("claude", success=True)
    hc_b = _make_health_check(
        "gemini", success=False, errors=("Provider 'gemini' returned no content.",)
    )
    hc_c = _make_health_check("copilot", success=True)

    other = _make_other_result(success=True)
    with (
        patch.dict("os.environ", {"NO_COLOR": "1"}),
        patch(
            "maverick.cli.commands.doctor.build_provider_health_checks",
            return_value=[hc_a, hc_b, hc_c],
        ),
        patch(
            "maverick.cli.commands.doctor.run_preflight_checks",
            new=AsyncMock(return_value=other),
        ),
    ):
        result = runner.invoke(doctor, [], obj={"config": fake_config})

    # Every provider was actually invoked.
    hc_a.validate.assert_awaited_once()
    hc_b.validate.assert_awaited_once()
    hc_c.validate.assert_awaited_once()

    # The failure shows up in the issues section, not just the table.
    assert "gemini" in result.output
    assert "returned no content" in result.output
    # Exit code reflects the failure.
    assert result.exit_code != 0


def test_no_config_skips_provider_checks_gracefully() -> None:
    """Doctor invoked outside a maverick project (no config) shouldn't
    crash — it should print a hint and report on whatever else it can."""
    runner = CliRunner()
    other = _make_other_result(success=True)

    with (
        patch.dict("os.environ", {"NO_COLOR": "1"}),
        patch(
            "maverick.cli.commands.doctor.run_preflight_checks",
            new=AsyncMock(return_value=other),
        ),
    ):
        result = runner.invoke(doctor, [], obj={"config": None})

    assert result.exit_code == 0
    assert "skipping provider checks" in result.output
