"""Tests for runway data models."""

from __future__ import annotations

from maverick.runway.models import (
    BeadOutcome,
    FixAttemptRecord,
    RunwayIndex,
    RunwayPassage,
    RunwayQueryResult,
    RunwayReviewFinding,
    RunwayStatus,
)


class TestBeadOutcome:
    """Tests for BeadOutcome model."""

    def test_create_minimal(self) -> None:
        outcome = BeadOutcome(bead_id="b1", epic_id="e1")
        assert outcome.bead_id == "b1"
        assert outcome.epic_id == "e1"
        assert outcome.files_changed == []
        assert outcome.validation_passed is False

    def test_frozen(self) -> None:
        outcome = BeadOutcome(bead_id="b1", epic_id="e1")
        with __import__("pytest").raises(Exception):
            outcome.bead_id = "b2"  # type: ignore[misc]

    def test_round_trip(self, sample_bead_outcome: BeadOutcome) -> None:
        data = sample_bead_outcome.to_dict()
        restored = BeadOutcome.from_dict(data)
        assert restored.bead_id == sample_bead_outcome.bead_id
        assert restored.files_changed == sample_bead_outcome.files_changed

    def test_timestamp_auto_set(self) -> None:
        outcome = BeadOutcome(bead_id="b1", epic_id="e1")
        assert outcome.timestamp  # Non-empty


class TestRunwayReviewFinding:
    """Tests for RunwayReviewFinding model."""

    def test_create_and_serialize(self) -> None:
        finding = RunwayReviewFinding(
            finding_id="F001",
            bead_id="b1",
            severity="major",
            description="Missing validation",
        )
        data = finding.to_dict()
        assert data["finding_id"] == "F001"
        assert data["severity"] == "major"

    def test_round_trip(self, sample_review_finding: RunwayReviewFinding) -> None:
        data = sample_review_finding.to_dict()
        restored = RunwayReviewFinding.from_dict(data)
        assert restored == sample_review_finding


class TestFixAttemptRecord:
    """Tests for FixAttemptRecord model."""

    def test_create_and_serialize(self) -> None:
        attempt = FixAttemptRecord(
            attempt_id="a1",
            finding_id="F001",
            bead_id="b1",
            succeeded=True,
        )
        data = attempt.to_dict()
        assert data["succeeded"] is True

    def test_round_trip(self, sample_fix_attempt: FixAttemptRecord) -> None:
        data = sample_fix_attempt.to_dict()
        restored = FixAttemptRecord.from_dict(data)
        assert restored == sample_fix_attempt


class TestRunwayIndex:
    """Tests for RunwayIndex model."""

    def test_defaults(self) -> None:
        index = RunwayIndex()
        assert index.version == 1
        assert index.last_consolidated == ""
        assert index.entities == []
        assert index.suppressed_patterns == []

    def test_round_trip(self) -> None:
        index = RunwayIndex(
            version=1,
            last_consolidated="2025-01-01T00:00:00",
            entities=["FooService"],
            episodic_counts={"bead-outcomes": 5},
        )
        data = index.to_dict()
        restored = RunwayIndex.from_dict(data)
        assert restored.entities == ["FooService"]
        assert restored.episodic_counts == {"bead-outcomes": 5}


class TestRunwayPassage:
    """Tests for RunwayPassage model."""

    def test_create(self) -> None:
        passage = RunwayPassage(
            source_file="semantic/architecture.md",
            content="The system uses event sourcing.",
            score=1.5,
            line_start=1,
            line_end=3,
        )
        assert passage.score == 1.5
        data = passage.to_dict()
        assert data["source_file"] == "semantic/architecture.md"


class TestRunwayQueryResult:
    """Tests for RunwayQueryResult model."""

    def test_empty(self) -> None:
        result = RunwayQueryResult(query="test")
        assert result.passages == []
        assert result.total_candidates == 0

    def test_with_passages(self) -> None:
        p = RunwayPassage(source_file="f.md", content="hello", score=1.0)
        result = RunwayQueryResult(passages=[p], query="hello", total_candidates=10)
        assert len(result.passages) == 1


class TestRunwayStatus:
    """Tests for RunwayStatus model."""

    def test_defaults(self) -> None:
        status = RunwayStatus()
        assert status.initialized is False
        assert status.bead_outcome_count == 0
