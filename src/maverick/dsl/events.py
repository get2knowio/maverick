"""Progress event definitions for workflow execution.

This module defines frozen dataclasses representing workflow execution events.
These events are emitted during workflow execution to track progress and state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from maverick.dsl.types import StepType


@dataclass(frozen=True, slots=True)
class StepStarted:
    """Event emitted when a workflow step begins execution.

    Attributes:
        step_name: Name of the step being started.
        step_type: Type of step (PYTHON, AGENT, etc.).
        timestamp: Unix timestamp when step started (defaults to current time).
    """

    step_name: str
    step_type: StepType
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class StepCompleted:
    """Event emitted when a workflow step completes execution.

    Attributes:
        step_name: Name of the step that completed.
        step_type: Type of step that completed.
        success: Whether the step completed successfully.
        duration_ms: Execution duration in milliseconds.
        timestamp: Unix timestamp when step completed (defaults to current time).
    """

    step_name: str
    step_type: StepType
    success: bool
    duration_ms: int
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class WorkflowStarted:
    """Event emitted when a workflow begins execution.

    Attributes:
        workflow_name: Name of the workflow being started.
        inputs: Input parameters provided to the workflow.
        timestamp: Unix timestamp when workflow started (defaults to current time).
    """

    workflow_name: str
    inputs: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class WorkflowCompleted:
    """Event emitted when a workflow completes execution.

    Attributes:
        workflow_name: Name of the workflow that completed.
        success: Whether the workflow completed successfully.
        total_duration_ms: Total execution duration in milliseconds.
        timestamp: Unix timestamp when workflow completed (defaults to current time).
    """

    workflow_name: str
    success: bool
    total_duration_ms: int
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class RollbackStarted:
    """Event emitted when rollback execution begins.

    Attributes:
        step_name: Name of the step whose rollback is being executed.
        timestamp: Unix timestamp when rollback started (defaults to current time).
    """

    step_name: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class RollbackCompleted:
    """Event emitted when a rollback completes.

    Attributes:
        step_name: Name of the step whose rollback completed.
        success: Whether the rollback executed without error.
        error: Error message if rollback failed.
        timestamp: Unix timestamp when rollback completed (defaults to current time).
    """

    step_name: str
    success: bool
    error: str | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class CheckpointSaved:
    """Event emitted when a checkpoint is saved.

    Attributes:
        step_name: Name of the checkpoint step.
        workflow_id: Unique identifier for this workflow run.
        timestamp: Unix timestamp when checkpoint was saved (defaults to current time).
    """

    step_name: str
    workflow_id: str
    timestamp: float = field(default_factory=time.time)


# Type alias for all progress events
ProgressEvent = (
    StepStarted
    | StepCompleted
    | WorkflowStarted
    | WorkflowCompleted
    | RollbackStarted
    | RollbackCompleted
    | CheckpointSaved
)
