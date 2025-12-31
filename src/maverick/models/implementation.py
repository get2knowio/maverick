"""Implementation models for ImplementerAgent.

This module defines data models for task execution, file changes,
validation results, and implementation outcomes.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

# =============================================================================
# Enums (T009)
# =============================================================================


class TaskStatus(str, Enum):
    """Status of a task in the task file.

    Attributes:
        PENDING: Task not yet started (checkbox unchecked `[ ]`).
        IN_PROGRESS: Task currently being executed.
        COMPLETED: Task successfully completed (checkbox checked `[x]`).
        FAILED: Task failed during execution.
        SKIPPED: Task skipped (dependencies failed or not applicable).

    Examples:
        >>> TaskStatus.PENDING
        <TaskStatus.PENDING: 'pending'>
        >>> TaskStatus.PENDING.value
        'pending'
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ChangeType(str, Enum):
    """Type of file change.

    Attributes:
        ADDED: New file created.
        MODIFIED: Existing file changed.
        DELETED: File removed.
        RENAMED: File renamed/moved.

    Examples:
        >>> ChangeType.MODIFIED
        <ChangeType.MODIFIED: 'modified'>
        >>> ChangeType.MODIFIED.value
        'modified'
    """

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class ValidationStep(str, Enum):
    """Steps in the validation pipeline.

    Attributes:
        FORMAT: Code formatting (ruff format).
        LINT: Linting (ruff check).
        TYPECHECK: Type checking (mypy).
        TEST: Unit/integration tests (pytest).

    Examples:
        >>> ValidationStep.FORMAT
        <ValidationStep.FORMAT: 'format'>
        >>> ValidationStep.FORMAT.value
        'format'
    """

    FORMAT = "format"
    LINT = "lint"
    TYPECHECK = "typecheck"
    TEST = "test"


# =============================================================================
# Value Objects (T010, T011, T012)
# =============================================================================


class Task(BaseModel):
    """Individual task parsed from a tasks.md file (T010).

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
        ...     description="Implement authentication module",
        ...     status=TaskStatus.PENDING,
        ...     parallel=False,
        ...     dependencies=[]
        ... )
        >>> task.is_actionable
        True
        >>> task.is_parallelizable
        False
    """

    id: str = Field(
        pattern=r"T\d{3,}",
        description="Task ID in format T### (e.g., T001)",
    )
    description: str = Field(
        min_length=1,
        description="Task description",
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        description="Current task status",
    )
    parallel: bool = Field(
        default=False,
        description="True if can run in parallel with other tasks",
    )
    user_story: str | None = Field(
        default=None,
        pattern=r"US\d+",
        description="User story reference (e.g., US1)",
    )
    phase: str | None = Field(
        default=None,
        description="Phase/section from markdown header",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Task IDs this task depends on",
    )

    model_config = ConfigDict(frozen=True)

    @property
    def is_parallelizable(self) -> bool:
        """Check if task can run concurrently.

        Returns:
            True if task is marked parallel and has no dependencies.
        """
        return self.parallel and not self.dependencies

    @property
    def is_actionable(self) -> bool:
        """Check if task is ready to execute.

        Returns:
            True if task status is PENDING.
        """
        return self.status == TaskStatus.PENDING


class FileChange(BaseModel):
    """Record of a single file modification (T011).

    Tracks what changed in a file during implementation or fix.

    Attributes:
        file_path: Path relative to repository root.
        change_type: Type of change (added, modified, deleted, renamed).
        lines_added: Number of lines added.
        lines_removed: Number of lines removed.
        old_path: Original path if renamed.

    Examples:
        >>> change = FileChange(
        ...     file_path="src/maverick/models/implementation.py",
        ...     change_type=ChangeType.ADDED,
        ...     lines_added=150,
        ...     lines_removed=0
        ... )
        >>> change.net_lines
        150
    """

    file_path: str = Field(description="File path relative to repo root")
    change_type: ChangeType = Field(
        default=ChangeType.MODIFIED,
        description="Type of file change",
    )
    lines_added: int = Field(
        default=0,
        ge=0,
        description="Lines added",
    )
    lines_removed: int = Field(
        default=0,
        ge=0,
        description="Lines removed",
    )
    old_path: str | None = Field(
        default=None,
        description="Original path if renamed",
    )

    model_config = ConfigDict(frozen=True)

    @property
    def net_lines(self) -> int:
        """Net change in lines (added - removed).

        Returns:
            The difference between lines_added and lines_removed.
        """
        return self.lines_added - self.lines_removed


