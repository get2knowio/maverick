"""Implementation context builder for Maverick agents.

This module provides the build_implementation_context function which aggregates
task definitions, project conventions, and git history for implementation agents.
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
    "build_implementation_context",
]

logger = get_logger(__name__)

# Type alias for context dictionaries
ContextDict: TypeAlias = dict[str, Any]

# Default values
DEFAULT_RECENT_COMMITS = 10


def build_implementation_context(
    task_file: Path,
    git: GitRepository,
    *,
    conventions_path: Path | None = None,
) -> ContextDict:
    """Build context for implementation agents.

    Aggregates task definitions, project conventions (CLAUDE.md), current branch
    info, and recent commits into a single context dictionary.

    Args:
        task_file: Path to tasks.md file containing task definitions.
        git: GitOperations instance for retrieving branch and commit info.
        conventions_path: Optional explicit path to CLAUDE.md.
                          If None, searches in current directory and parents.

    Returns:
        ContextDict with keys:
        - tasks: Raw content of task file (empty string if file missing)
        - conventions: CLAUDE.md content (empty string if not found)
        - branch: Current git branch name
        - recent_commits: List of last 10 commits as dicts
        - _metadata: TruncationMetadata with truncation info

    Raises:
        No exceptions are raised; errors are handled gracefully with warnings logged.

    Note:
        Git operation failures result in default values
        ("unknown" branch, empty commits list).
        File I/O errors return empty content with appropriate metadata.

    Example:
        >>> git = GitRepository()
        >>> ctx = build_implementation_context(Path("tasks.md"), git)
        >>> ctx.keys()
        dict_keys(['tasks', 'conventions', 'branch', 'recent_commits', '_metadata'])
    """
    # Track truncation info
    truncated = False
    original_lines = 0
    kept_lines = 0
    sections_affected: list[str] = []

    # Read task file
    tasks_content, tasks_truncated = _read_file_safely(task_file)
    if tasks_truncated:
        truncated = True
        sections_affected.append("tasks")

    # Read conventions
    conventions_content = _read_conventions(conventions_path)
    conventions_lines = (
        conventions_content.count("\n") + 1 if conventions_content else 0
    )

    # Check for secrets and log warnings
    content_pairs = [(tasks_content, "tasks"), (conventions_content, "conventions")]
    for content, name in content_pairs:
        if content:
            secrets = detect_secrets(content)
            for line_num, pattern in secrets:
                logger.warning(
                    "Potential secret detected in %s at line %d: %s pattern",
                    name,
                    line_num,
                    pattern,
                )

    # Get branch info
    try:
        branch = git.current_branch()
    except (OSError, RuntimeError, ValueError) as e:
        logger.warning("Failed to get current branch: %s", e)
        branch = "unknown"

    # Get recent commits
    recent_commits: list[dict[str, str]] = []
    try:
        commits = git.log(n=DEFAULT_RECENT_COMMITS)
        for commit in commits:
            recent_commits.append(
                {
                    "hash": commit.short_sha,
                    "message": commit.message,
                    "author": commit.author,
                    "date": commit.date,
                }
            )
    except (OSError, RuntimeError, ValueError) as e:
        logger.warning("Failed to get recent commits: %s", e)

    # Calculate line counts
    tasks_lines = tasks_content.count("\n") + 1 if tasks_content else 0
    original_lines = tasks_lines + conventions_lines
    kept_lines = original_lines  # No truncation applied to conventions yet

    return {
        "tasks": tasks_content,
        "conventions": conventions_content,
        "branch": branch,
        "recent_commits": recent_commits,
        "_metadata": {
            "truncated": truncated,
            "original_lines": original_lines,
            "kept_lines": kept_lines,
            "sections_affected": sections_affected,
        },
    }
