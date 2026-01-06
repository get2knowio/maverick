"""Unit tests for review_registry data models.

Tests the data models used for the review-fix accountability loop:
- Severity enum
- FindingStatus enum
- FindingCategory enum
- ReviewFinding frozen dataclass
- FixAttempt frozen dataclass
- TrackedFinding mutable dataclass
- IssueRegistry dataclass with query methods
"""

from __future__ import annotations

from datetime import datetime

import pytest

from maverick.models.review_registry import (
    FindingCategory,
    FindingStatus,
    FixAttempt,
    IssueRegistry,
    ReviewFinding,
    Severity,
    TrackedFinding,
)

# =============================================================================
# Enum Tests
# =============================================================================


class TestSeverityEnum:
    """Tests for Severity enum."""

    def test_severity_values(self) -> None:
        """Test all severity values are strings."""
        assert Severity.critical.value == "critical"
        assert Severity.major.value == "major"
        assert Severity.minor.value == "minor"

    def test_severity_is_string_enum(self) -> None:
        """Test severity enum inherits from str."""
        assert isinstance(Severity.critical, str)
        assert Severity.critical == "critical"

    def test_severity_iteration(self) -> None:
        """Test all severity levels are iterable."""
        severities = list(Severity)
        assert len(severities) == 3
        assert Severity.critical in severities
        assert Severity.major in severities
        assert Severity.minor in severities

    def test_severity_from_string(self) -> None:
        """Test creating severity from string value."""
        assert Severity("critical") == Severity.critical
        assert Severity("major") == Severity.major
        assert Severity("minor") == Severity.minor

    def test_severity_invalid_value_raises(self) -> None:
        """Test invalid string raises ValueError."""
        with pytest.raises(ValueError):
            Severity("invalid")


class TestFindingStatusEnum:
    """Tests for FindingStatus enum."""

    def test_status_values(self) -> None:
        """Test all status values are strings."""
        assert FindingStatus.open.value == "open"
        assert FindingStatus.fixed.value == "fixed"
        assert FindingStatus.blocked.value == "blocked"
        assert FindingStatus.deferred.value == "deferred"

    def test_status_is_string_enum(self) -> None:
        """Test status enum inherits from str."""
        assert isinstance(FindingStatus.open, str)
        assert FindingStatus.open == "open"

    def test_status_iteration(self) -> None:
        """Test all status values are iterable."""
        statuses = list(FindingStatus)
        assert len(statuses) == 4
        assert FindingStatus.open in statuses
        assert FindingStatus.fixed in statuses
        assert FindingStatus.blocked in statuses
        assert FindingStatus.deferred in statuses

    def test_status_from_string(self) -> None:
        """Test creating status from string value."""
        assert FindingStatus("open") == FindingStatus.open
        assert FindingStatus("fixed") == FindingStatus.fixed
        assert FindingStatus("blocked") == FindingStatus.blocked
        assert FindingStatus("deferred") == FindingStatus.deferred


class TestFindingCategoryEnum:
    """Tests for FindingCategory enum."""

    def test_category_values(self) -> None:
        """Test all category values are strings."""
        assert FindingCategory.security.value == "security"
        assert FindingCategory.correctness.value == "correctness"
        assert FindingCategory.performance.value == "performance"
        assert FindingCategory.style.value == "style"
        assert FindingCategory.spec_compliance.value == "spec_compliance"
        assert FindingCategory.maintainability.value == "maintainability"
        assert FindingCategory.other.value == "other"

    def test_category_iteration(self) -> None:
        """Test all categories are iterable."""
        categories = list(FindingCategory)
        assert len(categories) == 7
        assert FindingCategory.security in categories
        assert FindingCategory.correctness in categories

    def test_category_from_string(self) -> None:
        """Test creating category from string value."""
        assert FindingCategory("security") == FindingCategory.security
        assert FindingCategory("style") == FindingCategory.style


# =============================================================================
# ReviewFinding Tests
# =============================================================================


