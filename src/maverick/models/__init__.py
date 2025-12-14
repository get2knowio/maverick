"""Maverick Models Module.

Exports review-related data models for the CodeReviewerAgent.
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
