"""Maverick Models Module.

Exports data models for CodeReviewerAgent, ImplementerAgent, and IssueFixerAgent.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__: list[str] = []

try:
    from maverick.models.review import (
        ReviewContext,
        ReviewFinding,
        ReviewResult,
        ReviewSeverity,
        UsageStats,
    )
    __all__.extend([
        "ReviewSeverity",
        "ReviewFinding",
        "ReviewResult",
        "ReviewContext",
        "UsageStats",
    ])
except ImportError:
    logger.debug("Review models not yet available")

try:
    from maverick.models.implementation import (
        ChangeType,
        FileChange,
        Task,
        TaskStatus,
        ValidationResult,
        ValidationStep,
    )
    __all__.extend([
        "TaskStatus",
        "ChangeType",
        "ValidationStep",
        "Task",
        "FileChange",
        "ValidationResult",
    ])
except ImportError:
    logger.debug("Implementation models not yet available")

try:
    from maverick.models.issue_fix import (
        FixResult,
        IssueFixerContext,
    )
    __all__.extend([
        "FixResult",
        "IssueFixerContext",
    ])
except ImportError:
    logger.debug("Issue fix models not yet available")
