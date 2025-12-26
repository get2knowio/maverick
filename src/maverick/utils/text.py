"""Text processing utilities for Maverick.

This module provides basic text processing functions including token estimation
and line truncation for managing large text content.
"""

from __future__ import annotations

import tiktoken

__all__ = [
    "estimate_tokens",
    "truncate_line",
]

# Default values
DEFAULT_MAX_LINE_CHARS = 2000

# Create encoder once at module level for efficiency.
# cl100k_base is used as an approximation - Claude's actual tokenizer differs
# slightly but this provides sufficient accuracy for budget estimation.
_ENCODER = tiktoken.get_encoding("cl100k_base")


def estimate_tokens(text: str) -> int:
    """Estimate token count for text using tiktoken.

    Uses cl100k_base encoding which provides accurate token counting
    compatible with modern LLMs.

    Args:
        text: Text to estimate tokens for.

    Returns:
        Actual token count based on tiktoken encoding.

    Example:
        >>> estimate_tokens("Hello world!")
        3
    """
    if not text:
        return 0
    return len(_ENCODER.encode(text))


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
