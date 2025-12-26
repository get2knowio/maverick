"""Diff chunking and truncation utilities for CodeReviewerAgent.

This module contains helper functions for managing diff size:
- Token estimation for content
- Truncation decisions and file subset selection
- Chunking large diffs into token-budget-compliant pieces
"""

from __future__ import annotations

from typing import Any

import tiktoken
from unidiff import PatchSet
from unidiff.errors import UnidiffParseError

from maverick.agents.code_reviewer.constants import (
    DEFAULT_FILE_TOKEN_ESTIMATE,
    MAX_DIFF_FILES,
    MAX_DIFF_LINES,
    MAX_TOKENS_PER_CHUNK,
)
from maverick.logging import get_logger

logger = get_logger(__name__)

# Create encoder once at module level for efficiency.
# cl100k_base is compatible with GPT-4 and reasonably accurate for Claude.
_ENCODER = tiktoken.get_encoding("cl100k_base")


def estimate_tokens(content: str) -> int:
    """Estimate token count using tiktoken (T041, FR-021).

    Uses cl100k_base encoding which is close to Claude's tokenization.
    This provides more accurate token counting than character-based heuristics.

    Args:
        content: Text content to estimate.

    Returns:
        Actual token count based on tiktoken encoding.

    Examples:
        >>> estimate_tokens("Hello world!")
        3
        >>> estimate_tokens("")
        0
    """
    if not content:
        return 0
    return len(_ENCODER.encode(content))


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


def _parse_diff_with_unidiff(diff_content: str) -> dict[str, str]:
    """Parse diff content using unidiff and return a mapping of file paths to diff text.

    Args:
        diff_content: Full git diff content.

    Returns:
        Dictionary mapping file paths to their individual diff content.
        Empty dict if parsing fails.
    """
    try:
        patch = PatchSet.from_string(diff_content)
    except UnidiffParseError as e:
        logger.warning("unidiff_parse_error", error=str(e))
        return {}
    except Exception:  # noqa: BLE001
        # Catch any unexpected errors to ensure graceful fallback
        logger.error(
            "unidiff_unexpected_error",
            exc_info=True,
        )
        return {}

    file_diffs: dict[str, str] = {}
    for patched_file in patch:
        # Use .path which gives the canonical path without a/ or b/ prefix
        file_path = patched_file.path

        # Get the string representation of this file's diff
        # This includes the full diff header and all hunks
        file_diff_str = str(patched_file)
        file_diffs[file_path] = file_diff_str

        # Log additional info for special cases
        if patched_file.is_binary_file:
            logger.debug("binary_file_in_diff", file=file_path)
        if patched_file.is_rename:
            logger.debug(
                "rename_in_diff",
                source=patched_file.source_file,
                target=patched_file.target_file,
            )

    return file_diffs


def chunk_files(
    files: list[str],
    diff_content: str,
) -> list[list[str]]:
    """Split files into chunks respecting token budget (T042, FR-021).

    Each chunk's combined diff content should be under MAX_TOKENS_PER_CHUNK.
    Files are kept together (not split mid-file).

    Uses the unidiff library for reliable diff parsing, handling edge cases like
    binary files, renames, and malformed diffs gracefully.

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
    # Parse diff using unidiff for accurate per-file token estimation
    file_diffs = _parse_diff_with_unidiff(diff_content)

    chunks: list[list[str]] = []
    current_chunk: list[str] = []
    current_tokens = 0

    for file_path in files:
        # Look up the file's diff content from parsed data
        # unidiff normalizes paths, so try a few variations
        file_diff = file_diffs.get(file_path)

        # Try without leading directory if not found
        if file_diff is None:
            # Handle case where file_path might have extra prefix/suffix
            for parsed_path, diff_str in file_diffs.items():
                if parsed_path == file_path or parsed_path.endswith(f"/{file_path}"):
                    file_diff = diff_str
                    break

        if file_diff is not None:
            file_tokens = estimate_tokens(file_diff)
        else:
            # Fallback: assume average token count when file not in parsed diff
            # This can happen with binary files or if the file list doesn't match
            logger.debug(
                "file_not_in_parsed_diff",
                file=file_path,
                using_fallback_tokens=True,
            )
            file_tokens = DEFAULT_FILE_TOKEN_ESTIMATE

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
