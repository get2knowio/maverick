# Data Model: ImplementerAgent and IssueFixerAgent

**Feature**: 004-implementer-issue-fixer-agents | **Date**: 2025-12-14

## Overview

This document defines the data models for the ImplementerAgent and IssueFixerAgent feature, following patterns established in `src/maverick/models/review.py`.

---

## Enums

### TaskStatus

```python
class TaskStatus(str, Enum):
    """Status of a task in the task file.

    Attributes:
        PENDING: Task not yet started (checkbox unchecked `[ ]`).
        IN_PROGRESS: Task currently being executed.
        COMPLETED: Task successfully completed (checkbox checked `[x]`).
        FAILED: Task failed during execution.
        SKIPPED: Task skipped (dependencies failed or not applicable).
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
```

### ChangeType

```python
class ChangeType(str, Enum):
    """Type of file change.

    Attributes:
        ADDED: New file created.
        MODIFIED: Existing file changed.
        DELETED: File removed.
        RENAMED: File renamed/moved.
    """

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
```

### ValidationStep

```python
class ValidationStep(str, Enum):
    """Steps in the validation pipeline.

    Attributes:
        FORMAT: Code formatting (ruff format).
        LINT: Linting (ruff check).
        TYPECHECK: Type checking (mypy).
        TEST: Unit/integration tests (pytest).
    """

    FORMAT = "format"
    LINT = "lint"
    TYPECHECK = "typecheck"
    TEST = "test"
```

---

## Value Objects (Immutable)

### Task

```python
class Task(BaseModel):
    """Individual task parsed from a tasks.md file.

    Represents a single actionable item with metadata extracted
    from the .specify tasks.md format.

    Attributes:
        id: Unique task identifier (e.g., "T001", "T042").
        description: Human-readable task description.
        status: Current execution status.
        parallel: True if marked for parallel execution ([P] or P:).
        user_story: Optional user story reference (e.g., "US1", "US2").
        phase: Optional phase/section name from markdown header.
        dependencies: List of task IDs this task depends on.

    Examples:
        >>> task = Task(
        ...     id="T001",
        ...     description="Create directory structure",
        ...     status=TaskStatus.PENDING,
        ...     parallel=False,
        ...     phase="Phase 1: Setup"
        ... )
        >>> task.is_parallelizable
        False
    """

    id: str = Field(
        pattern=r"T\d{3,}",
        description="Task ID in format T### (e.g., T001)"
    )
    description: str = Field(
        min_length=5,
        description="Task description"
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        description="Current task status"
    )
    parallel: bool = Field(
        default=False,
        description="True if can run in parallel with other tasks"
    )
    user_story: str | None = Field(
        default=None,
        pattern=r"US\d+",
        description="User story reference (e.g., US1)"
    )
    phase: str | None = Field(
        default=None,
        description="Phase/section from markdown header"
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Task IDs this task depends on"
    )

    model_config = ConfigDict(frozen=True)

    @property
    def is_parallelizable(self) -> bool:
        """Check if task can run concurrently."""
        return self.parallel and not self.dependencies

    @property
    def is_actionable(self) -> bool:
        """Check if task is ready to execute."""
        return self.status == TaskStatus.PENDING
```

### FileChange

```python
class FileChange(BaseModel):
    """Record of a single file modification.

    Tracks what changed in a file during implementation or fix.

    Attributes:
        file_path: Path relative to repository root.
        change_type: Type of change (added, modified, deleted, renamed).
        lines_added: Number of lines added.
        lines_removed: Number of lines removed.
        old_path: Original path if renamed.

    Examples:
        >>> change = FileChange(
        ...     file_path="src/maverick/agents/implementer.py",
        ...     change_type=ChangeType.ADDED,
        ...     lines_added=150,
        ...     lines_removed=0
        ... )
    """

    file_path: str = Field(
        description="File path relative to repo root"
    )
    change_type: ChangeType = Field(
        default=ChangeType.MODIFIED,
        description="Type of file change"
    )
    lines_added: int = Field(
        default=0,
        ge=0,
        description="Lines added"
    )
    lines_removed: int = Field(
        default=0,
        ge=0,
        description="Lines removed"
    )
    old_path: str | None = Field(
        default=None,
        description="Original path if renamed"
    )

    model_config = ConfigDict(frozen=True)

    @property
    def net_lines(self) -> int:
        """Net change in lines (added - removed)."""
        return self.lines_added - self.lines_removed
```

### ValidationResult

