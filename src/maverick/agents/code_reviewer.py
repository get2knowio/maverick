"""Backwards compatibility shim for CodeReviewerAgent.

This module provides backwards compatibility for code that imports from
the old location. All functionality has been moved to the
maverick.agents.code_reviewer package.

For new code, please import from the package:
    from maverick.agents.code_reviewer import CodeReviewerAgent
"""

from __future__ import annotations

# Re-export everything from the new package location
from maverick.agents.code_reviewer import (  # type: ignore[attr-defined]
    DEFAULT_BASE_BRANCH,
    MAX_DIFF_FILES,
    MAX_DIFF_LINES,
    MAX_TOKENS_PER_CHUNK,
    SYSTEM_PROMPT,
    CodeReviewerAgent,
)

__all__ = [
    "CodeReviewerAgent",
    "DEFAULT_BASE_BRANCH",
    "MAX_DIFF_FILES",
    "MAX_DIFF_LINES",
    "MAX_TOKENS_PER_CHUNK",
    "SYSTEM_PROMPT",
]
