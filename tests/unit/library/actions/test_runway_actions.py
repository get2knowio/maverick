"""Tests for runway recording actions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from maverick.library.actions.runway import (
    record_bead_outcome,
    record_fix_attempt,
    record_review_findings,
)


@pytest.fixture
async def runway_dir(tmp_path: Path) -> Path:
    """Create an initialized runway store and return its parent (cwd)."""
    from maverick.runway.store import RunwayStore

    cwd = tmp_path / "project"
    cwd.mkdir()
    runway_path = cwd / ".maverick" / "runway"
    store = RunwayStore(runway_path)
    await store.initialize()
    return cwd


class TestRecordBeadOutcome:
    """Tests for record_bead_outcome action."""

    async def test_success(self, runway_dir: Path) -> None:
        result = await record_bead_outcome(
            bead_id="b1",
            epic_id="e1",
            title="Test bead",
            cwd=runway_dir,
        )
        assert result.success is True
        assert result.bead_id == "b1"
        assert result.error is None

    async def test_with_validation_and_review(self, runway_dir: Path) -> None:
        result = await record_bead_outcome(
            bead_id="b1",
            epic_id="e1",
            validation_result={"passed": True},
            review_result={"issues_found": 3, "issues_fixed": 2},
            cwd=runway_dir,
        )
        assert result.success is True

    async def test_not_initialized(self, tmp_path: Path) -> None:
        result = await record_bead_outcome(
            bead_id="b1",
            epic_id="e1",
            cwd=tmp_path,
        )
        assert result.success is False
        assert "not initialized" in (result.error or "").lower()

    async def test_handles_exception(self, runway_dir: Path) -> None:
        with patch(
            "maverick.library.actions.runway._get_store",
            side_effect=RuntimeError("boom"),
        ):
            result = await record_bead_outcome(
                bead_id="b1", epic_id="e1", cwd=runway_dir
            )
        assert result.success is False
        assert "boom" in (result.error or "")


class TestRecordReviewFindings:
    """Tests for record_review_findings action."""

    async def test_grouped_format(self, runway_dir: Path) -> None:
        review_result = {
            "groups": [
                {
                    "description": "Batch 1",
                    "findings": [
                        {
                            "id": "F001",
                            "file": "src/a.py",
                            "severity": "major",
                            "issue": "Missing check",
                        }
                    ],
                }
            ]
        }
        result = await record_review_findings(
            bead_id="b1",
            review_result=review_result,
            cwd=runway_dir,
        )
        assert result.success is True
        assert result.findings_recorded == 1

    async def test_flat_format(self, runway_dir: Path) -> None:
        review_result = {
            "issues_fixed": [
                {"issue_id": "I1", "fixed": True, "description": "Fixed thing"}
            ],
            "issues_remaining": [{"issue_id": "I2", "description": "Still broken"}],
        }
        result = await record_review_findings(
            bead_id="b1",
            review_result=review_result,
            cwd=runway_dir,
        )
        assert result.success is True
        assert result.findings_recorded == 2

    async def test_not_initialized(self, tmp_path: Path) -> None:
        result = await record_review_findings(
            bead_id="b1",
            review_result={},
            cwd=tmp_path,
        )
        assert result.success is False


class TestRecordFixAttempt:
    """Tests for record_fix_attempt action."""

    async def test_success(self, runway_dir: Path) -> None:
        result = await record_fix_attempt(
            finding_id="F1",
            bead_id="b1",
            approach="Added error handling",
            succeeded=True,
            cwd=runway_dir,
        )
        assert result.success is True
        assert result.attempt_id  # Non-empty

    async def test_not_initialized(self, tmp_path: Path) -> None:
        result = await record_fix_attempt(
            finding_id="F1",
            bead_id="b1",
            cwd=tmp_path,
        )
        assert result.success is False
