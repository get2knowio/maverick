"""Base interface for step handlers.

This module defines the protocol/ABC for step execution handlers.
All step handlers must conform to this interface for consistent execution.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any, Protocol, runtime_checkable

from maverick.dsl.context import WorkflowContext
from maverick.dsl.errors import ReferenceResolutionError
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.logging import get_logger

logger = get_logger(__name__)


@runtime_checkable
class StepHandler(Protocol):
    """Protocol that all step handlers must implement.

    Each step type has a dedicated handler that knows how to execute
    that specific step type using registry-resolved components.

    All handlers must follow this exact signature for:
    - Consistent error handling
    - Registry-based component resolution
    - Expression evaluation via resolved_inputs
    - Context propagation for step outputs

    The executor wraps handler output in StepResult, so handlers
    should return raw output values, not pre-wrapped results.
    """

    async def execute(
        self,
        step: Any,
        resolved_inputs: dict[str, Any],
        context: WorkflowContext,
        registry: ComponentRegistry,
        config: Any = None,
    ) -> Any:
        """Execute a workflow step.

        Args:
            step: Step record to execute (PythonStepRecord, AgentStepRecord, etc.).
                Type varies based on handler specialization.
            resolved_inputs: Step inputs with expressions already evaluated.
                For python/agent/generate steps, contains args/kwargs.
                For branch/parallel steps, may be empty.
            context: Workflow execution context containing:
                - inputs: Workflow input parameters (dict[str, Any])
                - results: Completed step results keyed by name (dict[str, StepResult])
                - workflow_name: Name of the workflow (optional)
                - config: Shared workflow configuration (optional)
                - _pending_rollbacks: Registered rollback actions
            registry: Component registry for resolving action/agent/generator
                references. Handlers must check existence before access.
            config: Optional workflow configuration (rarely used by handlers).

        Returns:
            Step output value. Will be wrapped in StepResult by executor.
            Return type varies based on step type:
            - PythonStep: action return value
            - AgentStep: agent execution result
            - GenerateStep: generated text string
            - ValidateStep: dict with success/stages
            - BranchStep: result from matched branch
            - ParallelStep: dict with results list
            - CheckpointStep: dict with saved/checkpoint_id/timestamp

        Raises:
            ReferenceResolutionError: If component not found in registry.
            ValueError: If required parameters are invalid.
            Exception: Any step-specific execution error.
        """
        ...


async def with_error_handling(
    handler_name: str,
    step_name: str,
    handler_fn: Callable[..., Coroutine[Any, Any, Any]],
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Wrap handler execution with consistent error handling.

    Provides standardized error logging and re-raising for all handlers.
    This ensures that errors from different handlers are logged consistently
    and that the executor can handle them uniformly.

    Args:
        handler_name: Name of the handler (for logging, e.g., "agent_step").
        step_name: Name of the step being executed (for logging).
        handler_fn: The async handler function to execute.
        *args: Positional arguments to pass to handler_fn.
        **kwargs: Keyword arguments to pass to handler_fn.

    Returns:
        The result from handler_fn.

    Raises:
        ReferenceResolutionError: Re-raised with additional logging.
        Exception: Any other exception from handler execution, re-raised.

    Example:
        ```python
        result = await with_error_handling(
            "python_step",
            step.name,
            execute_python_step,
            step,
            resolved_inputs,
            context,
            registry,
            config,
        )
        ```
    """
    try:
        return await handler_fn(*args, **kwargs)
    except ReferenceResolutionError as e:
        logger.error(
            f"{handler_name} handler failed: component not found",
            step=step_name,
            reference_type=e.reference_type,
            reference_name=e.reference_name,
        )
        raise
    except Exception as e:
        logger.error(
            f"{handler_name} handler failed: {type(e).__name__}",
            step=step_name,
            error=str(e),
        )
        raise


__all__ = [
    "StepHandler",
    "with_error_handling",
]
