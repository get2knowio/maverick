"""Type stubs for context builder utilities.

This file defines the public interface for the context builder module.
All functions are synchronous and return plain dictionaries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

# Type aliases
ContextDict = dict[str, Any]

class TruncationMetadata(TypedDict):
    """Metadata about content truncation."""

    truncated: bool
    original_lines: int
    kept_lines: int
    sections_affected: list[str]

class CommitDict(TypedDict):
    """Commit information in dict form."""

    hash: str
    message: str
    author: str
    date: str

class ErrorDict(TypedDict):
    """Structured error information."""

    file: str
    line: int
    message: str
    severity: str
    code: str | None

class DiffStatsDict(TypedDict):
    """Diff statistics."""

    files_changed: int
    insertions: int
    deletions: int

class IssueDict(TypedDict):
    """GitHub issue in dict form."""

    number: int
    title: str
    body: str
    labels: list[str]
    state: str
    url: str

# Main context builder functions

def build_implementation_context(
    task_file: Path,
    git: Any,  # GitOperations
    *,
    conventions_path: Path | None = None,
) -> ContextDict:
    """Build context for implementation agents.

    Args:
        task_file: Path to tasks.md file.
        git: GitOperations instance for branch/commit info.
        conventions_path: Optional path to CLAUDE.md (defaults to repo root).

    Returns:
        Dict with keys: tasks, conventions, branch, recent_commits, _metadata.

    Raises:
        No exceptions - missing files return empty content with metadata.
    """
    ...

def build_review_context(
    git: Any,  # GitOperations
    base_branch: str,
    *,
    conventions_path: Path | None = None,
    max_file_lines: int = 500,
) -> ContextDict:
    """Build context for code review agents.

    Args:
        git: GitOperations instance for diffs and file access.
        base_branch: Branch to diff against (e.g., "main").
        conventions_path: Optional path to CLAUDE.md.
        max_file_lines: Files larger than this are truncated.

    Returns:
        Dict with keys: diff, changed_files, conventions, stats, _metadata.
    """
    ...

def build_fix_context(
    validation_output: Any,  # ValidationOutput
    files: list[Path],
    *,
    context_lines: int = 10,
) -> ContextDict:
    """Build context for fix agents.

    Args:
        validation_output: ValidationOutput with error information.
        files: List of file paths to include source context for.
        context_lines: Lines of context around each error (default 10).

    Returns:
        Dict with keys: errors, source_files, error_summary, _metadata.
    """
    ...

def build_issue_context(
    issue: Any,  # GitHubIssue
    git: Any,  # GitOperations
    *,
    max_related_files: int = 10,
) -> ContextDict:
    """Build context for issue-related agents.

    Args:
        issue: GitHubIssue object with issue details.
        git: GitOperations instance.
        max_related_files: Maximum number of related files to include.

    Returns:
        Dict with keys: issue, related_files, recent_changes, _metadata.
    """
    ...

# Utility functions

def truncate_file(
    content: str,
    max_lines: int,
    around_lines: list[int] | None = None,
    *,
    context_lines: int = 10,
) -> str:
    """Truncate file content with context preservation.

    Args:
        content: Full file content.
        max_lines: Maximum lines to keep.
        around_lines: Line numbers to preserve context around.
        context_lines: Lines of context on each side of target lines.

    Returns:
        Truncated content with "..." markers where content was removed.
    """
    ...

def estimate_tokens(text: str) -> int:
    """Estimate token count for text.

    Uses character count / 4 approximation per FR-006.

    Args:
        text: Text to estimate.

    Returns:
        Approximate token count.
    """
    ...

def fit_to_budget(
    sections: dict[str, str],
    budget: int = 32000,
    *,
    min_section_tokens: int = 100,
) -> dict[str, Any]:
    """Proportionally truncate sections to fit token budget.

    Args:
        sections: Named text sections to fit.
        budget: Total token budget (default 32000).
        min_section_tokens: Minimum tokens per section.

    Returns:
        Truncated sections dict with _metadata key added if truncation occurred.
    """
    ...

# Internal utilities (exported for testing)

def detect_secrets(content: str) -> list[tuple[int, str]]:
    """Detect potential secrets in content.

    Args:
        content: Text content to scan.

    Returns:
        List of (line_number, pattern_matched) tuples.
    """
    ...

def truncate_line(line: str, max_chars: int = 2000) -> str:
    """Truncate a single line if too long.

    Args:
        line: Line content.
        max_chars: Maximum characters (default 2000).

    Returns:
        Line truncated to max_chars with "..." appended if truncated.
    """
    ...

def extract_file_paths(text: str) -> list[str]:
    """Extract file path references from text.

    Looks for patterns like src/foo.py, ./bar/baz.ts, etc.

    Args:
        text: Text to scan for file paths.

    Returns:
        List of extracted file paths.
    """
    ...
