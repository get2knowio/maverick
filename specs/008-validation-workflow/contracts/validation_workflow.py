"""Validation Workflow Contract Definitions.

This module defines the public interface contracts for the validation workflow.
These are type stubs and protocol definitions that document the expected API.

Note: This is a contract file, not implementation. It serves as the specification
for the actual implementation in src/maverick/workflows/validation.py.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from maverick.agents.base import MaverickAgent


# =============================================================================
# Enums (FR-002, FR-015)
# =============================================================================


class StageStatus(str, Enum):
    """Status of a validation stage.

    Represents the current or final state of a validation stage during
    workflow execution.

    Attributes:
        PENDING: Stage has not started execution.
        IN_PROGRESS: Stage is currently executing.
        PASSED: Stage completed successfully on first attempt.
        FAILED: Stage failed after exhausting all fix attempts.
        FIXED: Stage passed after one or more fix attempts.
        CANCELLED: Stage was terminated due to workflow cancellation.
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    FIXED = "fixed"
    CANCELLED = "cancelled"


# =============================================================================
# Configuration Models (FR-001 to FR-005)
# =============================================================================


class ValidationStage(BaseModel):
    """Configuration for a single validation stage.

    Defines a validation step with its command, fixability settings,
    and execution parameters.

    Attributes:
        name: Stage identifier (e.g., "format", "lint", "build", "test").
        command: Command and arguments to execute as list of strings.
        fixable: Whether the fix agent can attempt to repair failures.
        max_fix_attempts: Maximum fix attempts; 0 means non-fixable.
        timeout_seconds: Maximum execution time per command run.

    Example:
        >>> stage = ValidationStage(
        ...     name="lint",
        ...     command=["ruff", "check", "--fix", "."],
        ...     fixable=True,
        ...     max_fix_attempts=3,
        ... )
        >>> stage.is_fixable
        True
    """

    name: str = Field(min_length=1, description="Stage identifier")
    command: list[str] = Field(min_length=1, description="Command to execute")
    fixable: bool = Field(default=True, description="Can fix agent repair failures")
    max_fix_attempts: int = Field(
        default=3, ge=0, description="Max fix attempts (0 = non-fixable)"
    )
    timeout_seconds: float = Field(
        default=300.0, gt=0, description="Per-command timeout in seconds"
    )

    model_config = ConfigDict(frozen=True)

    @property
    def is_fixable(self) -> bool:
        """Check if stage can be fixed.

        Returns:
            True if fixable is True AND max_fix_attempts > 0.
        """
        return self.fixable and self.max_fix_attempts > 0


class ValidationWorkflowConfig(BaseModel):
    """Configuration options for workflow execution.

    Attributes:
        dry_run: If True, report planned actions without executing commands.
        stop_on_failure: If True, stop workflow at first stage failure.
        cwd: Working directory for command execution.
    """

    dry_run: bool = Field(default=False, description="Report without execution")
    stop_on_failure: bool = Field(default=False, description="Stop at first failure")
    cwd: Path | None = Field(default=None, description="Working directory")

    model_config = ConfigDict(arbitrary_types_allowed=True)


# =============================================================================
# Result Models (FR-014 to FR-017)
# =============================================================================


class StageResult(BaseModel):
    """Outcome of running a single validation stage.

    Captures the final state, fix attempts, and any error information
    for a completed or failed stage.

    Attributes:
        stage_name: Identifier of the executed stage.
        status: Final status after execution.
        fix_attempts: Number of fix attempts made (0 if passed first try).
        error_message: Final error message if status is FAILED.
        output: Combined stdout/stderr from command execution.
        duration_ms: Total execution time including all retries.
    """

    stage_name: str = Field(description="Stage identifier")
    status: StageStatus = Field(description="Final stage status")
    fix_attempts: int = Field(default=0, ge=0, description="Fix attempts made")
    error_message: str | None = Field(default=None, description="Error if failed")
    output: str = Field(default="", description="Command output")
    duration_ms: int = Field(default=0, ge=0, description="Total duration")

    model_config = ConfigDict(frozen=True)

    @property
    def was_fixed(self) -> bool:
        """Check if stage was fixed."""
        return self.status == StageStatus.FIXED

    @property
    def passed(self) -> bool:
        """Check if stage ultimately passed."""
        return self.status in (StageStatus.PASSED, StageStatus.FIXED)


class ValidationWorkflowResult(BaseModel):
    """Complete workflow execution result.

    Aggregates all stage results with overall success determination
    and summary statistics.

    Attributes:
        success: True if all stages passed (including fixed).
        stage_results: List of results for each stage.
        cancelled: True if workflow was cancelled before completion.
        total_duration_ms: Total workflow execution time.
        metadata: Additional context (dry_run status, etc.).
    """

    success: bool = Field(description="All stages passed")
    stage_results: list[StageResult] = Field(description="Per-stage results")
    cancelled: bool = Field(default=False, description="Workflow was cancelled")
    total_duration_ms: int = Field(default=0, ge=0, description="Total duration")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra context")

    model_config = ConfigDict(frozen=True)

    @property
    def passed_count(self) -> int:
        """Count of stages that passed (including fixed)."""
        return sum(1 for r in self.stage_results if r.passed)

    @property
    def failed_count(self) -> int:
        """Count of stages that failed."""
        return sum(1 for r in self.stage_results if r.status == StageStatus.FAILED)

    @property
    def fixed_count(self) -> int:
        """Count of stages that were fixed."""
        return sum(1 for r in self.stage_results if r.was_fixed)

    @property
    def summary(self) -> str:
        """Human-readable summary string."""
        total = len(self.stage_results)
        passed = self.passed_count
        if self.cancelled:
            return f"{passed}/{total} completed before cancellation"
        if self.success:
            fixed = self.fixed_count
            if fixed > 0:
                return f"{total}/{total} passed ({fixed} fixed)"
            return f"{total}/{total} passed"
        return f"{passed}/{total} passed, {self.failed_count} failed"