class ValidationResult(BaseModel):
    """Result of a single validation step (T012).

    Captures the outcome of running a validation step (format, lint,
    typecheck, or test) during the implementation validation pipeline.

    Attributes:
        step: Which validation step was run.
        success: True if validation passed.
        output: Command output (stdout/stderr).
        duration_ms: Time taken in milliseconds.
        auto_fixed: True if issues were auto-fixed.

    Examples:
        >>> result = ValidationResult(
        ...     step=ValidationStep.FORMAT,
        ...     success=True,
        ...     output="",
        ...     duration_ms=1200,
        ...     auto_fixed=True
        ... )
        >>> result.success
        True
    """

    step: ValidationStep = Field(description="Validation step name")
    success: bool = Field(description="True if step passed")
    output: str = Field(
        default="",
        description="Command output",
    )
    duration_ms: int = Field(
        default=0,
        ge=0,
        description="Duration in milliseconds",
    )
    auto_fixed: bool = Field(
        default=False,
        description="True if auto-fix was applied",
    )

    model_config = ConfigDict(frozen=True)


# =============================================================================
# Aggregate Objects (T013)
# =============================================================================


class TaskFile(BaseModel):
    """Parsed representation of a tasks.md file.

    Contains all tasks with their metadata, grouped by phase.
    Supports parsing from markdown content and tracking task execution state.

    Attributes:
        path: Path to the source tasks.md file.
        tasks: Ordered list of all tasks.
        phases: Tasks grouped by phase name.

    Examples:
        >>> content = '''## Phase 1
        ... - [ ] T001 Create directory
        ... - [ ] T002 [P] Create init file
        ... '''
        >>> task_file = TaskFile.parse(Path("tasks.md"), content)
        >>> task_file.pending_tasks
        [Task(id='T001', ...), Task(id='T002', ...)]
    """

    path: Path = Field(description="Path to tasks.md file")
    tasks: list[Task] = Field(default_factory=list, description="All tasks in order")
    phases: dict[str, list[Task]] = Field(
        default_factory=dict,
        description="Tasks grouped by phase",
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def parse(cls, path: Path, content: str | None = None) -> TaskFile:
        """Parse a tasks.md file into a TaskFile object.

        Args:
            path: Path to the tasks.md file.
            content: Optional content string. If not provided, reads from path.

        Returns:
            TaskFile with parsed tasks and phases.

        Raises:
            TaskParseError: If file format is invalid.
            FileNotFoundError: If path doesn't exist and content not provided.

        Note:
            For async contexts, use `parse_async()` instead to avoid blocking I/O.
        """
        from maverick.utils.task_parser import parse_tasks_md

        if content is None:
            content = path.read_text()

        tasks, phases = parse_tasks_md(content)
        return cls(path=path, tasks=tasks, phases=phases)

    @classmethod
    async def parse_async(cls, path: Path, content: str | None = None) -> TaskFile:
        """Parse a tasks.md file asynchronously.

        Args:
            path: Path to the tasks.md file.
            content: Optional content string. If not provided, reads from path.

        Returns:
            TaskFile with parsed tasks and phases.

        Raises:
            TaskParseError: If file format is invalid.
            FileNotFoundError: If path doesn't exist and content not provided.
        """
        import aiofiles

        from maverick.utils.task_parser import parse_tasks_md

        if content is None:
            async with aiofiles.open(path, encoding="utf-8") as f:
                content = await f.read()

        tasks, phases = parse_tasks_md(content)
        return cls(path=path, tasks=tasks, phases=phases)

    @property
    def pending_tasks(self) -> list[Task]:
        """Get all pending tasks."""
        return [t for t in self.tasks if t.status == TaskStatus.PENDING]

    @property
    def completed_tasks(self) -> list[Task]:
        """Get all completed tasks."""
        return [t for t in self.tasks if t.status == TaskStatus.COMPLETED]

    @property
    def failed_tasks(self) -> list[Task]:
        """Get all failed tasks."""
        return [t for t in self.tasks if t.status == TaskStatus.FAILED]

    def get_parallel_batch(self) -> list[Task]:
        """Get next batch of parallelizable pending tasks.

        Returns consecutive pending tasks that are marked as parallel.
        Stops at the first non-parallel task.

        Returns:
            List of tasks that can run in parallel.
        """
        batch: list[Task] = []
        for task in self.pending_tasks:
            if task.parallel and not task.dependencies:
                batch.append(task)
            elif batch:
                # Stop at first non-parallel task after we have some parallel tasks
                break
            else:
                # First task is not parallel, return empty batch
                break
        return batch

    def get_next_sequential(self) -> Task | None:
        """Get next non-parallel pending task.

        Returns:
            The next sequential task to execute, or None if all tasks
            are either completed or parallel.
        """
        for task in self.pending_tasks:
            if not task.parallel:
                return task
        return None

    def mark_task_status(self, task_id: str, status: TaskStatus) -> TaskFile:
        """Create a new TaskFile with one task's status updated.

        Since tasks are frozen, this creates new Task instances.

        Args:
            task_id: ID of task to update.
            status: New status for the task.

        Returns:
            New TaskFile with updated task status.
        """
        new_tasks = []
        for task in self.tasks:
            if task.id == task_id:
                # Create new task with updated status
                new_tasks.append(
                    Task(
                        id=task.id,
                        description=task.description,
                        status=status,
                        parallel=task.parallel,
                        user_story=task.user_story,
                        phase=task.phase,
                        dependencies=task.dependencies,
                    )
                )
            else:
                new_tasks.append(task)

        # Update phases dict
        new_phases: dict[str, list[Task]] = {}
        for phase_name, _phase_tasks in self.phases.items():
            new_phases[phase_name] = [t for t in new_tasks if t.phase == phase_name]

        return TaskFile(path=self.path, tasks=new_tasks, phases=new_phases)


# =============================================================================
# Phase Results
# =============================================================================


class PhaseResult(BaseModel):
    """Result of executing all tasks in a single phase.

    Represents the outcome of phase-level task execution where Claude
    handles parallelization of [P] marked tasks within the phase.

    Attributes:
        phase_name: Name of the phase (from tasks.md header).
        success: True if all tasks in phase completed successfully.
        tasks_completed: Count of successful tasks.
        tasks_failed: Count of failed tasks.
        task_results: Individual results for each task in the phase.
        files_changed: Aggregated file changes for the phase.
        duration_ms: Total execution time in milliseconds.
        error: Error message if phase failed.

    Examples:
        >>> result = PhaseResult(
        ...     phase_name="Phase 1: Setup",
        ...     success=True,
        ...     tasks_completed=3,
        ...     tasks_failed=0,
        ...     task_results=[...],
        ...     files_changed=[...],
        ...     duration_ms=12500
        ... )
        >>> result.success
        True
    """

    phase_name: str = Field(description="Phase name from tasks.md header")
    success: bool = Field(description="True if all phase tasks succeeded")
    tasks_completed: int = Field(ge=0, description="Count of completed tasks")
    tasks_failed: int = Field(ge=0, description="Count of failed tasks")
    task_results: list["TaskResult"] = Field(  # noqa: UP037
        default_factory=list, description="Results per task in phase"
    )
    files_changed: list[FileChange] = Field(
        default_factory=list, description="File changes in phase"
    )
    duration_ms: int = Field(default=0, ge=0, description="Execution duration")
    error: str | None = Field(default=None, description="Error message if phase failed")

    model_config = ConfigDict(frozen=True)

    @property
    def total_tasks(self) -> int:
        """Total number of tasks in phase."""
        return self.tasks_completed + self.tasks_failed


# =============================================================================
# Task Results (T026, T027)
# =============================================================================


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
    """

    task_id: str = Field(description="Task ID")
    status: TaskStatus = Field(description="Final task status")
    files_changed: list[FileChange] = Field(
        default_factory=list, description="Files modified"
    )
    tests_added: list[str] = Field(default_factory=list, description="Test files added")
    commit_sha: str | None = Field(default=None, description="Commit SHA if committed")
    error: str | None = Field(default=None, description="Error message if failed")
    duration_ms: int = Field(default=0, ge=0, description="Execution duration")
    validation: list[ValidationResult] = Field(
        default_factory=list, description="Validation results"
    )

    @property
    def succeeded(self) -> bool:
        """Check if task completed successfully."""
        return self.status == TaskStatus.COMPLETED


class ImplementationResult(BaseModel):
    """Aggregate result of task file execution.

    Attributes:
        success: True if all tasks completed successfully.
        tasks_completed: Count of successful tasks.
        tasks_failed: Count of failed tasks.
        tasks_skipped: Count of skipped tasks.
        task_results: Individual results for each task.
        files_changed: Aggregated file changes.
        commits: List of commit SHAs created.
        validation_passed: True if final validation passed.
        output: Raw agent output for debugging.
        metadata: Additional context.
        errors: List of error messages.
    """

    success: bool = Field(description="True if all tasks succeeded")
    tasks_completed: int = Field(ge=0, description="Count of completed tasks")
    tasks_failed: int = Field(ge=0, description="Count of failed tasks")
    tasks_skipped: int = Field(ge=0, description="Count of skipped tasks")
    task_results: list[TaskResult] = Field(
        default_factory=list, description="Results per task"
    )
    files_changed: list[FileChange] = Field(
        default_factory=list, description="All file changes"
    )
    commits: list[str] = Field(default_factory=list, description="Commit SHAs created")
    validation_passed: bool = Field(default=True, description="Final validation status")
    output: str = Field(default="", description="Raw output for debugging")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional context"
    )
    errors: list[str] = Field(default_factory=list, description="Error messages")

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
        tests: list[str] = []
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


# =============================================================================
# Context Objects (T028)
# =============================================================================


class ImplementerContext(BaseModel):
    """Input context for ImplementerAgent execution.

    Provides task source (file or description) and execution environment.

    Attributes:
        task_file: Path to tasks.md file (mutually exclusive with task_description).
        task_description: Direct task description (mutually exclusive with task_file).
        phase_name: Optional phase name to filter tasks to a specific phase.
        branch: Git branch name for context.
        cwd: Working directory for execution.
        skip_validation: If True, skip validation steps.
        dry_run: If True, don't commit changes.
    """

    task_file: Path | None = Field(default=None, description="Path to tasks.md file")
    task_description: str | None = Field(
        default=None,
        min_length=10,
        description="Direct task description",
    )
    phase_name: str | None = Field(
        default=None,
        description="Phase name to execute (enables phase-level execution mode)",
    )
    branch: str = Field(min_length=1, description="Git branch name")
    cwd: Path = Field(default_factory=Path.cwd, description="Working directory")
    skip_validation: bool = Field(default=False, description="Skip validation steps")
    dry_run: bool = Field(default=False, description="Don't create commits")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="after")
    def validate_task_source(self) -> ImplementerContext:
        """Ensure exactly one task source is provided."""
        if self.task_file and self.task_description:
            raise ValueError("Provide task_file OR task_description, not both")
        if not self.task_file and not self.task_description:
            raise ValueError("Must provide task_file or task_description")
        if self.phase_name and self.task_description:
            raise ValueError("phase_name requires task_file, not task_description")
        return self

    @property
    def is_single_task(self) -> bool:
        """Check if executing a single task description."""
        return self.task_description is not None

    @property
    def is_phase_mode(self) -> bool:
        """Check if executing in phase-level mode."""
        return self.phase_name is not None and self.task_file is not None
