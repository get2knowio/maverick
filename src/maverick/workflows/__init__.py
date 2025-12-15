"""Maverick Workflows Module.

Exports workflow orchestrators for multi-stage development processes.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__: list[str] = []

try:
    from maverick.workflows.validation import ValidationWorkflow, create_python_workflow

    __all__.extend(
        [
            "ValidationWorkflow",
            "create_python_workflow",
        ]
    )
except ImportError as e:
    if "validation" in str(e).lower():
        logger.debug("Validation workflow not yet available")
    else:
        raise  # Re-raise unexpected import errors

try:
    from maverick.workflows.fly import (
        FlyWorkflow,
        FlyConfig,
        FlyInputs,
        FlyResult,
        WorkflowStage,
        WorkflowState,
        FlyWorkflowStarted,
        FlyStageStarted,
        FlyStageCompleted,
        FlyWorkflowCompleted,
        FlyWorkflowFailed,
        FlyProgressEvent,
    )

    __all__.extend(
        [
            "FlyWorkflow",
            "FlyConfig",
            "FlyInputs",
            "FlyResult",
            "WorkflowStage",
            "WorkflowState",
            "FlyWorkflowStarted",
            "FlyStageStarted",
            "FlyStageCompleted",
            "FlyWorkflowCompleted",
            "FlyWorkflowFailed",
            "FlyProgressEvent",
        ]
    )
except ImportError as e:
    if "fly" in str(e).lower():
        logger.debug("Fly workflow not yet available")
    else:
        raise  # Re-raise unexpected import errors