# =============================================================================
# Progress Update (FR-010)
# =============================================================================


@dataclass(slots=True, frozen=True)
class ProgressUpdate:
    """Progress event emitted during workflow execution.

    Lightweight immutable event for real-time progress reporting to TUI.

    Attributes:
        stage: Current stage name.
        status: Current stage status.
        message: Human-readable context message.
        fix_attempt: Current fix attempt number (0 = first/only run).
        timestamp: Unix timestamp when event was created.
    """

    stage: str
    status: StageStatus
    message: str = ""
    fix_attempt: int = 0
    timestamp: float = field(default_factory=lambda: __import__("time").time())


# =============================================================================
# Workflow Protocol (FR-001 to FR-012)
# =============================================================================


@runtime_checkable
class ValidationWorkflowProtocol(Protocol):
    """Protocol defining the ValidationWorkflow interface.

    This protocol documents the expected public interface for the
    ValidationWorkflow class. Implementations must provide these methods.
    """

    @abstractmethod
    def __init__(
        self,
        stages: list[ValidationStage],
        fix_agent: MaverickAgent | None = None,
        config: ValidationWorkflowConfig | None = None,
    ) -> None:
        """Initialize the validation workflow.

        Args:
            stages: List of validation stages to execute in order.
            fix_agent: Optional agent for attempting fixes on failed stages.
            config: Optional workflow configuration.
        """
        ...

    @abstractmethod
    def run(self) -> AsyncIterator[ProgressUpdate]:
        """Execute the validation workflow.

        Runs all configured stages in sequence, yielding progress updates
        as each stage starts, completes, or undergoes fix attempts.

        Yields:
            ProgressUpdate events for TUI consumption.

        Returns:
            AsyncIterator that yields progress updates and completes when
            the workflow finishes (success, failure, or cancellation).

        Example:
            >>> workflow = ValidationWorkflow(stages, fix_agent)
            >>> async for progress in workflow.run():
            ...     print(f"{progress.stage}: {progress.status.value}")
            >>> result = workflow.get_result()
        """
        ...

    @abstractmethod
    def cancel(self) -> None:
        """Request workflow cancellation.

        Sets the cancellation flag. The workflow will stop at the earliest
        safe point (between stages or fix attempts) and report partial results.

        Cancellation is cooperative - currently executing commands will
        complete before the workflow stops.

        Example:
            >>> import asyncio
            >>> workflow = ValidationWorkflow(stages)
            >>> task = asyncio.create_task(consume_workflow(workflow))
            >>> workflow.cancel()  # Request cancellation
            >>> await task  # Workflow stops gracefully
        """
        ...

    @abstractmethod
    def get_result(self) -> ValidationWorkflowResult:
        """Get the final workflow result.

        Must be called after run() completes. Returns the aggregate result
        containing all stage outcomes.

        Returns:
            ValidationWorkflowResult with success status and stage breakdown.

        Raises:
            RuntimeError: If called before run() completes.
        """
        ...


# =============================================================================
# Default Configurations (FR-013)
# =============================================================================


DEFAULT_PYTHON_STAGES: list[ValidationStage] = [
    ValidationStage(
        name="format",
        command=["ruff", "format", "."],
        fixable=True,
        max_fix_attempts=2,
        timeout_seconds=60.0,
    ),
    ValidationStage(
        name="lint",
        command=["ruff", "check", "--fix", "."],
        fixable=True,
        max_fix_attempts=3,
        timeout_seconds=120.0,
    ),
    ValidationStage(
        name="typecheck",
        command=["mypy", "."],
        fixable=True,
        max_fix_attempts=2,
        timeout_seconds=300.0,
    ),
    ValidationStage(
        name="test",
        command=["pytest", "-x", "--tb=short"],
        fixable=False,
        max_fix_attempts=0,
        timeout_seconds=300.0,
    ),
]
"""Default validation stages for Python projects.

Uses ruff for formatting and linting, mypy for type checking, and pytest
for testing. Format and lint stages are fixable; test stage is not.
"""


# =============================================================================
# Factory Functions
# =============================================================================


def create_python_workflow(
    fix_agent: MaverickAgent | None = None,
    config: ValidationWorkflowConfig | None = None,
) -> ValidationWorkflowProtocol:
    """Create a validation workflow with Python defaults.

    Convenience factory for creating a workflow with standard Python
    validation stages (format, lint, typecheck, test).

    Args:
        fix_agent: Optional agent for fix attempts.
        config: Optional workflow configuration.

    Returns:
        Configured ValidationWorkflow instance.

    Example:
        >>> workflow = create_python_workflow(fix_agent=my_fixer)
        >>> async for progress in workflow.run():
        ...     handle_progress(progress)
    """
    # Implementation will import and instantiate ValidationWorkflow
    raise NotImplementedError("Contract stub - see implementation")
