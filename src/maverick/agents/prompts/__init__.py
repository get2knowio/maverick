"""Prompt templates and schemas for agents.

This package provides:
- reviewer_output: Structured JSON output schema for code reviewers
- review_fixer: Accountability-focused system prompt for the review fixer agent
"""

from __future__ import annotations

from maverick.agents.prompts.review_fixer import (
    INVALID_JUSTIFICATIONS,
    PREVIOUS_ATTEMPT_WARNING,
    REVIEW_FIXER_SYSTEM_PROMPT,
    VALID_BLOCKED_REASONS,
    format_system_prompt,
)
from maverick.agents.prompts.reviewer_output import (
    REVIEWER_OUTPUT_SCHEMA,
    SPEC_REVIEWER_ID_PREFIX,
    TECH_REVIEWER_ID_PREFIX,
)

__all__ = [
    "INVALID_JUSTIFICATIONS",
    "PREVIOUS_ATTEMPT_WARNING",
    "REVIEW_FIXER_SYSTEM_PROMPT",
    "REVIEWER_OUTPUT_SCHEMA",
    "SPEC_REVIEWER_ID_PREFIX",
    "TECH_REVIEWER_ID_PREFIX",
    "VALID_BLOCKED_REASONS",
    "format_system_prompt",
]
