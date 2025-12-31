"""Utility functions for agents.

This module provides shared utilities for agent implementations:
- Text extraction from Claude SDK message objects
- Usage extraction from Claude SDK messages
- Git file change detection

Avoiding direct imports of SDK types to maintain loose coupling.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from maverick.logging import get_logger
from maverick.models.implementation import ChangeType, FileChange

if TYPE_CHECKING:
    from maverick.agents.result import AgentUsage

logger = get_logger(__name__)


def get_zero_usage() -> AgentUsage:
    """Create an AgentUsage instance with all zeros.

    Provides a DRY way to create zero-initialized usage statistics
    for error cases and early returns.

    Returns:
        AgentUsage with all fields set to zero/None.
    """
    from maverick.agents.result import AgentUsage

    return AgentUsage(
        input_tokens=0,
        output_tokens=0,
        total_cost_usd=None,
        duration_ms=0,
    )


def extract_usage(messages: list[Any]) -> AgentUsage:
    """Extract usage statistics from SDK messages (FR-014).

    Searches for a ResultMessage in the message list and extracts
    token usage and timing information.

    Args:
        messages: List of messages from Claude SDK response.

    Returns:
        AgentUsage with token counts, cost, and timing.
        Returns zero usage if no ResultMessage found.
    """
    from maverick.agents.result import AgentUsage

    # Find ResultMessage for usage stats
    result_msg = None
    for msg in messages:
        if type(msg).__name__ == "ResultMessage":
            result_msg = msg
            break

    if result_msg is None:
        # No result message, return zeros
        return get_zero_usage()

    # Extract usage from ResultMessage
    usage = getattr(result_msg, "usage", None) or {}
    return AgentUsage(
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        total_cost_usd=getattr(result_msg, "total_cost_usd", None),
        duration_ms=getattr(result_msg, "duration_ms", 0),
    )


def extract_text(message: Any) -> str:
    """Extract text content from an AssistantMessage.

    Extracts plain text from an AssistantMessage object by iterating through
    its content blocks and concatenating text from TextBlock objects.

    Args:
        message: AssistantMessage object from Claude SDK

    Returns:
        Plain text content from all text blocks, concatenated with newlines.
        Returns empty string if message has no text content.
    """
    if message is None or not hasattr(message, "content"):
        return ""

    text_parts = []
    for block in message.content:
        # Check if this is a TextBlock by type name to avoid SDK imports
        if type(block).__name__ == "TextBlock" and hasattr(block, "text"):
            text_parts.append(block.text)

    return "\n".join(text_parts)


def extract_all_text(messages: list[Any]) -> str:
    """Extract text from all AssistantMessage objects in a list.

    Filters the message list to only AssistantMessage objects and extracts
    their text content, concatenating all text with double newlines.

    Args:
        messages: List of Message objects (may include UserMessage,
                 AssistantMessage, etc.)

    Returns:
        Combined text content from all AssistantMessage objects, separated
        by double newlines. Returns empty string if no AssistantMessages
        with text content are found.
    """
    text_parts = []
    for msg in messages:
        if msg is None:
            continue
        # Only extract from AssistantMessage types
        if type(msg).__name__ == "AssistantMessage":
            text = extract_text(msg)
            if text:
                text_parts.append(text)

    return "\n\n".join(text_parts)


async def detect_file_changes(cwd: Path) -> list[FileChange]:
    """Detect file changes from git status.

    Uses AsyncGitRepository to get diff statistics and converts them
    to FileChange objects for agent result reporting.

    Args:
        cwd: Working directory (repository root).

    Returns:
        List of FileChange objects for modified files.
        Returns empty list if changes cannot be detected.
    """
    from maverick.git import AsyncGitRepository

    try:
        repo = AsyncGitRepository(cwd)
        stats = await repo.diff_stats()
        return [
            FileChange(
                file_path=path,
                change_type=ChangeType.MODIFIED,
                lines_added=added,
                lines_removed=removed,
            )
            for path, (added, removed) in stats.per_file.items()
        ]
    except Exception as e:
        logger.warning("Could not detect file changes: %s", e)
        return []
