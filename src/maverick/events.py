"""Progress event definitions for workflow execution.

This module defines frozen dataclasses representing workflow execution events.
These events are emitted during workflow execution to track progress and state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, fields
from typing import Any, Literal

from maverick.results import RollbackError
from maverick.types import StepType

# Type alias for AgentStreamChunk chunk types
ChunkType = Literal["output", "thinking", "error"]


def _event_to_dict(event: object) -> dict[str, Any]:
    """Convert a frozen event dataclass to a JSON-serializable dictionary.

    Handles StepType enum conversion, tuple-to-list conversion, and dict
    copying for safe JSON serialization.

    Args:
        event: A frozen dataclass instance.

    Returns:
        Dictionary with an ``"event"`` key set to the class name and all
        dataclass fields as additional keys.
    """
    result: dict[str, Any] = {"event": type(event).__name__}
    for f in fields(event):  # type: ignore[arg-type]
        value = getattr(event, f.name)
        if isinstance(value, StepType):
            value = value.value
        elif isinstance(value, tuple):
            value = list(value)
        elif isinstance(value, dict):
            value = dict(value)
        result[f.name] = value
    return result


@dataclass(frozen=True, slots=True)
class StepStarted:
    """Event emitted when a workflow step begins execution.

    Attributes:
        step_name: Name of the step being started.
        step_type: Type of step (PYTHON, AGENT, etc.).
        timestamp: Unix timestamp when step started (defaults to current time).
    """

    step_name: str
    step_type: StepType
    display_label: str = ""
    timestamp: float = field(default_factory=time.time)
    step_path: str | None = None
    provider: str | None = None
    model_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


@dataclass(frozen=True, slots=True)
class StepCompleted:
    """Event emitted when a workflow step completes execution.

    Attributes:
        step_name: Name of the step that completed.
        step_type: Type of step that completed.
        success: Whether the step completed successfully.
        duration_ms: Execution duration in milliseconds.
        error: Error message if the step failed (None if successful).
        timestamp: Unix timestamp when step completed (defaults to current time).
    """

    step_name: str
    step_type: StepType
    success: bool
    duration_ms: int
    display_label: str = ""
    error: str | None = None
    timestamp: float = field(default_factory=time.time)
    step_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


@dataclass(frozen=True, slots=True)
class PreflightStarted:
    """Event emitted when preflight checks begin.

    Attributes:
        prerequisites: Tuple of prerequisite names to be checked.
        timestamp: Unix timestamp when preflight started (defaults to current time).
    """

    prerequisites: tuple[str, ...]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


@dataclass(frozen=True, slots=True)
class PreflightCheckPassed:
    """Event emitted when a single preflight check passes.

    Attributes:
        name: Prerequisite name (e.g., "git_identity").
        display_name: Human-readable name (e.g., "Git Identity").
        duration_ms: How long the check took in milliseconds.
        message: Success message from the check.
        timestamp: Unix timestamp when check completed.
    """

    name: str
    display_name: str
    duration_ms: int
    message: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


@dataclass(frozen=True, slots=True)
class PreflightCheckFailed:
    """Event emitted when a single preflight check fails.

    Attributes:
        name: Prerequisite name (e.g., "git_identity").
        display_name: Human-readable name (e.g., "Git Identity").
        duration_ms: How long the check took in milliseconds.
        message: Error message from the check.
        remediation: User-facing instructions to fix the issue.
        affected_steps: Tuple of step names that require this prerequisite.
        timestamp: Unix timestamp when check failed.
    """

    name: str
    display_name: str
    duration_ms: int
    message: str
    remediation: str = ""
    affected_steps: tuple[str, ...] = ()
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


@dataclass(frozen=True, slots=True)
class PreflightCompleted:
    """Event emitted when all preflight checks complete.

    Attributes:
        success: True if all checks passed, False otherwise.
        total_duration_ms: Total time for all checks in milliseconds.
        passed_count: Number of checks that passed.
        failed_count: Number of checks that failed.
        timestamp: Unix timestamp when preflight completed.
    """

    success: bool
    total_duration_ms: int
    passed_count: int
    failed_count: int
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


@dataclass(frozen=True, slots=True)
class WorkflowStarted:
    """Event emitted when a workflow begins execution.

    Attributes:
        workflow_name: Name of the workflow being started.
        inputs: Input parameters provided to the workflow.
        timestamp: Unix timestamp when workflow started (defaults to current time).
    """

    workflow_name: str
    inputs: dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


@dataclass(frozen=True, slots=True)
class WorkflowCompleted:
    """Event emitted when a workflow completes execution.

    Attributes:
        workflow_name: Name of the workflow that completed.
        success: Whether the workflow completed successfully.
        total_duration_ms: Total execution duration in milliseconds.
        timestamp: Unix timestamp when workflow completed (defaults to current time).
    """

    workflow_name: str
    success: bool
    total_duration_ms: int
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


@dataclass(frozen=True, slots=True)
class RollbackStarted:
    """Event emitted when rollback execution begins.

    Attributes:
        step_name: Name of the step whose rollback is being executed.
        timestamp: Unix timestamp when rollback started (defaults to current time).
        step_path: Hierarchical path for tree navigation (e.g., "loop/[0]/step").
    """

    step_name: str
    timestamp: float = field(default_factory=time.time)
    step_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


@dataclass(frozen=True, slots=True)
class RollbackCompleted:
    """Event emitted when a rollback completes.

    Attributes:
        step_name: Name of the step whose rollback completed.
        success: Whether the rollback executed without error.
        error: Error message if rollback failed.
        timestamp: Unix timestamp when rollback completed (defaults to current time).
    """

    step_name: str
    success: bool
    error: str | None = None
    timestamp: float = field(default_factory=time.time)
    step_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


@dataclass(frozen=True, slots=True)
class CheckpointSaved:
    """Event emitted when a checkpoint is saved.

    Attributes:
        step_name: Name of the checkpoint step.
        workflow_id: Unique identifier for this workflow run.
        timestamp: Unix timestamp when checkpoint was saved (defaults to current time).
    """

    step_name: str
    workflow_id: str
    timestamp: float = field(default_factory=time.time)
    step_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


@dataclass(frozen=True, slots=True)
class ValidationStarted:
    """Event emitted when semantic validation begins.

    Attributes:
        workflow_name: Name of the workflow being validated.
        timestamp: Unix timestamp when validation started (defaults to current time).
    """

    workflow_name: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


@dataclass(frozen=True, slots=True)
class ValidationCompleted:
    """Event emitted when semantic validation completes successfully.

    Attributes:
        workflow_name: Name of the workflow that was validated.
        warnings_count: Number of warnings found during validation.
        timestamp: Unix timestamp when validation completed (defaults to current time).
    """

    workflow_name: str
    warnings_count: int
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


@dataclass(frozen=True, slots=True)
class ValidationFailed:
    """Event emitted when semantic validation fails.

    Attributes:
        workflow_name: Name of the workflow that failed validation.
        errors: List of validation error messages.
        timestamp: Unix timestamp when validation failed (defaults to current time).
    """

    workflow_name: str
    errors: tuple[str, ...]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


@dataclass(frozen=True, slots=True)
class LoopIterationStarted:
    """Event emitted when a loop iteration begins.

    Attributes:
        step_name: Name of the loop step (e.g., "implement_by_phase").
        iteration_index: 0-based index of current iteration.
        total_iterations: Total number of iterations in the loop.
        item_label: Display label for iteration (e.g., "Phase 1: Core Data").
        parent_step_name: Parent loop step name for nested loops.
        timestamp: Unix timestamp when iteration started (defaults to current time).
    """

    step_name: str
    iteration_index: int
    total_iterations: int
    item_label: str
    parent_step_name: str | None = None
    timestamp: float = field(default_factory=time.time)
    step_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


@dataclass(frozen=True, slots=True)
class LoopIterationCompleted:
    """Event emitted when a loop iteration completes (success or failure).

    Attributes:
        step_name: Name of the loop step.
        iteration_index: 0-based index of completed iteration.
        success: Whether iteration completed successfully.
        duration_ms: Execution time in milliseconds.
        error: Error message if failed.
        timestamp: Unix timestamp when iteration completed (defaults to current time).
    """

    step_name: str
    iteration_index: int
    success: bool
    duration_ms: int
    error: str | None = None
    timestamp: float = field(default_factory=time.time)
    step_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


@dataclass(frozen=True, slots=True)
class LoopConditionChecked:
    """Event emitted when an ``until`` loop evaluates its termination condition.

    Attributes:
        step_name: Name of the loop step.
        iteration_index: 0-based index of the iteration that just completed.
        condition_met: Whether the until condition evaluated to truthy.
        condition_value: The raw value of the condition expression.
        timestamp: Unix timestamp when condition was checked.
        step_path: Hierarchical path for tree navigation.
    """

    step_name: str
    iteration_index: int
    condition_met: bool
    condition_value: Any = None
    timestamp: float = field(default_factory=time.time)
    step_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


@dataclass(frozen=True, slots=True)
class AgentStreamChunk:
    """Event emitted when agent produces streaming output.

    Attributes:
        step_name: Name of the step running the agent.
        agent_name: Name/type of the agent (e.g., "ImplementerAgent").
        text: Text content of the chunk.
        chunk_type: Type of chunk - "output", "thinking", or "error".
        timestamp: Unix timestamp when chunk was received (defaults to current time).
    """

    step_name: str
    agent_name: str
    text: str
    chunk_type: ChunkType
    timestamp: float = field(default_factory=time.time)
    step_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


# Type alias for StepOutput level
OutputLevel = Literal["info", "success", "warning", "error"]


@dataclass(frozen=True, slots=True)
class StepOutput:
    """Event emitted when any step produces informational output.

    This is the generic event type for workflow steps to contribute to the
    unified stream widget. Unlike AgentStreamChunk (which is agent-specific),
    StepOutput can be emitted by any step type: Python actions, validation
    steps, GitHub operations, etc.

    Use this event to emit:
    - Progress messages ("Fetching PR #123...")
    - Status updates ("3 files changed")
    - Warnings ("Rate limit approaching")
    - Errors that don't fail the step ("Retrying after timeout...")

    Attributes:
        step_name: Name of the step emitting output.
        message: Human-readable message content.
        level: Severity level for styling ("info", "success", "warning", "error").
        source: Optional source identifier (e.g., "github", "git", "validation").
        metadata: Optional structured data for rich display.
        timestamp: Unix timestamp when output was emitted.

    Example:
        # In a Python action:
        async def fetch_pr_details(
            pr_number: int,
            stream_callback: Callable[[str], Awaitable[None]] | None = None,
            event_callback: EventCallback | None = None,
        ) -> dict:
            if event_callback:
                await event_callback(StepOutput(
                    step_name="fetch_pr",
                    message=f"Fetching PR #{pr_number}...",
                    level="info",
                    source="github",
                ))
            # ... do work ...
    """

    step_name: str
    message: str
    display_label: str = ""
    level: OutputLevel = "info"
    source: str | None = None
    metadata: dict[str, Any] | None = None
    timestamp: float = field(default_factory=time.time)
    step_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


@dataclass(frozen=True, slots=True)
class AgentStarted:
    """Event emitted when an agent begins execution within a step.

    Used by the CLI renderer to track concurrent agents in a Rich Live
    table during fan-out phases (briefing, decompose detail).

    Attributes:
        step_name: Parent step (e.g., "briefing", "decompose").
        agent_name: Display label (e.g., "Navigator", "Contrarian").
        provider: Provider/model string (e.g., "claude/sonnet").
        timestamp: Unix timestamp when agent started.
    """

    step_name: str
    agent_name: str
    provider: str = ""
    display_label: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


@dataclass(frozen=True, slots=True)
class AgentCompleted:
    """Event emitted when an agent finishes execution within a step.

    Attributes:
        step_name: Parent step (e.g., "briefing", "decompose").
        agent_name: Display label matching the AgentStarted event.
        duration_seconds: Wall-clock time in seconds.
        success: Whether the agent completed without error.
        error: Error message if the agent failed.
        timestamp: Unix timestamp when agent completed.
    """

    step_name: str
    agent_name: str
    duration_seconds: float
    display_label: str = ""
    success: bool = True
    error: str | None = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return _event_to_dict(self)


# Type alias for all progress events
ProgressEvent = (
    PreflightStarted
    | PreflightCheckPassed
    | PreflightCheckFailed
    | PreflightCompleted
    | StepStarted
    | StepCompleted
    | WorkflowStarted
    | WorkflowCompleted
    | RollbackStarted
    | RollbackCompleted
    | CheckpointSaved
    | RollbackError
    | ValidationStarted
    | ValidationCompleted
    | ValidationFailed
    | LoopIterationStarted
    | LoopIterationCompleted
    | LoopConditionChecked
    | AgentStreamChunk
    | AgentStarted
    | AgentCompleted
    | StepOutput
)


# ----------------------------------------------------------------------------
# Deserialization
# ----------------------------------------------------------------------------

# Mapping of event class names to their concrete types. Used by
# event_from_dict() to reconstruct a ProgressEvent from its serialized form.
# RollbackError is intentionally omitted — it uses a non-standard to_dict() that
# does not include the "event" key, and is only emitted by workflow base code,
# never by supervisors.
_EVENT_CLASSES: dict[str, type] = {
    "PreflightStarted": PreflightStarted,
    "PreflightCheckPassed": PreflightCheckPassed,
    "PreflightCheckFailed": PreflightCheckFailed,
    "PreflightCompleted": PreflightCompleted,
    "StepStarted": StepStarted,
    "StepCompleted": StepCompleted,
    "WorkflowStarted": WorkflowStarted,
    "WorkflowCompleted": WorkflowCompleted,
    "RollbackStarted": RollbackStarted,
    "RollbackCompleted": RollbackCompleted,
    "CheckpointSaved": CheckpointSaved,
    "ValidationStarted": ValidationStarted,
    "ValidationCompleted": ValidationCompleted,
    "ValidationFailed": ValidationFailed,
    "LoopIterationStarted": LoopIterationStarted,
    "LoopIterationCompleted": LoopIterationCompleted,
    "LoopConditionChecked": LoopConditionChecked,
    "AgentStreamChunk": AgentStreamChunk,
    "AgentStarted": AgentStarted,
    "AgentCompleted": AgentCompleted,
    "StepOutput": StepOutput,
}

# Fields that _event_to_dict() converts from tuple → list and must be restored
# to tuples when rebuilding frozen dataclasses.
_TUPLE_FIELDS: dict[str, tuple[str, ...]] = {
    "PreflightStarted": ("prerequisites",),
    "PreflightCheckFailed": ("affected_steps",),
    "ValidationFailed": ("errors",),
}

# Fields that _event_to_dict() converts from StepType enum → str and must be
# restored.
_STEP_TYPE_FIELDS: dict[str, tuple[str, ...]] = {
    "StepStarted": ("step_type",),
    "StepCompleted": ("step_type",),
}


def event_from_dict(data: dict[str, Any]) -> ProgressEvent:
    """Reconstruct a ProgressEvent from its serialized dict form.

    Inverse of ``_event_to_dict()``. Useful when events are persisted
    to disk or carried over a process boundary and must be rehydrated.

    Args:
        data: Dictionary produced by ``event.to_dict()``. Must contain an
            ``"event"`` key naming the ProgressEvent subclass.

    Returns:
        A frozen ProgressEvent dataclass instance.

    Raises:
        ValueError: If ``data`` lacks an ``"event"`` key or names an unknown
            event class.
    """
    event_name = data.get("event")
    if not event_name:
        raise ValueError(f"serialized event missing 'event' key: {data!r}")

    cls = _EVENT_CLASSES.get(event_name)
    if cls is None:
        raise ValueError(f"unknown event class: {event_name!r}")

    kwargs = {k: v for k, v in data.items() if k != "event"}

    # Restore tuple fields
    for field_name in _TUPLE_FIELDS.get(event_name, ()):
        if field_name in kwargs and isinstance(kwargs[field_name], list):
            kwargs[field_name] = tuple(kwargs[field_name])

    # Restore StepType enum fields
    for field_name in _STEP_TYPE_FIELDS.get(event_name, ()):
        if field_name in kwargs and isinstance(kwargs[field_name], str):
            kwargs[field_name] = StepType(kwargs[field_name])

    return cls(**kwargs)  # type: ignore[return-value]
