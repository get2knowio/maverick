"""Typed parameter accessor utilities."""

from typing import Any, TypeVar


T = TypeVar("T")


class ParameterAccessError(KeyError):
    """Raised when required parameter is missing or invalid."""

    pass


def get_required_param(params: dict[str, Any], key: str, expected_type: type[T], description: str | None = None) -> T:
    """Get a required parameter with type checking.

    Args:
        params: Parameter dictionary
        key: Parameter key to retrieve
        expected_type: Expected type for the parameter
        description: Optional human-readable description for error messages

    Returns:
        Parameter value cast to expected type

    Raises:
        ParameterAccessError: If parameter is missing or wrong type
    """
    if key not in params:
        desc = f" ({description})" if description else ""
        raise ParameterAccessError(f"Required parameter '{key}'{desc} is missing")

    value = params[key]

    if not isinstance(value, expected_type):
        actual_type = type(value).__name__
        expected_name = expected_type.__name__
        desc = f" ({description})" if description else ""
        raise ParameterAccessError(f"Parameter '{key}'{desc} has type {actual_type}, expected {expected_name}")

    return value


def get_optional_param(
    params: dict[str, Any], key: str, expected_type: type[T], default: T | None = None, description: str | None = None
) -> T | None:
    """Get an optional parameter with type checking.

    Args:
        params: Parameter dictionary
        key: Parameter key to retrieve
        expected_type: Expected type for the parameter
        default: Default value if parameter is missing
        description: Optional human-readable description for error messages

    Returns:
        Parameter value cast to expected type, or default if missing

    Raises:
        ParameterAccessError: If parameter exists but has wrong type
    """
    if key not in params:
        return default

    value = params[key]

    if not isinstance(value, expected_type):
        actual_type = type(value).__name__
        expected_name = expected_type.__name__
        desc = f" ({description})" if description else ""
        raise ParameterAccessError(f"Parameter '{key}'{desc} has type {actual_type}, expected {expected_name}")

    return value
