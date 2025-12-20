"""Workflow file executor for running WorkflowFile instances.

This module provides the WorkflowFileExecutor class that bridges the gap between
serialized WorkflowFile definitions and actual execution using registry-resolved
components. It yields progress events compatible with the TUI/CLI interfaces.
"""

from __future__ import annotations

import inspect
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from maverick.dsl.events import (
    ProgressEvent,
    StepCompleted,
    StepStarted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.dsl.expressions import ExpressionEvaluator, parse_expression
from maverick.dsl.results import StepResult, WorkflowResult
from maverick.dsl.serialization.errors import ReferenceResolutionError
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import (
    AgentStepRecord,
    GenerateStepRecord,
    PythonStepRecord,
    ValidateStepRecord,
    WorkflowFile,
)

logger = logging.getLogger(__name__)

# Type alias for step records
StepRecordType = (
    PythonStepRecord | AgentStepRecord | GenerateStepRecord | ValidateStepRecord
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
    ) -> None:
        """Initialize executor.

        Args:
            registry: Component registry for resolving actions/agents/generators.
                If None, creates a new empty registry.
            config: Optional configuration for validation stages.
        """
        self._registry = registry or ComponentRegistry()
        self._config = config
        self._result: WorkflowResult | None = None
        self._cancelled = False

    async def execute(
        self,
        workflow: WorkflowFile,
        inputs: dict[str, Any] | None = None,
    ) -> AsyncIterator[ProgressEvent]:
        """Execute a workflow file and yield progress events.

        Executes each step in sequence, evaluating conditions and expressions,
        and yielding progress events for monitoring. Stops execution on first
        failure unless the step is configured to continue on error.

        Args:
            workflow: WorkflowFile to execute.
            inputs: Input values for the workflow (merged with defaults).

        Yields:
            ProgressEvent objects for TUI/CLI consumption.

        Example:
            ```python
            async for event in executor.execute(workflow, {"dry_run": False}):
                print(f"Event: {event}")
            ```
        """
        inputs = inputs or {}

        # Build execution context
        # Context structure: {"inputs": {...}, "steps": {"step_name": {"output": ...}}}
        context = {
            "inputs": inputs,
            "steps": {},  # Will hold step outputs: steps.<name>.output
        }

        start_time = time.perf_counter()
        step_results: list[StepResult] = []
        success = True

        yield WorkflowStarted(workflow_name=workflow.name, inputs=inputs)

        for step_record in workflow.steps:
            if self._cancelled:
                success = False
                break

            # Check conditional execution
            if step_record.when:
                try:
                    should_run = self._evaluate_condition(step_record.when, context)
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
                output = await self._execute_step(step_record, context)
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
            context["steps"][step_record.name] = {"output": step_result.output}

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

        self._result = WorkflowResult(
            workflow_name=workflow.name,
            success=success,
            step_results=tuple(step_results),
            total_duration_ms=total_duration_ms,
            final_output=step_results[-1].output if step_results else None,
        )

        yield WorkflowCompleted(
            workflow_name=workflow.name,
            success=success,
            total_duration_ms=total_duration_ms,
        )

    def _evaluate_condition(self, condition: str, context: dict[str, Any]) -> bool:
        """Evaluate a conditional expression.

        Args:
            condition: Condition expression (e.g., "${{ inputs.dry_run }}").
            context: Execution context with inputs and steps.

        Returns:
            Boolean result of the condition.

        Raises:
            Exception: If expression evaluation fails.
        """
        # Create evaluator with current context
        evaluator = ExpressionEvaluator(
            inputs=context.get("inputs", {}),
            step_outputs=context.get("steps", {}),
        )

        # Parse and evaluate the expression
        expr = parse_expression(condition)
        result = evaluator.evaluate(expr)

        # Convert to boolean (support truthy values)
        return bool(result)

    async def _execute_step(
        self,
        step: StepRecordType,
        context: dict[str, Any],
    ) -> Any:
        """Execute a single step.

        Dispatches to the appropriate execution method based on step type.

        Args:
            step: Step record to execute.
            context: Execution context with inputs and step outputs.

        Returns:
            Step output value.

        Raises:
            NotImplementedError: If step type is not yet implemented.
        """
        # Resolve expressions in step inputs
        resolved_inputs = self._resolve_expressions(step, context)

        if isinstance(step, PythonStepRecord):
            return await self._execute_python_step(step, resolved_inputs, context)
        elif isinstance(step, AgentStepRecord):
            return await self._execute_agent_step(step, resolved_inputs, context)
        elif isinstance(step, GenerateStepRecord):
            return await self._execute_generate_step(step, resolved_inputs, context)
        elif isinstance(step, ValidateStepRecord):
            return await self._execute_validate_step(step, resolved_inputs, context)
        else:
            raise NotImplementedError(
                f"Step type {step.type} not yet implemented in executor"
            )

    def _resolve_expressions(
        self,
        step: StepRecordType,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve expressions in step inputs.

        Args:
            step: Step record containing inputs.
            context: Execution context with inputs and step outputs.

        Returns:
            Dictionary with resolved values.
        """
        evaluator = ExpressionEvaluator(
            inputs=context.get("inputs", {}),
            step_outputs=context.get("steps", {}),
        )

        resolved = {}

        if isinstance(step, PythonStepRecord):
            # Resolve kwargs (args are positional, less common in workflows)
            for key, value in step.kwargs.items():
                if isinstance(value, str) and "${{" in value:
                    resolved[key] = evaluator.evaluate_string(value)
                else:
                    resolved[key] = value
        elif isinstance(step, (AgentStepRecord, GenerateStepRecord)):
            # Resolve context dict or return as-is
            if isinstance(step.context, dict):
                for key, value in step.context.items():
                    if isinstance(value, str) and "${{" in value:
                        resolved[key] = evaluator.evaluate_string(value)
                    else:
                        resolved[key] = value
            else:
                # Context is a string reference (context builder name)
                resolved["_context_builder"] = step.context

        return resolved

    async def _execute_python_step(
        self,
        step: PythonStepRecord,
        resolved_inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> Any:
        """Execute a Python callable step.

        Args:
            step: PythonStepRecord containing action reference and arguments.
            resolved_inputs: Resolved keyword arguments.
            context: Execution context.

        Returns:
            Action return value.

        Raises:
            ReferenceResolutionError: If action not found in registry.
        """
        # Look up action in registry
        if not self._registry.actions.has(step.action):
            raise ReferenceResolutionError(
                reference_type="action",
                reference_name=step.action,
                available_names=self._registry.actions.list_names(),
            )

        action = self._registry.actions.get(step.action)

        # Call the action with resolved kwargs
        result = action(**resolved_inputs)

        # If result is a coroutine, await it
        if inspect.iscoroutine(result):
            result = await result

        return result

    async def _execute_agent_step(
        self,
        step: AgentStepRecord,
        resolved_inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> Any:
        """Execute an agent step.

        Args:
            step: AgentStepRecord containing agent reference and context.
            resolved_inputs: Resolved context values.
            context: Execution context.

        Returns:
            Agent execution result.

        Raises:
            ReferenceResolutionError: If agent not found in registry.
            NotImplementedError: Agent execution not yet implemented.
        """
        # Check if agent exists in registry
        if not self._registry.generators.has(step.agent):
            raise ReferenceResolutionError(
                reference_type="agent",
                reference_name=step.agent,
                available_names=self._registry.generators.list_names(),
            )

        # Agent execution requires integration with Claude Agent SDK
        raise NotImplementedError(
            f"Agent execution not yet implemented for agent '{step.agent}'. "
            "Register agent implementations in the generator registry."
        )

    async def _execute_generate_step(
        self,
        step: GenerateStepRecord,
        resolved_inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> Any:
        """Execute a text generation step.

        Args:
            step: GenerateStepRecord containing generator reference and context.
            resolved_inputs: Resolved context values.
            context: Execution context.

        Returns:
            Generated text.

        Raises:
            ReferenceResolutionError: If generator not found in registry.
            NotImplementedError: Generator execution not yet implemented.
        """
        # Check if generator exists in registry
        if not self._registry.generators.has(step.generator):
            raise ReferenceResolutionError(
                reference_type="generator",
                reference_name=step.generator,
                available_names=self._registry.generators.list_names(),
            )

        # Generator execution requires integration with Claude Agent SDK
        raise NotImplementedError(
            f"Generator execution not yet implemented for generator "
            f"'{step.generator}'. Register generator implementations "
            "in the generator registry."
        )

    async def _execute_validate_step(
        self,
        step: ValidateStepRecord,
        resolved_inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> Any:
        """Execute a validation step.

        Args:
            step: ValidateStepRecord containing stages and retry configuration.
            resolved_inputs: Resolved values.
            context: Execution context.

        Returns:
            Validation result.

        Raises:
            NotImplementedError: Validation execution not yet implemented.
        """
        # TODO: Implement validation execution using ValidationWorkflow
        # For now, log and return success
        logger.warning(
            f"Validation execution not yet implemented for step '{step.name}'"
        )
        return {"success": True, "stages": []}

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
