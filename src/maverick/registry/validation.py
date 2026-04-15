"""Validation utilities for component registration (T025-T031).

This module provides validation helpers to ensure components registered in
the registries meet the expected type signatures and contracts.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from maverick.agents.base import MaverickAgent

__all__ = [
    "validate_signature",
    "validate_agent_class",
    "is_async_callable",
]


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
        validate_agent_class(ImplementerAgent, "implementer")
        ```
    """
    # First check if it's a class
    if not inspect.isclass(cls):
        raise TypeError(
            f"Agent '{component_name}' must be a class, got {type(cls).__name__} instead."
        )

    # Check if it inherits from MaverickAgent
    if not issubclass(cls, MaverickAgent):
        raise TypeError(
            f"Agent class '{component_name}' must inherit from MaverickAgent. "
            f"Got {cls.__name__} which inherits from: "
            f"{', '.join(base.__name__ for base in cls.__bases__)}"
        )

    # Check that it implements build_prompt (the ACP pattern)
    build_prompt_method = getattr(cls, "build_prompt", None)
    if not build_prompt_method or getattr(build_prompt_method, "__isabstractmethod__", False):
        methods = ", ".join(m for m in dir(cls) if not m.startswith("_"))
        raise TypeError(
            f"Agent class '{component_name}' must implement the "
            f"'build_prompt' method. Available methods: {methods}"
        )


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
