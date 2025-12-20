# Research: ImplementerAgent and IssueFixerAgent

**Feature**: 004-implementer-issue-fixer-agents | **Date**: 2025-12-14

## Overview

This document captures research findings for implementing two specialized agents:
1. **ImplementerAgent**: Executes structured task files with TDD approach
2. **IssueFixerAgent**: Resolves GitHub issues with minimal code changes

Both agents extend `MaverickAgent` and follow established patterns from `CodeReviewerAgent`.

---

## 1. Task File Parsing (.specify tasks.md Format)

### Decision: Build custom parser for tasks.md format

### Rationale
The .specify tasks.md format has specific requirements:
- Checkbox items: `[ ]` (pending) or `[x]` (completed)
- Task IDs: `[T001]`, `[T002]`, etc.
- Parallel markers: `P:` or `[P]` prefix indicates task can run concurrently
- User story tags: `[US1]`, `[US2]` for traceability
- Phase/section grouping with markdown headers

### Format Examples

```markdown
## Phase 2: Foundational

- [X] T001 Create directory structure
- [X] T002 [P] Create __init__.py files  # Can run in parallel
- [ ] T003 [US1] Implement core logic     # Maps to User Story 1
```

### Implementation

```python
from dataclasses import dataclass, field
from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

@dataclass(frozen=True, slots=True)
class Task:
    id: str                    # e.g., "T001"
    description: str           # Task description
    status: TaskStatus         # pending/completed
    parallel: bool = False     # True if marked [P] or P:
    user_story: str | None = None  # e.g., "US1"
    phase: str | None = None   # e.g., "Phase 2: Foundational"
    dependencies: list[str] = field(default_factory=list)  # Task IDs

@dataclass
class TaskFile:
    tasks: list[Task]
    phases: dict[str, list[Task]]  # Grouped by phase

    @classmethod
    def parse(cls, content: str) -> "TaskFile":
        # Regex patterns for parsing
        task_pattern = r"- \[([ xX])\] (T\d+)\s*(\[P\]|P:)?\s*(\[US\d+\])?\s*(.*)"
        # ... parsing logic
```

### Alternatives Considered
- Generic markdown parser (e.g., `mistune`): Too generic, doesn't understand task semantics
- YAML task format: Less human-readable, harder to edit manually

---

## 2. Parallel Task Execution

### Decision: Use `asyncio.gather()` with individual task wrappers for parallel sub-agents

### Rationale
- Constitution Principle VIII (Relentless Progress): Isolate failures, continue processing
- FR-006a: Retry failed sub-agents while others continue
- `asyncio.gather(return_exceptions=True)` allows collecting all results including failures

### Implementation

```python
import asyncio
from typing import NamedTuple

class ParallelResult(NamedTuple):
    task_id: str
    success: bool
    result: ImplementationResult | Exception

async def _execute_parallel_tasks(
    self,
    tasks: list[Task],
    context: AgentContext,
) -> list[ParallelResult]:
    """Execute tasks in parallel with isolated failure handling."""

    async def execute_with_retry(task: Task) -> ParallelResult:
        for attempt in range(3):  # Max 3 retries per FR-006a
            try:
                result = await self._execute_single_task(task, context)
                return ParallelResult(task.id, True, result)
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                return ParallelResult(task.id, False, e)

    # Launch all parallel tasks
    results = await asyncio.gather(
        *[execute_with_retry(task) for task in tasks],
        return_exceptions=True  # Don't fail on individual task failures
    )

    return results
```

### Pattern from CodeReviewerAgent
`code_reviewer.py:294` uses `asyncio.gather()` for parallel operations:
```python
diff_stats, conventions = await asyncio.gather(
    self._get_diff_stats(review_context),
    self._read_conventions(review_context),
)
```

---

## 3. Git Operations

### Decision: Use `asyncio.create_subprocess_exec()` for git commands (no shell=True)

### Rationale
- Constitution Principle VII: No `shell=True` without security justification
- Async subprocess allows non-blocking git operations
- Pattern established in `CodeReviewerAgent._get_diff_stats()`

### Git Commit Pattern

