"""Tests for simple review models."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from maverick.models.review_models import (
    Finding,
    FindingGroup,
    FindingTracker,
    FixAttempt,
    FixOutcome,
    GroupedReviewResult,
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


# =============================================================================
# Pydantic-specific behavior tests for converted models
# =============================================================================


class TestGroupedReviewResultAlias:
    """Verify ReviewResult is a backward-compatible alias."""

    def test_review_result_is_grouped_review_result(self) -> None:
        """ReviewResult should be the same class as GroupedReviewResult."""
        assert ReviewResult is GroupedReviewResult

    def test_isinstance_check(self) -> None:
        """Instances created via ReviewResult should be GroupedReviewResult."""
        result = ReviewResult(
            groups=[
                FindingGroup(
                    description="G1",
                    findings=[
                        Finding(
                            id="F001",
                            file="a.py",
                            line="1",
                            issue="Issue",
                            severity="major",
                            category="clean_code",
                        ),
                    ],
                ),
            ]
        )
        assert isinstance(result, GroupedReviewResult)


class TestFindingPydantic:
    """Pydantic-specific behavior tests for Finding."""

    def test_keyword_only_construction(self) -> None:
        """Finding must be constructed with keyword arguments."""
        finding = Finding(
            id="F001",
            file="src/foo.py",
            line="42",
            issue="Test",
            severity="major",
            category="clean_code",
        )
        assert finding.id == "F001"
        assert finding.file == "src/foo.py"
        assert finding.line == "42"

    def test_frozen_immutability(self) -> None:
        """Finding should reject attribute assignment (frozen model)."""
        finding = Finding(
            id="F001",
            file="src/foo.py",
            line="42",
            issue="Test",
            severity="major",
            category="clean_code",
        )
        with pytest.raises(ValidationError):
            finding.id = "F002"  # type: ignore[misc]

    def test_frozen_immutability_optional_field(self) -> None:
        """Frozen model should also reject assignment on optional fields."""
        finding = Finding(
            id="F001",
            file="src/foo.py",
            line="42",
            issue="Test",
            severity="major",
            category="clean_code",
        )
        with pytest.raises(ValidationError):
            finding.fix_hint = "new hint"  # type: ignore[misc]

    def test_model_dump_round_trip(self) -> None:
        """model_dump/model_validate should round-trip correctly."""
        original = Finding(
            id="F001",
            file="src/foo.py",
            line="42",
            issue="Test issue",
            severity="major",
            category="clean_code",
            fix_hint="Fix it",
        )

        dumped = original.model_dump()
        restored = Finding.model_validate(dumped)

        assert restored == original
        assert restored.id == "F001"
        assert restored.fix_hint == "Fix it"

    def test_model_dump_includes_none_fields(self) -> None:
        """model_dump() includes None fields; to_dict() excludes them."""
        finding = Finding(
            id="F001",
            file="a.py",
            line="1",
            issue="Test",
            severity="major",
            category="clean_code",
        )

        full_dump = finding.model_dump()
        to_dict_dump = finding.to_dict()

        # model_dump includes fix_hint=None
        assert "fix_hint" in full_dump
        assert full_dump["fix_hint"] is None

        # to_dict excludes fix_hint when None
        assert "fix_hint" not in to_dict_dump

    def test_to_dict_is_model_dump_exclude_none(self) -> None:
        """to_dict() should be equivalent to model_dump(exclude_none=True)."""
        finding = Finding(
            id="F001",
            file="src/foo.py",
            line="42",
            issue="Test",
            severity="major",
            category="clean_code",
            fix_hint="Hint",
        )

        assert finding.to_dict() == finding.model_dump(exclude_none=True)

    def test_to_dict_is_model_dump_exclude_none_without_optional(self) -> None:
        """to_dict() with None fields matches model_dump(exclude_none=True)."""
        finding = Finding(
            id="F001",
            file="a.py",
            line="1",
            issue="Test",
            severity="major",
            category="clean_code",
        )

        assert finding.to_dict() == finding.model_dump(exclude_none=True)

    def test_from_dict_is_model_validate(self) -> None:
        """from_dict() should produce same result as model_validate (str line)."""
        data = {
            "id": "F001",
            "file": "a.py",
            "line": "42",
            "issue": "Test",
            "severity": "major",
            "category": "clean_code",
        }

        from_dict_result = Finding.from_dict(data)
        model_validate_result = Finding.model_validate(data)

        assert from_dict_result == model_validate_result

    def test_backward_compat_line_as_int(self) -> None:
        """from_dict() should coerce line from int to str for checkpoint compat."""
        data = {
            "id": "F001",
            "file": "a.py",
            "line": 99,
            "issue": "Test",
            "severity": "major",
            "category": "clean_code",
        }

        finding = Finding.from_dict(data)
        assert finding.line == "99"
        assert isinstance(finding.line, str)

    def test_invalid_severity_rejected(self) -> None:
        """Finding should reject invalid severity values via Literal validation."""
        with pytest.raises(ValidationError):
            Finding(
                id="F001",
                file="a.py",
                line="1",
                issue="Test",
                severity="trivial",  # type: ignore[arg-type]
                category="clean_code",
            )

    def test_missing_required_field_rejected(self) -> None:
        """Finding should reject construction with missing required fields."""
        with pytest.raises(ValidationError):
            Finding(  # type: ignore[call-arg]
                id="F001",
                file="a.py",
                # line is missing
                issue="Test",
                severity="major",
                category="clean_code",
            )


class TestFindingGroupPydantic:
    """Pydantic-specific behavior tests for FindingGroup."""

    def test_keyword_only_construction(self) -> None:
        """FindingGroup must be constructed with keyword arguments."""
        group = FindingGroup(
            description="Batch 1",
            findings=[
                Finding(
                    id="F001",
                    file="a.py",
                    line="1",
                    issue="Issue",
                    severity="major",
                    category="clean_code",
                ),
            ],
        )
        assert group.description == "Batch 1"
        assert len(group.findings) == 1

    def test_frozen_immutability(self) -> None:
        """FindingGroup should reject attribute assignment (frozen model)."""
        group = FindingGroup(
            description="Batch 1",
            findings=[],
        )
        with pytest.raises(ValidationError):
            group.description = "Changed"  # type: ignore[misc]

    def test_frozen_immutability_findings_field(self) -> None:
        """FindingGroup should reject replacing the findings field."""
        group = FindingGroup(
            description="Batch 1",
            findings=[],
        )
        with pytest.raises(ValidationError):
            group.findings = [  # type: ignore[misc]
                Finding(
                    id="F001",
                    file="a.py",
                    line="1",
                    issue="Issue",
                    severity="major",
                    category="clean_code",
                ),
            ]

    def test_model_dump_round_trip(self) -> None:
        """model_dump/model_validate should round-trip FindingGroup."""
        original = FindingGroup(
            description="Batch 1",
            findings=[
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
                    line="10",
                    issue="Issue 2",
                    severity="minor",
                    category="type_hints",
                    fix_hint="Add type hints",
                ),
            ],
        )

        dumped = original.model_dump()
        restored = FindingGroup.model_validate(dumped)

        assert restored == original
        assert len(restored.findings) == 2
        assert restored.findings[1].fix_hint == "Add type hints"

    def test_to_dict_is_model_dump_exclude_none(self) -> None:
        """to_dict() should be equivalent to model_dump(exclude_none=True)."""
        group = FindingGroup(
            description="Test",
            findings=[
                Finding(
                    id="F001",
                    file="a.py",
                    line="1",
                    issue="Issue",
                    severity="major",
                    category="clean_code",
                ),
            ],
        )

        assert group.to_dict() == group.model_dump(exclude_none=True)

    def test_from_dict_is_model_validate(self) -> None:
        """from_dict() should produce the same result as model_validate."""
        data = {
            "description": "Test group",
            "findings": [
                {
                    "id": "F001",
                    "file": "a.py",
                    "line": "1",
                    "issue": "Issue",
                    "severity": "major",
                    "category": "clean_code",
                },
            ],
        }

        from_dict_result = FindingGroup.from_dict(data)
        model_validate_result = FindingGroup.model_validate(data)

        assert from_dict_result == model_validate_result

    def test_backward_compat_findings_with_int_line(self) -> None:
        """from_dict() should handle findings with int line (checkpoint compat)."""
        data = {
            "description": "Legacy group",
            "findings": [
                {
                    "id": "F001",
                    "file": "a.py",
                    "line": 42,
                    "issue": "Issue",
                    "severity": "major",
                    "category": "clean_code",
                },
            ],
        }

        # FindingGroup.from_dict -> model_validate handles nested Finding
        # construction. Pydantic coerces int to str for the line field.
        group = FindingGroup.from_dict(data)
        assert group.findings[0].line == "42"


class TestGroupedReviewResultPydantic:
    """Pydantic-specific behavior tests for GroupedReviewResult."""

    def test_keyword_only_construction(self) -> None:
        """GroupedReviewResult must be constructed with keyword arguments."""
        result = GroupedReviewResult(
            groups=[
                FindingGroup(
                    description="G1",
                    findings=[
                        Finding(
                            id="F001",
                            file="a.py",
                            line="1",
                            issue="Issue",
                            severity="major",
                            category="clean_code",
                        ),
                    ],
                ),
            ]
        )
        assert len(result.groups) == 1

    def test_frozen_immutability(self) -> None:
        """GroupedReviewResult should reject attribute assignment."""
        result = GroupedReviewResult(groups=[])
        with pytest.raises(ValidationError):
            result.groups = []  # type: ignore[misc]

    def test_model_dump_round_trip(self) -> None:
        """model_dump/model_validate should round-trip GroupedReviewResult."""
        original = GroupedReviewResult(
            groups=[
                FindingGroup(
                    description="Group 1",
                    findings=[
                        Finding(
                            id="F001",
                            file="a.py",
                            line="1",
                            issue="Issue 1",
                            severity="major",
                            category="clean_code",
                        ),
                    ],
                ),
                FindingGroup(
                    description="Group 2",
                    findings=[
                        Finding(
                            id="F002",
                            file="b.py",
                            line="2",
                            issue="Issue 2",
                            severity="critical",
                            category="security",
                            fix_hint="Fix this now",
                        ),
                    ],
                ),
            ]
        )

        dumped = original.model_dump()
        restored = GroupedReviewResult.model_validate(dumped)

        assert restored == original
        assert restored.total_count == 2
        assert restored.groups[1].findings[0].fix_hint == "Fix this now"

    def test_to_dict_is_model_dump_exclude_none(self) -> None:
        """to_dict() should be equivalent to model_dump(exclude_none=True)."""
        result = GroupedReviewResult(
            groups=[
                FindingGroup(
                    description="G1",
                    findings=[
                        Finding(
                            id="F001",
                            file="a.py",
                            line="1",
                            issue="Issue",
                            severity="major",
                            category="clean_code",
                        ),
                    ],
                ),
            ]
        )

        assert result.to_dict() == result.model_dump(exclude_none=True)

    def test_from_dict_is_model_validate(self) -> None:
        """from_dict() should produce the same result as model_validate."""
        data = {
            "groups": [
                {
                    "description": "G1",
                    "findings": [
                        {
                            "id": "F001",
                            "file": "a.py",
                            "line": "1",
                            "issue": "Issue",
                            "severity": "major",
                            "category": "clean_code",
                        },
                    ],
                },
            ]
        }

        from_dict_result = GroupedReviewResult.from_dict(data)
        model_validate_result = GroupedReviewResult.model_validate(data)

        assert from_dict_result == model_validate_result

    def test_backward_compat_checkpoint_dict(self) -> None:
        """from_dict() should handle checkpoint-style dicts with nested int lines."""
        checkpoint_data = {
            "groups": [
                {
                    "description": "Batch 1",
                    "findings": [
                        {
                            "id": "F001",
                            "file": "src/main.py",
                            "line": 10,
                            "issue": "Missing type hints",
                            "severity": "minor",
                            "category": "type_hints",
                        },
                        {
                            "id": "F002",
                            "file": "src/utils.py",
                            "line": 55,
                            "issue": "Security concern",
                            "severity": "critical",
                            "category": "security",
                            "fix_hint": "Use parameterized query",
                        },
                    ],
                },
            ]
        }

        result = GroupedReviewResult.from_dict(checkpoint_data)

        assert result.total_count == 2
        assert result.groups[0].findings[0].line == "10"
        assert result.groups[0].findings[1].line == "55"
        assert result.groups[0].findings[1].fix_hint == "Use parameterized query"

    def test_empty_groups(self) -> None:
        """GroupedReviewResult should work with empty groups list."""
        result = GroupedReviewResult(groups=[])
        assert result.total_count == 0
        assert result.all_findings == []
        assert result.to_dict() == {"groups": []}


class TestFixOutcomePydantic:
    """Pydantic-specific behavior tests for FixOutcome."""

    def test_keyword_only_construction(self) -> None:
        """FixOutcome must be constructed with keyword arguments."""
        outcome = FixOutcome(
            id="F001",
            outcome="fixed",
            explanation="Done",
        )
        assert outcome.id == "F001"
        assert outcome.outcome == "fixed"
        assert outcome.explanation == "Done"

    def test_frozen_immutability(self) -> None:
        """FixOutcome should reject attribute assignment (frozen model)."""
        outcome = FixOutcome(
            id="F001",
            outcome="fixed",
            explanation="Done",
        )
        with pytest.raises(ValidationError):
            outcome.outcome = "blocked"  # type: ignore[misc]

    def test_model_dump_round_trip(self) -> None:
        """model_dump/model_validate should round-trip FixOutcome."""
        original = FixOutcome(
            id="F001",
            outcome="blocked",
            explanation="Cannot fix due to external dependency",
        )

        dumped = original.model_dump()
        restored = FixOutcome.model_validate(dumped)

        assert restored == original

    def test_to_dict_equals_model_dump(self) -> None:
        """FixOutcome.to_dict() should equal model_dump() (no optional fields)."""
        outcome = FixOutcome(
            id="F001",
            outcome="deferred",
            explanation="Needs more context",
        )

        # FixOutcome has no optional fields, so model_dump() == to_dict()
        assert outcome.to_dict() == outcome.model_dump()

    def test_from_dict_is_model_validate(self) -> None:
        """from_dict() should produce the same result as model_validate."""
        data = {
            "id": "F001",
            "outcome": "fixed",
            "explanation": "Resolved",
        }

        from_dict_result = FixOutcome.from_dict(data)
        model_validate_result = FixOutcome.model_validate(data)

        assert from_dict_result == model_validate_result

    def test_invalid_outcome_rejected(self) -> None:
        """FixOutcome should reject invalid outcome values via Literal validation."""
        with pytest.raises(ValidationError):
            FixOutcome(
                id="F001",
                outcome="skipped",  # type: ignore[arg-type]
                explanation="Invalid",
            )

    def test_missing_required_field_rejected(self) -> None:
        """FixOutcome should reject construction with missing required fields."""
        with pytest.raises(ValidationError):
            FixOutcome(  # type: ignore[call-arg]
                id="F001",
                outcome="fixed",
                # explanation is missing
            )
