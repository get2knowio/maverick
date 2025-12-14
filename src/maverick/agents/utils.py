"""Utility functions for extracting data from Claude SDK message objects.

This module provides functions to extract text content from AssistantMessage
objects returned by the Claude Agent SDK, avoiding direct imports of SDK types
to maintain loose coupling.
"""

from __future__ import annotations

from typing import Any


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
