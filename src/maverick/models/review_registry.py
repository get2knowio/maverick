"""Data models for the review-fix accountability loop.

This module defines data models for tracking review findings, fix attempts,
and the overall state of the review-fix loop. These models support serialization
for checkpoint persistence.

Models:
- Severity: Finding severity level enum
- FindingStatus: Status of a tracked finding enum
- FindingCategory: Category of the finding enum
- ReviewFinding: Individual finding from code review (frozen dataclass)
- FixAttempt: Record of an attempt to fix a finding (frozen dataclass)
- TrackedFinding: Mutable wrapper for tracking finding status
- IssueRegistry: Registry of all tracked findings with iteration state
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# =============================================================================
# Enums (T001)
# =============================================================================


class Severity(str, Enum):
    """Finding severity level."""

    critical = "critical"
    major = "major"
    minor = "minor"


class FindingStatus(str, Enum):
    """Status of a tracked finding."""

    open = "open"
    fixed = "fixed"
    blocked = "blocked"
    deferred = "deferred"


class FindingCategory(str, Enum):
    """Category of the finding."""

    security = "security"
    correctness = "correctness"
    performance = "performance"
    style = "style"
    spec_compliance = "spec_compliance"
    maintainability = "maintainability"
    other = "other"


# =============================================================================
# Data Models (T002-T006)
# =============================================================================


@dataclass(frozen=True, slots=True)
class ReviewFinding:
    """Individual finding from code review.

    Represents a single issue identified during spec or technical review.
    This is a frozen dataclass for immutability and memory efficiency.

    Attributes:
        id: Unique identifier (e.g., RS001 for spec, RT001 for tech).
        severity: Severity level of the finding.
        category: Category of the finding.
        title: Short title describing the issue.
        description: Detailed description of the issue.
        file_path: Path to the affected file (None if general issue).
        line_start: Starting line number (None if not applicable).
        line_end: Ending line number (None if not applicable).
        suggested_fix: Suggested fix for the issue (None if not provided).
        source: Source of the finding (spec_reviewer or tech_reviewer).
    """

    id: str
    severity: Severity
    category: FindingCategory
    title: str
    description: str
    file_path: str | None
    line_start: int | None
    line_end: int | None
    suggested_fix: str | None
    source: str  # "spec_reviewer" or "tech_reviewer"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation for serialization."""
        return {
            "id": self.id,
            "severity": self.severity.value,
            "category": self.category.value,
            "title": self.title,
            "description": self.description,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "suggested_fix": self.suggested_fix,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewFinding:
        """Create a ReviewFinding from a dictionary.

        Args:
            data: Dictionary with finding data.

        Returns:
            A new ReviewFinding instance.
        """
        return cls(
            id=data["id"],
            severity=Severity(data["severity"]),
            category=FindingCategory(data["category"]),
            title=data["title"],
            description=data["description"],
            file_path=data.get("file_path"),
            line_start=data.get("line_start"),
            line_end=data.get("line_end"),
            suggested_fix=data.get("suggested_fix"),
            source=data["source"],
        )


@dataclass(frozen=True, slots=True)
class FixAttempt:
    """Record of an attempt to fix a finding.

    Captures the outcome and details of a single fix attempt.
    The outcome can only be fixed, blocked, or deferred (not open).

    Attributes:
        iteration: The iteration number when this attempt was made.
        timestamp: When the attempt was made.
        outcome: Result of the attempt (fixed, blocked, or deferred only).
        justification: Explanation for blocked/deferred outcomes.
        changes_made: Description of changes made (for fixed outcomes).
    """

    iteration: int
    timestamp: datetime
    outcome: FindingStatus  # Only fixed, blocked, deferred allowed
    justification: str | None
    changes_made: str | None

    def __post_init__(self) -> None:
        """Validate that outcome is not 'open'."""
        if self.outcome == FindingStatus.open:
            raise ValueError("FixAttempt outcome cannot be 'open'")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation for serialization."""
        return {
            "iteration": self.iteration,
            "timestamp": self.timestamp.isoformat(),
            "outcome": self.outcome.value,
            "justification": self.justification,
            "changes_made": self.changes_made,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FixAttempt:
        """Create a FixAttempt from a dictionary.

        Args:
            data: Dictionary with attempt data.

        Returns:
            A new FixAttempt instance.
        """
        return cls(
            iteration=data["iteration"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            outcome=FindingStatus(data["outcome"]),
            justification=data.get("justification"),
            changes_made=data.get("changes_made"),
        )


@dataclass
class TrackedFinding:
    """Mutable wrapper for tracking finding status over time.

    This is NOT frozen because we need to track status changes and
    append fix attempts as the review-fix loop progresses.

    Attributes:
        finding: The immutable ReviewFinding being tracked.
        status: Current status (defaults to open).
        attempts: List of fix attempts made.
        github_issue_number: GitHub issue number if created.
    """

    finding: ReviewFinding
    status: FindingStatus = FindingStatus.open
    attempts: list[FixAttempt] = field(default_factory=list)
    github_issue_number: int | None = None

    def add_attempt(self, attempt: FixAttempt) -> None:
        """Add a fix attempt and update status.

        Args:
            attempt: The fix attempt to add.
        """
        self.attempts.append(attempt)
        self.status = attempt.outcome

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation for serialization."""
        return {
            "finding": self.finding.to_dict(),
            "status": self.status.value,
            "attempts": [a.to_dict() for a in self.attempts],
            "github_issue_number": self.github_issue_number,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrackedFinding:
        """Create a TrackedFinding from a dictionary.

        Args:
            data: Dictionary with tracked finding data.

        Returns:
            A new TrackedFinding instance.
        """
        return cls(
            finding=ReviewFinding.from_dict(data["finding"]),
            status=FindingStatus(data["status"]),
            attempts=[FixAttempt.from_dict(a) for a in data.get("attempts", [])],
            github_issue_number=data.get("github_issue_number"),
        )


@dataclass
class IssueRegistry:
    """Registry of all tracked findings with iteration state.

    Manages the collection of findings and tracks the current iteration
    of the review-fix loop.

    Attributes:
        findings: List of all tracked findings.
        current_iteration: Current iteration number (0-indexed).
        max_iterations: Maximum number of iterations allowed.
    """

    findings: list[TrackedFinding] = field(default_factory=list)
    current_iteration: int = 0
    max_iterations: int = 3

    def get_actionable(self) -> list[TrackedFinding]:
        """Get findings that should be fixed in the current iteration.

        Returns findings with:
        - Status in (open, deferred)
        - Severity in (critical, major)

        Returns:
            List of actionable tracked findings.
        """
        actionable_statuses = {FindingStatus.open, FindingStatus.deferred}
        actionable_severities = {Severity.critical, Severity.major}
        return [
            tf
            for tf in self.findings
            if tf.status in actionable_statuses
            and tf.finding.severity in actionable_severities
        ]

    def get_for_issues(self) -> list[TrackedFinding]:
        """Get findings that need GitHub issues created.

        Returns findings that are:
        - blocked
        - deferred after max iterations reached
        - minor severity (not worth fixing in current PR)

        Returns:
            List of findings needing GitHub issues.
        """
        result: list[TrackedFinding] = []
        for tf in self.findings:
            # Blocked findings always get issues
            is_blocked = tf.status == FindingStatus.blocked
            # Deferred findings get issues if we're at max iterations
            is_deferred_at_max = (
                tf.status == FindingStatus.deferred
                and self.current_iteration >= self.max_iterations
            )
            # Minor findings are deferred to issues
            is_minor_open = (
                tf.finding.severity == Severity.minor
                and tf.status == FindingStatus.open
            )
            if is_blocked or is_deferred_at_max or is_minor_open:
                result.append(tf)
        return result

    @property
    def should_continue(self) -> bool:
        """Check if the review-fix loop should continue.

        Returns True if:
        - There are actionable findings remaining
        - Current iteration is less than max_iterations

        Returns:
            Whether to continue the loop.
        """
        has_actionable = bool(self.get_actionable())
        under_max = self.current_iteration < self.max_iterations
        return has_actionable and under_max

    def increment_iteration(self) -> None:
        """Increment the current iteration counter."""
        self.current_iteration += 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation for checkpoint persistence."""
        return {
            "findings": [tf.to_dict() for tf in self.findings],
            "current_iteration": self.current_iteration,
            "max_iterations": self.max_iterations,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IssueRegistry:
        """Create an IssueRegistry from a dictionary.

        Args:
            data: Dictionary with registry data.

        Returns:
            A new IssueRegistry instance.
        """
        return cls(
            findings=[TrackedFinding.from_dict(tf) for tf in data.get("findings", [])],
            current_iteration=data.get("current_iteration", 0),
            max_iterations=data.get("max_iterations", 3),
        )
