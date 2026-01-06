"""Tests for simple review models."""

from __future__ import annotations

from datetime import datetime

import pytest

from maverick.models.review_models import (
    Finding,
    FindingGroup,
    FindingTracker,
    FixAttempt,
    FixOutcome,
    ReviewResult,
    TrackedFinding,
)


class TestFinding:
    """Tests for Finding dataclass."""

    def test_to_dict(self) -> None:
        """Finding.to_dict() should serialize all fields."""
        finding = Finding(
            id="F001",
            file="src/foo.py",
            line="42",
            issue="Test issue",
            severity="major",
            category="clean_code",
            fix_hint="Fix it like this",
        )

        d = finding.to_dict()

        assert d["id"] == "F001"
        assert d["file"] == "src/foo.py"
        assert d["line"] == "42"
        assert d["issue"] == "Test issue"
        assert d["severity"] == "major"
        assert d["category"] == "clean_code"
        assert d["fix_hint"] == "Fix it like this"

    def test_to_dict_without_fix_hint(self) -> None:
        """Finding.to_dict() should omit fix_hint when None."""
        finding = Finding(
            id="F001",
            file="src/foo.py",
            line="42",
            issue="Test issue",
            severity="major",
            category="clean_code",
        )

        d = finding.to_dict()

        assert "fix_hint" not in d

    def test_from_dict(self) -> None:
        """Finding.from_dict() should deserialize correctly."""
        data = {
            "id": "F001",
            "file": "src/foo.py",
            "line": 42,  # Test int conversion
            "issue": "Test issue",
            "severity": "major",
            "category": "clean_code",
            "fix_hint": "Fix it",
        }

        finding = Finding.from_dict(data)

        assert finding.id == "F001"
        assert finding.file == "src/foo.py"
        assert finding.line == "42"  # Converted to string
        assert finding.issue == "Test issue"
        assert finding.severity == "major"
        assert finding.category == "clean_code"
        assert finding.fix_hint == "Fix it"

    def test_from_dict_without_fix_hint(self) -> None:
        """Finding.from_dict() should handle missing fix_hint."""
        data = {
            "id": "F001",
            "file": "src/foo.py",
            "line": "42",
            "issue": "Test issue",
            "severity": "major",
            "category": "clean_code",
        }

        finding = Finding.from_dict(data)

        assert finding.fix_hint is None


class TestFindingGroup:
    """Tests for FindingGroup dataclass."""

    def test_to_dict(self) -> None:
        """FindingGroup.to_dict() should serialize correctly."""
        group = FindingGroup(
            description="Test group",
            findings=(
                Finding(
                    id="F001",
                    file="a.py",
                    line="1",
                    issue="Issue 1",
                    severity="major",
                    category="clean_code",
                ),
            ),
        )

        d = group.to_dict()

        assert d["description"] == "Test group"
        assert len(d["findings"]) == 1
        assert d["findings"][0]["id"] == "F001"

    def test_from_dict(self) -> None:
        """FindingGroup.from_dict() should deserialize correctly."""
        data = {
            "description": "Test group",
            "findings": [
                {
                    "id": "F001",
                    "file": "a.py",
                    "line": "1",
                    "issue": "Issue 1",
                    "severity": "major",
                    "category": "clean_code",
                },
            ],
        }

        group = FindingGroup.from_dict(data)

        assert group.description == "Test group"
        assert len(group.findings) == 1
        assert group.findings[0].id == "F001"


class TestReviewResult:
    """Tests for ReviewResult dataclass."""

    def test_all_findings(self) -> None:
        """ReviewResult.all_findings should flatten all groups."""
        result = ReviewResult(
            groups=(
                FindingGroup(
                    description="Group 1",
                    findings=(
                        Finding(
                            id="F001",
                            file="a.py",
                            line="1",
                            issue="Issue 1",
                            severity="major",
                            category="clean_code",
                        ),
                        Finding(
                            id="F002",
                            file="b.py",
                            line="2",
                            issue="Issue 2",
                            severity="minor",
                            category="type_hints",
                        ),
                    ),
                ),
                FindingGroup(
                    description="Group 2",
                    findings=(
                        Finding(
                            id="F003",
                            file="c.py",
                            line="3",
                            issue="Issue 3",
                            severity="critical",
                            category="security",
                        ),
                    ),
                ),
            )
        )

        all_findings = result.all_findings

        assert len(all_findings) == 3
        assert {f.id for f in all_findings} == {"F001", "F002", "F003"}

    def test_total_count(self) -> None:
        """ReviewResult.total_count should count all findings."""
        result = ReviewResult(
            groups=(
                FindingGroup(
                    description="Group 1",
                    findings=(
                        Finding(
                            id="F001",
                            file="a.py",
                            line="1",
                            issue="Issue 1",
                            severity="major",
                            category="clean_code",
                        ),
                    ),
                ),
                FindingGroup(
                    description="Group 2",
                    findings=(
                        Finding(
                            id="F002",
                            file="b.py",
                            line="2",
                            issue="Issue 2",
                            severity="minor",
                            category="type_hints",
                        ),
                        Finding(
                            id="F003",
                            file="c.py",
                            line="3",
                            issue="Issue 3",
                            severity="critical",
                            category="security",
                        ),
                    ),
                ),
            )
        )

        assert result.total_count == 3

    def test_to_dict_and_from_dict_roundtrip(self) -> None:
        """ReviewResult should serialize and deserialize correctly."""
        original = ReviewResult(
            groups=(
                FindingGroup(
                    description="Test group",
                    findings=(
                        Finding(
                            id="F001",
                            file="a.py",
                            line="1",
                            issue="Issue 1",
                            severity="major",
                            category="clean_code",
                        ),
                    ),
                ),
            )
        )

        d = original.to_dict()
        restored = ReviewResult.from_dict(d)

        assert restored.total_count == original.total_count
        assert restored.groups[0].description == original.groups[0].description
        assert restored.groups[0].findings[0].id == original.groups[0].findings[0].id


