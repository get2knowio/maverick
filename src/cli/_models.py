"""CLI-local data models for Maverick CLI.

These models represent CLI-specific data structures used for discovery,
validation, and workflow input adaptation. They complement the workflow
models in src/models/orchestration.py.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CLITaskDescriptor:
    """Task descriptor with CLI context.

    This model wraps the workflow TaskDescriptor with additional CLI-specific
    context that is passed separately to the workflow.

    Attributes:
        task_id: Stable slug from spec directory + file name
        task_file: Absolute path to tasks.md
        spec_root: Absolute path to the spec directory containing the task
        branch_name: Optional branch hint; derived from task_id when not provided
        return_to_branch: Current git branch at CLI invocation time
        repo_root: Absolute repository root
        interactive: From --interactive flag
        model_prefs: Optional model preferences (provider, model, max_tokens)

    Invariants:
        - task_file/spec_root/repo_root must be absolute, non-empty paths
        - return_to_branch must be non-empty
        - If branch_name provided, must be git-safe (validated externally)
    """

    task_id: str
    task_file: str
    spec_root: str
    branch_name: str | None
    return_to_branch: str
    repo_root: str
    interactive: bool
    model_prefs: dict[str, str | int] | None = None

    def __post_init__(self) -> None:
        """Validate CLI task descriptor."""
        if not self.task_id or not self.task_id.strip():
            raise ValueError("task_id must be non-empty")

        if not self.task_file or not self.task_file.strip():
            raise ValueError("task_file must be non-empty")

        if not self.spec_root or not self.spec_root.strip():
            raise ValueError("spec_root must be non-empty")

        if not self.return_to_branch or not self.return_to_branch.strip():
            raise ValueError("return_to_branch must be non-empty")

        if not self.repo_root or not self.repo_root.strip():
            raise ValueError("repo_root must be non-empty")

        # Basic path shape validation without touching filesystem
        task_path = Path(self.task_file)
        spec_path = Path(self.spec_root)
        repo_path = Path(self.repo_root)

        if not task_path.is_absolute():
            raise ValueError("task_file must be an absolute path")

        if not spec_path.is_absolute():
            raise ValueError("spec_root must be an absolute path")

        if not repo_path.is_absolute():
            raise ValueError("repo_root must be an absolute path")

        # Validate model_prefs structure if provided
        if self.model_prefs is not None:
            if not isinstance(self.model_prefs, dict):
                raise ValueError("model_prefs must be a dict")

            allowed_keys = {"provider", "model", "max_tokens"}
            invalid_keys = set(self.model_prefs.keys()) - allowed_keys
            if invalid_keys:
                raise ValueError(
                    f"model_prefs contains invalid keys: {invalid_keys}. "
                    f"Allowed keys: {allowed_keys}"
                )

            # Validate value types
            if "provider" in self.model_prefs and not isinstance(
                self.model_prefs["provider"], str
            ):
                raise ValueError("model_prefs.provider must be a string")

            if "model" in self.model_prefs and not isinstance(
                self.model_prefs["model"], str
            ):
                raise ValueError("model_prefs.model must be a string")

            if "max_tokens" in self.model_prefs and not isinstance(
                self.model_prefs["max_tokens"], int
            ):
                raise ValueError("model_prefs.max_tokens must be an int")


@dataclass(frozen=True)
class DiscoveredTask:
    """Discovered task file with ordering metadata.

    Represents a tasks.md file discovered during spec directory scanning.
    Used internally by discovery module before conversion to CLITaskDescriptor.

    Attributes:
        file_path: Absolute path to tasks.md
        spec_dir: Absolute path to parent spec directory
        numeric_prefix: Numeric prefix for ordering (e.g., 1 from "001-feature")
        directory_name: Full directory name (e.g., "001-feature")

    Invariants:
        - file_path must exist
        - spec_dir must be parent of file_path
        - numeric_prefix must be >= 0
        - directory_name must be non-empty
    """

    file_path: str
    spec_dir: str
    numeric_prefix: int
    directory_name: str

    def __post_init__(self) -> None:
        """Validate discovered task."""
        if not self.file_path or not self.file_path.strip():
            raise ValueError("file_path must be non-empty")

        if not self.spec_dir or not self.spec_dir.strip():
            raise ValueError("spec_dir must be non-empty")

        if self.numeric_prefix < 0:
            raise ValueError("numeric_prefix must be >= 0")

        if not self.directory_name or not self.directory_name.strip():
            raise ValueError("directory_name must be non-empty")

        # Validate paths
        file_path_obj = Path(self.file_path)
        spec_dir_obj = Path(self.spec_dir)

        if not file_path_obj.exists():
            raise ValueError(f"file_path does not exist: {self.file_path}")

        try:
            file_path_obj.relative_to(spec_dir_obj)
        except ValueError as e:
            raise ValueError(
                f"spec_dir must be parent of file_path: {self.spec_dir} not parent of {self.file_path}"
            ) from e


@dataclass
class DryRunResult:
    """Result of dry-run mode showing discovered tasks without execution.

    Attributes:
        task_count: Number of tasks discovered
        discovery_ms: Time taken for discovery in milliseconds
        descriptors: List of CLITaskDescriptor objects that would be executed
    """

    task_count: int
    discovery_ms: int
    descriptors: list[CLITaskDescriptor]

    def __post_init__(self) -> None:
        """Validate dry-run result."""
        if self.task_count < 0:
            raise ValueError("task_count must be >= 0")

        if self.discovery_ms < 0:
            raise ValueError("discovery_ms must be >= 0")

        if self.task_count != len(self.descriptors):
            raise ValueError(
                f"task_count ({self.task_count}) must match descriptors length ({len(self.descriptors)})"
            )


@dataclass
class WorkflowStartResponse:
    """Response from starting a workflow.

    Attributes:
        workflow_id: Temporal workflow ID
        run_id: Temporal run ID
        task_count: Number of tasks in the workflow
        discovery_ms: Time taken for discovery in milliseconds
        workflow_start_ms: Time taken to start workflow in milliseconds
    """

    workflow_id: str
    run_id: str
    task_count: int
    discovery_ms: int
    workflow_start_ms: int

    def __post_init__(self) -> None:
        """Validate workflow start response."""
        if not self.workflow_id or not self.workflow_id.strip():
            raise ValueError("workflow_id must be non-empty")

        if not self.run_id or not self.run_id.strip():
            raise ValueError("run_id must be non-empty")

        if self.task_count < 0:
            raise ValueError("task_count must be >= 0")

        if self.discovery_ms < 0:
            raise ValueError("discovery_ms must be >= 0")

        if self.workflow_start_ms < 0:
            raise ValueError("workflow_start_ms must be >= 0")


@dataclass
class TaskProgressInfo:
    """Progress information for a single task.

    Attributes:
        task_id: Task identifier
        status: Current task status (pending|running|success|failed|skipped)
        last_message: Optional last status message
    """

    task_id: str
    status: str
    last_message: str | None = None

    def __post_init__(self) -> None:
        """Validate task progress info."""
        if not self.task_id or not self.task_id.strip():
            raise ValueError("task_id must be non-empty")

        valid_statuses = {"pending", "running", "success", "failed", "skipped"}
        if self.status not in valid_statuses:
            raise ValueError(
                f"status must be one of {valid_statuses}, got: {self.status}"
            )


@dataclass
class WorkflowStatusInfo:
    """Workflow status information.

    Attributes:
        workflow_id: Workflow identifier
        run_id: Run identifier
        state: Workflow state (running|completed|failed|paused)
        current_task_id: Currently executing task ID (None if not started or completed)
        current_phase: Currently executing phase (None if not started or completed)
        last_activity: Last activity name (None if not started)
        updated_at: ISO8601 timestamp of last update
        tasks: List of task progress information
        status_poll_latency_ms_p95: Optional 95th percentile poll latency in ms
        errors_count: Number of errors encountered
    """

    workflow_id: str
    run_id: str
    state: str
    current_task_id: str | None
    current_phase: str | None
    last_activity: str | None
    updated_at: str
    tasks: list[TaskProgressInfo]
    status_poll_latency_ms_p95: int | None = None
    errors_count: int = 0

    def __post_init__(self) -> None:
        """Validate workflow status info."""
        if not self.workflow_id or not self.workflow_id.strip():
            raise ValueError("workflow_id must be non-empty")

        if not self.run_id or not self.run_id.strip():
            raise ValueError("run_id must be non-empty")

        valid_states = {"running", "completed", "failed", "paused"}
        if self.state not in valid_states:
            raise ValueError(f"state must be one of {valid_states}, got: {self.state}")

        if not self.updated_at or not self.updated_at.strip():
            raise ValueError("updated_at must be non-empty")

        if self.errors_count < 0:
            raise ValueError("errors_count must be >= 0")

        if self.status_poll_latency_ms_p95 is not None and self.status_poll_latency_ms_p95 < 0:
            raise ValueError("status_poll_latency_ms_p95 must be >= 0")
