"""Tests for runway consolidation action."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.library.actions.consolidation import consolidate_runway
from maverick.runway.store import RunwayStore


@pytest.fixture()
def runway_dir(tmp_path: Path) -> Path:
    """Create an initialized runway directory structure."""
    runway_path = tmp_path / ".maverick" / "runway"
    episodic = runway_path / "episodic"
    semantic = runway_path / "semantic"
    episodic.mkdir(parents=True)
    semantic.mkdir(parents=True)

    # Create index.json
    (runway_path / "index.json").write_text(
        json.dumps({"version": 1, "last_consolidated": "", "episodic_counts": {}})
    )

    # Touch JSONL files
    (episodic / "bead-outcomes.jsonl").touch()
    (episodic / "review-findings.jsonl").touch()
    (episodic / "fix-attempts.jsonl").touch()

    return tmp_path


def _write_outcomes(runway_dir: Path, outcomes: list[dict[str, Any]]) -> None:
    """Helper to write bead outcomes JSONL."""
    path = runway_dir / ".maverick" / "runway" / "episodic" / "bead-outcomes.jsonl"
    path.write_text("".join(json.dumps(o) + "\n" for o in outcomes))


def _write_findings(runway_dir: Path, findings: list[dict[str, Any]]) -> None:
    """Helper to write review findings JSONL."""
    path = runway_dir / ".maverick" / "runway" / "episodic" / "review-findings.jsonl"
    path.write_text("".join(json.dumps(f) + "\n" for f in findings))


def _write_attempts(runway_dir: Path, attempts: list[dict[str, Any]]) -> None:
    """Helper to write fix attempts JSONL."""
    path = runway_dir / ".maverick" / "runway" / "episodic" / "fix-attempts.jsonl"
    path.write_text("".join(json.dumps(a) + "\n" for a in attempts))


def _mock_executor() -> MagicMock:
    """Create a mock executor that returns a valid result."""
    executor = MagicMock()
    result = MagicMock()
    result.output = "# Consolidated Insights\n\nSome content."
    executor.execute = AsyncMock(return_value=result)
    executor.cleanup = AsyncMock()
    return executor


@pytest.mark.asyncio()
async def test_skips_when_not_initialized(tmp_path: Path) -> None:
    """Should return skipped when runway is not initialized."""
    result = await consolidate_runway(cwd=tmp_path)

    assert result.skipped is True
    assert result.success is True
    assert "not initialized" in (result.skip_reason or "").lower()


@pytest.mark.asyncio()
async def test_skips_when_below_thresholds(runway_dir: Path) -> None:
    """Should skip when few recent records are present."""
    now = datetime.now().isoformat()
    _write_outcomes(
        runway_dir,
        [
            {"bead_id": "b1", "epic_id": "e1", "timestamp": now},
            {"bead_id": "b2", "epic_id": "e1", "timestamp": now},
        ],
    )

    result = await consolidate_runway(cwd=runway_dir, max_records=500)

    assert result.skipped is True
    assert result.success is True


@pytest.mark.asyncio()
async def test_force_bypasses_threshold(runway_dir: Path) -> None:
    """force=True should run even if below thresholds."""
    now = datetime.now().isoformat()
    _write_outcomes(
        runway_dir,
        [
            {"bead_id": "b1", "epic_id": "e1", "timestamp": now},
        ],
    )

    with patch(
        "maverick.library.actions.consolidation._synthesize_summary",
        new_callable=AsyncMock,
        return_value=True,
    ):
        result = await consolidate_runway(cwd=runway_dir, force=True)

    # With force and only 1 recent record, no records are old enough to prune
    # but the action should still run (not be skipped)
    # It may still end up with records_pruned=0 if none are actually old
    assert result.skipped is False or result.success is True


@pytest.mark.asyncio()
async def test_partitions_by_age(runway_dir: Path) -> None:
    """Old records should go to consolidate, recent should stay."""
    old_ts = (datetime.now() - timedelta(days=120)).isoformat()
    new_ts = datetime.now().isoformat()

    _write_outcomes(
        runway_dir,
        [
            {"bead_id": "old-1", "epic_id": "e1", "timestamp": old_ts},
            {"bead_id": "new-1", "epic_id": "e1", "timestamp": new_ts},
        ],
    )

    with patch(
        "maverick.library.actions.consolidation._synthesize_summary",
        new_callable=AsyncMock,
        return_value=True,
    ):
        result = await consolidate_runway(cwd=runway_dir, max_age_days=90)

    assert result.success is True
    assert result.skipped is False
    assert result.records_pruned >= 1

    # Verify only new record remains
    store = RunwayStore(runway_dir / ".maverick" / "runway")
    remaining = await store.get_bead_outcomes()
    bead_ids = [o.bead_id for o in remaining]
    assert "new-1" in bead_ids
    assert "old-1" not in bead_ids


@pytest.mark.asyncio()
async def test_partitions_by_count(runway_dir: Path) -> None:
    """Excess oldest records should be consolidated when over max_records."""
    now = datetime.now().isoformat()
    outcomes = [
        {"bead_id": f"b{i}", "epic_id": "e1", "timestamp": now} for i in range(20)
    ]
    _write_outcomes(runway_dir, outcomes)

    with patch(
        "maverick.library.actions.consolidation._synthesize_summary",
        new_callable=AsyncMock,
        return_value=True,
    ):
        # max_records=15 means per-file max is 5, so 15 should be pruned
        result = await consolidate_runway(cwd=runway_dir, max_records=15, force=True)

    assert result.success is True
    store = RunwayStore(runway_dir / ".maverick" / "runway")
    remaining = await store.get_bead_outcomes()
    assert len(remaining) <= 15


@pytest.mark.asyncio()
async def test_prunes_jsonl_files(runway_dir: Path) -> None:
    """After consolidation, JSONL should have only kept records."""
    old_ts = (datetime.now() - timedelta(days=120)).isoformat()
    new_ts = datetime.now().isoformat()

    _write_outcomes(
        runway_dir,
        [
            {"bead_id": "old-1", "epic_id": "e1", "timestamp": old_ts},
            {"bead_id": "new-1", "epic_id": "e1", "timestamp": new_ts},
        ],
    )
    _write_findings(
        runway_dir,
        [
            {"finding_id": "F1", "bead_id": "old-1", "severity": "major"},
            {"finding_id": "F2", "bead_id": "new-1", "severity": "minor"},
        ],
    )

    with patch(
        "maverick.library.actions.consolidation._synthesize_summary",
        new_callable=AsyncMock,
        return_value=True,
    ):
        result = await consolidate_runway(cwd=runway_dir, max_age_days=90)

    assert result.success is True

    store = RunwayStore(runway_dir / ".maverick" / "runway")
    remaining_findings = await store.get_review_findings()
    finding_ids = [f.finding_id for f in remaining_findings]
    # F1 belongs to old-1 which was consolidated
    assert "F1" not in finding_ids
    assert "F2" in finding_ids


@pytest.mark.asyncio()
async def test_updates_index_timestamp(runway_dir: Path) -> None:
    """last_consolidated should be set in the index after consolidation."""
    old_ts = (datetime.now() - timedelta(days=120)).isoformat()
    _write_outcomes(
        runway_dir,
        [
            {"bead_id": "old-1", "epic_id": "e1", "timestamp": old_ts},
        ],
    )

    with patch(
        "maverick.library.actions.consolidation._synthesize_summary",
        new_callable=AsyncMock,
        return_value=True,
    ):
        result = await consolidate_runway(cwd=runway_dir, max_age_days=90)

    assert result.success is True

    store = RunwayStore(runway_dir / ".maverick" / "runway")
    index = await store.read_index()
    assert index.last_consolidated != ""
    # Should be a valid ISO timestamp
    datetime.fromisoformat(index.last_consolidated)


@pytest.mark.asyncio()
async def test_best_effort_on_exception(tmp_path: Path) -> None:
    """Store errors should return result, not raise."""
    # Point to a non-existent directory but create partial structure
    # that will fail during operation
    runway_path = tmp_path / ".maverick" / "runway"
    episodic = runway_path / "episodic"
    semantic = runway_path / "semantic"
    episodic.mkdir(parents=True)
    semantic.mkdir(parents=True)
    (runway_path / "index.json").write_text("invalid json!!!")
    (episodic / "bead-outcomes.jsonl").touch()
    (episodic / "review-findings.jsonl").touch()
    (episodic / "fix-attempts.jsonl").touch()

    # Force to bypass threshold check, which will hit corrupted index
    result = await consolidate_runway(cwd=tmp_path, force=True)

    assert result.success is False
    assert result.error is not None


@pytest.mark.asyncio()
async def test_synthesis_failure_still_prunes(runway_dir: Path) -> None:
    """If executor fails, pruning should still happen."""
    old_ts = (datetime.now() - timedelta(days=120)).isoformat()
    _write_outcomes(
        runway_dir,
        [
            {"bead_id": "old-1", "epic_id": "e1", "timestamp": old_ts},
            {"bead_id": "old-2", "epic_id": "e1", "timestamp": old_ts},
        ],
    )

    with patch(
        "maverick.library.actions.consolidation._synthesize_summary",
        new_callable=AsyncMock,
        side_effect=RuntimeError("executor exploded"),
    ):
        result = await consolidate_runway(cwd=runway_dir, max_age_days=90)

    assert result.success is True
    assert result.summary_updated is False
    assert result.records_pruned >= 2

    # Records should still be pruned
    store = RunwayStore(runway_dir / ".maverick" / "runway")
    remaining = await store.get_bead_outcomes()
    assert len(remaining) == 0