class TestReviewFinding:
    """Tests for ReviewFinding frozen dataclass."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating ReviewFinding with all fields."""
        finding = ReviewFinding(
            id="RS001",
            severity=Severity.critical,
            category=FindingCategory.security,
            title="SQL injection vulnerability",
            description="User input is directly concatenated into SQL query",
            file_path="src/api/users.py",
            line_start=87,
            line_end=92,
            suggested_fix="Use parameterized queries",
            source="spec_reviewer",
        )

        assert finding.id == "RS001"
        assert finding.severity == Severity.critical
        assert finding.category == FindingCategory.security
        assert finding.title == "SQL injection vulnerability"
        assert (
            finding.description == "User input is directly concatenated into SQL query"
        )
        assert finding.file_path == "src/api/users.py"
        assert finding.line_start == 87
        assert finding.line_end == 92
        assert finding.suggested_fix == "Use parameterized queries"
        assert finding.source == "spec_reviewer"

    def test_creation_with_optional_fields_as_none(self) -> None:
        """Test creating ReviewFinding with optional fields as None."""
        finding = ReviewFinding(
            id="RT001",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Missing error handling",
            description="Function does not handle exceptions",
            file_path=None,
            line_start=None,
            line_end=None,
            suggested_fix=None,
            source="tech_reviewer",
        )

        assert finding.id == "RT001"
        assert finding.file_path is None
        assert finding.line_start is None
        assert finding.line_end is None
        assert finding.suggested_fix is None

    def test_to_dict_produces_correct_output(self) -> None:
        """Test to_dict() produces correct dictionary representation."""
        finding = ReviewFinding(
            id="RS002",
            severity=Severity.minor,
            category=FindingCategory.style,
            title="Inconsistent naming",
            description="Variable uses camelCase instead of snake_case",
            file_path="src/utils/helpers.py",
            line_start=42,
            line_end=None,
            suggested_fix="Rename to user_name",
            source="spec_reviewer",
        )

        data = finding.to_dict()

        assert data["id"] == "RS002"
        assert data["severity"] == "minor"
        assert data["category"] == "style"
        assert data["title"] == "Inconsistent naming"
        assert data["description"] == "Variable uses camelCase instead of snake_case"
        assert data["file_path"] == "src/utils/helpers.py"
        assert data["line_start"] == 42
        assert data["line_end"] is None
        assert data["suggested_fix"] == "Rename to user_name"
        assert data["source"] == "spec_reviewer"

    def test_from_dict_roundtrip(self) -> None:
        """Test from_dict() correctly deserializes."""
        original = ReviewFinding(
            id="RT002",
            severity=Severity.critical,
            category=FindingCategory.security,
            title="Hardcoded credentials",
            description="API key is hardcoded in source",
            file_path="src/config.py",
            line_start=10,
            line_end=15,
            suggested_fix="Use environment variables",
            source="tech_reviewer",
        )

        data = original.to_dict()
        restored = ReviewFinding.from_dict(data)

        assert restored.id == original.id
        assert restored.severity == original.severity
        assert restored.category == original.category
        assert restored.title == original.title
        assert restored.description == original.description
        assert restored.file_path == original.file_path
        assert restored.line_start == original.line_start
        assert restored.line_end == original.line_end
        assert restored.suggested_fix == original.suggested_fix
        assert restored.source == original.source

    def test_immutability_frozen(self) -> None:
        """Test ReviewFinding is frozen (immutable)."""
        finding = ReviewFinding(
            id="RS003",
            severity=Severity.major,
            category=FindingCategory.correctness,
            title="Test finding",
            description="Test description",
            file_path="test.py",
            line_start=1,
            line_end=None,
            suggested_fix=None,
            source="spec_reviewer",
        )

        with pytest.raises(AttributeError):
            finding.severity = Severity.minor  # type: ignore[misc]


# =============================================================================
# FixAttempt Tests
# =============================================================================


