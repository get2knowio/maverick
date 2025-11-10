"""Data models for multi-task orchestration workflow.

This module defines the input/output dataclasses used by the multi-task
orchestration workflow for processing multiple task files sequentially.
"""

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Literal

from src.utils.git_cli import validate_branch_name


# Type definitions for status fields
TaskProgressStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]
PhaseResultStatus = Literal["success", "failed"]
TaskResultStatus = Literal["success", "failed", "skipped", "unprocessed"]


@dataclass(frozen=True)
class TaskDescriptor:
    """Descriptor for a task with branch context.

    Attributes:
        task_id: Unique identifier for the task
        spec_path: Path to task specification file as string (must be under specs/)
        explicit_branch: Optional explicit branch override
        phases: List of phases to execute for this task

    Invariants:
        - task_id must be non-empty
        - phases must contain at least one phase
        - explicit_branch, if provided, must be git-safe (validated)
        - If explicit_branch is None, spec_path must be under specs/ directory
        - Either explicit_branch is set OR spec_path.parent.name supplies a slug
    """

    task_id: str
    spec_path: str  # Store as string for JSON serialization
    explicit_branch: str | None
    phases: list[str]

    def __post_init__(self) -> None:
        """Validate task descriptor."""
        if not self.task_id or not self.task_id.strip():
            raise ValueError("task_id must be non-empty")

        if not self.phases:
            raise ValueError("phases must contain at least one phase")

        # Normalize spec_path (convert Path to str if needed)
        if isinstance(self.spec_path, Path):
            object.__setattr__(self, "spec_path", str(self.spec_path))

        # Validate explicit_branch if provided
        if self.explicit_branch is not None:
            validate_branch_name(self.explicit_branch)

        # If no explicit branch, ensure spec_path is under specs/
        if self.explicit_branch is None:
            # Check if spec_path starts with "specs/"
            path_obj = Path(self.spec_path)
            parts = path_obj.parts
            if not parts or parts[0] != "specs":
                raise ValueError(
                    "spec_path must be under specs/ directory when explicit_branch is None"
                )

    @cached_property
    def resolved_branch(self) -> str:
        """Get the resolved branch name for this task.

        Returns explicit_branch if set, otherwise derives from spec_path parent directory.

        Returns:
            Resolved branch name
        """
        if self.explicit_branch is not None:
            return self.explicit_branch

        # Derive from spec_path: specs/<slug>/... -> use <slug>
        # Find the directory name under specs/
        path_obj = Path(self.spec_path)
        parts = path_obj.parts
        if len(parts) >= 2 and parts[0] == "specs":
            return parts[1]

        # This should not happen due to __post_init__ validation
        # but provide fallback for safety
        return str(path_obj.parent.name)


@dataclass(frozen=True)
class OrchestrationInput:
    """Input parameters for multi-task orchestration workflow.

    Attributes:
        task_descriptors: List of TaskDescriptor objects to process sequentially
        interactive_mode: If True, pause after each phase for approval
        retry_limit: Maximum retry attempts for phase execution (1-10)
        repo_path: Repository root path for task execution
        default_model: Default AI model for phase execution (optional)
        default_agent_profile: Default agent profile (optional)
        task_file_paths: DEPRECATED - use task_descriptors instead (for backward compatibility)
        branch: DEPRECATED - each task has its own branch via TaskDescriptor

    Invariants:
        - Either task_descriptors OR task_file_paths must be provided (not both)
        - retry_limit must be between 1 and 10 inclusive
        - repo_path must be non-empty
    """

    # New preferred fields
    task_descriptors: tuple[TaskDescriptor, ...] | None = None
    interactive_mode: bool = False
    retry_limit: int = 3
    repo_path: str = ""
    default_model: str | None = None
    default_agent_profile: str | None = None
    
    # Deprecated backward compatibility fields
    task_file_paths: tuple[str, ...] | None = None
    branch: str | None = None

    def __post_init__(self) -> None:
        """Validate input parameters."""
        # Handle backward compatibility: convert task_file_paths to task_descriptors
        if self.task_file_paths is not None and self.task_descriptors is None:
            # Backward compatibility shim
            normalized_paths: list[str] = []
            for raw_path in self.task_file_paths:
                stripped_path = raw_path.strip()
                if not stripped_path:
                    raise ValueError("task_file_paths cannot contain empty paths")
                normalized_paths.append(stripped_path)

            if not normalized_paths:
                raise ValueError("task_file_paths must contain at least one path")

            branch_value = (self.branch or "").strip()
            if not branch_value:
                raise ValueError("branch must be non-empty")

            object.__setattr__(self, "branch", branch_value)
            object.__setattr__(self, "task_file_paths", tuple(normalized_paths))

            # Convert file paths to TaskDescriptors
            descriptors = []
            for idx, file_path in enumerate(normalized_paths):
                descriptor = TaskDescriptor(
                    task_id=f"task-{idx}",
                    spec_path=file_path,
                    explicit_branch=branch_value,
                    phases=["phase1"],  # Default phases - will be discovered
                )
                descriptors.append(descriptor)

            object.__setattr__(self, "task_descriptors", tuple(descriptors))
        elif self.task_descriptors is None and self.task_file_paths is None:
            raise ValueError("Either task_descriptors or task_file_paths must be provided")
        elif self.task_descriptors is not None and self.task_file_paths is not None:
            self._validate_legacy_consistency()

        # Validate task_descriptors
        if not self.task_descriptors:
            raise ValueError("task_descriptors must contain at least one descriptor")

        if self.retry_limit < 1 or self.retry_limit > 10:
            raise ValueError("retry_limit must be between 1 and 10")

        if not self.repo_path or not self.repo_path.strip():
            raise ValueError("repo_path must be non-empty")

        # Normalize strings
        object.__setattr__(self, "repo_path", self.repo_path.strip())

    def _validate_legacy_consistency(self) -> None:
        """Ensure deprecated task_file_paths stay consistent with descriptors."""
        if self.task_descriptors is None or self.task_file_paths is None:
            return

        if len(self.task_descriptors) != len(self.task_file_paths):
            raise ValueError("task_descriptors and task_file_paths length mismatch")

        for descriptor, file_path in zip(self.task_descriptors, self.task_file_paths):
            if descriptor.spec_path != file_path:
                raise ValueError("task_descriptors and task_file_paths must reference the same paths")

        if self.branch is not None:
            for descriptor in self.task_descriptors:
                if descriptor.explicit_branch != self.branch:
                    raise ValueError("task_descriptors branch must match legacy branch value")


