"""Progress events for the Refuel Workflow.

This module defines all event types emitted during refuel workflow execution.
"""

from __future__ import annotations

from dataclasses import dataclass

from maverick.workflows.refuel.models import (
    GitHubIssue,
    IssueProcessingResult,
    RefuelInputs,
    RefuelResult,
)

__all__ = [
    "RefuelStarted",
    "IssueProcessingStarted",
    "IssueProcessingCompleted",
    "RefuelCompleted",
    "RefuelProgressEvent",
]


@dataclass(frozen=True, slots=True)
class RefuelStarted:
    """Event emitted when refuel workflow starts.

    Attributes:
        inputs: Workflow input configuration.
        issues_found: Number of matching issues.
    """

    inputs: RefuelInputs
    issues_found: int


@dataclass(frozen=True, slots=True)
class IssueProcessingStarted:
    """Event emitted when issue processing begins.

    Attributes:
        issue: Issue being processed.
        index: Current index (1-based) of this issue in the processing queue.
        total: Total issues to process.
    """

    issue: GitHubIssue
    index: int
    total: int


@dataclass(frozen=True, slots=True)
class IssueProcessingCompleted:
    """Event emitted when issue processing completes.

    Attributes:
        result: Processing outcome.
    """

    result: IssueProcessingResult


@dataclass(frozen=True, slots=True)
class RefuelCompleted:
    """Event emitted when refuel workflow completes.

    Attributes:
        result: Aggregate workflow result.
    """

    result: RefuelResult


# Union type for event handling
RefuelProgressEvent = (
    RefuelStarted | IssueProcessingStarted | IssueProcessingCompleted | RefuelCompleted
)