class TestFixAttempt:
    """Tests for FixAttempt frozen dataclass."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating FixAttempt with all fields."""
        timestamp = datetime(2025, 1, 5, 10, 30, 0)
        attempt = FixAttempt(
            iteration=1,
            timestamp=timestamp,
            outcome=FindingStatus.fixed,
            justification=None,
            changes_made="Updated query to use parameterized format",
        )

        assert attempt.iteration == 1
        assert attempt.timestamp == timestamp
        assert attempt.outcome == FindingStatus.fixed
        assert attempt.justification is None
        assert attempt.changes_made == "Updated query to use parameterized format"

    def test_creation_blocked_with_justification(self) -> None:
        """Test creating blocked FixAttempt with justification."""
        timestamp = datetime(2025, 1, 5, 11, 0, 0)
        attempt = FixAttempt(
            iteration=2,
            timestamp=timestamp,
            outcome=FindingStatus.blocked,
            justification="Requires external service modification",
            changes_made=None,
        )

        assert attempt.outcome == FindingStatus.blocked
        assert attempt.justification == "Requires external service modification"
        assert attempt.changes_made is None

    def test_creation_deferred_with_justification(self) -> None:
        """Test creating deferred FixAttempt with justification."""
        timestamp = datetime(2025, 1, 5, 12, 0, 0)
        attempt = FixAttempt(
            iteration=1,
            timestamp=timestamp,
            outcome=FindingStatus.deferred,
            justification="Need more context from other files",
            changes_made=None,
        )

        assert attempt.outcome == FindingStatus.deferred
        assert attempt.justification == "Need more context from other files"

    def test_outcome_cannot_be_open(self) -> None:
        """Test that FixAttempt outcome cannot be 'open'."""
        timestamp = datetime(2025, 1, 5, 10, 0, 0)
        with pytest.raises(ValueError, match="outcome cannot be 'open'"):
            FixAttempt(
                iteration=1,
                timestamp=timestamp,
                outcome=FindingStatus.open,
                justification=None,
                changes_made=None,
            )

    def test_to_dict_produces_correct_output(self) -> None:
        """Test to_dict() produces correct dictionary."""
        timestamp = datetime(2025, 1, 5, 10, 30, 0)
        attempt = FixAttempt(
            iteration=1,
            timestamp=timestamp,
            outcome=FindingStatus.fixed,
            justification=None,
            changes_made="Fixed the issue",
        )

        data = attempt.to_dict()

        assert data["iteration"] == 1
        assert data["timestamp"] == "2025-01-05T10:30:00"
        assert data["outcome"] == "fixed"
        assert data["justification"] is None
        assert data["changes_made"] == "Fixed the issue"

    def test_from_dict_roundtrip(self) -> None:
        """Test to_dict() and from_dict() roundtrip."""
        timestamp = datetime(2025, 1, 5, 14, 0, 0)
        original = FixAttempt(
            iteration=2,
            timestamp=timestamp,
            outcome=FindingStatus.blocked,
            justification="Cannot fix without breaking API",
            changes_made=None,
        )

        data = original.to_dict()
        restored = FixAttempt.from_dict(data)

        assert restored.iteration == original.iteration
        assert restored.timestamp == original.timestamp
        assert restored.outcome == original.outcome
        assert restored.justification == original.justification
        assert restored.changes_made == original.changes_made

    def test_immutability_frozen(self) -> None:
        """Test FixAttempt is frozen (immutable)."""
        timestamp = datetime(2025, 1, 5, 10, 0, 0)
        attempt = FixAttempt(
            iteration=1,
            timestamp=timestamp,
            outcome=FindingStatus.fixed,
            justification=None,
            changes_made="Fixed",
        )

        with pytest.raises(AttributeError):
            attempt.outcome = FindingStatus.blocked  # type: ignore[misc]


# =============================================================================
# TrackedFinding Tests
# =============================================================================


