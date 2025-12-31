"""Issue context builder for Maverick agents.

This module provides the build_issue_context function which combines GitHub
issue details with referenced file content and recent repository changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias

from maverick.logging import get_logger
from maverick.utils.files import _read_file_safely
from maverick.utils.paths import extract_file_paths
from maverick.utils.secrets import detect_secrets

if TYPE_CHECKING:
    from maverick.git import GitRepository
    from maverick.runners.models import GitHubIssue

__all__ = [
    "build_issue_context",
]

logger = get_logger(__name__)

# Type alias for context dictionaries
ContextDict: TypeAlias = dict[str, Any]

# Default values
DEFAULT_MAX_RELATED_FILES = 10


def build_issue_context(
    issue: GitHubIssue,
    git: GitRepository,
    *,
    max_related_files: int = DEFAULT_MAX_RELATED_FILES,
) -> ContextDict:
    """Build context for issue-related agents.

    Combines GitHub issue details with referenced file content and recent
    repository changes.

    Args:
        issue: GitHubIssue object containing issue details.
        git: GitOperations instance for repository context.
        max_related_files: Maximum number of related files to include (default 10).

    Returns:
        ContextDict with keys:
        - issue: Dict with number, title, body, labels, state, url
        - related_files: Dict mapping file paths to their content
        - recent_changes: List of last 5 commits as dicts
        - _metadata: TruncationMetadata with truncation info

    Raises:
        No exceptions are raised; errors are handled gracefully with warnings logged.

    Note:
        Git operation failures result in empty recent_changes list.
        Missing related files are skipped silently.

    Example:
        >>> ctx = build_issue_context(issue, git)
        >>> ctx['issue']['title']
        'Fix token estimation bug'
    """
    truncated = False
    sections_affected: list[str] = []
    original_lines = 0
    kept_lines = 0

    # Convert issue to dict
    issue_dict: dict[str, Any] = {
        "number": issue.number,
        "title": issue.title,
        "body": issue.body,
        "labels": list(issue.labels),
        "state": issue.state,
        "url": issue.url,
    }

    # Extract file paths from issue body
    file_paths = extract_file_paths(issue.body)

    # Read related files (up to max_related_files)
    related_files: dict[str, str] = {}
    for path_str in file_paths[:max_related_files]:
        # Try both relative and absolute paths
        path = Path(path_str)
        if not path.exists():
            # Try relative to cwd
            path = Path.cwd() / path_str
            if not path.exists():
                continue

        content, was_truncated = _read_file_safely(path)
        if content:
            if was_truncated:
                truncated = True
                if "related_files" not in sections_affected:
                    sections_affected.append("related_files")
            related_files[path_str] = content
            content_lines = content.count("\n") + 1
            original_lines += content_lines
            kept_lines += content_lines

    # Check for secrets in issue body
    secrets = detect_secrets(issue.body)
    for line_num, pattern in secrets:
        logger.warning(
            "Potential secret detected in issue body at line %d: %s pattern",
            line_num,
            pattern,
        )

    # Get recent changes (last 5 commits)
    recent_changes: list[dict[str, str]] = []
    try:
        commits = git.log(n=5)
        for commit in commits:
            recent_changes.append(
                {
                    "hash": commit.short_sha,
                    "message": commit.message,
                    "author": commit.author,
                    "date": commit.date,
                }
            )
    except (OSError, RuntimeError, ValueError) as e:
        logger.warning("Failed to get recent changes: %s", e)

    return {
        "issue": issue_dict,
        "related_files": related_files,
        "recent_changes": recent_changes,
        "_metadata": {
            "truncated": truncated,
            "original_lines": original_lines,
            "kept_lines": kept_lines,
            "sections_affected": sections_affected,
        },
    }
