# Data Model: Context Builder Utilities

**Feature Branch**: `018-context-builder`
**Date**: 2025-12-18
**Status**: Complete

## Overview

This document defines the data structures used by the context builder utilities. All context builders return plain Python dictionaries (not dataclasses) for easy prompt interpolation per FR-009.

## Type Definitions

### ContextDict (Return Type)

All context builders return a `ContextDict` - a plain Python `dict[str, Any]` with the following guaranteed structure:

```python
ContextDict = dict[str, Any]
# All returned dicts MUST include '_metadata' key when truncation occurs (FR-010)
```

### TruncationMetadata

Included in all returned dicts when any content has been truncated:

```python
TruncationMetadata = TypedDict('TruncationMetadata', {
    'truncated': bool,           # True if any content was truncated
    'original_lines': int,       # Total lines before truncation
    'kept_lines': int,           # Lines retained after truncation
    'sections_affected': list[str],  # Which context sections were truncated
})
```

**Validation Rules**:
- `truncated` is True if and only if `original_lines > kept_lines`
- `sections_affected` contains only valid section names from the parent dict
- `kept_lines <= original_lines` always

---

## Context Builder Return Schemas

### build_implementation_context()

**Input**:
- `task_file: Path` - Path to tasks.md file
- `git: GitOperations` - Git operations instance

**Output Schema**:
```python
{
    'tasks': str,           # Raw content of task file
    'conventions': str,     # CLAUDE.md content (or empty with warning)
    'branch': str,          # Current git branch name
    'recent_commits': list[dict],  # Last 10 commits as dicts
    '_metadata': TruncationMetadata,  # Truncation info
}
```

**Commit Dict Schema**:
```python
{
    'hash': str,         # Short commit hash
    'message': str,      # Commit message (first line)
    'author': str,       # Author name
    'date': str,         # ISO 8601 date
}
```

**State Transitions**: N/A (stateless function)

---

### build_review_context()

**Input**:
- `git: GitOperations` - Git operations instance
- `base_branch: str` - Branch to diff against (e.g., "main")

**Output Schema**:
```python
{
    'diff': str,                    # Full diff output
    'changed_files': dict[str, str],  # {path: content} for changed files
    'conventions': str,             # CLAUDE.md content
    'stats': dict,                  # Diff statistics
    '_metadata': TruncationMetadata,
}
```

**Stats Dict Schema**:
```python
{
    'files_changed': int,   # Number of files changed
    'insertions': int,      # Lines added
    'deletions': int,       # Lines removed
}
```

**File Inclusion Rules** (FR-012):
- Files < 500 lines: Include full content
- Files >= 500 lines: Truncate with "..." markers

---

### build_fix_context()

**Input**:
- `validation_output: ValidationOutput` - Validation result with errors
- `files: list[Path]` - Files to include context for

**Output Schema**:
```python
{
    'errors': list[dict],          # Structured error information
    'source_files': dict[str, str],  # {path: truncated_content}
    'error_summary': str,          # Human-readable summary
    '_metadata': TruncationMetadata,
}
```

**Error Dict Schema**:
```python
{
    'file': str,       # File path
    'line': int,       # Line number
    'message': str,    # Error message
    'severity': str,   # "error" | "warning"
    'code': str | None,  # Error code if available
}
```

**Source File Content Rules** (FR-013):
- Include ±10 lines around each error line number
- Merge overlapping context regions
- Replace removed content with "..." markers

---

### build_issue_context()

**Input**:
- `issue: GitHubIssue` - GitHub issue object
- `git: GitOperations` - Git operations instance

**Output Schema**:
```python
{
    'issue': dict,                  # Issue details
    'related_files': dict[str, str],  # {path: content} for referenced files
    'recent_changes': list[dict],   # Recent commits (last 5)
    '_metadata': TruncationMetadata,
}
```

**Issue Dict Schema**:
```python
{
    'number': int,
    'title': str,
    'body': str,
    'labels': list[str],
    'state': str,
    'url': str,
}
```

**Related File Detection**:
- Scan issue body for file path patterns (e.g., `src/foo.py`, `./bar/baz.ts`)
- Verify paths exist before including
- Skip binary files

---

## Utility Function Schemas

### truncate_file()

**Input**:
- `content: str` - File content to truncate
- `max_lines: int` - Maximum lines to keep
- `around_lines: list[int]` - Line numbers to preserve context around

**Output**: `str` - Truncated content with "..." markers

**Algorithm**:
1. Split content into lines
2. Mark preservation windows (±10 lines around each target)
3. Merge overlapping windows
4. Extract marked regions with "..." separators

---

### estimate_tokens()

**Input**: `text: str` - Text to estimate

**Output**: `int` - Approximate token count

**Formula**: `len(text) // 4` (per FR-006)

---

### fit_to_budget()

**Input**:
- `sections: dict[str, str]` - Named sections to fit
- `budget: int = 32000` - Token budget (default from FR-007)

**Output**: `dict[str, str]` - Truncated sections

**Algorithm**:
1. Estimate tokens for each section
2. If total ≤ budget, return unchanged
3. Calculate proportional allocation per section
4. Truncate each section to its allocation
5. Return with `_metadata` added

---

## External Type References

### GitOperations

From `maverick.utils.git_operations`:

```python
class GitOperations:
    def current_branch(self) -> str: ...
    def log(self, n: int = 10) -> list[CommitInfo]: ...
    def diff(self, base: str = "HEAD", head: str | None = None) -> str: ...
    def diff_stats(self, base: str = "HEAD") -> DiffStats: ...
```

### ValidationOutput

From `maverick.runners.models`:

```python
@dataclass(frozen=True, slots=True)
class ValidationOutput:
    success: bool
    stages: tuple[StageResult, ...]
    total_duration_ms: int
```

### GitHubIssue

From `maverick.runners.models`:

```python
@dataclass(frozen=True, slots=True)
class GitHubIssue:
    number: int
    title: str
    body: str
    labels: tuple[str, ...]
    state: str
    assignees: tuple[str, ...]
    url: str
```

---

## Invariants

1. **Metadata Always Present**: When truncation occurs, `_metadata` key MUST be present
2. **Graceful Degradation**: Missing files return empty strings with metadata indicating absence
3. **Memory Bounds**: No single operation allocates >100MB (SC-007)
4. **Token Accuracy**: Estimates within 20% of actual for typical code (SC-003)
5. **Budget Compliance**: `fit_to_budget()` output within 5% of specified budget (SC-002)
