"""Diff chunking and truncation utilities for CodeReviewerAgent.

This module contains helper functions for managing diff size:
- Token estimation for content
- Truncation decisions and file subset selection
- Chunking large diffs into token-budget-compliant pieces
"""

from __future__ import annotations

import re
from typing import Any

from maverick.agents.code_reviewer.constants import (
    MAX_DIFF_FILES,
    MAX_DIFF_LINES,
    MAX_TOKENS_PER_CHUNK,
)


def estimate_tokens(content: str) -> int:
    """Rough estimate of token count for content (T041, FR-021).

    Uses rough heuristic: 1 token ≈ 4 characters. This is a conservative
    estimate for determining when to chunk reviews.

    Args:
        content: Text content to estimate.

    Returns:
        Estimated token count.

    Examples:
        >>> estimate_tokens("Hello world!")
        3
        >>> estimate_tokens("A" * 400)
        100
    """
    return len(content) // 4


def should_truncate(diff_stats: dict[str, Any]) -> bool:
    """Check if diff exceeds size limits (T037, FR-017).

    Args:
        diff_stats: Dictionary with 'files' list and 'total_lines' count.

    Returns:
        True if truncation is needed (exceeds MAX_DIFF_LINES or MAX_DIFF_FILES).

    Examples:
        >>> should_truncate({"files": ["a.py"], "total_lines": 100})
        False
        >>> should_truncate({"files": ["a.py"] * 60, "total_lines": 100})
        True
        >>> should_truncate({"files": ["a.py"], "total_lines": 3000})
        True
    """
    return (
        len(diff_stats["files"]) > MAX_DIFF_FILES
        or diff_stats["total_lines"] > MAX_DIFF_LINES
    )


def truncate_files(
    files: list[str],
    diff_stats: dict[str, Any],
) -> tuple[list[str], str]:
    """Truncate file list and generate notice (T038, FR-017).

    Files are kept in git diff order (alphabetical) for reproducibility.

    Args:
        files: List of files to potentially truncate.
        diff_stats: Dictionary with 'files' list and 'total_lines' count.

    Returns:
        Tuple of (truncated_file_list, truncation_notice_string).
        If no truncation needed, notice is empty string.

    Examples:
        >>> files = ["a.py", "b.py", "c.py"]
        >>> stats = {"files": files, "total_lines": 100}
        >>> truncate_files(files, stats)
        (['a.py', 'b.py', 'c.py'], '')

        >>> files = ["file{}.py".format(i) for i in range(60)]
        >>> stats = {"files": files, "total_lines": 100}
        >>> truncated, notice = truncate_files(files, stats)
        >>> len(truncated)
        50
        >>> "50 of 60" in notice
        True
    """
    if not should_truncate(diff_stats):
        return files, ""

    # Truncate to MAX_DIFF_FILES
    truncated_files = files[:MAX_DIFF_FILES]
    total_files = len(diff_stats["files"])
    skipped = total_files - MAX_DIFF_FILES

    notice = (
        f"Truncated: reviewing {MAX_DIFF_FILES} of {total_files} files "
        f"({skipped} skipped)"
    )

    return truncated_files, notice


def chunk_files(
    files: list[str],
    diff_content: str,
) -> list[list[str]]:
    """Split files into chunks respecting token budget (T042, FR-021).

    Each chunk's combined diff content should be under MAX_TOKENS_PER_CHUNK.
    Files are kept together (not split mid-file).

    Args:
        files: List of file paths to chunk.
        diff_content: Full diff content for all files.

    Returns:
        List of file chunks, where each chunk is a list of file paths.

    Examples:
        >>> files = ["a.py", "b.py", "c.py"]
        >>> diff = "small diff content"
        >>> chunk_files(files, diff)
        [['a.py', 'b.py', 'c.py']]

    Note:
        This is a best-effort chunking strategy. Very large individual files
        may still exceed the token limit.
    """
    chunks: list[list[str]] = []
    current_chunk: list[str] = []
    current_tokens = 0

    for file_path in files:
        # Extract this file's diff section (heuristic: find the file's diff block)
        # This is approximate - we estimate based on the full diff content
        escaped_path = re.escape(file_path)
        file_pattern = rf"diff --git a/{escaped_path} b/{escaped_path}"
        file_match = re.search(file_pattern, diff_content)

        if file_match:
            # Find next file or end of diff
            start_pos = file_match.start()
            next_file_pattern = r"diff --git a/"
            next_match = re.search(next_file_pattern, diff_content[start_pos + 1 :])

            if next_match:
                end_pos = start_pos + 1 + next_match.start()
                file_diff = diff_content[start_pos:end_pos]
            else:
                file_diff = diff_content[start_pos:]

            file_tokens = estimate_tokens(file_diff)
        else:
            # Fallback: assume average token count
            file_tokens = 1000

        # Check if adding this file would exceed chunk limit
        if current_tokens + file_tokens > MAX_TOKENS_PER_CHUNK and current_chunk:
            # Start new chunk
            chunks.append(current_chunk)
            current_chunk = [file_path]
            current_tokens = file_tokens
        else:
            # Add to current chunk
            current_chunk.append(file_path)
            current_tokens += file_tokens

    # Add final chunk if not empty
    if current_chunk:
        chunks.append(current_chunk)

    # Ensure we always return at least one chunk
    if not chunks:
        chunks = [files] if files else [[]]

    return chunks
