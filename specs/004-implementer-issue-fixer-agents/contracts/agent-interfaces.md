# Agent Interface Contracts

**Feature**: 004-implementer-issue-fixer-agents | **Date**: 2025-12-14

## Overview

This document defines the interface contracts for ImplementerAgent and IssueFixerAgent, specifying their public APIs, expected inputs/outputs, and behavioral guarantees.

---

## ImplementerAgent Interface

### Class Definition

```python
class ImplementerAgent(MaverickAgent):
    """Agent for executing structured task files (FR-001).

    Implements methodical, test-driven task execution from tasks.md files
    or direct task descriptions.

    Example:
        >>> agent = ImplementerAgent()
        >>> context = ImplementerContext(
        ...     task_file=Path("specs/004/tasks.md"),
        ...     branch="feature/implement"
        ... )
        >>> result = await agent.execute(context)
        >>> result.success
        True
    """

    def __init__(
        self,
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
    ) -> None:
        """Initialize ImplementerAgent.

        Args:
            model: Claude model ID (defaults to claude-sonnet-4-5-20250929).
            mcp_servers: Optional MCP server configurations.
        """
        ...

    async def execute(
        self,
        context: ImplementerContext,
    ) -> ImplementationResult:
        """Execute tasks from file or description (FR-004).

        Args:
            context: Execution context with task source and options.

        Returns:
            ImplementationResult with task outcomes and file changes.

        Raises:
            TaskParseError: If task file has invalid format (FR-010).
            AgentError: On unrecoverable execution errors.
        """
        ...
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `name` | `str` | Always `"implementer"` |
| `system_prompt` | `str` | Implementation-focused prompt with TDD guidance |
| `allowed_tools` | `list[str]` | `["Read", "Write", "Edit", "Bash", "Glob", "Grep"]` (FR-003) |
| `model` | `str` | Claude model ID |

### Execute Method Contract

**Preconditions:**
- `context.task_file` exists and is readable, OR `context.task_description` is provided
- `context.cwd` is a valid git repository
- Git is installed and configured

**Postconditions:**
- All pending tasks in file are attempted
- Git commits created for completed work (unless `dry_run=True`)
- Validation run after each task (unless `skip_validation=True`)
- Result contains detailed task outcomes

**Error Handling:**
- Invalid task format: Raises `TaskParseError` with line number
- Task execution failure: Marks task as failed, continues to next
- Validation failure: Retries up to 3 times, then marks task failed
- Git failure: Attempts recovery per FR-024a, fails if unrecoverable

---

## IssueFixerAgent Interface

### Class Definition

```python
class IssueFixerAgent(MaverickAgent):
    """Agent for resolving GitHub issues with minimal changes (FR-011).

    Implements targeted bug fixes by analyzing issues, implementing
    minimal fixes, and verifying resolution.

    Example:
        >>> agent = IssueFixerAgent()
        >>> context = IssueFixerContext(issue_number=42)
        >>> result = await agent.execute(context)
        >>> result.success
        True
    """

    def __init__(
        self,
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
    ) -> None:
        """Initialize IssueFixerAgent.

        Args:
            model: Claude model ID (defaults to claude-sonnet-4-5-20250929).
            mcp_servers: Optional MCP server configurations (GitHub MCP optional).
        """
        ...

    async def execute(
        self,
        context: IssueFixerContext,
    ) -> FixResult:
        """Fix a GitHub issue (FR-014).

        Args:
            context: Execution context with issue source and options.

        Returns:
            FixResult with fix details and verification status.

        Raises:
            GitHubError: If issue cannot be fetched (after retries).
            AgentError: On unrecoverable execution errors.
        """
        ...
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `name` | `str` | Always `"issue-fixer"` |
| `system_prompt` | `str` | Fix-focused prompt emphasizing minimal changes |
| `allowed_tools` | `list[str]` | `["Read", "Write", "Edit", "Bash", "Glob", "Grep"]` + MCP tools (FR-013) |
| `model` | `str` | Claude model ID |

### Execute Method Contract

**Preconditions:**
- `context.issue_number` is valid GitHub issue, OR `context.issue_data` is complete
- `context.cwd` is a valid git repository
- GitHub CLI is installed and authenticated (if using `issue_number`)

**Postconditions:**
- Issue details fetched (if not provided)
- Root cause identified and documented in result
- Minimal fix implemented (target <100 lines)
- Verification attempted
- Git commit created referencing issue (unless `dry_run=True`)

**Error Handling:**
- Issue not found: Raises `GitHubError` with `"Issue #N not found"`
- Rate limit: Retries with exponential backoff, raises after exhaustion (FR-015a)
- Fix verification fails: Returns `FixResult` with `verification_passed=False`
- Validation failure: Retries up to 3 times per FR-024

---

## Shared Contracts

### Validation Pipeline

Both agents share the validation pipeline with this contract:

