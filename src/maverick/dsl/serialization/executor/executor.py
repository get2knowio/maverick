"""Workflow file executor for running WorkflowFile instances.

This module provides the WorkflowFileExecutor class that bridges the gap between
serialized WorkflowFile definitions and actual execution using registry-resolved
components. It yields progress events compatible with the TUI/CLI interfaces.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from maverick.dsl.checkpoint.store import CheckpointStore, FileCheckpointStore
from maverick.dsl.events import (
    ProgressEvent,
    StepCompleted,
    StepStarted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.dsl.results import StepResult, WorkflowResult
from maverick.dsl.serialization.executor import checkpointing, conditions, context
from maverick.dsl.serialization.executor.handlers import (
    agent_step,
    branch_step,
    checkpoint_step,
    generate_step,
    parallel_step,
    python_step,
    subworkflow_step,
    validate_step,
)
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import (
    AgentStepRecord,
    BranchStepRecord,
    CheckpointStepRecord,
    GenerateStepRecord,
    ParallelStepRecord,
    PythonStepRecord,
    SubWorkflowStepRecord,
    ValidateStepRecord,
    WorkflowFile,
)
from maverick.logging import get_logger

logger = get_logger(__name__)

# Type alias for step records
StepRecordType = (
    PythonStepRecord
    | AgentStepRecord
    | GenerateStepRecord
    | ValidateStepRecord
    | SubWorkflowStepRecord
    | BranchStepRecord
    | ParallelStepRecord
    | CheckpointStepRecord
)


class WorkflowFileExecutor:
    """Executes WorkflowFile instances using registered components.

    This executor bridges the gap between declarative workflow files (YAML/JSON)
    and runtime execution. It resolves component references from registries,
    evaluates expressions, handles conditional execution, and yields progress
    events for monitoring.

    Attributes:
        _registry: Component registry for resolving actions/agents/generators.
        _config: Optional configuration for validation stages.
        _result: Cached WorkflowResult after execution.
        _cancelled: Flag for cooperative cancellation.

    Example:
        ```python
        from maverick.dsl.serialization import parse_workflow, ComponentRegistry
        from maverick.dsl.serialization.executor import WorkflowFileExecutor

        # Parse workflow from YAML
        workflow = parse_workflow(yaml_content)

        # Create executor with registry
        registry = ComponentRegistry()
        executor = WorkflowFileExecutor(registry=registry)

        # Execute and consume events
        async for event in executor.execute(workflow, inputs={"branch": "main"}):
            if isinstance(event, StepStarted):
                print(f"Starting step: {event.step_name}")
            elif isinstance(event, StepCompleted):
                print(f"Completed step: {event.step_name} (success={event.success})")

        # Get final result
        result = executor.get_result()
        print(f"Workflow success: {result.success}")
        ```
    """

    def __init__(
        self,
        registry: ComponentRegistry | None = None,
        config: Any = None,
        checkpoint_store: CheckpointStore | None = None,
    ) -> None:
        """Initialize executor.

        Args:
            registry: Component registry for resolving actions/agents/generators.
                If None, creates a new empty registry.
            config: Optional configuration for validation stages.
            checkpoint_store: Optional checkpoint store for workflow resumability.
                If None, creates a FileCheckpointStore with default path.
        """
        self._registry = registry or ComponentRegistry()
        self._config = config
        self._checkpoint_store = checkpoint_store or FileCheckpointStore()
        self._result: WorkflowResult | None = None
        self._cancelled = False

    async def execute(
        self,
        workflow: WorkflowFile,
        inputs: dict[str, Any] | None = None,
        resume_from_checkpoint: bool = False,
    ) -> AsyncIterator[ProgressEvent]:
        """Execute a workflow file and yield progress events.

        Executes each step in sequence, evaluating conditions and expressions,
        and yielding progress events for monitoring. Stops execution on first
        failure unless the step is configured to continue on error.

        Args:
            workflow: WorkflowFile to execute.
            inputs: Input values for the workflow (merged with defaults).
            resume_from_checkpoint: If True, attempts to resume from the latest
                checkpoint. Validates that inputs match the checkpoint.

        Yields:
            ProgressEvent objects for TUI/CLI consumption.

        Raises:
            ValueError: If resuming from checkpoint but inputs don't match.

        Example:
            ```python
            async for event in executor.execute(workflow, {"dry_run": False}):
                print(f"Event: {event}")
            # Resume from checkpoint
            async for event in executor.execute(
                workflow, {"dry_run": False}, resume_from_checkpoint=True
            ):
                print(f"Event: {event}")
            ```
        """
        inputs = inputs or {}

        # Handle checkpoint resume
        (
            checkpoint_data,
            resume_after_step,
        ) = await checkpointing.load_checkpoint_if_resuming(
            workflow, inputs, resume_from_checkpoint, self._checkpoint_store
        )

        # Build execution context
        exec_context = context.create_execution_context(workflow.name, inputs)

        # Restore step results from checkpoint if resuming
        checkpointing.restore_context_from_checkpoint(checkpoint_data, exec_context)

        start_time = time.perf_counter()
        step_results: list[StepResult] = []
        success = True

        # Track whether we've passed the resume checkpoint
        past_resume_point = not resume_from_checkpoint

        yield WorkflowStarted(workflow_name=workflow.name, inputs=inputs)

        for step_record in workflow.steps:
            if self._cancelled:
                success = False
                break

            # Skip steps before resume checkpoint
            if not past_resume_point:
                should_skip, past_resume_point = checkpointing.should_skip_step(
                    step_record, resume_after_step, past_resume_point
                )
                if should_skip:
                    continue

            # Check conditional execution
            if step_record.when:
                try:
                    should_run = conditions.evaluate_condition(
                        step_record.when, exec_context
                    )
                    if not should_run:
                        logger.debug(
                            f"Skipping step '{step_record.name}' (condition=false)"
                        )
                        continue
                except Exception as e:
                    logger.warning(
                        f"Error evaluating condition for step '{step_record.name}': {e}"
                    )
                    # Treat condition error as false (skip the step)
                    continue

            yield StepStarted(step_name=step_record.name, step_type=step_record.type)

            step_start = time.perf_counter()
            try:
                output = await self._execute_step(step_record, exec_context)
                step_result = StepResult(
                    name=step_record.name,
                    step_type=step_record.type,
                    success=True,
                    output=output,
                    duration_ms=int((time.perf_counter() - step_start) * 1000),
                )
            except Exception as e:
                logger.exception(f"Step '{step_record.name}' failed")
                step_result = StepResult(
                    name=step_record.name,
                    step_type=step_record.type,
                    success=False,
                    output=None,
                    duration_ms=int((time.perf_counter() - step_start) * 1000),
                    error=str(e),
                )

            step_results.append(step_result)
            # Store step output in context for subsequent expressions
            # Validate output before storing to ensure safe expression evaluation
            validated_output = context.validate_step_output(
                step_result.output,
                step_record.name,
                step_record.type,
            )
            context.store_step_output(exec_context, step_record.name, validated_output)

            yield StepCompleted(
                step_name=step_record.name,
                step_type=step_record.type,
                success=step_result.success,
                duration_ms=step_result.duration_ms,
            )

            if not step_result.success:
                success = False
                break

        total_duration_ms = int((time.perf_counter() - start_time) * 1000)

        # Validate final output before storing in result
        # (defensive check even though step outputs are already validated)
        final_output = None
        if step_results:
            final_output = context.validate_step_output(
                step_results[-1].output,
                step_results[-1].name,
                step_results[-1].step_type,
            )

        self._result = WorkflowResult(
            workflow_name=workflow.name,
            success=success,
            step_results=tuple(step_results),
            total_duration_ms=total_duration_ms,
            final_output=final_output,
        )

        yield WorkflowCompleted(
            workflow_name=workflow.name,
            success=success,
            total_duration_ms=total_duration_ms,
        )

    async def _execute_step(
        self,
        step: StepRecordType,
        exec_context: dict[str, Any],
    ) -> Any:
        """Execute a single step.

        Dispatches to the appropriate handler based on step type.

        Args:
            step: Step record to execute.
            exec_context: Execution context with inputs and step outputs.

        Returns:
            Step output value.

        Raises:
            NotImplementedError: If step type is not yet implemented.
        """
        # Resolve expressions in step inputs
        resolved_inputs = conditions.resolve_expressions(step, exec_context)

        if isinstance(step, PythonStepRecord):
            return await python_step.execute_python_step(
                step, resolved_inputs, exec_context, self._registry, self._config
            )
        elif isinstance(step, AgentStepRecord):
            return await agent_step.execute_agent_step(
                step, resolved_inputs, exec_context, self._registry, self._config
            )
        elif isinstance(step, GenerateStepRecord):
            return await generate_step.execute_generate_step(
                step, resolved_inputs, exec_context, self._registry, self._config
            )
        elif isinstance(step, ValidateStepRecord):
            return await validate_step.execute_validate_step(
                step, resolved_inputs, exec_context, self._registry, self._config
            )
        elif isinstance(step, SubWorkflowStepRecord):
            return await subworkflow_step.execute_subworkflow_step(
                step, resolved_inputs, exec_context, self._registry, self._config
            )
        elif isinstance(step, BranchStepRecord):
            return await branch_step.execute_branch_step(
                step,
                resolved_inputs,
                exec_context,
                self._registry,
                self._config,
                execute_step_fn=self._execute_step,
            )
        elif isinstance(step, ParallelStepRecord):
            return await parallel_step.execute_parallel_step(
                step,
                resolved_inputs,
                exec_context,
                self._registry,
                self._config,
                execute_step_fn=self._execute_step,
            )
        elif isinstance(step, CheckpointStepRecord):
            return await checkpoint_step.execute_checkpoint_step(
                step,
                resolved_inputs,
                exec_context,
                self._registry,
                self._config,
                checkpoint_store=self._checkpoint_store,
            )
        else:
            raise NotImplementedError(
                f"Step type {step.type} not yet implemented in executor"
            )

    def get_result(self) -> WorkflowResult:
        """Get the final workflow result.

        Returns:
            WorkflowResult from the last execution.

        Raises:
            RuntimeError: If workflow has not been executed yet.

        Example:
            ```python
            async for event in executor.execute(workflow):
                pass  # Process events

            result = executor.get_result()
            print(f"Success: {result.success}")
            print(f"Duration: {result.total_duration_ms}ms")
            ```
        """
        if self._result is None:
            raise RuntimeError("Workflow has not been executed yet")
        return self._result

    def cancel(self) -> None:
        """Request workflow cancellation.

        Sets the cancellation flag that will be checked before each step.
        Currently executing steps will complete before cancellation takes effect.

        Example:
            ```python
            executor = WorkflowFileExecutor()

            # Start execution
            task = asyncio.create_task(executor.execute(workflow))

            # Later, cancel it
            executor.cancel()
            ```
        """
        self._cancelled = True
