"""Context builder utilities for Maverick agents.

This module provides synchronous utility functions that build optimized context
dictionaries for agent prompts. All functions are synchronous (file I/O only)
and return plain dicts for easy prompt interpolation.

Context builders include:
- build_implementation_context(): Task definitions, conventions, branch info
- build_review_context(): Diffs, changed files, conventions for code review
- build_fix_context(): Validation errors with surrounding source context
- build_issue_context(): GitHub issue details with related files

Supporting utilities:
- truncate_file(): Content truncation with context preservation
- estimate_tokens(): Token count estimation (chars / 4)
- fit_to_budget(): Proportional section truncation for token budgets

Example:
    ```python
    from pathlib import Path
    from maverick.utils.git_operations import GitOperations
    from maverick.utils.context import build_implementation_context

    git = GitOperations()
    context = build_implementation_context(
        task_file=Path("specs/feature/tasks.md"),
        git=git,
    )
    print(context['tasks'])
    print(context['branch'])
    ```
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias

if TYPE_CHECKING:
    from maverick.runners.models import GitHubIssue, ValidationOutput
    from maverick.utils.git_operations import GitOperations

__all__ = [
    "build_fix_context",
    "build_implementation_context",
    "build_issue_context",
    "build_review_context",
    "detect_secrets",
    "estimate_tokens",
    "extract_file_paths",
    "fit_to_budget",
    "truncate_file",
    "truncate_line",
]

logger = logging.getLogger(__name__)

# Type alias for context dictionaries
ContextDict: TypeAlias = dict[str, Any]

# =============================================================================
# Constants
# =============================================================================

# Secret detection patterns (high precision, low false positives)
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("api_key", re.compile(
        r"(?:api[_-]?key|apikey)\s*[:=]\s*['\"]?[\w-]{20,}", re.IGNORECASE
    )),
    ("bearer_token", re.compile(
        r"(?:bearer|authorization)\s*[:=]\s*['\"]?[\w.-]+", re.IGNORECASE
    )),
    ("aws_key", re.compile(r"(?:AKIA|ABIA|ACCA|ASIA)[A-Z0-9]{16}")),
    ("secret_password", re.compile(
        r"(?:secret|password|passwd|pwd)\s*[:=]\s*['\"]?[^\s'\"]{8,}",
        re.IGNORECASE,
    )),
    ("private_key", re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----")),
]

# Default values
DEFAULT_MAX_LINE_CHARS = 2000
DEFAULT_MAX_FILE_LINES = 50000
DEFAULT_CONTEXT_LINES = 10
DEFAULT_TOKEN_BUDGET = 32000
DEFAULT_MIN_SECTION_TOKENS = 100
DEFAULT_MAX_FILE_LINES_REVIEW = 500
DEFAULT_MAX_RELATED_FILES = 10
DEFAULT_RECENT_COMMITS = 10
MAX_PARENT_SEARCH_DEPTH = 10

# =============================================================================
# Foundational Utilities
# =============================================================================


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


def detect_secrets(content: str) -> list[tuple[int, str]]:
    """Detect potential secrets in content.

    Scans content for common secret patterns like API keys, tokens,
    and passwords. Returns line numbers and pattern names for logging.

    Args:
        content: Text content to scan for secrets.

    Returns:
        List of (line_number, pattern_name) tuples for each detected secret.
        Line numbers are 1-indexed.

    Example:
        >>> detect_secrets("api_key = 'sk-12345678901234567890'")
        [(1, 'api_key')]
    """
    findings: list[tuple[int, str]] = []
    lines = content.splitlines()

    for line_num, line in enumerate(lines, start=1):
        for pattern_name, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append((line_num, pattern_name))
                break  # One match per line is enough

    return findings


def extract_file_paths(text: str) -> list[str]:
    """Extract file path references from text.

    Looks for patterns like src/foo.py, ./bar/baz.ts, path/to/file.ext.
    Filters out common false positives like URLs and version numbers.

    Args:
        text: Text to scan for file paths.

    Returns:
        List of extracted file paths (deduplicated, order preserved).

    Example:
        >>> extract_file_paths("Check src/main.py and ./tests/test_main.py")
        ['src/main.py', './tests/test_main.py']
    """
    # Pattern matches paths with at least one directory separator and a file extension
    # Excludes URLs (http://, https://) and common false positives
    pattern = re.compile(
        r"(?<![:/])(?:\.?/)?(?:[\w.-]+/)+[\w.-]+\.(?:py|ts|js|tsx|jsx|rs|go|java|kt|rb|php|c|cpp|h|hpp|md|yaml|yml|json|toml|txt|sql|sh|bash)(?![/\w])",
        re.IGNORECASE,
    )

    matches = pattern.findall(text)

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for match in matches:
        # Clean up leading ./ for consistency
        clean_path = match.lstrip("./") if match.startswith("./") else match
        if clean_path not in seen:
            seen.add(clean_path)
            result.append(match)

    return result


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
        with path.open('rb') as f:
            sample = f.read(8192)
            if b'\x00' in sample:
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


# =============================================================================
# Context Builder Functions
# =============================================================================


def build_implementation_context(
    task_file: Path,
    git: GitOperations,
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
        >>> git = GitOperations()
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
            recent_commits.append({
                "hash": commit.short_hash,
                "message": commit.message,
                "author": commit.author,
                "date": commit.date,
            })
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


def build_review_context(
    git: GitOperations,
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
        >>> git = GitOperations()
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


def build_fix_context(
    validation_output: ValidationOutput,
    files: list[Path],
    *,
    context_lines: int = DEFAULT_CONTEXT_LINES,
) -> ContextDict:
    """Build context for fix agents.

    Extracts validation errors and provides surrounding source code context
    around each error location.

    Args:
        validation_output: ValidationOutput containing error information.
        files: List of file paths to include source context for.
        context_lines: Lines of context around each error (default 10).

    Returns:
        ContextDict with keys:
        - errors: List of error dicts with file, line, message, severity, code
        - source_files: Dict mapping file paths to truncated content with context
        - error_summary: Human-readable summary (e.g., "3 errors in 2 files")
        - _metadata: TruncationMetadata with truncation info

    Raises:
        No exceptions are raised; missing files are handled gracefully.

    Note:
        File I/O errors return empty content with appropriate metadata.

    Example:
        >>> ctx = build_fix_context(validation_result, [Path("src/main.py")])
        >>> ctx['error_summary']
        '3 errors in 2 files'
    """
    truncated = False
    sections_affected: list[str] = []
    original_lines = 0
    kept_lines = 0

    # Extract errors from validation output
    errors: list[dict[str, Any]] = []
    error_lines_by_file: dict[str, list[int]] = {}

    for stage in validation_output.stages:
        for error in stage.errors:
            errors.append({
                "file": error.file,
                "line": error.line,
                "message": error.message,
                "severity": error.severity or "error",
                "code": error.code,
            })
            # Track error lines per file
            if error.file not in error_lines_by_file:
                error_lines_by_file[error.file] = []
            error_lines_by_file[error.file].append(error.line)

    # Read source files with context around errors
    source_files: dict[str, str] = {}
    for file_path in files:
        if not file_path.exists():
            continue

        content, _ = _read_file_safely(file_path)
        if not content:
            continue

        file_str = str(file_path)
        error_lines = error_lines_by_file.get(file_str, [])

        # If this file has errors, truncate around them
        if error_lines:
            content_lines = content.count("\n") + 1
            original_lines += content_lines
            # Calculate reasonable budget: each error line gets context + some padding
            max_lines_budget = len(error_lines) * (context_lines * 2 + 5)
            truncated_content = truncate_file(
                content,
                max_lines=max_lines_budget,
                around_lines=error_lines,
                context_lines=context_lines,
            )
            truncated_lines = truncated_content.count("\n") + 1
            kept_lines += truncated_lines
            if truncated_lines < content_lines:
                truncated = True
                if "source_files" not in sections_affected:
                    sections_affected.append("source_files")
            source_files[file_str] = truncated_content
        else:
            # No errors in this file - include full content up to limit
            content_lines = content.count("\n") + 1
            original_lines += content_lines
            kept_lines += content_lines
            source_files[file_str] = content

    # Check for secrets in source files
    for file_str, content in source_files.items():
        secrets = detect_secrets(content)
        for line_num, pattern in secrets:
            logger.warning(
                "Potential secret detected in %s at line %d: %s pattern",
                file_str,
                line_num,
                pattern,
            )

    # Generate error summary
    error_count = len(errors)
    file_count = len({e["file"] for e in errors})
    if error_count == 0:
        error_summary = "No errors"
    elif error_count == 1:
        error_summary = "1 error in 1 file"
    elif file_count == 1:
        error_summary = f"{error_count} errors in 1 file"
    else:
        error_summary = f"{error_count} errors in {file_count} files"

    return {
        "errors": errors,
        "source_files": source_files,
        "error_summary": error_summary,
        "_metadata": {
            "truncated": truncated,
            "original_lines": original_lines,
            "kept_lines": kept_lines,
            "sections_affected": sections_affected,
        },
    }


def build_issue_context(
    issue: GitHubIssue,
    git: GitOperations,
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
            recent_changes.append({
                "hash": commit.short_hash,
                "message": commit.message,
                "author": commit.author,
                "date": commit.date,
            })
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


def fit_to_budget(
    sections: dict[str, str],
    budget: int = DEFAULT_TOKEN_BUDGET,
    *,
    min_section_tokens: int = DEFAULT_MIN_SECTION_TOKENS,
) -> dict[str, Any]:
    """Proportionally truncate sections to fit within token budget.

    Allocates tokens to each section proportionally based on its original size,
    ensuring each section gets at least min_section_tokens.

    Args:
        sections: Dict mapping section names to their text content.
        budget: Total token budget (default 32000).
        min_section_tokens: Minimum tokens per section (default 100).

    Returns:
        Dict with same keys as input, values truncated to fit budget.
        Includes '_metadata' key with truncation info if any truncation occurred.

    Example:
        >>> sections = {'a': 'x' * 10000, 'b': 'y' * 5000}
        >>> fitted = fit_to_budget(sections, budget=3000)
        >>> estimate_tokens(fitted['a']) + estimate_tokens(fitted['b']) <= 3000
        True
    """
    if not sections:
        return {}

    # Estimate tokens for each section
    section_tokens: dict[str, int] = {
        name: estimate_tokens(content) for name, content in sections.items()
    }
    total_tokens = sum(section_tokens.values())

    # If under budget, return unchanged
    if total_tokens <= budget:
        return dict(sections)

    # Calculate proportional allocation
    result: dict[str, Any] = {}
    sections_affected: list[str] = []
    original_lines = 0
    kept_lines = 0

    for name, content in sections.items():
        original_tokens = section_tokens[name]
        original_lines += content.count("\n") + 1

        # Calculate this section's budget (proportional)
        if total_tokens > 0:
            section_budget = max(
                min_section_tokens,
                int(budget * original_tokens / total_tokens),
            )
        else:
            section_budget = min_section_tokens

        # If section fits in its budget, keep it unchanged
        if original_tokens <= section_budget:
            result[name] = content
            kept_lines += content.count("\n") + 1
        else:
            # Truncate to fit budget (estimate chars from tokens)
            max_chars = section_budget * 4
            truncated_content = content[:max_chars]
            if len(content) > max_chars:
                truncated_content += "\n... [content truncated to fit budget]"
            result[name] = truncated_content
            kept_lines += truncated_content.count("\n") + 1
            sections_affected.append(name)

    # Add metadata if truncation occurred
    if sections_affected:
        result["_metadata"] = {
            "truncated": True,
            "original_lines": original_lines,
            "kept_lines": kept_lines,
            "sections_affected": sections_affected,
        }

    return result