@dataclass
class TaskProgress:
    """Progress state for a single task.

    Attributes:
        task_index: Zero-based index in task list
        task_file_path: Path to task file
        current_phase: Name of currently executing phase (None if not started)
        completed_phases: List of phase names that have completed
        status: Current task status

    Invariants:
        - task_index must be >= 0
        - task_file_path must be non-empty
        - If status is "pending", current_phase must be None and completed_phases must be empty
        - If status is "completed", current_phase must be None
        - If status is "in_progress", current_phase must be non-None
    """

    task_index: int
    task_file_path: str
    current_phase: str | None
    completed_phases: list[str]
    status: TaskProgressStatus

    def __post_init__(self) -> None:
        """Validate task progress state."""
        if self.task_index < 0:
            raise ValueError("task_index must be >= 0")

        if not self.task_file_path or not self.task_file_path.strip():
            raise ValueError("task_file_path must be non-empty")

        # Validate status invariants
        if self.status == "pending":
            if self.current_phase is not None:
                raise ValueError("status=pending requires current_phase=None")
            if self.completed_phases:
                raise ValueError("status=pending requires empty completed_phases")

        if self.status == "completed" and self.current_phase is not None:
            raise ValueError("status=completed requires current_phase=None")

        if self.status == "in_progress" and self.current_phase is None:
            raise ValueError("status=in_progress requires non-None current_phase")


@dataclass(frozen=True)
class PhaseResult:
    """Result of executing a single phase.

    Attributes:
        phase_name: Name of the phase executed
        status: Execution outcome (success or failed)
        duration_seconds: Total execution time in seconds
        error_message: Error description if status is failed (None otherwise)
        retry_count: Number of retries attempted (0 if succeeded on first try)

    Invariants:
        - phase_name must be non-empty
        - duration_seconds must be >= 0
        - If status is "failed", error_message must be non-None
        - If status is "success", error_message must be None
        - retry_count must be >= 0
    """

    phase_name: str
    status: PhaseResultStatus
    duration_seconds: int
    error_message: str | None
    retry_count: int

    def __post_init__(self) -> None:
        """Validate phase result."""
        if not self.phase_name or not self.phase_name.strip():
            raise ValueError("phase_name must be non-empty")

        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must be >= 0")

        if self.status == "failed" and self.error_message is None:
            raise ValueError("status=failed requires non-None error_message")

        if self.status == "success" and self.error_message is not None:
            raise ValueError("status=success requires error_message=None")

        if self.retry_count < 0:
            raise ValueError("retry_count must be >= 0")

        # Normalize phase name
        object.__setattr__(self, "phase_name", self.phase_name.strip())


