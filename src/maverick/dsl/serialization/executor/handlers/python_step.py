"""Python step handler for executing Python callable actions.

This module handles execution of PythonStepRecord steps.
"""

from __future__ import annotations

import inspect
from typing import Any

from maverick.dsl.serialization.errors import ReferenceResolutionError
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import PythonStepRecord


async def execute_python_step(
    step: PythonStepRecord,
    resolved_inputs: dict[str, Any],
    context: dict[str, Any],
    registry: ComponentRegistry,
    config: Any = None,
) -> Any:
    """Execute a Python callable step.

    Args:
        step: PythonStepRecord containing action reference and arguments.
        resolved_inputs: Resolved keyword arguments.
        context: Execution context.
        registry: Component registry for resolving action.
        config: Optional configuration (unused).

    Returns:
        Action return value.

    Raises:
        ReferenceResolutionError: If action not found in registry.
    """
    # Look up action in registry
    if not registry.actions.has(step.action):
        raise ReferenceResolutionError(
            reference_type="action",
            reference_name=step.action,
            available_names=registry.actions.list_names(),
        )

    action = registry.actions.get(step.action)

    # Call the action with resolved kwargs
    result = action(**resolved_inputs)

    # If result is a coroutine, await it
    if inspect.iscoroutine(result):
        result = await result

    return result
