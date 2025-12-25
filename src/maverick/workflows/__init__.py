"""Maverick Workflows Module.

Exports workflow orchestrators for multi-stage development processes.
"""

from __future__ import annotations

from maverick.logging import get_logger

logger = get_logger(__name__)

__all__: list[str] = []

try:
    from maverick.workflows.base import WorkflowDSLMixin

    __all__.extend(["WorkflowDSLMixin"])
except ImportError as e:
    if "base" in str(e).lower():
        logger.debug("Workflow base not yet available")
    else:
        raise  # Re-raise unexpected import errors

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
        FlyConfig,
        FlyInputs,
        FlyProgressEvent,
        FlyResult,
        FlyStageCompleted,
        FlyStageStarted,
        FlyWorkflow,
        FlyWorkflowCompleted,
        FlyWorkflowFailed,
        FlyWorkflowStarted,
        WorkflowStage,
        WorkflowState,
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

try:
    from maverick.workflows.refuel import (
        GitHubIssue,
        IssueProcessingCompleted,
        IssueProcessingResult,
        IssueProcessingStarted,
        IssueStatus,
        RefuelCompleted,
        RefuelConfig,
        RefuelInputs,
        RefuelProgressEvent,
        RefuelResult,
        RefuelStarted,
        RefuelWorkflow,
    )

    __all__.extend(
        [
            "RefuelWorkflow",
            "RefuelConfig",
            "RefuelInputs",
            "RefuelResult",
            "GitHubIssue",
            "IssueStatus",
            "IssueProcessingResult",
            "RefuelStarted",
            "IssueProcessingStarted",
            "IssueProcessingCompleted",
            "RefuelCompleted",
            "RefuelProgressEvent",
        ]
    )
except ImportError as e:
    if "refuel" in str(e).lower():
        logger.debug("Refuel workflow not yet available")
    else:
        raise  # Re-raise unexpected import errors