```python
class ValidationResult(BaseModel):
    """Result of a single validation step.

    Attributes:
        step: Which validation step was run.
        success: True if validation passed.
        output: Command output (stdout/stderr).
        duration_ms: Time taken in milliseconds.
        auto_fixed: True if issues were auto-fixed.

    Examples:
        >>> result = ValidationResult(
        ...     step=ValidationStep.LINT,
        ...     success=True,
        ...     output="All checks passed",
        ...     duration_ms=1200
        ... )
    """

    step: ValidationStep = Field(
        description="Validation step name"
    )
    success: bool = Field(
        description="True if step passed"
    )
    output: str = Field(
        default="",
        description="Command output"
    )
    duration_ms: int = Field(
        default=0,
        ge=0,
        description="Duration in milliseconds"
    )
    auto_fixed: bool = Field(
        default=False,
        description="True if auto-fix was applied"
    )

    model_config = ConfigDict(frozen=True)
```

---

## Aggregate Objects

### TaskFile

```python
class TaskFile(BaseModel):
    """Parsed representation of a tasks.md file.

    Contains all tasks with their metadata, grouped by phase.

    Attributes:
        path: Path to the source tasks.md file.
        tasks: Ordered list of all tasks.
        phases: Tasks grouped by phase name.

    Examples:
        >>> task_file = TaskFile.parse(Path("specs/004/tasks.md"))
        >>> task_file.pending_tasks
        [Task(...), Task(...)]
        >>> task_file.get_parallel_batch()
        [Task(...), Task(...)]  # All tasks marked [P] that are ready
    """

    path: Path = Field(
        description="Path to tasks.md file"
    )
    tasks: list[Task] = Field(
        default_factory=list,
        description="All tasks in order"
    )
    phases: dict[str, list[Task]] = Field(
        default_factory=dict,
        description="Tasks grouped by phase"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def pending_tasks(self) -> list[Task]:
        """Get all pending tasks."""
        return [t for t in self.tasks if t.status == TaskStatus.PENDING]

    @property
    def completed_tasks(self) -> list[Task]:
        """Get all completed tasks."""
        return [t for t in self.tasks if t.status == TaskStatus.COMPLETED]

    def get_parallel_batch(self) -> list[Task]:
        """Get next batch of parallelizable pending tasks."""
        return [t for t in self.pending_tasks if t.is_parallelizable]

    def get_next_sequential(self) -> Task | None:
        """Get next non-parallel pending task."""
        for task in self.pending_tasks:
            if not task.parallel:
                return task
        return None
```

### TaskResult

```python
class TaskResult(BaseModel):
    """Result of executing a single task.

    Attributes:
        task_id: ID of the executed task.
        status: Final status after execution.
        files_changed: List of file changes made.
        tests_added: List of test file paths added/modified.
        commit_sha: Git commit SHA if committed.
        error: Error message if failed.
        duration_ms: Execution time in milliseconds.
        validation: Validation results for this task.

    Examples:
        >>> result = TaskResult(
        ...     task_id="T001",
        ...     status=TaskStatus.COMPLETED,
        ...     files_changed=[FileChange(...)],
        ...     commit_sha="abc123"
        ... )
    """

    task_id: str = Field(
        description="Task ID"
    )
    status: TaskStatus = Field(
        description="Final task status"
    )
    files_changed: list[FileChange] = Field(
        default_factory=list,
        description="Files modified by this task"
    )
    tests_added: list[str] = Field(
        default_factory=list,
        description="Test files added/modified"
    )
    commit_sha: str | None = Field(
        default=None,
        description="Commit SHA if committed"
    )
    error: str | None = Field(
        default=None,
        description="Error message if failed"
    )
    duration_ms: int = Field(
        default=0,
        ge=0,
        description="Execution duration"
    )
    validation: list[ValidationResult] = Field(
        default_factory=list,
        description="Validation results"
    )

    @property
    def succeeded(self) -> bool:
        """Check if task completed successfully."""
        return self.status == TaskStatus.COMPLETED
```

---

## Result Objects

### ImplementationResult

