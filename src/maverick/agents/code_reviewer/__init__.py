"""CodeReviewerAgent package.

This package provides an automated code review agent that analyzes git diffs
and provides structured feedback across multiple review dimensions.

Public API:
    - CodeReviewerAgent: Main agent class
    - Constants: MAX_DIFF_LINES, MAX_DIFF_FILES, MAX_TOKENS_PER_CHUNK,
      DEFAULT_BASE_BRANCH
    - SYSTEM_PROMPT: Agent system prompt (for testing/inspection)
"""

from __future__ import annotations

from maverick.agents.code_reviewer.agent import CodeReviewerAgent
from maverick.agents.code_reviewer.constants import (
    DEFAULT_BASE_BRANCH,
    MAX_DIFF_FILES,
    MAX_DIFF_LINES,
    MAX_TOKENS_PER_CHUNK,
)
from maverick.agents.code_reviewer.prompts import SYSTEM_PROMPT

__all__ = [
    "CodeReviewerAgent",
    "DEFAULT_BASE_BRANCH",
    "MAX_DIFF_FILES",
    "MAX_DIFF_LINES",
    "MAX_TOKENS_PER_CHUNK",
    "SYSTEM_PROMPT",
]