class TestTrackedFinding:
    """Tests for TrackedFinding mutable dataclass."""

    @pytest.fixture
    def sample_finding(self) -> ReviewFinding:
        """Create a sample ReviewFinding for tests."""
        return ReviewFinding(
            id="RS001",
            severity=Severity.critical,
            category=FindingCategory.security,
            title="SQL injection",
            description="Vulnerable query",
            file_path="src/db.py",
            line_start=50,
            line_end=55,
            suggested_fix="Use parameterized queries",
            source="spec_reviewer",
        )

    def test_creation_with_default_status(self, sample_finding: ReviewFinding) -> None:
        """Test TrackedFinding defaults to open status."""
        tracked = TrackedFinding(finding=sample_finding)

        assert tracked.finding == sample_finding
        assert tracked.status == FindingStatus.open
        assert tracked.attempts == []
        assert tracked.github_issue_number is None

    def test_add_attempt_updates_status(self, sample_finding: ReviewFinding) -> None:
        """Test add_attempt() updates status to attempt outcome."""
        tracked = TrackedFinding(finding=sample_finding)
        attempt = FixAttempt(
            iteration=1,
            timestamp=datetime.now(),
            outcome=FindingStatus.fixed,
            justification=None,
            changes_made="Applied fix",
        )

        tracked.add_attempt(attempt)

        assert tracked.status == FindingStatus.fixed
        assert len(tracked.attempts) == 1
        assert tracked.attempts[0] == attempt

    def test_multiple_attempts_accumulate(self, sample_finding: ReviewFinding) -> None:
        """Test multiple add_attempt() calls accumulate attempts."""
        tracked = TrackedFinding(finding=sample_finding)

        attempt1 = FixAttempt(
            iteration=1,
            timestamp=datetime(2025, 1, 5, 10, 0, 0),
            outcome=FindingStatus.deferred,
            justification="Need more context",
            changes_made=None,
        )
        attempt2 = FixAttempt(
            iteration=2,
            timestamp=datetime(2025, 1, 5, 11, 0, 0),
            outcome=FindingStatus.fixed,
            justification=None,
            changes_made="Finally fixed it",
        )

        tracked.add_attempt(attempt1)
        assert tracked.status.value == "deferred"
        assert len(tracked.attempts) == 1

        tracked.add_attempt(attempt2)
        assert tracked.status.value == "fixed"
        assert len(tracked.attempts) == 2

    def test_to_dict_produces_correct_output(
        self, sample_finding: ReviewFinding
    ) -> None:
        """Test to_dict() produces correct dictionary."""
        tracked = TrackedFinding(
            finding=sample_finding,
            status=FindingStatus.blocked,
            github_issue_number=123,
        )
        attempt = FixAttempt(
            iteration=1,
            timestamp=datetime(2025, 1, 5, 10, 0, 0),
            outcome=FindingStatus.blocked,
            justification="Cannot fix",
            changes_made=None,
        )
        tracked.attempts.append(attempt)

        data = tracked.to_dict()

        assert data["finding"]["id"] == "RS001"
        assert data["status"] == "blocked"
        assert data["github_issue_number"] == 123
        assert len(data["attempts"]) == 1
        assert data["attempts"][0]["outcome"] == "blocked"

    def test_from_dict_roundtrip(self, sample_finding: ReviewFinding) -> None:
        """Test to_dict() and from_dict() roundtrip."""
        original = TrackedFinding(
            finding=sample_finding,
            status=FindingStatus.deferred,
            github_issue_number=456,
        )
        attempt = FixAttempt(
            iteration=1,
            timestamp=datetime(2025, 1, 5, 12, 0, 0),
            outcome=FindingStatus.deferred,
            justification="Deferred for later",
            changes_made=None,
        )
        original.add_attempt(attempt)

        data = original.to_dict()
        restored = TrackedFinding.from_dict(data)

        assert restored.finding.id == original.finding.id
        assert restored.status == original.status
        assert restored.github_issue_number == original.github_issue_number
        assert len(restored.attempts) == 1
        assert restored.attempts[0].outcome == attempt.outcome

    def test_mutability_status_can_change(self, sample_finding: ReviewFinding) -> None:
        """Test TrackedFinding is mutable (status can change)."""
        tracked = TrackedFinding(finding=sample_finding)

        tracked.status = FindingStatus.fixed  # Should not raise

        assert tracked.status == FindingStatus.fixed


# =============================================================================
# IssueRegistry Tests
# =============================================================================