```python
async def _git_commit(
    self,
    message: str,
    cwd: Path,
) -> str:
    """Create a git commit with conventional commit message.

    Returns:
        Commit SHA on success.

    Raises:
        GitError: On commit failure with recovery suggestions.
    """
    # Check for dirty index first
    if await self._has_dirty_index(cwd):
        await self._auto_stash(cwd)
        try:
            return await self._do_commit(message, cwd)
        finally:
            await self._auto_unstash(cwd)

    return await self._do_commit(message, cwd)

async def _do_commit(self, message: str, cwd: Path) -> str:
    process = await asyncio.create_subprocess_exec(
        "git", "commit", "-m", message,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(
        process.communicate(),
        timeout=30.0,
    )

    if process.returncode != 0:
        error_msg = stderr.decode().strip()
        if "pre-commit hook" in error_msg:
            # Attempt auto-fix per FR-024a
            await self._fix_precommit_issues(cwd)
            return await self._do_commit(message, cwd)
        raise GitError(f"Commit failed: {error_msg}")

    # Extract commit SHA
    return stdout.decode().strip().split()[1]
```

### Git Error Recovery (FR-024a)

| Error Type | Recovery Action |
|------------|-----------------|
| Dirty index | Auto-stash, commit, unstash |
| Pre-commit hook failure | Auto-fix (format/lint), retry once |
| Merge conflict | FAIL with descriptive error (no auto-recovery) |

---

## 4. GitHub Issue Fetching

### Decision: Use GitHub CLI (`gh`) with retry and exponential backoff

### Rationale
- Assumption: GitHub CLI is installed and authenticated (spec assumptions)
- CLI provides clean JSON output
- Retry with backoff handles rate limits (FR-015a)

### Implementation

```python
import json
from typing import Any

MAX_GITHUB_RETRIES = 3
GITHUB_BACKOFF_BASE = 2  # seconds

async def _fetch_issue(
    self,
    issue_number: int,
    cwd: Path,
) -> dict[str, Any]:
    """Fetch GitHub issue details with retry logic.

    Args:
        issue_number: GitHub issue number.
        cwd: Working directory (for repo context).

    Returns:
        Issue data dictionary with title, body, labels, etc.

    Raises:
        GitHubError: After retry exhaustion with actionable message.
    """
    for attempt in range(MAX_GITHUB_RETRIES):
        try:
            process = await asyncio.create_subprocess_exec(
                "gh", "issue", "view", str(issue_number),
                "--json", "title,body,labels,state,number,url",
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30.0,
            )

            if process.returncode == 0:
                return json.loads(stdout.decode())

            error_msg = stderr.decode().strip()

            # Check for rate limit
            if "rate limit" in error_msg.lower():
                if attempt < MAX_GITHUB_RETRIES - 1:
                    wait_time = GITHUB_BACKOFF_BASE ** (attempt + 1)
                    await asyncio.sleep(wait_time)
                    continue
                raise GitHubError(
                    f"GitHub rate limit exceeded, retry after {wait_time} seconds"
                )

            # Check for not found
            if "not found" in error_msg.lower():
                raise GitHubError(f"Issue #{issue_number} not found")

            raise GitHubError(f"GitHub CLI error: {error_msg}")

        except asyncio.TimeoutError:
            if attempt < MAX_GITHUB_RETRIES - 1:
                continue
            raise GitHubError("GitHub request timed out after retries")

    raise GitHubError("GitHub fetch failed after all retries")
```

---

## 5. Validation Runner

### Decision: Sequential validation (format → lint → test) with auto-fix retry

### Rationale
- Format must run before lint (formatter may fix lint issues)
- Tests should run last (depend on code being correct)
- Auto-fix up to 3 times per FR-024

### Validation Commands (from pyproject.toml pattern)

| Step | Command | Auto-fixable |
|------|---------|--------------|
| Format | `ruff format .` | Yes (applies fixes) |
| Lint | `ruff check --fix .` | Yes (with --fix) |
| Type check | `mypy .` | No |
| Test | `pytest` | No |

### Implementation