@dataclass(frozen=True)
class TaskResult:
    """Complete result of processing a single task.

    Attributes:
        task_file_path: Path to task file
        overall_status: Final status after all phases
        phase_results: List of results for each phase executed
        total_duration_seconds: Total time for all phases
        failure_reason: Description if overall_status is failed (None otherwise)

    Invariants:
        - task_file_path must be non-empty
        - total_duration_seconds must be >= 0
        - If overall_status is "success", all phase_results must have status "success"
        - If overall_status is "failed", at least one phase_result must have status "failed"
        - If overall_status is "failed", failure_reason must be non-None
        - If overall_status is not "failed", failure_reason must be None
        - If overall_status is "unprocessed", phase_results must be empty
    """

    task_file_path: str
    overall_status: TaskResultStatus
    phase_results: tuple[PhaseResult, ...]
    total_duration_seconds: int
    failure_reason: str | None

    def __post_init__(self) -> None:
        """Validate task result."""
        if not self.task_file_path or not self.task_file_path.strip():
            raise ValueError("task_file_path must be non-empty")

        if self.total_duration_seconds < 0:
            raise ValueError("total_duration_seconds must be >= 0")

        # Validate status-based invariants
        if self.overall_status == "success" and any(pr.status == "failed" for pr in self.phase_results):
            raise ValueError("overall_status=success cannot have failed phase_results")

        if self.overall_status == "failed":
            if not any(pr.status == "failed" for pr in self.phase_results):
                raise ValueError("overall_status=failed requires at least one failed phase_result")
            if self.failure_reason is None:
                raise ValueError("overall_status=failed requires non-None failure_reason")

        if self.overall_status != "failed" and self.failure_reason is not None:
            raise ValueError("failure_reason must be None when overall_status is not failed")

        if self.overall_status == "unprocessed" and self.phase_results:
            raise ValueError("overall_status=unprocessed requires empty phase_results")

        # Normalize path
        object.__setattr__(self, "task_file_path", self.task_file_path.strip())


@dataclass(frozen=True)
class OrchestrationResult:
    """Aggregated result of multi-task orchestration workflow.

    Attributes:
        total_tasks: Total number of tasks in input
        successful_tasks: Count of tasks with overall_status="success"
        failed_tasks: Count of tasks with overall_status="failed"
        skipped_tasks: Count of tasks with overall_status="skipped"
        unprocessed_tasks: Count of tasks with overall_status="unprocessed"
        task_results: List of results for each task (in input order)
        unprocessed_task_paths: Paths of tasks not attempted due to early termination
        early_termination: True if workflow stopped due to task failure
        total_duration_seconds: Total workflow execution time

    Invariants:
        - total_tasks must equal sum of successful_tasks, failed_tasks, skipped_tasks, and unprocessed_tasks
        - total_tasks must equal len(task_results) + len(unprocessed_task_paths)
        - If early_termination is True, unprocessed_tasks must be > 0
        - total_duration_seconds must be >= 0
        - All counts must be >= 0
    """

    total_tasks: int
    successful_tasks: int
    failed_tasks: int
    skipped_tasks: int
    unprocessed_tasks: int
    task_results: tuple[TaskResult, ...]
    unprocessed_task_paths: tuple[str, ...]
    early_termination: bool
    total_duration_seconds: int

    def __post_init__(self) -> None:
        """Validate orchestration result."""
        # Validate counts are non-negative
        if self.total_tasks < 0:
            raise ValueError("total_tasks must be >= 0")
        if self.successful_tasks < 0:
            raise ValueError("successful_tasks must be >= 0")
        if self.failed_tasks < 0:
            raise ValueError("failed_tasks must be >= 0")
        if self.skipped_tasks < 0:
            raise ValueError("skipped_tasks must be >= 0")
        if self.unprocessed_tasks < 0:
            raise ValueError("unprocessed_tasks must be >= 0")
        if self.total_duration_seconds < 0:
            raise ValueError("total_duration_seconds must be >= 0")

        # Validate count consistency
        sum_counts = (
            self.successful_tasks
            + self.failed_tasks
            + self.skipped_tasks
            + self.unprocessed_tasks
        )
        if self.total_tasks != sum_counts:
            raise ValueError(
                f"total_tasks ({self.total_tasks}) must equal sum of status counts ({sum_counts})"
            )

        # Validate result list consistency
        total_results = len(self.task_results) + len(self.unprocessed_task_paths)
        if self.total_tasks != total_results:
            raise ValueError(
                f"total_tasks ({self.total_tasks}) must equal task_results + unprocessed_task_paths ({total_results})"
            )

        # Validate early termination invariant
        if self.early_termination and self.unprocessed_tasks == 0:
            raise ValueError("early_termination=True requires unprocessed_tasks > 0")

        # Verify actual counts match task_results
        actual_successful = sum(
            1 for tr in self.task_results if tr.overall_status == "success"
        )
        actual_failed = sum(1 for tr in self.task_results if tr.overall_status == "failed")
        actual_skipped = sum(1 for tr in self.task_results if tr.overall_status == "skipped")

        if self.successful_tasks != actual_successful:
            raise ValueError(
                f"successful_tasks ({self.successful_tasks}) does not match actual count ({actual_successful})"
            )
        if self.failed_tasks != actual_failed:
            raise ValueError(
                f"failed_tasks ({self.failed_tasks}) does not match actual count ({actual_failed})"
            )
        if self.skipped_tasks != actual_skipped:
            raise ValueError(
                f"skipped_tasks ({self.skipped_tasks}) does not match actual count ({actual_skipped})"
            )
