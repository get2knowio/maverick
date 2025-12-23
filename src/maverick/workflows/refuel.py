"""Refuel Workflow compatibility shim.

This module provides backwards compatibility for imports from the old monolithic
refuel.py module. All implementation has been moved to the refuel/ package.

Deprecated: Import from maverick.workflows.refuel package instead.
    from maverick.workflows.refuel import RefuelWorkflow, RefuelInputs
"""

from __future__ import annotations

# Re-export DSL dependencies for test mocking compatibility
from maverick.dsl.serialization.executor import WorkflowFileExecutor  # noqa: F401

# Re-export all public names from the refuel package
from maverick.workflows.refuel.events import (
    IssueProcessingCompleted,
    IssueProcessingStarted,
    RefuelCompleted,
    RefuelProgressEvent,
    RefuelStarted,
)
from maverick.workflows.refuel.models import (
    GitHubIssue,
    IssueProcessingResult,
    IssueStatus,
    RefuelConfig,
    RefuelInputs,
    RefuelResult,
    RefuelStepName,
)
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
    # Workflow
    "RefuelWorkflow",
]
