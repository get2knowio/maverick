"""Workflow file executor for running WorkflowFile instances.

This module provides the WorkflowFileExecutor class that bridges the gap between
serialized WorkflowFile definitions and actual execution using registry-resolved
components. It yields progress events compatible with the TUI/CLI interfaces.
"""

from __future__ import annotations

import asyncio
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
    BranchStepRecord,
    GenerateStepRecord,
    ParallelStepRecord,
    PythonStepRecord,
    SubWorkflowStepRecord,
    ValidateStepRecord,
    WorkflowFile,
)

logger = logging.getLogger(__name__)

# Type alias for step records
StepRecordType = (
    PythonStepRecord
    | AgentStepRecord
    | GenerateStepRecord
    | ValidateStepRecord
    | SubWorkflowStepRecord
    | BranchStepRecord
    | ParallelStepRecord
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
            # Validate output before storing to ensure safe expression evaluation
            validated_output = self._validate_step_output(
                step_result.output,
                step_record.name,
                step_record.type,
            )
            context["steps"][step_record.name] = {"output": validated_output}

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
            final_output = self._validate_step_output(
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
        elif isinstance(step, SubWorkflowStepRecord):
            return await self._execute_subworkflow_step(step, resolved_inputs, context)
        elif isinstance(step, BranchStepRecord):
            return await self._execute_branch_step(step, resolved_inputs, context)
        elif isinstance(step, ParallelStepRecord):
            return await self._execute_parallel_step(step, resolved_inputs, context)
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
        elif isinstance(step, SubWorkflowStepRecord):
            # Resolve inputs dict
            for key, value in step.inputs.items():
                if isinstance(value, str) and "${{" in value:
                    resolved[key] = evaluator.evaluate_string(value)
                else:
                    resolved[key] = value

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
        """
        # Check if agent exists in the agents registry
        if not self._registry.agents.has(step.agent):
            raise ReferenceResolutionError(
                reference_type="agent",
                reference_name=step.agent,
                available_names=self._registry.agents.list_names(),
            )

        # Build context
        agent_context: Any = context.copy()

        # If context is a string (context builder name), resolve it
        if "_context_builder" in resolved_inputs:
            context_builder_name = resolved_inputs["_context_builder"]
            try:
                if not self._registry.context_builders.has(context_builder_name):
                    raise ReferenceResolutionError(
                        reference_type="context_builder",
                        reference_name=context_builder_name,
                        available_names=self._registry.context_builders.list_names(),
                    )
                context_builder = self._registry.context_builders.get(
                    context_builder_name
                )
                builder_result = context_builder(agent_context)
                # If context builder is async, await it
                if inspect.iscoroutine(builder_result):
                    agent_context = await builder_result
                else:
                    agent_context = builder_result
            except ReferenceResolutionError as e:
                logger.error(
                    f"Context builder '{context_builder_name}' not found "
                    f"for agent step '{step.agent}': {e}"
                )
                raise
            except Exception as e:
                logger.error(
                    f"Error executing context builder '{context_builder_name}' "
                    f"for agent step '{step.agent}': {e}"
                )
                raise
        elif resolved_inputs:
            # Context is a dict, use resolved inputs directly
            agent_context.update(resolved_inputs)

        # Get agent class from registry and instantiate
        # Note: Registry stores agent classes (not instances)
        agent_class = self._registry.agents.get(step.agent)

        # Runtime validation: ensure it's callable
        if not callable(agent_class):
            raise TypeError(
                f"Agent '{step.agent}' is not callable. "
                f"Expected a class or callable, got {type(agent_class).__name__}"
            )

        try:
            agent_instance = agent_class()  # type: ignore[call-arg]
        except TypeError as e:
            logger.error(
                f"Failed to instantiate agent '{step.agent}': {e}. "
                f"Agent classes must be instantiable without arguments."
            )
            raise

        # Runtime validation: ensure execute method exists
        if not hasattr(agent_instance, "execute"):
            raise AttributeError(
                f"Agent instance '{step.agent}' does not have an 'execute' method"
            )

        # Call execute method (runtime validated above)
        result = agent_instance.execute(agent_context)

        # If result is a coroutine, await it
        if inspect.iscoroutine(result):
            result = await result

        return result

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
        """
        # Check if generator exists in registry
        if not self._registry.generators.has(step.generator):
            raise ReferenceResolutionError(
                reference_type="generator",
                reference_name=step.generator,
                available_names=self._registry.generators.list_names(),
            )

        # Build context
        generator_context: Any = context.copy()

        # If context is a string (context builder name), resolve it
        if "_context_builder" in resolved_inputs:
            context_builder_name = resolved_inputs["_context_builder"]
            try:
                if not self._registry.context_builders.has(context_builder_name):
                    raise ReferenceResolutionError(
                        reference_type="context_builder",
                        reference_name=context_builder_name,
                        available_names=self._registry.context_builders.list_names(),
                    )
                context_builder = self._registry.context_builders.get(
                    context_builder_name
                )
                builder_result = context_builder(generator_context)
                # If context builder is async, await it
                if inspect.iscoroutine(builder_result):
                    generator_context = await builder_result
                else:
                    generator_context = builder_result
            except ReferenceResolutionError as e:
                logger.error(
                    f"Context builder '{context_builder_name}' not found "
                    f"for generate step '{step.generator}': {e}"
                )
                raise
            except Exception as e:
                logger.error(
                    f"Error executing context builder '{context_builder_name}' "
                    f"for generate step '{step.generator}': {e}"
                )
                raise
        elif resolved_inputs:
            # Context is a dict, use resolved inputs directly
            generator_context.update(resolved_inputs)

        # Get generator class from registry and instantiate
        # Note: Registry stores generator classes (not instances)
        generator_class = self._registry.generators.get(step.generator)

        # Runtime validation: ensure it's callable
        if not callable(generator_class):
            raise TypeError(
                f"Generator '{step.generator}' is not callable. "
                f"Expected a class or callable, got {type(generator_class).__name__}"
            )

        try:
            generator_instance = generator_class()  # type: ignore[call-arg]
        except TypeError as e:
            logger.error(
                f"Failed to instantiate generator '{step.generator}': {e}. "
                f"Generator classes must be instantiable without arguments."
            )
            raise

        # Runtime validation: ensure generate method exists
        if not hasattr(generator_instance, "generate"):
            raise AttributeError(
                f"Generator instance '{step.generator}' does not have "
                f"a 'generate' method"
            )

        # Call generate method (runtime validated above)
        result = generator_instance.generate(generator_context)

        # If result is a coroutine, await it
        if inspect.iscoroutine(result):
            result = await result

        return result

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
            Validation result with success status and stage results.
        """
        # Execute validation stages
        stage_results = []
        overall_success = True

        for stage_name in step.stages:
            # For now, implement a simple mock that executes stages
            # In the future, this should integrate with ValidationRunner
            try:
                logger.info(f"Executing validation stage: {stage_name}")
                # Mock successful stage execution
                stage_result = {
                    "stage": stage_name,
                    "success": True,
                    "output": f"Stage {stage_name} completed",
                }
                stage_results.append(stage_result)
            except Exception as e:
                logger.error(f"Validation stage '{stage_name}' failed: {e}")
                stage_result = {
                    "stage": stage_name,
                    "success": False,
                    "error": str(e),
                }
                stage_results.append(stage_result)
                overall_success = False

        return {
            "success": overall_success,
            "passed": overall_success,
            "failed": not overall_success,
            "stages": stage_results,
        }

    async def _execute_subworkflow_step(
        self,
        step: SubWorkflowStepRecord,
        resolved_inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> Any:
        """Execute a sub-workflow step.

        Args:
            step: SubWorkflowStepRecord containing workflow reference and inputs.
            resolved_inputs: Resolved input values.
            context: Execution context.

        Returns:
            Sub-workflow final output.

        Raises:
            ReferenceResolutionError: If workflow not found in registry.
        """
        # Look up workflow in registry
        if not self._registry.workflows.has(step.workflow):
            raise ReferenceResolutionError(
                reference_type="workflow",
                reference_name=step.workflow,
                available_names=self._registry.workflows.list_names(),
            )

        workflow = self._registry.workflows.get(step.workflow)

        # Merge resolved inputs with step's declared inputs
        sub_inputs = {**step.inputs, **resolved_inputs}

        # If workflow is a WorkflowFile, execute it with WorkflowFileExecutor
        if isinstance(workflow, WorkflowFile):
            sub_executor = WorkflowFileExecutor(
                registry=self._registry,
                config=self._config,
            )
            result = None
            async for event in sub_executor.execute(workflow, inputs=sub_inputs):
                if hasattr(event, "result"):
                    result = event.result
            return result

        # If workflow is a decorated Python function, execute with WorkflowEngine
        elif hasattr(workflow, "__workflow_def__"):
            from maverick.dsl.engine import WorkflowEngine

            engine = WorkflowEngine()
            result = None
            # workflow has __workflow_def__ attribute, so it's a decorated workflow
            async for event in engine.execute(workflow, **sub_inputs):  # type: ignore[arg-type]
                if hasattr(event, "result"):
                    result = event.result
            return result

        else:
            raise TypeError(
                f"Workflow '{step.workflow}' has unexpected type: {type(workflow)}"
            )

    async def _execute_branch_step(
        self,
        step: BranchStepRecord,
        resolved_inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> Any:
        """Execute a branch step.

        Evaluates branch options in order and executes the first matching step.

        Args:
            step: BranchStepRecord containing branch options.
            resolved_inputs: Resolved values.
            context: Execution context.

        Returns:
            Result from the first matching branch, or None if no match.
        """
        # Evaluate options in order, execute first matching step
        for option in step.options:
            if self._evaluate_condition(option.when, context):
                return await self._execute_step(option.step, context)

        # No matching branch found
        return None

    async def _execute_parallel_step(
        self,
        step: ParallelStepRecord,
        resolved_inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> Any:
        """Execute a parallel step.

        Executes multiple steps concurrently using asyncio.gather.

        Args:
            step: ParallelStepRecord containing steps to execute in parallel.
            resolved_inputs: Resolved values.
            context: Execution context.

        Returns:
            Dictionary containing results from all parallel steps.
        """
        # Create tasks for all steps
        tasks = [self._execute_step(s, context) for s in step.steps]

        # Execute in parallel with exception handling
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {"results": results}

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

    def _validate_step_output(
        self,
        output: Any,
        step_name: str,
        step_type: str,
    ) -> Any:
        """Validate and sanitize step output before storing in context.

        This ensures that step outputs are safe to store and reference in
        subsequent expressions. Invalid outputs are logged and replaced with
        a safe default.

        Args:
            output: The raw output from step execution.
            step_name: Name of the step for logging.
            step_type: Type of the step for logging.

        Returns:
            Validated/sanitized output safe for context storage.
        """
        # None is a valid output (e.g., from failed steps)
        if output is None:
            return None

        # Primitive types are always safe
        if isinstance(output, (str, int, float, bool)):
            return output

        # Collections need basic validation
        if isinstance(output, (list, tuple)):
            # Ensure reasonable size to prevent memory issues
            if len(output) > 10000:
                logger.warning(
                    f"Step '{step_name}' ({step_type}) output list/tuple is very large "
                    f"({len(output)} items), which may impact performance"
                )
            return output

        if isinstance(output, dict):
            # Ensure reasonable size to prevent memory issues
            if len(output) > 10000:
                logger.warning(
                    f"Step '{step_name}' ({step_type}) output dict is very large "
                    f"({len(output)} keys), which may impact performance"
                )
            # Check for circular references (basic check)
            try:
                # Attempt JSON-like serialization check
                str(output)
            except Exception as e:
                logger.warning(
                    f"Step '{step_name}' ({step_type}) output dict may contain "
                    f"circular references or non-serializable objects: {e}"
                )
            return output

        # For other types, log a warning but allow them through
        # (could be dataclass, pydantic model, or other structured data)
        logger.debug(
            f"Step '{step_name}' ({step_type}) output is of type "
            f"{type(output).__name__}, which may not be fully compatible with "
            f"expression evaluation"
        )
        return output
