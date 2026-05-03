"""Tests for runway consolidation integration in land command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.cli.commands.land import _maybe_consolidate
from maverick.library.actions.types import RunwayConsolidationResult


@pytest.mark.asyncio()
async def test_no_consolidate_flag_skips() -> None:
    """When no_consolidate=True, _maybe_consolidate should do nothing."""
    with patch("maverick.library.actions.consolidation.consolidate_runway") as mock_consolidate:
        await _maybe_consolidate(Path("/tmp/repo"), no_consolidate=True)
        mock_consolidate.assert_not_called()


@pytest.mark.asyncio()
async def test_consolidation_disabled_by_config() -> None:
    """Should skip when runway.enabled is False."""
    mock_config = MagicMock()
    mock_config.runway.enabled = False

    with (
        patch("maverick.config.load_config", return_value=mock_config),
        patch("maverick.library.actions.consolidation.consolidate_runway") as mock_consolidate,
    ):
        await _maybe_consolidate(Path("/tmp/repo"), no_consolidate=False)
        mock_consolidate.assert_not_called()


@pytest.mark.asyncio()
async def test_consolidation_disabled_by_auto_config() -> None:
    """Should skip when runway.consolidation.auto is False."""
    mock_config = MagicMock()
    mock_config.runway.enabled = True
    mock_config.runway.consolidation.auto = False

    with (
        patch("maverick.config.load_config", return_value=mock_config),
        patch("maverick.library.actions.consolidation.consolidate_runway") as mock_consolidate,
    ):
        await _maybe_consolidate(Path("/tmp/repo"), no_consolidate=False)
        mock_consolidate.assert_not_called()


@pytest.mark.asyncio()
async def test_consolidation_called_when_enabled() -> None:
    """Should call consolidate_runway when config allows."""
    mock_config = MagicMock()
    mock_config.runway.enabled = True
    mock_config.runway.consolidation.auto = True
    mock_config.runway.consolidation.max_episodic_age_days = 90
    mock_config.runway.consolidation.max_episodic_records = 500

    mock_result = RunwayConsolidationResult(
        success=True,
        records_pruned=10,
        summary_updated=True,
        skipped=False,
        skip_reason=None,
        error=None,
    )

    with (
        patch("maverick.config.load_config", return_value=mock_config),
        patch(
            "maverick.library.actions.consolidation.consolidate_runway",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_consolidate,
    ):
        await _maybe_consolidate(Path("/tmp/repo"), no_consolidate=False)
        mock_consolidate.assert_called_once()
        call_kwargs = mock_consolidate.call_args[1]
        # Single-repo land never forces consolidation: there's no
        # workspace teardown threatening to lose the data.
        assert call_kwargs["force"] is False
        assert call_kwargs["cwd"] == Path("/tmp/repo")


@pytest.mark.asyncio()
async def test_consolidation_failure_doesnt_block_land() -> None:
    """Exception during consolidation should not raise."""
    mock_config = MagicMock()
    mock_config.runway.enabled = True
    mock_config.runway.consolidation.auto = True
    mock_config.runway.consolidation.max_episodic_age_days = 90
    mock_config.runway.consolidation.max_episodic_records = 500

    with (
        patch("maverick.config.load_config", return_value=mock_config),
        patch(
            "maverick.library.actions.consolidation.consolidate_runway",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ),
    ):
        # Should not raise
        await _maybe_consolidate(Path("/tmp/repo"), no_consolidate=False)
