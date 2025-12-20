"""Workflow decorator and metadata classes.

This module provides the @workflow decorator for defining workflows
and the dataclasses that capture workflow metadata.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


@dataclass(frozen=True, slots=True)
class WorkflowParameter:
    """Parameter metadata extracted from workflow function signature.

    Captures information about each parameter of a workflow function
    for validation, documentation, and introspection.

    Attributes:
        name: Parameter name from function signature.
        annotation: Type annotation if provided, else None.
        default: Default value if provided, else None.
        kind: Parameter kind name (e.g., "POSITIONAL_OR_KEYWORD", "VAR_POSITIONAL").
    """

    name: str
    annotation: type | None
    default: Any
    kind: str


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    """Workflow metadata captured by @workflow decorator.

    Stores all metadata about a decorated workflow function including
    its name, description, parameters, and the underlying generator function.

    Attributes:
        name: Workflow identifier (unique within the application).
        description: Human-readable workflow description.
        parameters: Captured function parameters as a tuple.
        func: The decorated generator function.
    """

    name: str
    description: str
    parameters: tuple[WorkflowParameter, ...]
    func: Callable[..., Generator[Any, Any, Any]]


def workflow(
    name: str,
    description: str = "",
) -> Callable[
    [Callable[P, Generator[Any, Any, R]]], Callable[P, Generator[Any, Any, R]]
]:
    """Create a workflow from a generator function.

    The decorated function must be a generator that yields StepDefinition objects.
    The workflow decorator captures function signature metadata and attaches
    a WorkflowDefinition to the wrapper function.

    Args:
        name: Unique workflow identifier.
        description: Human-readable workflow description.

    Returns:
        Decorator that transforms generator function into executable workflow.

    Raises:
        ValueError: If name is empty.
        TypeError: If decorated function is not a generator.

    Example:
        @workflow(name="my-workflow", description="Does something useful")
        def my_workflow(input_data: str):
            result = yield step("process").python(action=process, args=(input_data,))
            return {"processed": result}
    """
    if not name or not name.strip():
        raise ValueError("Workflow name cannot be empty or whitespace")

    def decorator(
        func: Callable[P, Generator[Any, Any, R]],
    ) -> Callable[P, Generator[Any, Any, R]]:
        # Verify the function is a generator
        if not inspect.isgeneratorfunction(func):
            raise TypeError(
                f"Workflow function '{func.__name__}' must be a generator function "
                "(must use 'yield' to yield steps)"
            )

        # Capture signature metadata
        sig = inspect.signature(func)
        parameters = tuple(
            WorkflowParameter(
                name=param_name,
                annotation=(
                    param.annotation
                    if param.annotation != inspect.Parameter.empty
                    else None
                ),
                default=(
                    param.default if param.default != inspect.Parameter.empty else None
                ),
                kind=param.kind.name,
            )
            for param_name, param in sig.parameters.items()
        )

        workflow_def = WorkflowDefinition(
            name=name,
            description=description,
            parameters=parameters,
            func=func,
        )

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> Generator[Any, Any, R]:
            # The wrapper simply calls the original function
            # Execution is handled by WorkflowEngine
            return func(*args, **kwargs)

        # Attach workflow definition to wrapper for introspection
        wrapper.__workflow_def__ = workflow_def  # type: ignore[attr-defined]

        return wrapper

    return decorator
