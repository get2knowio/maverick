"""Subworkflow step handler for executing nested workflows.

This module handles execution of SubWorkflowStepRecord steps.
"""

from __future__ import annotations

from typing import Any

from maverick.dsl.serialization.errors import ReferenceResolutionError
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import SubWorkflowStepRecord, WorkflowFile


async def execute_subworkflow_step(
    step: SubWorkflowStepRecord,
    resolved_inputs: dict[str, Any],
    context: dict[str, Any],
    registry: ComponentRegistry,
    config: Any = None,
) -> Any:
    """Execute a sub-workflow step.

    Args:
        step: SubWorkflowStepRecord containing workflow reference and inputs.
        resolved_inputs: Resolved input values.
        context: Execution context.
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

    # If workflow is a WorkflowFile, execute it with WorkflowFileExecutor
    if isinstance(workflow, WorkflowFile):
        # Import here to avoid circular dependency
        from maverick.dsl.serialization.executor.executor import WorkflowFileExecutor

        sub_executor = WorkflowFileExecutor(
            registry=registry,
            config=config,
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
