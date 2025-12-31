"""Review context builder for Maverick agents.

This module provides the build_review_context function which compiles diff output,
changed file contents, and project conventions for code review agents.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias

from maverick.logging import get_logger
from maverick.utils.files import _read_conventions, _read_file_safely
from maverick.utils.secrets import detect_secrets

if TYPE_CHECKING:
    from maverick.git import GitRepository

__all__ = [
    "build_review_context",
]

logger = get_logger(__name__)

# Type alias for context dictionaries
ContextDict: TypeAlias = dict[str, Any]

# Default values
DEFAULT_MAX_FILE_LINES_REVIEW = 500


def build_review_context(
    git: GitRepository,
    base_branch: str,
    *,
    conventions_path: Path | None = None,
    max_file_lines: int = DEFAULT_MAX_FILE_LINES_REVIEW,
) -> ContextDict:
    """Build context for code review agents.

    Compiles diff output, changed file contents, project conventions, and
    diff statistics for code review.

    Args:
        git: GitOperations instance for retrieving diff and file info.
        base_branch: Branch to diff against (e.g., "main", "origin/main").
        conventions_path: Optional explicit path to CLAUDE.md.
        max_file_lines: Files larger than this are truncated (default 500).

    Returns:
        ContextDict with keys:
        - diff: Full diff output between base_branch and HEAD
        - changed_files: Dict mapping file paths to their current content
        - conventions: CLAUDE.md content
        - stats: Dict with files_changed, insertions, deletions counts
        - _metadata: TruncationMetadata with truncation info

    Raises:
        No exceptions are raised; errors are handled gracefully with warnings logged.

    Note:
        Git operation failures result in empty diff/stats.
        Individual file read errors are logged and skipped.

    Example:
        >>> git = GitRepository()
        >>> ctx = build_review_context(git, "main")
        >>> ctx['stats']['files_changed']
        5
    """
    truncated = False
    sections_affected: list[str] = []
    original_lines = 0
    kept_lines = 0

    # Get diff
    try:
        diff_content = git.diff(base=base_branch)
    except (OSError, RuntimeError, ValueError) as e:
        logger.warning("Failed to get diff against %s: %s", base_branch, e)
        diff_content = ""

    # Get diff stats
    stats_dict: dict[str, int] = {"files_changed": 0, "insertions": 0, "deletions": 0}
    changed_file_list: list[str] = []
    try:
        diff_stats = git.diff_stats(base=base_branch)
        stats_dict = {
            "files_changed": diff_stats.files_changed,
            "insertions": diff_stats.insertions,
            "deletions": diff_stats.deletions,
        }
        changed_file_list = list(diff_stats.file_list)
    except (OSError, RuntimeError, ValueError) as e:
        logger.warning("Failed to get diff stats: %s", e)
        stats_dict = {}  # Reset to empty on error

    # Read changed files
    changed_files: dict[str, str] = {}
    for file_path in changed_file_list:
        path = Path(file_path)
        if not path.exists():
            continue

        # Skip binary files
        try:
            content, was_truncated = _read_file_safely(path, max_lines=max_file_lines)
            if was_truncated:
                truncated = True
                if "changed_files" not in sections_affected:
                    sections_affected.append("changed_files")
            changed_files[file_path] = content
        except (OSError, RuntimeError, ValueError) as e:
            logger.warning("Failed to read changed file %s: %s", file_path, e)

    # Read conventions
    conventions_content = _read_conventions(conventions_path)

    # Check for secrets
    for content, name in [
        (diff_content, "diff"),
        (conventions_content, "conventions"),
    ]:
        if content:
            secrets = detect_secrets(content)
            for line_num, pattern in secrets:
                logger.warning(
                    "Potential secret detected in %s at line %d: %s pattern",
                    name,
                    line_num,
                    pattern,
                )

    # Calculate line counts
    diff_lines = diff_content.count("\n") + 1 if diff_content else 0
    conv_lines = conventions_content.count("\n") + 1 if conventions_content else 0
    files_lines = sum(c.count("\n") + 1 for c in changed_files.values())
    original_lines = diff_lines + conv_lines + files_lines
    kept_lines = original_lines  # Simplified - actual tracking would be more complex

    return {
        "diff": diff_content,
        "changed_files": changed_files,
        "conventions": conventions_content,
        "stats": stats_dict,
        "_metadata": {
            "truncated": truncated,
            "original_lines": original_lines,
            "kept_lines": kept_lines,
            "sections_affected": sections_affected,
        },
    }
