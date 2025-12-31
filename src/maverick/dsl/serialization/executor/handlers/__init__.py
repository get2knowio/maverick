"""Step handlers for workflow execution.

This package contains specialized handlers for each step type.
All handlers conform to the StepHandler protocol for consistent execution.
"""

from __future__ import annotations

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
from maverick.dsl.serialization.executor.handlers.base import (
    StepHandler,
    with_error_handling,
)
from maverick.dsl.types import StepType

# Handler registry: maps step types to their execution handlers
# All handlers conform to the StepHandler protocol
STEP_HANDLERS: dict[StepType, StepHandler] = {
    StepType.PYTHON: python_step.execute_python_step,  # type: ignore[dict-item]
    StepType.AGENT: agent_step.execute_agent_step,  # type: ignore[dict-item]
    StepType.GENERATE: generate_step.execute_generate_step,  # type: ignore[dict-item]
    StepType.VALIDATE: validate_step.execute_validate_step,  # type: ignore[dict-item]
    StepType.SUBWORKFLOW: subworkflow_step.execute_subworkflow_step,  # type: ignore[dict-item]
    StepType.BRANCH: branch_step.execute_branch_step,  # type: ignore[dict-item]
    StepType.PARALLEL: parallel_step.execute_parallel_step,  # type: ignore[dict-item]
    StepType.CHECKPOINT: checkpoint_step.execute_checkpoint_step,  # type: ignore[dict-item]
}


def get_handler(step_type: StepType) -> StepHandler:
    """Get the handler for a given step type.

    Args:
        step_type: The type of step to get a handler for.

    Returns:
        The handler function for that step type.

    Raises:
        ValueError: If no handler exists for the given step type.

    Example:
        ```python
        from maverick.dsl.types import StepType
        from maverick.dsl.serialization.executor.handlers import get_handler

        handler = get_handler(StepType.PYTHON)
        result = await handler(step, resolved_inputs, context, registry)
        ```
    """
    if step_type not in STEP_HANDLERS:
        raise ValueError(
            f"No handler registered for step type: {step_type}. "
            f"Available types: {list(STEP_HANDLERS.keys())}"
        )
    return STEP_HANDLERS[step_type]


__all__ = [
    "StepHandler",
    "with_error_handling",
    "get_handler",
    "STEP_HANDLERS",
    "agent_step",
    "branch_step",
    "checkpoint_step",
    "generate_step",
    "parallel_step",
    "python_step",
    "subworkflow_step",
    "validate_step",
]
