"""Simple models for unified review-fix workflow.

This module provides lightweight data structures for tracking code review
findings and fix outcomes. Designed for simplicity over the previous
complex IssueRegistry approach.

Finding, FindingGroup, GroupedReviewResult, and FixOutcome are Pydantic
BaseModel subclasses with ``ConfigDict(frozen=True)`` for immutability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

__all__ = [
    "Finding",
    "FindingGroup",
    "GroupedReviewResult",
    "FixOutcome",
    "FixAttempt",
    "TrackedFinding",
    "FindingTracker",
]

# -----------------------------------------------------------------------------
# Core Finding Models (Pydantic)
# -----------------------------------------------------------------------------


class Finding(BaseModel):
    """A single code review finding.

    Attributes:
        id: Unique identifier (e.g., "F001")
        file: File path relative to repo root
        line: Line number or range (e.g., "45" or "45-67")
        issue: Description of the problem
        severity: Severity level
        category: Classification of the issue type
        fix_hint: Optional suggestion for fixing
    """

    model_config = ConfigDict(frozen=True)

    id: str
    file: str
    line: str
    issue: str
    severity: Literal["critical", "major", "minor"]
    category: str
    fix_hint: str | None = None

    @field_validator("line", mode="before")
    @classmethod
    def _coerce_line_to_str(cls, v: object) -> str:
        """Coerce line to str for backward compat with int-valued checkpoints."""
        return str(v)

    def to_dict(self) -> dict[str, Any]:
        """Alias for ``model_dump()`` for backward compatibility."""
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Finding:
        """Create Finding from dictionary.

        Handles legacy data where ``line`` may be an int via the
        ``_coerce_line_to_str`` field validator.
        """
        return cls.model_validate(data)


class FindingGroup(BaseModel):
    """A group of findings that can be fixed independently.

    Findings within a group have no dependencies on each other and
    can be worked on in parallel.

    Attributes:
        description: Brief description of the group (e.g., "Batch 1").
        findings: List of findings in this group.
    """

    model_config = ConfigDict(frozen=True)

    description: str
    findings: list[Finding]

    def to_dict(self) -> dict[str, Any]:
        """Alias for ``model_dump()`` for backward compatibility."""
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FindingGroup:
        """Create FindingGroup from dictionary."""
        return cls.model_validate(data)


class GroupedReviewResult(BaseModel):
    """Result from the unified reviewer.

    Contains all findings grouped by parallelization opportunity.

    Renamed from ``ReviewResult`` to avoid collision with the Pydantic
    ``ReviewResult`` in ``maverick.models.review``.

    Attributes:
        groups: List of finding groups
    """

    model_config = ConfigDict(frozen=True)

    groups: list[FindingGroup]

    def to_dict(self) -> dict[str, Any]:
        """Alias for ``model_dump()`` for backward compatibility."""
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GroupedReviewResult:
        """Create GroupedReviewResult from dictionary."""
        return cls.model_validate(data)

    @property
    def all_findings(self) -> list[Finding]:
        """Get flat list of all findings across groups."""
        return [f for group in self.groups for f in group.findings]

    @property
    def total_count(self) -> int:
        """Total number of findings."""
        return sum(len(g.findings) for g in self.groups)


# Backward-compatible alias
ReviewResult = GroupedReviewResult


# -----------------------------------------------------------------------------
# Fix Outcome Models (Pydantic)
# -----------------------------------------------------------------------------


class FixOutcome(BaseModel):
    """Outcome of attempting to fix a single finding.

    Attributes:
        id: Finding ID this outcome refers to
        outcome: Result of the fix attempt
        explanation: Brief explanation of what happened
    """

    model_config = ConfigDict(frozen=True)

    id: str
    outcome: Literal["fixed", "blocked", "deferred"]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        """Alias for ``model_dump()`` for backward compatibility."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FixOutcome:
        """Create FixOutcome from dictionary."""
        return cls.model_validate(data)


# -----------------------------------------------------------------------------
# Tracking Models (remain as dataclasses — not agent output types)
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FixAttempt:
    """Record of a single fix attempt.

    Attributes:
        timestamp: When the attempt was made
        outcome: Result of the attempt
        explanation: Fixer's explanation
    """

    timestamp: datetime
    outcome: Literal["fixed", "blocked", "deferred"]
    explanation: str


@dataclass
class TrackedFinding:
    """A finding with its tracking state.

    Attributes:
        finding: The original finding
        status: Current status (open, fixed, blocked)
        attempts: History of fix attempts
    """

    finding: Finding
    status: Literal["open", "fixed", "blocked"] = "open"
    attempts: list[FixAttempt] = field(default_factory=list)


