"""Tests for ``maverick runway consolidate`` CLI command."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from maverick.cli.commands.runway._group import runway
from maverick.library.actions.types import RunwayConsolidationResult


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def mock_config() -> MagicMock:
    config = MagicMock()
    config.runway.consolidation.max_episodic_age_days = 90
    config.runway.consolidation.max_episodic_records = 500
    return config


def test_consolidate_invokes_action(runner: CliRunner, mock_config: MagicMock) -> None:
    """CLI should call consolidate_runway action."""
    mock_result = RunwayConsolidationResult(
        success=True,
        records_pruned=5,
        summary_updated=True,
        skipped=False,
        skip_reason=None,
        error=None,
    )

    # Import the consolidate module to register the command
    import maverick.cli.commands.runway.consolidate  # noqa: F401

    with (
        patch(
            "maverick.config.load_config",
            return_value=mock_config,
        ),
        patch(
            "maverick.library.actions.consolidation.consolidate_runway",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_action,
    ):
        result = runner.invoke(runway, ["consolidate"])

    assert result.exit_code == 0
    mock_action.assert_called_once()
    call_kwargs = mock_action.call_args[1]
    assert call_kwargs["force"] is False


def test_force_flag_passed(runner: CliRunner, mock_config: MagicMock) -> None:
    """--force flag should set force=True in action call."""
    mock_result = RunwayConsolidationResult(
        success=True,
        records_pruned=0,
        summary_updated=False,
        skipped=False,
        skip_reason=None,
        error=None,
    )

    import maverick.cli.commands.runway.consolidate  # noqa: F401

    with (
        patch(
            "maverick.config.load_config",
            return_value=mock_config,
        ),
        patch(
            "maverick.library.actions.consolidation.consolidate_runway",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_action,
    ):
        result = runner.invoke(runway, ["consolidate", "--force"])

    assert result.exit_code == 0
    call_kwargs = mock_action.call_args[1]
    assert call_kwargs["force"] is True
