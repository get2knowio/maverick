from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable, Generator
from typing import Any

from maverick.dsl.context import WorkflowContext
from maverick.dsl.decorator import WorkflowDefinition
from maverick.dsl.events import (
    ProgressEvent,
    StepCompleted,
    StepStarted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.dsl.results import StepResult, WorkflowResult
from maverick.dsl.steps.base import StepDefinition
from maverick.exceptions import DuplicateStepNameError


class WorkflowEngine:
    """Workflow execution engine.

    Executes workflow definitions, manages context, and emits progress events
    for TUI consumption.
    """

    def __init__(
        self,
        config: Any = None,
    ) -> None:
        """Initialize the workflow engine.

        Args:
            config: Optional configuration for validation stages, etc.
        """
        self._config = config
        self._result: WorkflowResult | None = None
        self._cancelled = False

    async def execute(
        self,
        workflow_func: Callable[..., Any],
        **inputs: Any,
    ) -> AsyncIterator[ProgressEvent]:
        """Execute a workflow and yield progress events.

        Args:
            workflow_func: Decorated workflow function.
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
        has_explicit_return = False
        success = True

        # Emit workflow started
        yield WorkflowStarted(workflow_name=workflow_name, inputs=inputs)

        # Create generator from workflow function
        gen: Generator[StepDefinition, Any, Any] = workflow_def.func(**inputs)

        # Start generator
        try:
            step_to_execute = gen.send(None)
        except StopIteration as e:
            # Workflow returned immediately with no steps
            has_explicit_return = True
            final_output = e.value
            step_to_execute = None

        # Execute steps
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

        # Calculate total duration
        total_duration_ms = int((time.perf_counter() - start_time) * 1000)

        # Create result
        self._result = WorkflowResult(
            workflow_name=workflow_name,
            success=success,
            step_results=tuple(step_results),
            total_duration_ms=total_duration_ms,
            final_output=final_output,
        )

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

    def cancel(self) -> None:
        """Request workflow cancellation.

        Cancellation is cooperative and takes effect at step boundaries.
        """
        self._cancelled = True