```python
class ImplementationResult(BaseModel):
    """Aggregate result of task file execution (FR-009).

    Returned by ImplementerAgent.execute() to summarize
    all task executions and their outcomes.

    Attributes:
        success: True if all tasks completed successfully.
        tasks_completed: Count of successful tasks.
        tasks_failed: Count of failed tasks.
        tasks_skipped: Count of skipped tasks.
        task_results: Individual results for each task.
        files_changed: Aggregated file changes across all tasks.
        commits: List of commit SHAs created.
        validation_passed: True if final validation passed.
        output: Raw agent output for debugging.
        metadata: Additional context (branch, timestamps, etc.).
        errors: List of error messages encountered.

    Examples:
        >>> result = ImplementationResult(
        ...     success=True,
        ...     tasks_completed=5,
        ...     tasks_failed=0,
        ...     tasks_skipped=0,
        ...     commits=["abc123", "def456"]
        ... )
        >>> result.total_lines_changed
        250
    """

    success: bool = Field(
        description="True if all tasks succeeded"
    )
    tasks_completed: int = Field(
        ge=0,
        description="Count of completed tasks"
    )
    tasks_failed: int = Field(
        ge=0,
        description="Count of failed tasks"
    )
    tasks_skipped: int = Field(
        ge=0,
        description="Count of skipped tasks"
    )
    task_results: list[TaskResult] = Field(
        default_factory=list,
        description="Results per task"
    )
    files_changed: list[FileChange] = Field(
        default_factory=list,
        description="All file changes"
    )
    commits: list[str] = Field(
        default_factory=list,
        description="Commit SHAs created"
    )
    validation_passed: bool = Field(
        default=True,
        description="Final validation status"
    )
    output: str = Field(
        default="",
        description="Raw output for debugging"
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Additional context"
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Error messages"
    )

    @property
    def total_tasks(self) -> int:
        """Total number of tasks processed."""
        return self.tasks_completed + self.tasks_failed + self.tasks_skipped

    @property
    def total_lines_changed(self) -> int:
        """Total lines added + removed."""
        return sum(c.lines_added + c.lines_removed for c in self.files_changed)

    @property
    def tests_added(self) -> list[str]:
        """All test files across all tasks."""
        tests = []
        for tr in self.task_results:
            tests.extend(tr.tests_added)
        return list(set(tests))

    def to_summary(self) -> str:
        """Generate human-readable summary."""
        parts = [f"{self.tasks_completed}/{self.total_tasks} tasks completed"]
        if self.tasks_failed > 0:
            parts.append(f"{self.tasks_failed} failed")
        if self.commits:
            parts.append(f"{len(self.commits)} commits")
        if not self.validation_passed:
            parts.append("validation failed")
        return ", ".join(parts)
```

### FixResult

```python
class FixResult(BaseModel):
    """Result of a GitHub issue fix attempt (FR-020).

    Returned by IssueFixerAgent.execute() to summarize
    the fix attempt and verification.

    Attributes:
        success: True if issue was fixed and verified.
        issue_number: GitHub issue number.
        issue_title: Issue title for reference.
        issue_url: Link to the GitHub issue.
        root_cause: Identified root cause of the issue.
        fix_description: Description of the fix applied.
        files_changed: List of file changes made.
        commit_sha: Git commit SHA if committed.
        verification_passed: True if fix was verified working.
        validation_passed: True if code validation passed.
        output: Raw agent output for debugging.
        metadata: Additional context.
        errors: List of error messages encountered.

    Examples:
        >>> result = FixResult(
        ...     success=True,
        ...     issue_number=42,
        ...     issue_title="Login fails on Safari",
        ...     issue_url="https://github.com/org/repo/issues/42",
        ...     root_cause="Missing WebKit-specific CSS prefix",
        ...     fix_description="Added -webkit- prefix to flexbox rules"
        ... )
    """

    success: bool = Field(
        description="True if issue was fixed"
    )
    issue_number: int = Field(
        ge=1,
        description="GitHub issue number"
    )
    issue_title: str = Field(
        description="Issue title"
    )
    issue_url: str = Field(
        description="GitHub issue URL"
    )
    root_cause: str = Field(
        default="",
        description="Identified root cause"
    )
    fix_description: str = Field(
        default="",
        description="Description of fix applied"
    )
    files_changed: list[FileChange] = Field(
        default_factory=list,
        description="Files modified"
    )
    commit_sha: str | None = Field(
        default=None,
        description="Commit SHA if committed"
    )
    verification_passed: bool = Field(
        default=False,
        description="True if fix was verified"
    )
    validation_passed: bool = Field(
        default=True,
        description="True if validation passed"
    )
    output: str = Field(
        default="",
        description="Raw output for debugging"
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Additional context"
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Error messages"
    )

    @property
    def total_lines_changed(self) -> int:
        """Total lines added + removed."""
        return sum(c.lines_added + c.lines_removed for c in self.files_changed)

    @property
    def is_minimal_fix(self) -> bool:
        """Check if fix is under 100 lines (typical bug fix target)."""
        return self.total_lines_changed < 100

    def to_summary(self) -> str:
        """Generate human-readable summary."""
        status = "Fixed" if self.success else "Failed"
        parts = [f"{status} #{self.issue_number}: {self.issue_title}"]
        if self.files_changed:
            parts.append(f"{len(self.files_changed)} files, {self.total_lines_changed} lines")
        if self.verification_passed:
            parts.append("verified")
        return " | ".join(parts)
```

---

## Context Objects

### ImplementerContext

