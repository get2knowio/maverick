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
    with patch(
        "maverick.library.actions.consolidation.consolidate_runway"
    ) as mock_consolidate:
        await _maybe_consolidate(Path("/tmp/repo"), no_consolidate=True)
        mock_consolidate.assert_not_called()


@pytest.mark.asyncio()
async def test_consolidation_disabled_by_config() -> None:
    """Should skip when runway.enabled is False."""
    mock_config = MagicMock()
    mock_config.runway.enabled = False

    with (
        patch("maverick.config.load_config", return_value=mock_config),
        patch(
            "maverick.library.actions.consolidation.consolidate_runway"
        ) as mock_consolidate,
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
        patch(
            "maverick.library.actions.consolidation.consolidate_runway"
        ) as mock_consolidate,
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
        patch("maverick.cli.commands.land._sync_runway_semantics"),
    ):
        await _maybe_consolidate(Path("/tmp/repo"), no_consolidate=False)
        mock_consolidate.assert_called_once()


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


@pytest.mark.asyncio()
async def test_force_when_workspace_differs_from_user_repo() -> None:
    """force=True when runway_cwd != user_repo (workspace about to be torn down)."""
    mock_config = MagicMock()
    mock_config.runway.enabled = True
    mock_config.runway.consolidation.auto = True
    mock_config.runway.consolidation.max_episodic_age_days = 90
    mock_config.runway.consolidation.max_episodic_records = 500

    mock_result = RunwayConsolidationResult(
        success=True,
        records_pruned=5,
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
        patch("maverick.cli.commands.land._sync_runway_semantics") as mock_sync,
    ):
        await _maybe_consolidate(
            Path("/tmp/workspace"),
            no_consolidate=False,
            user_repo=Path("/tmp/user-repo"),
        )
        mock_consolidate.assert_called_once()
        call_kwargs = mock_consolidate.call_args[1]
        assert call_kwargs["force"] is True
        assert call_kwargs["cwd"] == Path("/tmp/workspace")
        mock_sync.assert_called_once_with(
            Path("/tmp/workspace"), Path("/tmp/user-repo")
        )


@pytest.mark.asyncio()
async def test_no_force_when_same_path() -> None:
    """force=False when runway_cwd == user_repo (no workspace)."""
    mock_config = MagicMock()
    mock_config.runway.enabled = True
    mock_config.runway.consolidation.auto = True
    mock_config.runway.consolidation.max_episodic_age_days = 90
    mock_config.runway.consolidation.max_episodic_records = 500

    mock_result = RunwayConsolidationResult(
        success=True,
        records_pruned=0,
        summary_updated=False,
        skipped=True,
        skip_reason="Below thresholds",
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
        repo = Path("/tmp/repo")
        await _maybe_consolidate(repo, no_consolidate=False, user_repo=repo)
        call_kwargs = mock_consolidate.call_args[1]
        assert call_kwargs["force"] is False


def test_sync_runway_data(tmp_path: Path) -> None:
    """Semantic, episodic, and index files should be copied."""
    from maverick.cli.commands.land import _sync_runway_semantics

    # Set up source (workspace) runway
    src = tmp_path / "workspace"
    src_runway = src / ".maverick" / "runway"
    src_semantic = src_runway / "semantic"
    src_episodic = src_runway / "episodic"
    src_semantic.mkdir(parents=True)
    src_episodic.mkdir(parents=True)
    (src_semantic / "consolidated-insights.md").write_text("# Insights")
    (src_episodic / "bead-outcomes.jsonl").write_text('{"bead_id":"b1"}\n')
    (src_runway / "index.json").write_text('{"version": 1}')

    # Set up destination (user repo) runway
    dst = tmp_path / "user-repo"
    (dst / ".maverick" / "runway").mkdir(parents=True)

    _sync_runway_semantics(src, dst)

    dst_runway = dst / ".maverick" / "runway"
    insights = dst_runway / "semantic" / "consolidated-insights.md"
    outcomes = dst_runway / "episodic" / "bead-outcomes.jsonl"
    assert insights.read_text() == "# Insights"
    assert outcomes.read_text() == '{"bead_id":"b1"}\n'
    assert (dst_runway / "index.json").read_text() == '{"version": 1}'


def test_sync_runway_semantics_no_dst_runway(tmp_path: Path) -> None:
    """Sync should be a no-op when user repo has no runway."""
    from maverick.cli.commands.land import _sync_runway_semantics

    src = tmp_path / "workspace"
    src_semantic = src / ".maverick" / "runway" / "semantic"
    src_semantic.mkdir(parents=True)
    (src_semantic / "consolidated-insights.md").write_text("# Insights")

    dst = tmp_path / "user-repo"
    dst.mkdir()

    _sync_runway_semantics(src, dst)

    assert not (dst / ".maverick").exists()
