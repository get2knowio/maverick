"""Shared prompt fragments for Maverick agents.

This package provides reusable prompt text blocks that are shared across
multiple agent system prompts. Each agent composes its own system prompt
by importing the shared fragments it needs.
"""

from __future__ import annotations

from maverick.agents.prompts.common import (
    CODE_QUALITY_PRINCIPLES,
    TOOL_USAGE_EDIT,
    TOOL_USAGE_GLOB,
    TOOL_USAGE_GREP,
    TOOL_USAGE_READ,
    TOOL_USAGE_TASK,
    TOOL_USAGE_WRITE,
)

__all__ = [
    "CODE_QUALITY_PRINCIPLES",
    "TOOL_USAGE_EDIT",
    "TOOL_USAGE_GLOB",
    "TOOL_USAGE_GREP",
    "TOOL_USAGE_READ",
    "TOOL_USAGE_TASK",
    "TOOL_USAGE_WRITE",
]