```python
class ImplementerContext(BaseModel):
    """Input context for ImplementerAgent execution (FR-004).

    Provides task source (file or description) and execution environment.

    Attributes:
        task_file: Path to tasks.md file (mutually exclusive with task_description).
        task_description: Direct task description (mutually exclusive with task_file).
        branch: Git branch name for context.
        cwd: Working directory for execution.
        skip_validation: If True, skip validation steps (for testing).
        dry_run: If True, don't commit changes (for testing).

    Examples:
        >>> context = ImplementerContext(
        ...     task_file=Path("specs/004/tasks.md"),
        ...     branch="feature/implement-agents"
        ... )

        >>> context = ImplementerContext(
        ...     task_description="Add logging to the API handler",
        ...     branch="feature/add-logging"
        ... )
    """

    task_file: Path | None = Field(
        default=None,
        description="Path to tasks.md file"
    )
    task_description: str | None = Field(
        default=None,
        min_length=10,
        description="Direct task description"
    )
    branch: str = Field(
        min_length=1,
        description="Git branch name"
    )
    cwd: Path = Field(
        default_factory=Path.cwd,
        description="Working directory"
    )
    skip_validation: bool = Field(
        default=False,
        description="Skip validation steps"
    )
    dry_run: bool = Field(
        default=False,
        description="Don't create commits"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode='after')
    def validate_task_source(self) -> Self:
        """Ensure exactly one task source is provided (FR-010)."""
        if self.task_file and self.task_description:
            raise ValueError("Provide task_file OR task_description, not both")
        if not self.task_file and not self.task_description:
            raise ValueError("Must provide task_file or task_description")
        return self

    @property
    def is_single_task(self) -> bool:
        """Check if executing a single task description."""
        return self.task_description is not None
```

### IssueFixerContext

```python
class IssueFixerContext(BaseModel):
    """Input context for IssueFixerAgent execution (FR-014).

    Provides issue source (number or pre-fetched data) and execution environment.

    Attributes:
        issue_number: GitHub issue number (mutually exclusive with issue_data).
        issue_data: Pre-fetched issue data (mutually exclusive with issue_number).
        cwd: Working directory for execution.
        skip_validation: If True, skip validation steps.
        dry_run: If True, don't commit changes.

    Examples:
        >>> context = IssueFixerContext(
        ...     issue_number=42
        ... )

        >>> context = IssueFixerContext(
        ...     issue_data={
        ...         "number": 42,
        ...         "title": "Bug in login",
        ...         "body": "Steps to reproduce..."
        ...     }
        ... )
    """

    issue_number: int | None = Field(
        default=None,
        ge=1,
        description="GitHub issue number"
    )
    issue_data: dict | None = Field(
        default=None,
        description="Pre-fetched issue data"
    )
    cwd: Path = Field(
        default_factory=Path.cwd,
        description="Working directory"
    )
    skip_validation: bool = Field(
        default=False,
        description="Skip validation steps"
    )
    dry_run: bool = Field(
        default=False,
        description="Don't create commits"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode='after')
    def validate_issue_source(self) -> Self:
        """Ensure exactly one issue source is provided."""
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

    @property
    def effective_issue_number(self) -> int:
        """Get issue number from either source."""
        if self.issue_number:
            return self.issue_number
        return self.issue_data["number"]  # type: ignore
```

---

## Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Task File Flow                           │
│                                                                 │
│   TaskFile ────contains────> Task (many)                       │
│      │                         │                                │
│      │                         ▼                                │
│      │                    TaskResult                            │
│      │                         │                                │
│      └───────aggregates───────>│                                │
│                                ▼                                │
│                      ImplementationResult                       │
│                              │                                  │
│                              ├──> FileChange (many)             │
│                              ├──> ValidationResult (many)       │
│                              └──> commits (list[str])           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        Issue Fix Flow                           │
│                                                                 │
│   IssueFixerContext ────> GitHub Issue Data                    │
│          │                      │                               │
│          │                      ▼                               │
│          │                 IssueFixerAgent                      │
│          │                      │                               │
│          └──────────────────────┤                               │
│                                 ▼                               │
│                            FixResult                            │
│                                 │                               │
│                                 ├──> FileChange (many)          │
│                                 ├──> ValidationResult (many)    │
│                                 └──> commit_sha                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## File Locations

| Model | File |
|-------|------|
| TaskStatus, ChangeType, ValidationStep | `src/maverick/models/implementation.py` |
| Task, TaskFile | `src/maverick/models/implementation.py` |
| FileChange, ValidationResult | `src/maverick/models/implementation.py` |
| TaskResult, ImplementationResult | `src/maverick/models/implementation.py` |
| ImplementerContext | `src/maverick/models/implementation.py` |
| FixResult | `src/maverick/models/issue_fix.py` |
| IssueFixerContext | `src/maverick/models/issue_fix.py` |

---

## JSON Serialization

All models support `model_dump_json()` and `model_validate_json()` for:
- Agent output parsing (FR-025)
- TUI state persistence
- Workflow checkpointing (Constitution VIII)

Example:
```python
# Serialize
json_str = result.model_dump_json(indent=2)

# Deserialize
result = ImplementationResult.model_validate_json(json_str)
```
