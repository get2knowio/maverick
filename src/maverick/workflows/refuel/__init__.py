"""Refuel Workflow package.

This package provides the Refuel workflow implementation which orchestrates
tech-debt resolution by discovering GitHub issues, processing them, and creating PRs.

The public API is re-exported from this module to maintain backwards
compatibility with imports like:
    from maverick.workflows.refuel import RefuelWorkflow, RefuelInputs
"""

from __future__ import annotations

# Re-export DSL dependencies for test mocking compatibility
from maverick.dsl.serialization.executor import WorkflowFileExecutor  # noqa: F401

# Import events
from maverick.workflows.refuel.events import (
    IssueProcessingCompleted,
    IssueProcessingStarted,
    RefuelCompleted,
    RefuelProgressEvent,
    RefuelStarted,
)

# Import helpers
from maverick.workflows.refuel.helpers import convert_runner_issue_to_workflow_issue

# Import models
from maverick.workflows.refuel.models import (
    GitHubIssue,
    IssueProcessingResult,
    IssueStatus,
    RefuelConfig,
    RefuelInputs,
    RefuelResult,
    RefuelStepName,
)

# Import workflow
from maverick.workflows.refuel.workflow import RefuelWorkflow

__all__ = [
    # Data structures
    "GitHubIssue",
    "IssueStatus",
    "RefuelStepName",
    "RefuelInputs",
    "IssueProcessingResult",
    "RefuelResult",
    # Configuration
    "RefuelConfig",
    # Progress Events
    "RefuelStarted",
    "IssueProcessingStarted",
    "IssueProcessingCompleted",
    "RefuelCompleted",
    "RefuelProgressEvent",
    # Helpers
    "convert_runner_issue_to_workflow_issue",
    # Workflow
    "RefuelWorkflow",
    # DSL (for test mocking compatibility)
    "WorkflowFileExecutor",
]
