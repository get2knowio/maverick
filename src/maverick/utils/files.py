"""File I/O and truncation utilities for Maverick.

This module provides safe file reading with truncation capabilities and
context preservation for managing large file content.
"""

from __future__ import annotations

from pathlib import Path

from maverick.logging import get_logger
from maverick.utils.text import truncate_line

__all__ = [
    "truncate_file",
    "_read_file_safely",
    "_read_conventions",
]

logger = get_logger(__name__)

# Default values
DEFAULT_MAX_FILE_LINES = 50000
DEFAULT_CONTEXT_LINES = 10
MAX_PARENT_SEARCH_DEPTH = 10


def _read_file_safely(
    path: Path, max_lines: int = DEFAULT_MAX_FILE_LINES
) -> tuple[str, bool]:
    """Read file with line limit to prevent memory issues.

    Args:
        path: Path to file to read.
        max_lines: Maximum lines to read (default 50000).

    Returns:
        Tuple of (content, was_truncated).
        - content: File content up to max_lines, with each line truncated at 2000 chars.
        - was_truncated: True if file exceeded max_lines.

    Note:
        Returns empty string and False if file doesn't exist or can't be read.
        Binary files (detected by null bytes in first 8KB) are skipped.
    """
    if not path.exists() or not path.is_file():
        return "", False

    # Check for binary content (null bytes in first 8KB)
    try:
        with path.open("rb") as f:
            sample = f.read(8192)
            if b"\x00" in sample:
                logger.debug("Skipping binary file: %s", path)
                return "", False
    except OSError:
        return "", False

    try:
        lines: list[str] = []
        was_truncated = False

        with path.open(encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    was_truncated = True
                    break
                # Truncate long lines and strip trailing newline
                lines.append(truncate_line(line.rstrip("\n\r")))

        return "\n".join(lines), was_truncated
    except OSError:
        logger.warning("Failed to read file: %s", path)
        return "", False


def _read_conventions(path: Path | None = None) -> str:
    """Read CLAUDE.md conventions file.

    Args:
        path: Explicit path to conventions file.
              If None, searches for CLAUDE.md in current directory and parents.

    Returns:
        Conventions file content, or empty string if not found.
    """
    if path is not None:
        content, _ = _read_file_safely(path)
        return content

    # Search for CLAUDE.md in current directory and parents
    search_path = Path.cwd()
    for _ in range(MAX_PARENT_SEARCH_DEPTH):  # Limit search depth
        claude_md = search_path / "CLAUDE.md"
        if claude_md.exists():
            content, _ = _read_file_safely(claude_md)
            return content
        parent = search_path.parent
        if parent == search_path:
            break
        search_path = parent

    return ""


def truncate_file(
    content: str,
    max_lines: int,
    around_lines: list[int] | None = None,
    *,
    context_lines: int = DEFAULT_CONTEXT_LINES,
) -> str:
    """Truncate file content with context preservation around specific lines.

    Preserves content around specified line numbers while truncating the rest.
    Uses "..." markers to indicate removed content.

    Args:
        content: Full file content to truncate.
        max_lines: Maximum total lines to keep.
        around_lines: Line numbers (1-indexed) to preserve context around.
                      If None, keeps first max_lines of the file.
        context_lines: Lines of context on each side of target lines (default 10).

    Returns:
        Truncated content with "..." markers where content was removed.

    Example:
        >>> content = "\\n".join(f"line {i}" for i in range(1, 101))
        >>> result = truncate_file(content, max_lines=30, around_lines=[50])
        >>> "line 50" in result
        True
        >>> "..." in result
        True
    """
    lines = content.splitlines()
    total_lines = len(lines)

    # If content fits, return as-is
    if total_lines <= max_lines:
        return content

    # If no specific lines to preserve, keep first max_lines
    if not around_lines:
        truncated = lines[:max_lines]
        truncated.append("...")
        truncated.append(f"[{total_lines - max_lines} more lines truncated]")
        return "\n".join(truncated)

    # Build preservation windows
    windows: list[tuple[int, int]] = []
    for target_line in around_lines:
        # Convert 1-indexed to 0-indexed
        idx = target_line - 1
        start = max(0, idx - context_lines)
        end = min(total_lines, idx + context_lines + 1)
        windows.append((start, end))

    # Merge overlapping windows
    windows.sort()
    merged: list[tuple[int, int]] = []
    for start, end in windows:
        if merged and start <= merged[-1][1]:
            # Overlapping - extend previous window
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    # Check if merged windows exceed budget
    total_kept = sum(end - start for start, end in merged)
    if total_kept > max_lines:
        # Need to reduce window sizes proportionally
        scale = max_lines / total_kept
        new_merged: list[tuple[int, int]] = []
        for start, end in merged:
            new_size = max(1, int((end - start) * scale))
            # Center the reduced window around the original middle
            mid = (start + end) // 2
            new_start = max(0, mid - new_size // 2)
            new_end = min(total_lines, new_start + new_size)
            new_merged.append((new_start, new_end))
        merged = new_merged

    # Build result with "..." separators
    result_parts: list[str] = []
    last_end = 0

    for start, end in merged:
        if start > last_end:
            skipped = start - last_end
            result_parts.append(f"... [{skipped} lines skipped] ...")
        result_parts.extend(lines[start:end])
        last_end = end

    if last_end < total_lines:
        skipped = total_lines - last_end
        result_parts.append(f"... [{skipped} lines skipped] ...")

    return "\n".join(result_parts)
