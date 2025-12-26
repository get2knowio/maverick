from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable, Generator
from datetime import UTC, datetime
from typing import Any

from maverick.dsl.checkpoint.data import CheckpointData, compute_inputs_hash
from maverick.dsl.checkpoint.store import CheckpointStore, FileCheckpointStore
from maverick.dsl.context import WorkflowContext
from maverick.dsl.decorator import WorkflowDefinition
from maverick.dsl.errors import CheckpointNotFoundError, InputMismatchError
from maverick.dsl.events import (
    CheckpointSaved,
    ProgressEvent,
    RollbackCompleted,
    RollbackStarted,
    StepCompleted,
    StepStarted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.dsl.results import RollbackError, StepResult, WorkflowResult
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.steps.checkpoint import CheckpointStep
from maverick.dsl.types import StepType
from maverick.exceptions import DuplicateStepNameError
from maverick.logging import get_logger

logger = get_logger(__name__)


class WorkflowEngine:
    """Workflow execution engine.

    Executes workflow definitions, manages context, and emits progress events
    for TUI consumption.
    """

    def __init__(
        self,
        config: Any = None,
        checkpoint_store: CheckpointStore | None = None,
    ) -> None:
        """Initialize the workflow engine.

        Args:
            config: Optional configuration for validation stages, etc.
            checkpoint_store: Optional store for checkpoint persistence.
                Default: FileCheckpointStore if not specified during resume.
        """
        self._config = config
        self._checkpoint_store = checkpoint_store
        self._result: WorkflowResult | None = None
        self._cancelled = False

    async def _save_checkpoint(
        self,
        workflow_name: str,
        workflow_id: str,
        step_name: str,
        inputs: dict[str, Any],
        step_results: list[StepResult],
    ) -> None:
        """Save workflow state at checkpoint.

        Args:
            workflow_name: Name of the workflow.
            workflow_id: Unique ID for this workflow run.
            step_name: Name of the checkpoint step.
            inputs: Workflow input arguments.
            step_results: All step results so far.
        """
        if self._checkpoint_store is None:
            return

        checkpoint_data = CheckpointData(
            checkpoint_id=step_name,
            workflow_name=workflow_name,
            inputs_hash=compute_inputs_hash(inputs),
            step_results=tuple(sr.to_dict() for sr in step_results),
            saved_at=datetime.now(UTC).isoformat(),
        )
        await self._checkpoint_store.save(workflow_id, checkpoint_data)

    async def _execute_steps(
        self,
        gen: Generator[StepDefinition, Any, Any],
        context: WorkflowContext,
        initial_step: StepDefinition | None,
        seen_names: set[str],
        step_results: list[StepResult],
        workflow_name: str,
        workflow_id: str | None,
        inputs: dict[str, Any],
        result_container: dict[str, Any],
    ) -> AsyncIterator[ProgressEvent]:
        """Execute workflow steps from the generator."""
        step_to_execute = initial_step
        final_output: Any = None
        has_explicit_return = False
        success = True

        while step_to_execute is not None:
            step = step_to_execute

            # Check for duplicate step name (FR-005)
            if step.name in seen_names:
                raise DuplicateStepNameError(step.name)
            seen_names.add(step.name)

            # Check for cancellation
            if self._cancelled:
                success = False
                break

            # Emit step started
            yield StepStarted(step_name=step.name, step_type=step.step_type)

            # Execute step
            step_start_time = time.perf_counter()
            try:
                step_result = await step.execute(context)
            except Exception as e:
                duration_ms = int((time.perf_counter() - step_start_time) * 1000)
                step_result = StepResult(
                    name=step.name,
                    step_type=step.step_type,
                    success=False,
                    output=None,
                    duration_ms=duration_ms,
                    error=f"Step '{step.name}' raised {type(e).__name__}: {e}",
                )
            step_results.append(step_result)
            context.results[step.name] = step_result

            # Emit step completed
            yield StepCompleted(
                step_name=step.name,
                step_type=step.step_type,
                success=step_result.success,
                duration_ms=step_result.duration_ms,
            )

            # Save checkpoint if this is a checkpoint step
            if isinstance(step, CheckpointStep) and step_result.success:
                actual_workflow_id = workflow_id or workflow_name
                logger.debug(
                    f"Saving checkpoint for step '{step.name}' "
                    f"(workflow_id={actual_workflow_id})"
                )
                await self._save_checkpoint(
                    workflow_name=workflow_name,
                    workflow_id=actual_workflow_id,
                    step_name=step.name,
                    inputs=inputs,
                    step_results=step_results,
                )
                logger.info(f"Checkpoint saved for step '{step.name}'")
                yield CheckpointSaved(
                    step_name=step.name,
                    workflow_id=actual_workflow_id,
                )

            # Handle step failure (fail-fast per FR-018)
            if not step_result.success:
                success = False
                break

            # Send result back to generator and get next step
            try:
                step_to_execute = gen.send(step_result.output)
            except StopIteration as e:
                # Workflow completed with explicit return
                has_explicit_return = True
                final_output = e.value
                break

        # Determine final output per FR-021
        if not success:
            final_output = None
        elif has_explicit_return and final_output is not None:
            pass  # Use explicit return value
        elif step_results:
            final_output = step_results[-1].output
        else:
            final_output = None

        result_container["success"] = success
        result_container["final_output"] = final_output

    async def execute(
        self,
        workflow_func: Callable[..., Any],
        workflow_id: str | None = None,
        **inputs: Any,
    ) -> AsyncIterator[ProgressEvent]:
        """Execute a workflow and yield progress events.

        Args:
            workflow_func: Decorated workflow function.
            workflow_id: Optional unique identifier for this workflow run.
            **inputs: Workflow input arguments.

        Yields:
            ProgressEvent objects (WorkflowStarted, StepStarted, etc.).
        """
        # Get workflow definition from decorated function
        workflow_def: WorkflowDefinition = workflow_func.__workflow_def__  # type: ignore[attr-defined]
        workflow_name = workflow_def.name

        # Create context
        context = WorkflowContext(inputs=inputs, config=self._config)

        # Track execution
        start_time = time.perf_counter()
        step_results: list[StepResult] = []
        seen_names: set[str] = set()
        final_output: Any = None
        success = True
        result_container: dict[str, Any] = {}

        # Emit workflow started
        yield WorkflowStarted(workflow_name=workflow_name, inputs=inputs)

        # Create generator from workflow function
        gen: Generator[StepDefinition, Any, Any] = workflow_def.func(**inputs)

        # Start generator
        try:
            step_to_execute = gen.send(None)
        except StopIteration as e:
            # Workflow returned immediately with no steps
            step_to_execute = None
            final_output = e.value
            success = True

        # Execute steps if we have any
        if step_to_execute is not None:
            async for event in self._execute_steps(
                gen,
                context,
                step_to_execute,
                seen_names,
                step_results,
                workflow_name,
                workflow_id,
                inputs,
                result_container,
            ):
                yield event

            success = result_container.get("success", False)
            final_output = result_container.get("final_output")

        # Execute rollbacks if workflow failed
        rollback_errors_list: list[RollbackError] = []
        if not success:
            async for event in self._execute_rollbacks(context):
                if isinstance(event, RollbackError):
                    rollback_errors_list.append(event)
                else:
                    yield event
        rollback_errors: tuple[RollbackError, ...] = tuple(rollback_errors_list)

        # Calculate total duration
        total_duration_ms = int((time.perf_counter() - start_time) * 1000)

        # Create result
        self._result = WorkflowResult(
            workflow_name=workflow_name,
            success=success,
            step_results=tuple(step_results),
            total_duration_ms=total_duration_ms,
            final_output=final_output,
            rollback_errors=rollback_errors,
        )

        # Emit workflow completed
        yield WorkflowCompleted(
            workflow_name=workflow_name,
            success=success,
            total_duration_ms=total_duration_ms,
        )

    async def resume(
        self,
        workflow_func: Callable[..., Any],
        workflow_id: str,
        checkpoint_store: CheckpointStore | None = None,
        **inputs: Any,
    ) -> AsyncIterator[ProgressEvent]:
        """Resume workflow from latest checkpoint.

        Args:
            workflow_func: Decorated workflow function.
            workflow_id: Unique identifier for this workflow run.
            checkpoint_store: Store to load checkpoint from.
                Default: FileCheckpointStore at .maverick/checkpoints/
            **inputs: Workflow input arguments.
                Must match inputs at checkpoint time (hash validated).

        Yields:
            ProgressEvent objects (same as execute()).

        Raises:
            CheckpointNotFoundError: If no checkpoint exists.
            InputMismatchError: If current inputs don't match checkpoint.
        """
        store = checkpoint_store or self._checkpoint_store or FileCheckpointStore()

        # Load latest checkpoint
        checkpoint = await store.load_latest(workflow_id)
        if checkpoint is None:
            raise CheckpointNotFoundError(workflow_id)

        # Validate inputs match
        current_hash = compute_inputs_hash(inputs)
        if current_hash != checkpoint.inputs_hash:
            raise InputMismatchError(checkpoint.inputs_hash, current_hash)

        # Get workflow definition
        workflow_def: WorkflowDefinition = workflow_func.__workflow_def__  # type: ignore[attr-defined]
        workflow_name = workflow_def.name

        logger.info(
            f"Resuming workflow '{workflow_name}' "
            f"from checkpoint '{checkpoint.checkpoint_id}'"
        )

        # Restore step results from checkpoint
        restored_results: dict[str, StepResult] = {}
        for sr_dict in checkpoint.step_results:
            step_type = StepType(sr_dict["step_type"])
            sr = StepResult(
                name=sr_dict["name"],
                step_type=step_type,
                success=sr_dict["success"],
                output=sr_dict["output"],
                duration_ms=sr_dict["duration_ms"],
                error=sr_dict.get("error"),
            )
            restored_results[sr.name] = sr

        # Set up to use this store for any new checkpoints
        self._checkpoint_store = store

        # Create context with restored results
        context = WorkflowContext(inputs=inputs, config=self._config)
        context.results = restored_results

        # Track execution
        start_time = time.perf_counter()
        step_results: list[StepResult] = list(restored_results.values())
        seen_names: set[str] = set(restored_results.keys())
        final_output: Any = None
        has_explicit_return = False
        success = True
        result_container: dict[str, Any] = {}

        # Emit workflow started
        yield WorkflowStarted(workflow_name=workflow_name, inputs=inputs)

        # Create generator from workflow function
        gen: Generator[StepDefinition, Any, Any] = workflow_def.func(**inputs)

        # Fast-forward generator to checkpoint position
        try:
            step_to_execute = gen.send(None)
            while step_to_execute is not None and step_to_execute.name in seen_names:
                # Send the restored result and get next step
                restored_result = restored_results[step_to_execute.name]
                step_to_execute = gen.send(restored_result.output)
        except StopIteration as e:
            has_explicit_return = True
            final_output = e.value
            step_to_execute = None
            success = True

        # Continue with normal execution from here
        executed_new_steps = False
        if step_to_execute is not None:
            executed_new_steps = True
            async for event in self._execute_steps(
                gen,
                context,
                step_to_execute,
                seen_names,
                step_results,
                workflow_name,
                workflow_id,
                inputs,
                result_container,
            ):
                yield event

            success = result_container.get("success", False)
            final_output = result_container.get("final_output")

        elif has_explicit_return:
            # Already done after fast-forward
            pass
        else:
            # Fast-forward ended but no more steps and no explicit return?
            # That means we just finished execution.
            pass

        # Execute rollbacks if workflow failed
        rollback_errors_list: list[RollbackError] = []
        if not success:
            async for event in self._execute_rollbacks(context):
                if isinstance(event, RollbackError):
                    rollback_errors_list.append(event)
                else:
                    yield event
        rollback_errors: tuple[RollbackError, ...] = tuple(rollback_errors_list)

        # Calculate total duration
        total_duration_ms = int((time.perf_counter() - start_time) * 1000)

        # Determine final output (only if we didn't execute new steps)
        if executed_new_steps:
            # final_output already set from result_container
            pass
        elif not success:
            final_output = None
        elif has_explicit_return and final_output is not None:
            pass
        elif step_results:
            final_output = step_results[-1].output
        else:
            final_output = None

        # Create result
        self._result = WorkflowResult(
            workflow_name=workflow_name,
            success=success,
            step_results=tuple(step_results),
            total_duration_ms=total_duration_ms,
            final_output=final_output,
            rollback_errors=rollback_errors,
        )

        # Clear checkpoints on success
        if success:
            await store.clear(workflow_id)

        # Emit workflow completed
        yield WorkflowCompleted(
            workflow_name=workflow_name,
            success=success,
            total_duration_ms=total_duration_ms,
        )

    def get_result(self) -> WorkflowResult:
        """Get the final workflow result.

        Returns:
            WorkflowResult with success status and step results.

        Raises:
            RuntimeError: If called before execute() completes.
        """
        if self._result is None:
            msg = "Workflow has not been executed yet. Call execute() first."
            raise RuntimeError(msg)
        return self._result

    async def _execute_rollbacks(
        self,
        context: WorkflowContext,
    ) -> AsyncIterator[ProgressEvent | RollbackError]:
        """Execute rollbacks in reverse order, yielding events and errors.

        Rollbacks are best-effort: execution continues even if some fail.

        Args:
            context: Workflow execution context with pending rollbacks.

        Yields:
            RollbackStarted and RollbackCompleted events, plus RollbackError
            for any failed rollback actions.
        """
        # Execute in reverse order (most recent first)
        for registration in reversed(context._pending_rollbacks):
            yield RollbackStarted(step_name=registration.step_name)
            logger.debug(f"Executing rollback for step '{registration.step_name}'")

            error_msg: str | None = None
            try:
                result = registration.action(context)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                error_msg = f"{type(e).__name__}: {e}"
                logger.error(
                    f"Rollback failed for step '{registration.step_name}': {error_msg}"
                )
                yield RollbackError(
                    step_name=registration.step_name,
                    error=error_msg,
                )

            yield RollbackCompleted(
                step_name=registration.step_name,
                success=error_msg is None,
                error=error_msg,
            )

    def cancel(self) -> None:
        """Request workflow cancellation.

        Cancellation is cooperative and takes effect at step boundaries.
        """
        self._cancelled = True
