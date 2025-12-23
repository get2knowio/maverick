"""Text processing utilities for Maverick.

This module provides basic text processing functions including token estimation
and line truncation for managing large text content.
"""

from __future__ import annotations

__all__ = [
    "estimate_tokens",
    "truncate_line",
]

# Default values
DEFAULT_MAX_LINE_CHARS = 2000


def estimate_tokens(text: str) -> int:
    """Estimate token count for text.

    Uses character count / 4 approximation per FR-006.
    This provides ~20% accuracy for typical source code.

    Args:
        text: Text to estimate tokens for.

    Returns:
        Approximate token count (integer).

    Example:
        >>> estimate_tokens("Hello world!")
        3
    """
    return len(text) // 4


def truncate_line(line: str, max_chars: int = DEFAULT_MAX_LINE_CHARS) -> str:
    """Truncate a single line if it exceeds max_chars.

    Args:
        line: Line content to potentially truncate.
        max_chars: Maximum characters allowed (default 2000).

    Returns:
        Original line if under limit, or truncated line with "..." appended.

    Example:
        >>> truncate_line("short line")
        'short line'
        >>> len(truncate_line("x" * 3000, max_chars=100))
        103
    """
    if len(line) <= max_chars:
        return line
    return line[:max_chars] + "..."
