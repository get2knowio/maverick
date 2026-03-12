"""Fixtures for runway tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.runway.models import BeadOutcome, FixAttemptRecord, RunwayReviewFinding
from maverick.runway.store import RunwayStore


@pytest.fixture
def runway_path(tmp_path: Path) -> Path:
    """Return a temporary runway path."""
    return tmp_path / ".maverick" / "runway"


@pytest.fixture
async def initialized_store(runway_path: Path) -> RunwayStore:
    """Return an initialized RunwayStore."""
    store = RunwayStore(runway_path)
    await store.initialize()
    return store


@pytest.fixture
def sample_bead_outcome() -> BeadOutcome:
    """Return a sample BeadOutcome for testing."""
    return BeadOutcome(
        bead_id="bead-001",
        epic_id="epic-001",
        flight_plan="test-plan",
        title="Add feature X",
        files_changed=["src/foo.py", "tests/test_foo.py"],
        validation_passed=True,
        review_findings_count=2,
        review_fixed_count=1,
        key_decisions=["Used strategy pattern"],
        mistakes_caught=["Missing null check"],
    )


@pytest.fixture
def sample_review_finding() -> RunwayReviewFinding:
    """Return a sample RunwayReviewFinding for testing."""
    return RunwayReviewFinding(
        finding_id="F001",
        bead_id="bead-001",
        reviewer="technical",
        severity="major",
        category="correctness",
        file_path="src/foo.py",
        description="Missing error handling in parse()",
        resolution="fixed",
    )


@pytest.fixture
def sample_fix_attempt() -> FixAttemptRecord:
    """Return a sample FixAttemptRecord for testing."""
    return FixAttemptRecord(
        attempt_id="att-001",
        finding_id="F001",
        bead_id="bead-001",
        approach="Added try/except with specific exception type",
        succeeded=True,
        failure_reason="",
    )
