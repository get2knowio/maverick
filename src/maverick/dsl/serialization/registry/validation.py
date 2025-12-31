"""Validation utilities for component registration (T025-T031).

This module provides validation helpers to ensure components registered in
the DSL registries meet the expected type signatures and contracts.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.generators import GeneratorAgent

__all__ = [
    "validate_callable",
    "validate_signature",
    "validate_agent_class",
    "validate_generator_class",
    "validate_context_builder",
    "is_async_callable",
]


def validate_callable(component: Any, component_name: str) -> None:
    """Validate that a component is callable.

    Args:
        component: Component to validate.
        component_name: Name of the component (for error messages).

    Raises:
        TypeError: If component is not callable.

    Example:
        ```python
        validate_callable(my_function, "my_action")
        ```
    """
    if not callable(component):
        raise TypeError(
            f"Component '{component_name}' must be callable. "
            f"Got {type(component).__name__} instead."
        )


def validate_signature(
    func: Callable[..., Any],
    component_name: str,
    min_params: int | None = None,
    max_params: int | None = None,
    expected_params: int | None = None,
) -> None:
    """Validate the signature of a callable.

    Args:
        func: Function to validate.
        component_name: Name of the component (for error messages).
        min_params: Minimum number of positional parameters (optional).
        max_params: Maximum number of positional parameters (optional).
        expected_params: Exact number of positional parameters (optional).

    Raises:
        TypeError: If signature does not match expectations.

    Example:
        ```python
        # Context builders should accept exactly 2 parameters
        validate_signature(builder_func, "my_builder", expected_params=2)

        # Actions can accept variable parameters
        validate_signature(action_func, "my_action", min_params=0)
        ```
    """
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError) as e:
        raise TypeError(
            f"Cannot inspect signature of '{component_name}': {e}. "
            f"Make sure the component is a valid Python callable."
        ) from e

    # Count positional parameters (excluding *args, **kwargs)
    positional_params = [
        p
        for p in sig.parameters.values()
        if p.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]
    param_count = len(positional_params)

    # Check exact count if specified
    if expected_params is not None and param_count != expected_params:
        plural_expected = "parameter" if expected_params == 1 else "parameters"
        plural_actual = "parameter" if param_count == 1 else "parameters"
        raise TypeError(
            f"Component '{component_name}' must accept exactly "
            f"{expected_params} positional {plural_expected}, "
            f"but accepts {param_count} {plural_actual}. Signature: {sig}"
        )

    # Check minimum if specified
    if min_params is not None and param_count < min_params:
        raise TypeError(
            f"Component '{component_name}' must accept at least "
            f"{min_params} positional parameter(s), but accepts {param_count}. "
            f"Signature: {sig}"
        )

    # Check maximum if specified
    if max_params is not None and param_count > max_params:
        raise TypeError(
            f"Component '{component_name}' must accept at most "
            f"{max_params} positional parameter(s), but accepts {param_count}. "
            f"Signature: {sig}"
        )


def validate_agent_class(cls: Any, component_name: str) -> None:
    """Validate that a class inherits from MaverickAgent.

    Args:
        cls: Class to validate.
        component_name: Name of the component (for error messages).

    Raises:
        TypeError: If class is not a class or doesn't inherit from MaverickAgent.

    Example:
        ```python
        validate_agent_class(CodeReviewerAgent, "code_reviewer")
        ```
    """
    # First check if it's a class
    if not inspect.isclass(cls):
        raise TypeError(
            f"Agent '{component_name}' must be a class, "
            f"got {type(cls).__name__} instead."
        )

    # Check if it inherits from MaverickAgent
    if not issubclass(cls, MaverickAgent):
        raise TypeError(
            f"Agent class '{component_name}' must inherit from MaverickAgent. "
            f"Got {cls.__name__} which inherits from: "
            f"{', '.join(base.__name__ for base in cls.__bases__)}"
        )

    # Check that it implements execute method (not just inherited abstract one)
    # MaverickAgent has execute as abstract, so we need to check if the subclass
    # overrides it. We do this by checking if 'execute' is in the class __dict__
    # (not inherited) and is callable.
    if "execute" not in cls.__dict__:
        # execute is not overridden in this class
        # Check if it's abstract (from MaverickAgent)
        execute_method = getattr(cls, "execute", None)
        if execute_method and getattr(execute_method, "__isabstractmethod__", False):
            raise TypeError(
                f"Agent class '{component_name}' must implement the "
                f"abstract 'execute' method. Class {cls.__name__} inherits from "
                f"MaverickAgent but does not override execute()."
            )
        elif not execute_method:
            methods = ", ".join(m for m in dir(cls) if not m.startswith("_"))
            raise TypeError(
                f"Agent class '{component_name}' must define an 'execute' method. "
                f"Available methods: {methods}"
            )


def validate_generator_class(cls: Any, component_name: str) -> None:
    """Validate that a class inherits from GeneratorAgent.

    Args:
        cls: Class to validate.
        component_name: Name of the component (for error messages).

    Raises:
        TypeError: If class is not a class or doesn't inherit from GeneratorAgent.

    Example:
        ```python
        validate_generator_class(CommitMessageGenerator, "commit_msg")
        ```
    """
    # First check if it's a class
    if not inspect.isclass(cls):
        raise TypeError(
            f"Generator '{component_name}' must be a class, "
            f"got {type(cls).__name__} instead."
        )

    # Check if it inherits from GeneratorAgent
    if not issubclass(cls, GeneratorAgent):
        raise TypeError(
            f"Generator class '{component_name}' must inherit from "
            f"GeneratorAgent. Got {cls.__name__} which inherits from: "
            f"{', '.join(base.__name__ for base in cls.__bases__)}"
        )

    # Check that it implements generate method
    if "generate" not in cls.__dict__:
        # generate is not overridden in this class
        # Check if it's abstract (from GeneratorAgent)
        generate_method = getattr(cls, "generate", None)
        if generate_method and getattr(generate_method, "__isabstractmethod__", False):
            raise TypeError(
                f"Generator class '{component_name}' must implement the "
                f"abstract 'generate' method. Class {cls.__name__} inherits from "
                f"GeneratorAgent but does not override generate()."
            )
        elif not generate_method:
            methods = ", ".join(m for m in dir(cls) if not m.startswith("_"))
            raise TypeError(
                f"Generator class '{component_name}' must define a 'generate' "
                f"method. Available methods: {methods}"
            )


def validate_context_builder(func: Callable[..., Any], component_name: str) -> None:
    """Validate that a context builder has the correct signature.

    Context builders must accept exactly 2 positional parameters:
    - inputs: dict[str, Any] - Workflow input parameters
    - step_results: dict[str, Any] - Results from previous steps

    Args:
        func: Context builder function to validate.
        component_name: Name of the component (for error messages).

    Raises:
        TypeError: If signature is invalid.

    Example:
        ```python
        def build_context(inputs: dict, step_results: dict) -> dict:
            return {...}

        validate_context_builder(build_context, "my_builder")
        ```
    """
    # First ensure it's callable
    validate_callable(func, component_name)

    # Then validate signature - must accept exactly 2 parameters
    validate_signature(func, component_name, expected_params=2)


def is_async_callable(func: Callable[..., Any]) -> bool:
    """Check if a callable is async (returns a coroutine).

    Args:
        func: Callable to check.

    Returns:
        True if the callable is async, False otherwise.

    Example:
        ```python
        async def async_func():
            pass

        def sync_func():
            pass

        assert is_async_callable(async_func) is True
        assert is_async_callable(sync_func) is False
        ```
    """
    return inspect.iscoroutinefunction(func)
