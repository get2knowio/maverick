"""Event types for the Fly Workflow.

This module defines all event dataclasses and enums used to track
workflow progress and state changes during Fly workflow execution.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maverick.workflows.fly.models import FlyInputs, FlyResult, WorkflowState


@dataclass(frozen=True, slots=True)
class FlyWorkflowStarted:
    """Event emitted when fly workflow starts."""

    inputs: FlyInputs
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class FlyStageStarted:
    """Event emitted when a stage starts."""

    stage: Any  # WorkflowStage - imported in models to avoid cycle
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class FlyStageCompleted:
    """Event emitted when a stage completes."""

    stage: Any  # WorkflowStage - imported in models to avoid cycle
    result: Any  # Stage-specific result type
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class FlyWorkflowCompleted:
    """Event emitted when workflow completes successfully."""

    result: FlyResult
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class FlyWorkflowFailed:
    """Event emitted when workflow fails."""

    error: str
    state: WorkflowState
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class FlyPhaseStarted:
    """Event emitted when a phase starts execution.

    Used for phase-level task execution where Claude handles
    parallelization of [P] marked tasks within each phase.
    """

    phase_name: str
    phase_index: int
    total_phases: int
    task_count: int
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class FlyPhaseCompleted:
    """Event emitted when a phase completes execution."""

    phase_name: str
    phase_index: int
    success: bool
    tasks_completed: int
    tasks_failed: int
    timestamp: float = field(default_factory=time.time)


# Union type for event handling
FlyProgressEvent = (
    FlyWorkflowStarted
    | FlyStageStarted
    | FlyStageCompleted
    | FlyWorkflowCompleted
    | FlyWorkflowFailed
    | FlyPhaseStarted
    | FlyPhaseCompleted
)


__all__ = [
    "FlyWorkflowStarted",
    "FlyStageStarted",
    "FlyStageCompleted",
    "FlyWorkflowCompleted",
    "FlyWorkflowFailed",
    "FlyPhaseStarted",
    "FlyPhaseCompleted",
    "FlyProgressEvent",
]