```python
from dataclasses import dataclass
from enum import Enum

class ValidationStep(str, Enum):
    FORMAT = "format"
    LINT = "lint"
    TYPECHECK = "typecheck"
    TEST = "test"

@dataclass
class ValidationResult:
    success: bool
    step: ValidationStep
    output: str
    fixed: bool = False  # True if auto-fix was applied

async def _run_validation(
    self,
    cwd: Path,
    max_retries: int = 3,
) -> list[ValidationResult]:
    """Run validation pipeline with auto-fix retries.

    Returns:
        List of ValidationResults for each step.

    Raises:
        ValidationError: If validation fails after max_retries.
    """
    results = []

    for step in [ValidationStep.FORMAT, ValidationStep.LINT, ValidationStep.TYPECHECK, ValidationStep.TEST]:
        for attempt in range(max_retries):
            result = await self._run_validation_step(step, cwd)

            if result.success:
                results.append(result)
                break

            # Attempt auto-fix for format/lint
            if step in [ValidationStep.FORMAT, ValidationStep.LINT] and attempt < max_retries - 1:
                await self._auto_fix_step(step, cwd)
                continue

            # Non-fixable or exhausted retries
            results.append(result)
            if not result.success:
                return results  # Stop pipeline on failure

    return results
```

---

## 6. System Prompts

### ImplementerAgent System Prompt

```python
IMPLEMENTER_SYSTEM_PROMPT = """You are an expert software engineer focused on methodical, test-driven implementation.

## Core Approach
1. Understand the task fully before writing code
2. Write tests first or alongside implementation (TDD)
3. Follow project conventions from CLAUDE.md
4. Make small, incremental changes with clear commits
5. Validate after each change (format, lint, test)

## Task Execution
For each task:
1. Read the task description carefully
2. Identify affected files and dependencies
3. Write/update tests for the new functionality
4. Implement the minimal code to pass tests
5. Run validation (format, lint, test)
6. Fix any issues before committing
7. Create a commit with conventional commit message

## Conventional Commits
Use format: `type(scope): description`
- feat: New feature
- fix: Bug fix
- refactor: Code refactoring
- test: Test additions/changes
- docs: Documentation
- chore: Maintenance tasks

## Tools Available
Read, Write, Edit, MultiEdit, Bash, Glob, Grep

## Output
After completing a task, provide:
- Files changed (with line counts)
- Tests added/modified
- Commit reference
- Any issues encountered
"""
```

### IssueFixerAgent System Prompt

```python
ISSUE_FIXER_SYSTEM_PROMPT = """You are an expert software engineer focused on minimal, targeted bug fixes.

## Core Approach
1. Understand the issue completely before making changes
2. Identify the root cause, not just symptoms
3. Make the MINIMUM changes necessary to fix the issue
4. Do NOT refactor unrelated code
5. Verify the fix works before committing

## Issue Analysis
For each issue:
1. Read the issue title and description
2. Look for reproduction steps
3. Identify affected code paths
4. Find the root cause
5. Plan the minimal fix

## Fix Guidelines
- Change only what's necessary (target <100 lines for typical bugs)
- Don't "improve" surrounding code
- Don't add features while fixing bugs
- Don't change formatting of untouched code
- Add a test that reproduces the bug (if feasible)

## Verification
Before committing:
1. Run the reproduction steps (if provided)
2. Run related tests
3. Run full validation pipeline
4. Confirm the fix is minimal

## Commit Message
Use format: `fix(scope): description`
Include: `Fixes #<issue_number>` in the commit body

## Tools Available
Read, Write, Edit, Bash, Glob, Grep

