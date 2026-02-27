"""Python Workflow Protocol Contracts.

This file defines the interface contracts for the Python-native workflow system.
These are reference contracts — the actual implementation will be in
src/maverick/workflows/base.py.

Feature: 035-python-workflow
Date: 2026-02-26
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

# These imports reference existing types that will be reused as-is
# (not redefined here — shown for contract clarity)
#
# from maverick.config import MaverickConfig
# from maverick.dsl.checkpoint.store import CheckpointStore
# from maverick.dsl.events import (
#     CheckpointSaved,
#     ProgressEvent,
#     RollbackCompleted,
#     RollbackStarted,
#     StepCompleted,
#     StepOutput,
#     StepStarted,
#     WorkflowCompleted,
#     WorkflowStarted,
# )
# from maverick.dsl.executor.config import StepConfig, resolve_step_config
#   NOTE: StepConfig is NOT exported from maverick.dsl.executor.__init__
#   Import directly from maverick.dsl.executor.config
# from maverick.dsl.executor.protocol import StepExecutor
# from maverick.dsl.results import StepResult, WorkflowResult
# from maverick.dsl.serialization.registry import ComponentRegistry
# from maverick.dsl.types import StepType
#
# NOTE: Do NOT reuse maverick.dsl.types.RollbackAction — it requires
# WorkflowContext which Python workflows don't have. Use PythonRollbackAction.

# Python workflow rollback callable — no WorkflowContext needed
PythonRollbackAction = Callable[[], Awaitable[None]]


# ---------------------------------------------------------------------------
# Contract 1: PythonWorkflow ABC
# ---------------------------------------------------------------------------


class PythonWorkflow(ABC):
    """Abstract base class for Python-native workflows.

    Provides:
    - Configuration resolution via resolve_step_config()
    - Progress event emission via emit_* helpers
    - Step result tracking and WorkflowResult aggregation
    - Rollback registration and execution
    - Checkpoint save/load delegation

    Subclasses implement _run() with their workflow logic.

    Args:
        config: Project configuration (MaverickConfig).
        registry: Component registry for action/agent dispatch.
        checkpoint_store: Optional checkpoint persistence backend.
        step_executor: Optional agent step executor (StepExecutor protocol).
        workflow_name: Identifier for this workflow instance.
    """

    def __init__(
        self,
        *,
        config: Any,  # MaverickConfig
        registry: Any,  # ComponentRegistry
        checkpoint_store: Any | None = None,  # CheckpointStore
        step_executor: Any | None = None,  # StepExecutor
        workflow_name: str,
    ) -> None: ...

    # -- Public API (final — not overridden by subclasses) --

    async def execute(
        self, inputs: dict[str, Any]
    ) -> AsyncGenerator[Any, None]:  # AsyncGenerator[ProgressEvent, None]
        """Execute the workflow, yielding progress events.

        Template method pattern:
        1. Emits WorkflowStarted
        2. Runs _run() in background task
        3. Yields ProgressEvents from internal queue
        4. On completion: stores aggregated WorkflowResult in self.result,
           emits WorkflowCompleted (note: the event does NOT embed the result —
           it only has workflow_name/success/total_duration_ms/timestamp)
        5. On failure: executes rollbacks, stores failure result in self.result,
           emits WorkflowCompleted(success=False)

        After iteration completes, the caller accesses self.result for the
        full WorkflowResult including step_results and final_output.

        Args:
            inputs: Workflow input parameters.

        Yields:
            ProgressEvent instances (StepStarted, StepCompleted, StepOutput, etc.)
            Final event is always WorkflowCompleted signaling completion.
        """
        ...

    def resolve_step_config(
        self,
        step_name: str,
        step_type: Any = None,  # StepType, defaults to PYTHON
    ) -> Any:  # StepConfig
        """Resolve per-step configuration by merging defaults with overrides.

        Uses the 4-layer resolution from maverick.dsl.executor.config:
        - inline_config: None (Python workflows don't have YAML inline config)
        - project_step_config: from self.config.steps.get(step_name)
        - agent_config: None (resolved separately for agent steps)
        - global_model: from self.config.model

        Args:
            step_name: The step name to resolve config for.
            step_type: Step type for mode inference. Defaults to StepType.PYTHON.

        Returns:
            Resolved StepConfig with merged values.
        """
        ...

    # -- Event Emission Helpers --

    async def emit_step_started(
        self,
        name: str,
        step_type: Any = None,  # StepType, defaults to PYTHON
    ) -> None:
        """Emit a StepStarted event and record the start time.

        Args:
            name: Step name (unique within workflow execution).
            step_type: Step type for the event. Defaults to StepType.PYTHON.
        """
        ...

    async def emit_step_completed(
        self,
        name: str,
        output: Any = None,
        step_type: Any = None,  # StepType, defaults to PYTHON
    ) -> None:
        """Emit a StepCompleted event with success=True.

        Also creates a StepResult and appends to internal results list.

        Args:
            name: Step name (must match a prior emit_step_started call).
            output: Step output value (stored in StepResult).
            step_type: Step type for the event.
        """
        ...

    async def emit_step_failed(
        self,
        name: str,
        error: str,
        step_type: Any = None,  # StepType, defaults to PYTHON
    ) -> None:
        """Emit a StepCompleted event with success=False.

        Also creates a failure StepResult and appends to internal results list.

        Args:
            name: Step name (must match a prior emit_step_started call).
            error: Error description.
            step_type: Step type for the event.
        """
        ...

    async def emit_output(
        self,
        step_name: str,
        message: str,
        level: str = "info",
        source: str | None = None,
    ) -> None:
        """Emit a StepOutput event for informational messages.

        Args:
            step_name: Name of the step producing the output.
            message: Human-readable message.
            level: One of "info", "success", "warning", "error".
            source: Optional source identifier (e.g., "github", "jj").
        """
        ...

    # -- Rollback --

    def register_rollback(
        self,
        name: str,
        action: Any,  # PythonRollbackAction (Callable[[], Awaitable[None]])
    ) -> None:
        """Register a rollback action to execute on workflow failure.

        Rollbacks execute in reverse registration order.
        Uses PythonRollbackAction (simple async callable with no params),
        NOT the DSL's RollbackAction which requires WorkflowContext.

        Args:
            name: Identifier for the rollback (for logging/events).
            action: Async callable (no params) to execute during rollback.
        """
        ...

    # -- Checkpointing --

    async def save_checkpoint(self, data: dict[str, Any]) -> None:
        """Save a checkpoint via the configured CheckpointStore.

        Delegates to checkpoint_store.save(self._workflow_name, data).
        Emits a CheckpointSaved(step_name=current_step, workflow_id=workflow_name)
        event on success.
        No-op if checkpoint_store is None.

        Args:
            data: Checkpoint data to persist.
        """
        ...

    async def load_checkpoint(self) -> dict[str, Any] | None:
        """Load the latest checkpoint for this workflow.

        Delegates to checkpoint_store.load_latest(self._workflow_name).

        Returns:
            Checkpoint data dict, or None if no checkpoint exists
            or checkpoint_store is None.
        """
        ...

    # -- Abstract Method --

    @abstractmethod
    async def _run(self, inputs: dict[str, Any]) -> Any:
        """Implement workflow logic.

        Subclasses call self.emit_* helpers to report progress.
        The return value becomes the WorkflowResult.final_output.

        Args:
            inputs: Workflow input parameters (validated by caller).

        Returns:
            Final output value for the WorkflowResult.
        """
        ...


# ---------------------------------------------------------------------------
# Contract 2: FlyBeadsWorkflow
# ---------------------------------------------------------------------------


class FlyBeadsWorkflow(PythonWorkflow):
    """Bead-driven development workflow.

    Iterates ready beads until done:
    1. Preflight checks (API, git, jj, bd)
    2. Create workspace (jj git clone)
    3. Bead loop:
       a. Select next bead
       b. Snapshot jj operation
       c. Implement (agent step)
       d. Sync dependencies
       e. Validate and fix
       f. Review and fix
       g. Commit or rollback
    4. Return summary

    Inputs:
        epic_id: str (optional, default "")
        max_beads: int (optional, default 30)
        dry_run: bool (optional, default False)
        skip_review: bool (optional, default False)

    Checkpoints: Per-bead (after each bead completes successfully)
    Rollback: Workspace-level (teardown on failure)
    """

    async def _run(self, inputs: dict[str, Any]) -> Any: ...


# ---------------------------------------------------------------------------
# Contract 3: RefuelSpeckitWorkflow
# ---------------------------------------------------------------------------


class RefuelSpeckitWorkflow(PythonWorkflow):
    """Spec-to-beads pipeline workflow.

    Linear steps:
    1. Checkout spec branch
    2. Parse tasks.md
    3. Extract dependencies (agent step)
    4. Enrich beads (agent step)
    5. Create beads via bd CLI
    6. Wire dependencies
    7. Commit beads
    8. Merge spec branch

    Inputs:
        spec: str (required) - Spec identifier
        dry_run: bool (optional, default False)

    Checkpoints: None (short-lived, linear workflow)
    Rollback: Branch cleanup on failure
    """

    async def _run(self, inputs: dict[str, Any]) -> Any: ...


# ---------------------------------------------------------------------------
# Contract 4: CLI Integration — execute_python_workflow()
# ---------------------------------------------------------------------------


@dataclass
class PythonWorkflowRunConfig:
    """Configuration for executing a Python workflow from the CLI.

    Encapsulates all the setup that execute_python_workflow() needs.
    """

    workflow_class: type  # PythonWorkflow subclass
    inputs: dict[str, Any] = field(default_factory=dict)
    session_log_path: Any | None = None  # Path | None
    restart: bool = False


async def execute_python_workflow(
    ctx: Any,  # click.Context
    run_config: PythonWorkflowRunConfig,
) -> None:
    """Execute a Python workflow from a CLI command.

    1. Creates MaverickConfig, ComponentRegistry, CheckpointStore, StepExecutor
    2. Instantiates the workflow class
    3. Calls workflow.execute(inputs)
    4. Renders events via shared render_workflow_events()
    5. Records events to session journal (if configured)
    6. Displays final summary

    Args:
        ctx: Click context with CLIContext attached.
        run_config: Workflow execution configuration.
    """
    ...


async def render_workflow_events(
    events: AsyncGenerator[Any, None],  # AsyncGenerator[ProgressEvent, None]
    console: Any,  # rich.console.Console
    session_journal: Any | None = None,  # SessionJournal | None
) -> Any:  # WorkflowResult
    """Render workflow progress events to the console.

    Shared between YAML workflow execution (execute_workflow_run)
    and Python workflow execution (execute_python_workflow).

    Args:
        events: Async generator of ProgressEvent instances.
        console: Rich console for output rendering.
        session_journal: Optional session journal for event recording.

    Returns:
        The WorkflowResult extracted from the final WorkflowCompleted event.
    """
    ...
