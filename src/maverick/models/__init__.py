"""Maverick Models Module.

Exports data models for CodeReviewerAgent, ImplementerAgent, and IssueFixerAgent.
"""

from __future__ import annotations

from maverick.logging import get_logger

logger = get_logger(__name__)

__all__: list[str] = []

try:
    from maverick.models.review import (
        ReviewContext,
        ReviewFinding,
        ReviewResult,
        ReviewSeverity,
        UsageStats,
    )

    __all__.extend(
        [
            "ReviewSeverity",
            "ReviewFinding",
            "ReviewResult",
            "ReviewContext",
            "UsageStats",
        ]
    )
except ImportError as e:
    if "review" in str(e).lower():
        logger.debug("Review models not yet available")
    else:
        raise  # Re-raise unexpected import errors

try:
    from maverick.models.implementation import (
        ChangeType,
        FileChange,
        Task,
        TaskStatus,
        ValidationResult,
        ValidationStep,
    )

    __all__.extend(
        [
            "TaskStatus",
            "ChangeType",
            "ValidationStep",
            "Task",
            "FileChange",
            "ValidationResult",
        ]
    )
except ImportError as e:
    if "implementation" in str(e).lower():
        logger.debug("Implementation models not yet available")
    else:
        raise  # Re-raise unexpected import errors

try:
    from maverick.models.issue_fix import (
        FixResult,
        IssueFixerContext,
    )

    __all__.extend(
        [
            "FixResult",
            "IssueFixerContext",
        ]
    )
except ImportError as e:
    if "issue_fix" in str(e).lower():
        logger.debug("Issue fix models not yet available")
    else:
        raise  # Re-raise unexpected import errors

try:
    from maverick.models.validation import (
        DEFAULT_PYTHON_STAGES,
        ProgressUpdate,
        StageResult,
        StageStatus,
        ValidationStage,
        ValidationWorkflowConfig,
        ValidationWorkflowResult,
    )

    __all__.extend(
        [
            "StageStatus",
            "ValidationStage",
            "StageResult",
            "ValidationWorkflowResult",
            "ValidationWorkflowConfig",
            "ProgressUpdate",
            "DEFAULT_PYTHON_STAGES",
        ]
    )
except ImportError as e:
    if "validation" in str(e).lower():
        logger.debug("Validation models not yet available")
    else:
        raise  # Re-raise unexpected import errors
