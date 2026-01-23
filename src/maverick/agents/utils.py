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


def extract_streaming_text(message: Any) -> str:
    """Extract text for streaming display, including partial tokens and tool activity.

    This function handles both:
    - StreamEvent messages (token-by-token streaming via include_partial_messages=True)
    - AssistantMessage (complete messages with TextBlock and ToolUseBlock)

    Args:
        message: Message object from Claude SDK (StreamEvent, AssistantMessage, etc.)

    Returns:
        Formatted text suitable for streaming display. Includes:
        - Token deltas from StreamEvent (character-by-character)
        - Text content from TextBlock
        - Tool activity from ToolUseBlock (e.g., "> Reading src/file.py")
        - Empty string if no displayable content
    """
    if message is None:
        return ""

    msg_type = type(message).__name__

    # Handle StreamEvent (partial messages from include_partial_messages=True)
    # This provides true token-by-token streaming like a chat interface
    # SDK types.py shows: StreamEvent.event is dict[str, Any]
    if msg_type == "StreamEvent":
        event = getattr(message, "event", None)
        if not isinstance(event, dict):
            return ""

        event_type = event.get("type", "")

        # content_block_delta contains the streaming token
        if event_type == "content_block_delta":
            delta = event.get("delta")
            if not isinstance(delta, dict):
                return ""
            return str(delta.get("text", ""))

        # content_block_start may contain initial text for text blocks
        if event_type == "content_block_start":
            content_block = event.get("content_block")
            if not isinstance(content_block, dict):
                return ""
            # Only extract text from text blocks, not tool_use blocks
            if content_block.get("type") == "text":
                return str(content_block.get("text", ""))

        # Other stream events (message_start, message_stop, etc.) don't have text
        return ""

    # Handle AssistantMessage with content blocks (complete messages)
    # NOTE: With include_partial_messages=True, text content is already streamed
    # via StreamEvent deltas above. We only extract ToolUseBlock content here
    # to avoid duplicate text output. TextBlock content is intentionally skipped.
    if not hasattr(message, "content"):
        return ""

    text_parts = []
    for block in message.content:
        block_type = type(block).__name__

        # Skip TextBlock - text was already streamed via StreamEvent deltas
        # Including it here would cause duplicate output

        # ToolUseBlock - format tool activity for display
        if block_type == "ToolUseBlock":
            tool_name = getattr(block, "name", "unknown")
            tool_input = getattr(block, "input", {})

            # Format based on tool type with emoji prefixes for visual scanning
            tool_text = _format_tool_call(tool_name, tool_input)
            if tool_text:
                text_parts.append(tool_text)

        # ToolResultBlock - format tool output for display (especially Task/subagent)
        elif block_type == "ToolResultBlock":
            tool_name = getattr(block, "tool_use_id", "")
            content = getattr(block, "content", "")

            # For Task results (subagent output), display a completion indicator
            # The actual result content can be lengthy, so we summarize
            if content:
                # Truncate long results for display
                result_preview = str(content)[:200]
                if len(str(content)) > 200:
                    result_preview += "..."
                text_parts.append(f"\n✅ Done: {result_preview}")

    return "\n".join(text_parts)


def _shorten_path(path: str, max_length: int = 50) -> str:
    """Shorten a file path for display.

    Args:
        path: Full file path
        max_length: Maximum length before truncation

    Returns:
        Shortened path, keeping the filename and truncating the middle
    """
    if len(path) <= max_length:
        return path

    # Keep the last part (filename) and truncate the beginning
    parts = path.split("/")
    if len(parts) <= 2:
        return path

    filename = parts[-1]
    if len(filename) >= max_length - 4:
        return "..." + filename[-(max_length - 3) :]

    # Build path from end until we hit the limit
    result_parts = [filename]
    remaining = max_length - len(filename) - 4  # 4 for ".../""

    for part in reversed(parts[:-1]):
        if len(part) + 1 <= remaining:  # +1 for /
            result_parts.insert(0, part)
            remaining -= len(part) + 1
        else:
            break

    return ".../" + "/".join(result_parts)


# Tool emoji mapping for visual scanning in streaming output
_TOOL_EMOJIS: dict[str, str] = {
    "Read": "\U0001F4D6",  # 📖
    "Write": "\U0001F4DD",  # 📝
    "Edit": "\u270F\uFE0F",  # ✏️
    "Glob": "\U0001F50D",  # 🔍
    "Grep": "\U0001F50D",  # 🔍
    "Bash": "\U0001F4BB",  # 💻
    "Task": "\U0001F916",  # 🤖
    "WebFetch": "\U0001F310",  # 🌐
    "WebSearch": "\U0001F310",  # 🌐
}
_DEFAULT_TOOL_EMOJI = "\U0001F527"  # 🔧


def _format_tool_call(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Format a tool call for streaming display with emoji prefix.

    Uses emoji prefixes for quick visual scanning of tool activity.
    Format: "\\nemoji ToolName: key_parameter" (newline prefix ensures own line)

    Args:
        tool_name: Name of the tool being called
        tool_input: Input parameters for the tool

    Returns:
        Formatted tool call string with leading newline, or empty string if
        no meaningful display. The newline ensures tool calls always start
        on their own line in streaming output.
    """
    emoji = _TOOL_EMOJIS.get(tool_name, _DEFAULT_TOOL_EMOJI)

    if tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        if file_path:
            short_path = _shorten_path(file_path)
            return f"\n{emoji} Read: {short_path}"
        return ""

    if tool_name == "Write":
        file_path = tool_input.get("file_path", "")
        if file_path:
            short_path = _shorten_path(file_path)
            return f"\n{emoji} Write: {short_path}"
        return ""

    if tool_name == "Edit":
        file_path = tool_input.get("file_path", "")
        if file_path:
            short_path = _shorten_path(file_path)
            return f"\n{emoji} Edit: {short_path}"
        return ""

    if tool_name == "Glob":
        pattern = tool_input.get("pattern", "")
        return f"\n{emoji} Glob: {pattern}"

    if tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        return f"\n{emoji} Grep: {pattern}"

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        # Truncate long commands (80 chars like claude-stream-format)
        if len(command) > 80:
            command = command[:77] + "..."
        return f"\n{emoji} Bash: {command}"

    if tool_name == "Task":
        description = tool_input.get("description", "")
        return f"\n{emoji} Task: {description}"

    if tool_name in ("WebFetch", "WebSearch"):
        url = tool_input.get("url", "")
        query = tool_input.get("query", "")
        param = url or query
        if len(param) > 60:
            param = param[:57] + "..."
        return f"\n{emoji} {tool_name}: {param}"

    # Generic fallback for other tools
    return f"\n{emoji} {tool_name}"


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
