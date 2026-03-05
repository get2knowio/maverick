"""Utility functions for agents.

This module provides shared utilities for agent implementations:
- Tool call display formatting
- Git file change detection
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maverick.logging import get_logger
from maverick.models.implementation import ChangeType, FileChange

logger = get_logger(__name__)


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


# Prefix character for tool call display (Unicode L-bracket └)
_TOOL_PREFIX = "\u2514"


def _format_tool_call(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Format a tool call for streaming display with └ prefix.

    Uses └ prefix for visually distinct but unobtrusive tool activity display.
    Format: "└ ToolName: key_parameter\\n"

    Note: This output must be plain text (no Rich markup tags) because it flows
    through sentence-boundary text buffering that can split content mid-string.
    Rich markup like [dim]...[/dim] would be broken across buffer flushes,
    causing MarkupError. Styling is applied at the widget level via CSS classes.

    The trailing newline is critical: the sentence-boundary buffer splits at
    ": " (colon+space), which would break "└ Bash: make test" into two entries.
    The trailing newline ensures it is the last boundary in the buffer, so the
    entire tool call line is flushed as one piece. The newline is stripped by
    .rstrip() before display.

    Args:
        tool_name: Name of the tool being called
        tool_input: Input parameters for the tool

    Returns:
        Formatted tool call string with trailing newline, or empty string
        if no meaningful display.
    """
    if tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        if file_path:
            short_path = _shorten_path(file_path)
            return f"{_TOOL_PREFIX} Read: {short_path}\n"
        return ""

    if tool_name == "Write":
        file_path = tool_input.get("file_path", "")
        if file_path:
            short_path = _shorten_path(file_path)
            return f"{_TOOL_PREFIX} Write: {short_path}\n"
        return ""

    if tool_name == "Edit":
        file_path = tool_input.get("file_path", "")
        if file_path:
            short_path = _shorten_path(file_path)
            return f"{_TOOL_PREFIX} Edit: {short_path}\n"
        return ""

    if tool_name == "Glob":
        pattern = tool_input.get("pattern", "")
        return f"{_TOOL_PREFIX} Glob: {pattern}\n"

    if tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        return f"{_TOOL_PREFIX} Grep: {pattern}\n"

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        # Truncate long commands (80 chars like claude-stream-format)
        if len(command) > 80:
            command = command[:77] + "..."
        return f"{_TOOL_PREFIX} Bash: {command}\n"

    if tool_name == "Task":
        description = tool_input.get("description", "")
        return f"{_TOOL_PREFIX} Task: {description}\n"

    if tool_name in ("WebFetch", "WebSearch"):
        url = tool_input.get("url", "")
        query = tool_input.get("query", "")
        param = url or query
        if len(param) > 60:
            param = param[:57] + "..."
        return f"{_TOOL_PREFIX} {tool_name}: {param}\n"

    # Generic fallback for other tools
    return f"{_TOOL_PREFIX} {tool_name}\n"


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
