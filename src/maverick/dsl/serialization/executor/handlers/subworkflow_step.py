"""Subworkflow step handler for executing nested workflows.

This module handles execution of SubWorkflowStepRecord steps.
"""

from __future__ import annotations

from typing import Any

from maverick.dsl.context import WorkflowContext
from maverick.dsl.errors import ReferenceResolutionError
from maverick.dsl.events import WorkflowCompleted, WorkflowStarted
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import SubWorkflowStepRecord, WorkflowFile


async def execute_subworkflow_step(
    step: SubWorkflowStepRecord,
    resolved_inputs: dict[str, Any],
    context: WorkflowContext,
    registry: ComponentRegistry,
    config: Any = None,
    event_callback: Any = None,
) -> Any:
    """Execute a sub-workflow step.

    Args:
        step: SubWorkflowStepRecord containing workflow reference and inputs.
        resolved_inputs: Resolved input values.
        context: WorkflowContext with inputs and step results.
        registry: Component registry for resolving workflow.
        config: Optional configuration.

    Returns:
        Sub-workflow final output.

    Raises:
        ReferenceResolutionError: If workflow not found in registry.
    """
    # Look up workflow in registry
    if not registry.workflows.has(step.workflow):
        raise ReferenceResolutionError(
            reference_type="workflow",
            reference_name=step.workflow,
            available_names=registry.workflows.list_names(),
        )

    workflow = registry.workflows.get(step.workflow)

    # Merge resolved inputs with step's declared inputs
    sub_inputs = {**step.inputs, **resolved_inputs}

    # Workflow must be a WorkflowFile (YAML-based serialization DSL)
    if not isinstance(workflow, WorkflowFile):
        raise TypeError(
            f"Workflow '{step.workflow}' must be a WorkflowFile instance. "
            f"Got: {type(workflow).__name__}. "
            f"Note: Decorator-based workflows are no longer supported."
        )

    # Import here to avoid circular dependency
    from maverick.dsl.serialization.executor.executor import WorkflowFileExecutor

    sub_executor = WorkflowFileExecutor(
        registry=registry,
        config=config,
    )
    # Process and forward events to parent workflow
    async for event in sub_executor.execute(workflow, inputs=sub_inputs):
        # Forward events to parent for real-time streaming, but filter out
        # sub-workflow lifecycle events (WorkflowStarted/Completed) since
        # those are internal to this sub-workflow and would be misinterpreted
        # by the parent as the top-level workflow completing.
        if event_callback is not None and not isinstance(
            event, (WorkflowStarted, WorkflowCompleted)
        ):
            await event_callback(event)

    # Get final result from sub-executor
    workflow_result = sub_executor.get_result()

    # Propagate failure to parent workflow
    if not workflow_result.success:
        # Get the failed step for error message
        failed_step = workflow_result.failed_step
        error_msg = (
            f"Sub-workflow '{step.workflow}' failed at step '{failed_step.name}'"
            if failed_step
            else f"Sub-workflow '{step.workflow}' failed"
        )
        if failed_step and failed_step.error:
            error_msg += f": {failed_step.error}"
        raise RuntimeError(error_msg)

    return workflow_result.final_output
