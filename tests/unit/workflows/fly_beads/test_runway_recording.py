"""Tests for runway recording in bead workflow steps."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from maverick.workflows.fly_beads.models import BeadContext
from maverick.workflows.fly_beads.steps import (
    record_runway_outcome,
    record_runway_review,
)


@pytest.fixture
def mock_workflow() -> MagicMock:
    """Return a mock FlyBeadsWorkflow."""
    wf = MagicMock()
    wf.emit_output = AsyncMock()
    wf.emit_step_started = AsyncMock()
    wf.emit_step_completed = AsyncMock()
    wf.emit_step_failed = AsyncMock()
    return wf


@pytest.fixture
async def ctx_with_runway(tmp_path: Path) -> BeadContext:
    """Return a BeadContext with an initialized runway store."""
    from maverick.runway.store import RunwayStore

    cwd = tmp_path / "workspace"
    cwd.mkdir()
    store = RunwayStore(cwd / ".maverick" / "runway")
    await store.initialize()
    return BeadContext(
        bead_id="b1",
        title="Test bead",
        description="Test description",
        epic_id="e1",
        cwd=cwd,
        validation_result={"passed": True},
        review_result={"issues_found": 1, "issues_fixed": 1},
    )


class TestRecordRunwayOutcome:
    """Tests for record_runway_outcome step function."""

    async def test_records_successfully(
        self,
        mock_workflow: MagicMock,
        ctx_with_runway: BeadContext,
    ) -> None:
        await record_runway_outcome(mock_workflow, ctx_with_runway)
        # Verify data was written
        from maverick.runway.store import RunwayStore

        store = RunwayStore(ctx_with_runway.cwd / ".maverick" / "runway")  # type: ignore[operator]
        outcomes = await store.get_bead_outcomes()
        assert len(outcomes) == 1
        assert outcomes[0].bead_id == "b1"

    async def test_best_effort_on_failure(
        self,
        mock_workflow: MagicMock,
    ) -> None:
        """Should not raise even if recording fails."""
        ctx = BeadContext(
            bead_id="b1",
            title="Test",
            description="desc",
            epic_id="e1",
            cwd=Path("/nonexistent"),
        )
        # Should not raise
        await record_runway_outcome(mock_workflow, ctx)


class TestRecordRunwayReview:
    """Tests for record_runway_review step function."""

    async def test_records_findings(
        self,
        mock_workflow: MagicMock,
        ctx_with_runway: BeadContext,
    ) -> None:
        ctx_with_runway.review_result = {
            "groups": [
                {
                    "description": "Batch 1",
                    "findings": [
                        {
                            "id": "F1",
                            "file": "src/a.py",
                            "severity": "major",
                            "issue": "Bug",
                        }
                    ],
                }
            ]
        }
        await record_runway_review(mock_workflow, ctx_with_runway)
        from maverick.runway.store import RunwayStore

        store = RunwayStore(ctx_with_runway.cwd / ".maverick" / "runway")  # type: ignore[operator]
        findings = await store.get_review_findings()
        assert len(findings) == 1

    async def test_skips_when_no_review_result(
        self,
        mock_workflow: MagicMock,
    ) -> None:
        ctx = BeadContext(
            bead_id="b1",
            title="Test",
            description="desc",
            epic_id="e1",
            cwd=None,
            review_result=None,
        )
        # Should return immediately, no error
        await record_runway_review(mock_workflow, ctx)

    async def test_best_effort_on_failure(
        self,
        mock_workflow: MagicMock,
    ) -> None:
        ctx = BeadContext(
            bead_id="b1",
            title="Test",
            description="desc",
            epic_id="e1",
            cwd=Path("/nonexistent"),
            review_result={"groups": []},
        )
        # Should not raise
        await record_runway_review(mock_workflow, ctx)