class TestIssueRegistry:
    """Tests for IssueRegistry dataclass."""

    def _create_tracked_finding(
        self,
        finding_id: str,
        severity: Severity,
        status: FindingStatus = FindingStatus.open,
    ) -> TrackedFinding:
        """Helper to create TrackedFinding with specified parameters."""
        finding = ReviewFinding(
            id=finding_id,
            severity=severity,
            category=FindingCategory.correctness,
            title=f"Finding {finding_id}",
            description=f"Description for {finding_id}",
            file_path="test.py",
            line_start=1,
            line_end=None,
            suggested_fix=None,
            source="spec_reviewer",
        )
        return TrackedFinding(finding=finding, status=status)

    def test_get_actionable_returns_open_critical_major(self) -> None:
        """Test get_actionable() returns only open/deferred critical/major."""
        registry = IssueRegistry(
            findings=[
                self._create_tracked_finding(
                    "RS001", Severity.critical, FindingStatus.open
                ),
                self._create_tracked_finding(
                    "RS002", Severity.major, FindingStatus.open
                ),
                self._create_tracked_finding(
                    "RS003", Severity.critical, FindingStatus.deferred
                ),
            ]
        )

        actionable = registry.get_actionable()

        assert len(actionable) == 3
        ids = {tf.finding.id for tf in actionable}
        assert ids == {"RS001", "RS002", "RS003"}

    def test_get_actionable_excludes_fixed(self) -> None:
        """Test get_actionable() excludes fixed findings."""
        registry = IssueRegistry(
            findings=[
                self._create_tracked_finding(
                    "RS001", Severity.critical, FindingStatus.fixed
                ),
                self._create_tracked_finding(
                    "RS002", Severity.major, FindingStatus.open
                ),
            ]
        )

        actionable = registry.get_actionable()

        assert len(actionable) == 1
        assert actionable[0].finding.id == "RS002"

    def test_get_actionable_excludes_blocked(self) -> None:
        """Test get_actionable() excludes blocked findings."""
        registry = IssueRegistry(
            findings=[
                self._create_tracked_finding(
                    "RS001", Severity.critical, FindingStatus.blocked
                ),
                self._create_tracked_finding(
                    "RS002", Severity.major, FindingStatus.open
                ),
            ]
        )

        actionable = registry.get_actionable()

        assert len(actionable) == 1
        assert actionable[0].finding.id == "RS002"

    def test_get_actionable_excludes_minor(self) -> None:
        """Test get_actionable() excludes minor severity findings."""
        registry = IssueRegistry(
            findings=[
                self._create_tracked_finding(
                    "RS001", Severity.minor, FindingStatus.open
                ),
                self._create_tracked_finding(
                    "RS002", Severity.major, FindingStatus.open
                ),
            ]
        )

        actionable = registry.get_actionable()

        assert len(actionable) == 1
        assert actionable[0].finding.id == "RS002"

    def test_get_for_issues_returns_blocked(self) -> None:
        """Test get_for_issues() returns blocked findings."""
        registry = IssueRegistry(
            findings=[
                self._create_tracked_finding(
                    "RS001", Severity.critical, FindingStatus.blocked
                ),
            ]
        )

        for_issues = registry.get_for_issues()

        assert len(for_issues) == 1
        assert for_issues[0].finding.id == "RS001"

    def test_get_for_issues_returns_deferred_after_max(self) -> None:
        """Test get_for_issues() returns deferred after max iterations."""
        registry = IssueRegistry(
            findings=[
                self._create_tracked_finding(
                    "RS001", Severity.major, FindingStatus.deferred
                ),
            ],
            current_iteration=3,
            max_iterations=3,
        )

        for_issues = registry.get_for_issues()

        assert len(for_issues) == 1
        assert for_issues[0].finding.id == "RS001"

    def test_get_for_issues_excludes_deferred_before_max(self) -> None:
        """Test get_for_issues() excludes deferred before max iterations."""
        registry = IssueRegistry(
            findings=[
                self._create_tracked_finding(
                    "RS001", Severity.major, FindingStatus.deferred
                ),
            ],
            current_iteration=1,
            max_iterations=3,
        )

        for_issues = registry.get_for_issues()

        assert len(for_issues) == 0

    def test_get_for_issues_returns_minor(self) -> None:
        """Test get_for_issues() returns open minor severity findings."""
        registry = IssueRegistry(
            findings=[
                self._create_tracked_finding(
                    "RS001", Severity.minor, FindingStatus.open
                ),
            ]
        )

        for_issues = registry.get_for_issues()

        assert len(for_issues) == 1
        assert for_issues[0].finding.id == "RS001"

    def test_should_continue_true_with_actionable(self) -> None:
        """Test should_continue is True when actionable items exist."""
        registry = IssueRegistry(
            findings=[
                self._create_tracked_finding(
                    "RS001", Severity.critical, FindingStatus.open
                ),
            ],
            current_iteration=0,
            max_iterations=3,
        )

        assert registry.should_continue is True

    def test_should_continue_false_at_max_iterations(self) -> None:
        """Test should_continue is False at max iterations."""
        registry = IssueRegistry(
            findings=[
                self._create_tracked_finding(
                    "RS001", Severity.critical, FindingStatus.open
                ),
            ],
            current_iteration=3,
            max_iterations=3,
        )

        assert registry.should_continue is False

    def test_should_continue_false_no_actionable(self) -> None:
        """Test should_continue is False with no actionable items."""
        registry = IssueRegistry(
            findings=[
                self._create_tracked_finding(
                    "RS001", Severity.critical, FindingStatus.fixed
                ),
            ],
            current_iteration=0,
            max_iterations=3,
        )

        assert registry.should_continue is False

    def test_increment_iteration(self) -> None:
        """Test increment_iteration() increases counter."""
        registry = IssueRegistry(current_iteration=0)

        registry.increment_iteration()

        assert registry.current_iteration == 1

        registry.increment_iteration()

        assert registry.current_iteration == 2

    def test_to_dict_produces_correct_output(self) -> None:
        """Test to_dict() produces correct dictionary."""
        registry = IssueRegistry(
            findings=[
                self._create_tracked_finding("RS001", Severity.critical),
            ],
            current_iteration=1,
            max_iterations=5,
        )

        data = registry.to_dict()

        assert len(data["findings"]) == 1
        assert data["findings"][0]["finding"]["id"] == "RS001"
        assert data["current_iteration"] == 1
        assert data["max_iterations"] == 5

    def test_from_dict_roundtrip(self) -> None:
        """Test to_dict() and from_dict() roundtrip."""
        original = IssueRegistry(
            findings=[
                self._create_tracked_finding("RS001", Severity.critical),
                self._create_tracked_finding(
                    "RS002", Severity.major, FindingStatus.fixed
                ),
            ],
            current_iteration=2,
            max_iterations=4,
        )

        data = original.to_dict()
        restored = IssueRegistry.from_dict(data)

        assert len(restored.findings) == 2
        assert restored.findings[0].finding.id == "RS001"
        assert restored.findings[1].finding.id == "RS002"
        assert restored.findings[1].status == FindingStatus.fixed
        assert restored.current_iteration == 2
        assert restored.max_iterations == 4

    def test_empty_registry(self) -> None:
        """Test empty registry behavior."""
        registry = IssueRegistry()

        assert registry.get_actionable() == []
        assert registry.get_for_issues() == []
        assert registry.should_continue is False
        assert registry.current_iteration == 0

    def test_from_dict_with_empty_findings(self) -> None:
        """Test from_dict() with empty findings list."""
        data = {
            "findings": [],
            "current_iteration": 0,
            "max_iterations": 3,
        }

        registry = IssueRegistry.from_dict(data)

        assert registry.findings == []
        assert registry.current_iteration == 0
        assert registry.max_iterations == 3

    def test_from_dict_with_defaults(self) -> None:
        """Test from_dict() uses defaults for missing keys."""
        data: dict[str, list[dict[str, object]]] = {"findings": []}

        registry = IssueRegistry.from_dict(data)

        assert registry.current_iteration == 0
        assert registry.max_iterations == 3