```python
async def _run_validation(
    self,
    cwd: Path,
    max_retries: int = 3,
) -> list[ValidationResult]:
    """Run validation pipeline (FR-008, FR-021, FR-024).

    Pipeline order: format -> lint -> typecheck -> test

    Args:
        cwd: Working directory.
        max_retries: Max auto-fix attempts for fixable steps.

    Returns:
        List of ValidationResult for each step attempted.

    Raises:
        ValidationError: If validation fails after all retries.

    Behavior:
        - Runs steps sequentially
        - Auto-fixes format/lint issues up to max_retries
        - Stops pipeline on first non-fixable failure
        - Returns partial results on failure
    """
    ...
```

### Git Commit Contract

```python
async def _create_commit(
    self,
    message: str,
    cwd: Path,
) -> str:
    """Create git commit with conventional message (FR-007, FR-019, FR-023).

    Args:
        message: Commit message (must follow conventional commits format).
        cwd: Working directory.

    Returns:
        Commit SHA on success.

    Raises:
        GitError: On unrecoverable commit failure.

    Recovery behavior (FR-024a):
        - Dirty index: Auto-stash, commit, unstash
        - Pre-commit hook failure: Attempt auto-fix, retry once
        - Merge conflict: FAIL with descriptive error
    """
    ...
```

---

## Error Contracts

### TaskParseError

```python
class TaskParseError(AgentError):
    """Raised when task file parsing fails.

    Attributes:
        message: Error description.
        line_number: Line where error occurred (if known).
    """

    # Raised when:
    # - File is not valid markdown
    # - Task ID format is invalid (not T###)
    # - Checkbox syntax is malformed
    # - Dependencies reference non-existent tasks
```

### GitHubError

```python
class GitHubError(AgentError):
    """Raised when GitHub operations fail.

    Attributes:
        message: Error description.
        issue_number: Issue number (if applicable).
        retry_after: Seconds to wait for rate limit (if applicable).
    """

    # Raised when:
    # - Issue not found: "Issue #N not found"
    # - Rate limit: "GitHub rate limit exceeded, retry after X seconds"
    # - Auth failure: "GitHub authentication failed"
    # - Network error: After retry exhaustion
```

### GitError

```python
class GitError(AgentError):
    """Raised when git operations fail.

    Attributes:
        message: Error description.
        operation: Git operation that failed.
        recoverable: True if error might be recoverable.
    """

    # Raised when:
    # - Commit fails after recovery attempts
    # - Merge conflict detected (recoverable=False)
    # - Repository is not a git repo
```

### ValidationError

```python
class ValidationError(AgentError):
    """Raised when validation fails after retries.

    Attributes:
        message: Error description.
        step: Validation step that failed.
        output: Command output.
    """

    # Raised when:
    # - Format/lint fails after max_retries auto-fix attempts
    # - Type check fails (no auto-fix available)
    # - Tests fail (no auto-fix available)
```

---

## Behavioral Guarantees

### Parallel Execution (ImplementerAgent)

1. Tasks marked `[P]` may execute concurrently
2. Each parallel task runs in isolated context
3. Failed parallel tasks are retried up to 3 times
4. Results are aggregated after all parallel tasks complete
5. Subsequent sequential tasks wait for parallel batch to complete

### Minimal Changes (IssueFixerAgent)

1. Only files directly related to the issue are modified
2. No refactoring of surrounding code
3. No formatting changes to untouched code
4. Target fix size is <100 lines for typical bugs
5. `FixResult.is_minimal_fix` property validates this

### Checkpoint Behavior

1. Commits created after each logical unit of work
2. Partial progress preserved even on failure
3. Results include all completed work before failure
4. `ImplementationResult.task_results` contains per-task outcomes

---

## Usage Examples

### ImplementerAgent with Task File

```python
from maverick.agents import ImplementerAgent
from maverick.models.implementation import ImplementerContext
from pathlib import Path

agent = ImplementerAgent()
context = ImplementerContext(
    task_file=Path("specs/004-implementer-issue-fixer-agents/tasks.md"),
    branch="feature/implement-agents",
)

result = await agent.execute(context)

print(f"Completed: {result.tasks_completed}/{result.total_tasks}")
print(f"Commits: {result.commits}")
for task_result in result.task_results:
    status = "OK" if task_result.succeeded else "FAIL"
    print(f"  {task_result.task_id}: {status}")
```

### ImplementerAgent with Direct Task

```python
context = ImplementerContext(
    task_description="Add logging to the API handler in src/api/handler.py",
    branch="feature/add-logging",
)

result = await agent.execute(context)
```

### IssueFixerAgent with Issue Number

```python
from maverick.agents import IssueFixerAgent
from maverick.models.issue_fix import IssueFixerContext

agent = IssueFixerAgent()
context = IssueFixerContext(issue_number=42)

result = await agent.execute(context)

if result.success:
    print(f"Fixed #{result.issue_number}: {result.fix_description}")
    print(f"Commit: {result.commit_sha}")
else:
    print(f"Failed: {result.errors}")
```

### IssueFixerAgent with Pre-fetched Data

```python
# Pre-fetched by RefuelWorkflow to avoid redundant API calls
issue_data = {
    "number": 42,
    "title": "Login fails on Safari",
    "body": "Steps to reproduce...",
    "labels": [{"name": "bug"}],
    "url": "https://github.com/org/repo/issues/42",
}

context = IssueFixerContext(issue_data=issue_data)
result = await agent.execute(context)
```
