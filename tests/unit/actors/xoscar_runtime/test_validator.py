"""Tests for the xoscar ``ValidatorActor``.

Behavioural expectations port directly from the Thespian version — the
validator remains deterministic; only the message transport changes.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
import xoscar as xo

from maverick.actors.xoscar.messages import ValidateRequest, ValidationResult
from maverick.actors.xoscar.validator import ValidatorActor


def _flight_plan(sc_count: int = 2) -> SimpleNamespace:
    return SimpleNamespace(
        success_criteria=[SimpleNamespace(ref=f"SC-{i + 1:03d}") for i in range(sc_count)]
    )


@pytest.mark.asyncio
async def test_validator_returns_passed_for_valid_specs(pool_address: str) -> None:
    ref = await xo.create_actor(
        ValidatorActor,
        _flight_plan(sc_count=2),
        address=pool_address,
        uid="validator",
    )
    try:
        with patch(
            "maverick.library.actions.decompose.validate_decomposition",
            return_value=None,
        ):
            result = await ref.validate(ValidateRequest(specs=()))
        assert isinstance(result, ValidationResult)
        assert result.passed is True
        assert result.error_type is None
        assert result.gaps == ()
    finally:
        await xo.destroy_actor(ref)


@pytest.mark.asyncio
async def test_validator_reports_coverage_gaps(pool_address: str) -> None:
    from maverick.library.actions.decompose import SCCoverageError

    ref = await xo.create_actor(
        ValidatorActor,
        _flight_plan(sc_count=3),
        address=pool_address,
        uid="validator",
    )
    try:
        gaps = ["SC-001", "SC-003"]
        with patch(
            "maverick.library.actions.decompose.validate_decomposition",
            side_effect=SCCoverageError(gaps=gaps, message="coverage gap"),
        ):
            result = await ref.validate(ValidateRequest(specs=()))
        assert result.passed is False
        assert result.error_type == "coverage"
        assert result.gaps == tuple(gaps)
        assert "coverage gap" in result.message
    finally:
        await xo.destroy_actor(ref)


@pytest.mark.asyncio
async def test_validator_reports_other_errors(pool_address: str) -> None:
    ref = await xo.create_actor(
        ValidatorActor,
        _flight_plan(sc_count=1),
        address=pool_address,
        uid="validator",
    )
    try:
        with patch(
            "maverick.library.actions.decompose.validate_decomposition",
            side_effect=ValueError("boom"),
        ):
            result = await ref.validate(ValidateRequest(specs=()))
        assert result.passed is False
        assert result.error_type == "other"
        assert result.gaps == ()
        assert "boom" in result.message
    finally:
        await xo.destroy_actor(ref)