class TestFixOutcome:
    """Tests for FixOutcome dataclass."""

    def test_to_dict(self) -> None:
        """FixOutcome.to_dict() should serialize correctly."""
        outcome = FixOutcome(
            id="F001",
            outcome="fixed",
            explanation="Fixed the issue",
        )

        d = outcome.to_dict()

        assert d["id"] == "F001"
        assert d["outcome"] == "fixed"
        assert d["explanation"] == "Fixed the issue"

    def test_from_dict(self) -> None:
        """FixOutcome.from_dict() should deserialize correctly."""
        data = {
            "id": "F001",
            "outcome": "blocked",
            "explanation": "Cannot fix",
        }

        outcome = FixOutcome.from_dict(data)

        assert outcome.id == "F001"
        assert outcome.outcome == "blocked"
        assert outcome.explanation == "Cannot fix"


class TestFindingTracker:
    """Tests for FindingTracker class."""

    @pytest.fixture
    def sample_review_result(self) -> ReviewResult:
        """Create a sample ReviewResult for testing."""
        return ReviewResult(
            groups=(
                FindingGroup(
                    description="Group 1",
                    findings=(
                        Finding(
                            id="F001",
                            file="a.py",
                            line="1",
                            issue="Issue 1",
                            severity="major",
                            category="clean_code",
                        ),
                        Finding(
                            id="F002",
                            file="b.py",
                            line="2",
                            issue="Issue 2",
                            severity="minor",
                            category="type_hints",
                        ),
                    ),
                ),
                FindingGroup(
                    description="Group 2",
                    findings=(
                        Finding(
                            id="F003",
                            file="c.py",
                            line="3",
                            issue="Issue 3",
                            severity="critical",
                            category="security",
                        ),
                    ),
                ),
            )
        )

    def test_initialization(self, sample_review_result: ReviewResult) -> None:
        """FindingTracker should initialize with all findings as open."""
        tracker = FindingTracker(sample_review_result)

        assert tracker.total_count == 3
        assert len(tracker.get_open_findings()) == 3
        assert len(tracker.get_actionable_findings()) == 3

    def test_record_fixed_outcome(self, sample_review_result: ReviewResult) -> None:
        """Recording fixed outcome should update status."""
        tracker = FindingTracker(sample_review_result)

        tracker.record_outcome(
            FixOutcome(id="F001", outcome="fixed", explanation="Done")
        )

        assert tracker.get_fixed_count() == 1
        assert len(tracker.get_actionable_findings()) == 2

        tf = tracker.get_finding("F001")
        assert tf is not None
        assert tf.status == "fixed"
        assert len(tf.attempts) == 1

    def test_record_blocked_outcome(self, sample_review_result: ReviewResult) -> None:
        """Recording blocked outcome should update status."""
        tracker = FindingTracker(sample_review_result)

        tracker.record_outcome(
            FixOutcome(id="F001", outcome="blocked", explanation="Cannot fix")
        )

        assert tracker.get_blocked_count() == 1
        assert len(tracker.get_actionable_findings()) == 2

    def test_record_deferred_outcome(self, sample_review_result: ReviewResult) -> None:
        """Recording deferred outcome should keep item actionable for retry."""
        tracker = FindingTracker(sample_review_result)

        tracker.record_outcome(
            FixOutcome(id="F001", outcome="deferred", explanation="Need more info")
        )

        # Still actionable
        assert len(tracker.get_actionable_findings()) == 3

        tf = tracker.get_finding("F001")
        assert tf is not None
        assert len(tf.attempts) == 1
        assert tf.attempts[0].outcome == "deferred"

    def test_deferred_exceeds_retry_limit(
        self, sample_review_result: ReviewResult
    ) -> None:
        """Deferred items should stop being actionable after 3 attempts."""
        tracker = FindingTracker(sample_review_result)

        # Defer 3 times
        for _ in range(3):
            tracker.record_outcome(
                FixOutcome(id="F001", outcome="deferred", explanation="Need more info")
            )

        # Should no longer be actionable
        actionable = tracker.get_actionable_findings()
        assert "F001" not in {f.id for f in actionable}

        # Should be in unresolved
        unresolved = tracker.get_unresolved()
        assert any(tf.finding.id == "F001" for tf in unresolved)

    def test_is_complete_all_fixed(self, sample_review_result: ReviewResult) -> None:
        """is_complete should return True when all fixed."""
        tracker = FindingTracker(sample_review_result)

        for finding_id in ["F001", "F002", "F003"]:
            tracker.record_outcome(
                FixOutcome(id=finding_id, outcome="fixed", explanation="Done")
            )

        assert tracker.is_complete()

    def test_is_complete_all_blocked(self, sample_review_result: ReviewResult) -> None:
        """is_complete should return True when all blocked."""
        tracker = FindingTracker(sample_review_result)

        for finding_id in ["F001", "F002", "F003"]:
            tracker.record_outcome(
                FixOutcome(id=finding_id, outcome="blocked", explanation="Cannot fix")
            )

        assert tracker.is_complete()

    def test_is_complete_mixed(self, sample_review_result: ReviewResult) -> None:
        """is_complete should return True when all are fixed or blocked."""
        tracker = FindingTracker(sample_review_result)

        tracker.record_outcome(
            FixOutcome(id="F001", outcome="fixed", explanation="Done")
        )
        tracker.record_outcome(
            FixOutcome(id="F002", outcome="blocked", explanation="Cannot")
        )
        tracker.record_outcome(
            FixOutcome(id="F003", outcome="fixed", explanation="Done")
        )

        assert tracker.is_complete()

    def test_get_actionable_with_groups(
        self, sample_review_result: ReviewResult
    ) -> None:
        """get_actionable_with_groups should preserve group structure."""
        tracker = FindingTracker(sample_review_result)

        # Fix one item from group 1
        tracker.record_outcome(
            FixOutcome(id="F001", outcome="fixed", explanation="Done")
        )

        groups = tracker.get_actionable_with_groups()

        # Should have 2 groups, but group 1 only has F002 now
        group_1 = next((g for g in groups if g.description == "Group 1"), None)
        assert group_1 is not None
        assert len(group_1.findings) == 1
        assert group_1.findings[0].id == "F002"

    def test_record_outcomes_batch(self, sample_review_result: ReviewResult) -> None:
        """record_outcomes should handle multiple outcomes at once."""
        tracker = FindingTracker(sample_review_result)

        tracker.record_outcomes(
            [
                FixOutcome(id="F001", outcome="fixed", explanation="Done"),
                FixOutcome(id="F002", outcome="blocked", explanation="Cannot"),
            ]
        )

        assert tracker.get_fixed_count() == 1
        assert tracker.get_blocked_count() == 1

    def test_record_unknown_id_raises(self, sample_review_result: ReviewResult) -> None:
        """Recording outcome for unknown ID should raise KeyError."""
        tracker = FindingTracker(sample_review_result)

        with pytest.raises(KeyError):
            tracker.record_outcome(
                FixOutcome(id="UNKNOWN", outcome="fixed", explanation="?")
            )

    def test_get_summary(self, sample_review_result: ReviewResult) -> None:
        """get_summary should return correct counts."""
        tracker = FindingTracker(sample_review_result)

        tracker.record_outcome(
            FixOutcome(id="F001", outcome="fixed", explanation="Done")
        )
        tracker.record_outcome(
            FixOutcome(id="F002", outcome="blocked", explanation="Cannot")
        )
        tracker.record_outcome(
            FixOutcome(id="F003", outcome="deferred", explanation="Later")
        )

        summary = tracker.get_summary()

        assert summary["total"] == 3
        assert summary["fixed"] == 1
        assert summary["blocked"] == 1
        assert summary["deferred"] == 1
        assert summary["open"] == 0


class TestTrackedFinding:
    """Tests for TrackedFinding dataclass."""

    def test_default_values(self) -> None:
        """TrackedFinding should have correct defaults."""
        finding = Finding(
            id="F001",
            file="a.py",
            line="1",
            issue="Test",
            severity="major",
            category="clean_code",
        )
        tracked = TrackedFinding(finding=finding)

        assert tracked.status == "open"
        assert tracked.attempts == []


class TestFixAttempt:
    """Tests for FixAttempt dataclass."""

    def test_creation(self) -> None:
        """FixAttempt should store all fields."""
        now = datetime.now()
        attempt = FixAttempt(
            timestamp=now,
            outcome="fixed",
            explanation="Done",
        )

        assert attempt.timestamp == now
        assert attempt.outcome == "fixed"
        assert attempt.explanation == "Done"