class FindingTracker:
    """Tracks findings and their fix status across iterations.

    Simple replacement for the complex IssueRegistry. Maintains state
    of each finding as fixes are attempted.

    Example:
        >>> tracker = FindingTracker(review_result)
        >>> findings = tracker.get_actionable_findings()
        >>> # ... run fixer ...
        >>> for outcome in outcomes:
        ...     tracker.record_outcome(outcome)
        >>> if tracker.is_complete():
        ...     print("All done!")
    """

    def __init__(self, review_result: GroupedReviewResult) -> None:
        """Initialize tracker from review result.

        Args:
            review_result: Result from unified reviewer
        """
        self._findings: dict[str, TrackedFinding] = {}
        for group in review_result.groups:
            for finding in group.findings:
                self._findings[finding.id] = TrackedFinding(finding=finding)
        self._groups = review_result.groups

    @property
    def total_count(self) -> int:
        """Total number of findings being tracked."""
        return len(self._findings)

    def get_finding(self, finding_id: str) -> TrackedFinding | None:
        """Get a tracked finding by ID."""
        return self._findings.get(finding_id)

    def get_open_findings(self) -> list[Finding]:
        """Get findings that have never been attempted."""
        return [tf.finding for tf in self._findings.values() if tf.status == "open"]

    def get_actionable_findings(self) -> list[Finding]:
        """Get findings that can be worked on (open or deferred for retry)."""
        actionable = []
        for tf in self._findings.values():
            if tf.status == "fixed" or tf.status == "blocked":
                continue
            elif tf.status == "open" and len(tf.attempts) < 3:
                actionable.append(tf.finding)
        return actionable

    def get_actionable_with_groups(self) -> list[FindingGroup]:
        """Get actionable findings preserving group structure.

        Returns groups containing only actionable findings, filtering
        out fixed/blocked items while maintaining parallelization hints.
        """
        actionable_ids = {f.id for f in self.get_actionable_findings()}
        result = []
        for group in self._groups:
            group_findings = [f for f in group.findings if f.id in actionable_ids]
            if group_findings:
                result.append(
                    FindingGroup(
                        description=group.description,
                        findings=group_findings,
                    )
                )
        return result

    def record_outcome(self, outcome: FixOutcome) -> None:
        """Record the result of a fix attempt.

        Args:
            outcome: The fix outcome to record

        Raises:
            KeyError: If finding ID not found
        """
        tf = self._findings.get(outcome.id)
        if tf is None:
            raise KeyError(f"Unknown finding ID: {outcome.id}")

        tf.attempts.append(
            FixAttempt(
                timestamp=datetime.now(),
                outcome=outcome.outcome,
                explanation=outcome.explanation,
            )
        )

        if outcome.outcome == "fixed":
            tf.status = "fixed"
        elif outcome.outcome == "blocked":
            tf.status = "blocked"

    def record_outcomes(self, outcomes: list[FixOutcome]) -> None:
        """Record multiple fix outcomes.

        Args:
            outcomes: List of fix outcomes to record
        """
        for outcome in outcomes:
            self.record_outcome(outcome)

    def get_fixed_count(self) -> int:
        """Count of fixed findings."""
        return sum(1 for tf in self._findings.values() if tf.status == "fixed")

    def get_blocked_count(self) -> int:
        """Count of blocked findings."""
        return sum(1 for tf in self._findings.values() if tf.status == "blocked")

    def get_unresolved(self) -> list[TrackedFinding]:
        """Get findings that weren't successfully fixed.

        Returns blocked items plus deferred items that exceeded retry limit.
        These should be converted to GitHub issues.
        """
        unresolved = []
        for tf in self._findings.values():
            if tf.status == "blocked" or (
                tf.status == "open" and len(tf.attempts) >= 3
            ):
                unresolved.append(tf)
            elif len(tf.attempts) > 0:
                last = tf.attempts[-1]
                if last.outcome == "deferred" and len(tf.attempts) >= 3:
                    unresolved.append(tf)
        return unresolved

    def is_complete(self) -> bool:
        """Check if all findings are resolved (fixed or blocked).

        Returns True when there are no more actionable findings.
        """
        return len(self.get_actionable_findings()) == 0

    def get_summary(self) -> dict[str, int]:
        """Get summary statistics."""
        fixed = 0
        blocked = 0
        deferred = 0
        open_count = 0

        for tf in self._findings.values():
            if tf.status == "fixed":
                fixed += 1
            elif tf.status == "blocked":
                blocked += 1
            elif len(tf.attempts) > 0 and tf.attempts[-1].outcome == "deferred":
                deferred += 1
            else:
                open_count += 1

        return {
            "total": len(self._findings),
            "fixed": fixed,
            "blocked": blocked,
            "deferred": deferred,
            "open": open_count,
        }