## Output
After fixing:
- Issue reference
- Files changed (with line counts)
- Root cause identified
- Verification results
"""
```

---

## 7. Result Dataclasses

### Decision: Extend base patterns from `AgentResult` and `ReviewResult`

### ImplementationResult

```python
from dataclasses import dataclass, field
from typing import Any
from pydantic import BaseModel, Field

class FileChange(BaseModel):
    """Record of a single file change."""
    file_path: str
    lines_added: int = 0
    lines_removed: int = 0
    change_type: str = "modified"  # added, modified, deleted

class TaskResult(BaseModel):
    """Result of a single task execution."""
    task_id: str
    status: str  # completed, failed, skipped
    files_changed: list[FileChange] = Field(default_factory=list)
    tests_added: list[str] = Field(default_factory=list)
    commit_sha: str | None = None
    error: str | None = None
    duration_ms: int = 0

class ImplementationResult(BaseModel):
    """Aggregate result of task file execution."""
    success: bool
    tasks_completed: int
    tasks_failed: int
    tasks_skipped: int
    task_results: list[TaskResult] = Field(default_factory=list)
    files_changed: list[FileChange] = Field(default_factory=list)  # Aggregated
    commits: list[str] = Field(default_factory=list)
    validation_passed: bool = True
    output: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### FixResult

```python
class FixResult(BaseModel):
    """Result of an issue fix attempt."""
    success: bool
    issue_number: int
    issue_title: str
    issue_url: str
    files_changed: list[FileChange] = Field(default_factory=list)
    root_cause: str = ""
    fix_description: str = ""
    commit_sha: str | None = None
    verification_passed: bool = False
    validation_passed: bool = True
    output: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
```

---

## 8. Agent Tool Selection

### Decision: Different tool sets for each agent per principle of least privilege

### ImplementerAgent Tools (FR-003)
```python
IMPLEMENTER_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]
```
- **Write**: Creates new files (tests, implementation)
- **Edit**: Modifies existing files
- **Bash**: Runs validation commands, git operations
- **Read/Glob/Grep**: Code exploration

### IssueFixerAgent Tools (FR-013)
```python
ISSUE_FIXER_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]
# Plus MCP tools if GitHub MCP server is configured:
# "mcp__github__get_issue", "mcp__github__add_comment"
```

Note: Both agents have similar tool sets, but IssueFixerAgent may optionally use GitHub MCP tools for richer issue interaction.

---

## 9. Context Objects

### ImplementerContext

```python
class ImplementerContext(BaseModel):
    """Input context for ImplementerAgent."""
    task_file: Path | None = None  # Path to tasks.md
    task_description: str | None = None  # Direct task (mutually exclusive with task_file)
    branch: str
    cwd: Path = Field(default_factory=Path.cwd)

    @model_validator(mode='after')
    def validate_input(self) -> Self:
        if self.task_file and self.task_description:
            raise ValueError("Provide task_file OR task_description, not both")
        if not self.task_file and not self.task_description:
            raise ValueError("Must provide task_file or task_description")
        return self
```

### IssueFixerContext

```python
class IssueFixerContext(BaseModel):
    """Input context for IssueFixerAgent."""
    issue_number: int | None = None
    issue_data: dict[str, Any] | None = None  # Pre-fetched data
    cwd: Path = Field(default_factory=Path.cwd)

    @model_validator(mode='after')
    def validate_input(self) -> Self:
        if self.issue_number and self.issue_data:
            raise ValueError("Provide issue_number OR issue_data, not both")
        if not self.issue_number and not self.issue_data:
            raise ValueError("Must provide issue_number or issue_data")
        if self.issue_data:
            required = {"number", "title", "body"}
            missing = required - set(self.issue_data.keys())
            if missing:
                raise ValueError(f"issue_data missing required fields: {missing}")
        return self
```

---

## 10. Exception Types

### New Exceptions for exceptions.py

```python
class TaskParseError(AgentError):
    """Exception for task file parsing failures."""
    def __init__(self, message: str, line_number: int | None = None):
        self.line_number = line_number
        super().__init__(message)

class GitError(AgentError):
    """Exception for git operation failures."""
    def __init__(
        self,
        message: str,
        operation: str | None = None,  # e.g., "commit", "stash"
        recoverable: bool = False,
    ):
        self.operation = operation
        self.recoverable = recoverable
        super().__init__(message)

class GitHubError(AgentError):
    """Exception for GitHub API/CLI failures."""
    def __init__(
        self,
        message: str,
        issue_number: int | None = None,
        retry_after: int | None = None,  # Seconds to wait for rate limit
    ):
        self.issue_number = issue_number
        self.retry_after = retry_after
        super().__init__(message)

class ValidationError(AgentError):
    """Exception for validation failures."""
    def __init__(
        self,
        message: str,
        step: str | None = None,  # e.g., "lint", "test"
        output: str | None = None,
    ):
        self.step = step
        self.output = output
        super().__init__(message)
```

---

## Sources

- [Maverick MaverickAgent base.py](./../../src/maverick/agents/base.py) - Base class patterns
- [Maverick CodeReviewerAgent](./../../src/maverick/agents/code_reviewer.py) - Established agent patterns
- [Feature 002-base-agent research.md](../002-base-agent/research.md) - SDK patterns
- [Feature 003-code-reviewer-agent tasks.md](../003-code-reviewer-agent/tasks.md) - Task format reference
- [Spec 004-implementer-issue-fixer-agents](./spec.md) - Feature requirements
- [Maverick Constitution](./../../.specify/memory/constitution.md) - Design principles
