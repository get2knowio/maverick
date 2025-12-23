"""Fly Workflow package.

This package provides the Fly workflow implementation which orchestrates
the complete spec-based development workflow.

The public API is re-exported from this module to maintain backwards
compatibility with imports like:
    from maverick.workflows.fly import FlyWorkflow, FlyInputs
"""

from __future__ import annotations

# Import DSL utilities
from maverick.workflows.fly.dsl import (
    DSL_STEP_TO_STAGE,
    DslStepName,
    get_phase_names,
)

# Import events
from maverick.workflows.fly.events import (
    FlyPhaseCompleted,
    FlyPhaseStarted,
    FlyProgressEvent,
    FlyStageCompleted,
    FlyStageStarted,
    FlyWorkflowCompleted,
    FlyWorkflowFailed,
    FlyWorkflowStarted,
)

# Import models
from maverick.workflows.fly.models import (
    FlyConfig,
    FlyInputs,
    FlyResult,
    WorkflowStage,
    WorkflowState,
)

# Import workflow
from maverick.workflows.fly.workflow import FlyWorkflow

__all__ = [
    # Enums
    "WorkflowStage",
    "DslStepName",
    # Constants
    "DSL_STEP_TO_STAGE",
    # Configuration
    "FlyInputs",
    "FlyConfig",
    # State
    "WorkflowState",
    # Result
    "FlyResult",
    # Progress Events
    "FlyWorkflowStarted",
    "FlyStageStarted",
    "FlyStageCompleted",
    "FlyWorkflowCompleted",
    "FlyWorkflowFailed",
    "FlyPhaseStarted",
    "FlyPhaseCompleted",
    "FlyProgressEvent",
    # Helper Functions
    "get_phase_names",
    # Workflow
    "FlyWorkflow",
]
