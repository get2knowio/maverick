"""Tests for RunwayStore JSONL rewrite methods."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maverick.runway.models import BeadOutcome, FixAttemptRecord, RunwayReviewFinding
from maverick.runway.store import RunwayStore


@pytest.fixture()
def initialized_store(tmp_path: Path) -> RunwayStore:
    """Create an initialized RunwayStore with some seed data."""
    runway_path = tmp_path / ".maverick" / "runway"
    store = RunwayStore(runway_path)

    # Create directory structure
    episodic = runway_path / "episodic"
    semantic = runway_path / "semantic"
    episodic.mkdir(parents=True)
    semantic.mkdir(parents=True)

    # Create index.json
    (runway_path / "index.json").write_text('{"version": 1}')

    # Seed bead-outcomes.jsonl with old data
    outcomes_file = episodic / "bead-outcomes.jsonl"
    old_records = [
        {"bead_id": "old-1", "epic_id": "e1", "timestamp": "2025-01-01T00:00:00"},
        {"bead_id": "old-2", "epic_id": "e1", "timestamp": "2025-01-02T00:00:00"},
    ]
    outcomes_file.write_text("".join(json.dumps(r) + "\n" for r in old_records))

    # Seed review-findings.jsonl
    findings_file = episodic / "review-findings.jsonl"
    findings_file.write_text(json.dumps({"finding_id": "F1", "bead_id": "old-1"}) + "\n")

    # Seed fix-attempts.jsonl
    attempts_file = episodic / "fix-attempts.jsonl"
    attempts_file.write_text(
        json.dumps({"attempt_id": "A1", "finding_id": "F1", "bead_id": "old-1"}) + "\n"
    )

    return store


@pytest.mark.asyncio()
async def test_rewrite_jsonl_replaces_file(initialized_store: RunwayStore) -> None:
    """Old records should be gone, new records present after rewrite."""
    path = initialized_store.path / "episodic" / "bead-outcomes.jsonl"

    new_records = [
        {"bead_id": "new-1", "epic_id": "e2"},
        {"bead_id": "new-2", "epic_id": "e2"},
    ]
    await initialized_store.rewrite_jsonl(path, new_records)

    content = path.read_text()
    lines = [line for line in content.strip().split("\n") if line.strip()]
    assert len(lines) == 2

    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["bead_id"] == "new-1"
    assert parsed[1]["bead_id"] == "new-2"

    # Old records should not be present
    assert "old-1" not in content
    assert "old-2" not in content


@pytest.mark.asyncio()
async def test_rewrite_jsonl_empty_list(initialized_store: RunwayStore) -> None:
    """Rewriting with empty list should create an empty file."""
    path = initialized_store.path / "episodic" / "bead-outcomes.jsonl"

    await initialized_store.rewrite_jsonl(path, [])

    content = path.read_text()
    assert content == ""


@pytest.mark.asyncio()
async def test_rewrite_bead_outcomes_typed(initialized_store: RunwayStore) -> None:
    """Typed rewrite method should work with BeadOutcome objects."""
    outcomes = [
        BeadOutcome(bead_id="b1", epic_id="e1", title="Test"),
        BeadOutcome(bead_id="b2", epic_id="e1", title="Test 2"),
    ]
    await initialized_store.rewrite_bead_outcomes(outcomes)

    result = await initialized_store.get_bead_outcomes()
    assert len(result) == 2
    assert result[0].bead_id == "b1"
    assert result[1].bead_id == "b2"


@pytest.mark.asyncio()
async def test_rewrite_review_findings_typed(initialized_store: RunwayStore) -> None:
    """Typed rewrite method should work with RunwayReviewFinding objects."""
    findings = [
        RunwayReviewFinding(finding_id="F10", bead_id="b1", severity="major"),
    ]
    await initialized_store.rewrite_review_findings(findings)

    result = await initialized_store.get_review_findings()
    assert len(result) == 1
    assert result[0].finding_id == "F10"


@pytest.mark.asyncio()
async def test_rewrite_fix_attempts_typed(initialized_store: RunwayStore) -> None:
    """Typed rewrite method should work with FixAttemptRecord objects."""
    attempts = [
        FixAttemptRecord(attempt_id="A10", finding_id="F10", bead_id="b1", succeeded=True),
    ]
    await initialized_store.rewrite_fix_attempts(attempts)

    result = await initialized_store.get_fix_attempts()
    assert len(result) == 1
    assert result[0].attempt_id == "A10"


@pytest.mark.asyncio()
async def test_rewrite_preserves_other_files(initialized_store: RunwayStore) -> None:
    """Rewriting one JSONL file should not affect other files."""
    await initialized_store.rewrite_bead_outcomes([])

    # Review findings should be untouched
    findings = await initialized_store.get_review_findings()
    assert len(findings) == 1
    assert findings[0].finding_id == "F1"

    # Fix attempts should be untouched
    attempts = await initialized_store.get_fix_attempts()
    assert len(attempts) == 1
    assert attempts[0].attempt_id == "A1"
