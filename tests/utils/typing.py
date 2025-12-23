"""Type utilities for testing.

This module provides TypeGuard utilities for better type narrowing in tests.
"""

from __future__ import annotations

from typing import Any, TypeGuard, TypeVar

T = TypeVar("T")


def is_list_of_strings(val: Any) -> TypeGuard[list[str]]:
    """Check if value is a list of strings.

    Args:
        val: Value to check.

    Returns:
        True if val is list[str], False otherwise.
    """
    return isinstance(val, list) and all(isinstance(x, str) for x in val)


def is_dict_str_any(val: Any) -> TypeGuard[dict[str, Any]]:
    """Check if value is a dict with string keys.

    Args:
        val: Value to check.

    Returns:
        True if val is dict[str, Any], False otherwise.
    """
    return isinstance(val, dict) and all(isinstance(k, str) for k in val)


def is_instance_of(val: Any, cls: type[T]) -> TypeGuard[T]:
    """Generic type guard for isinstance checks.

    Args:
        val: Value to check.
        cls: Class to check against.

    Returns:
        True if val is instance of cls.
    """
    return isinstance(val, cls)
