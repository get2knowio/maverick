from __future__ import annotations

from typing import Any

from maverick.exceptions.base import MaverickError


class HookError(MaverickError):
    """Base exception for hook-related errors.

    Attributes:
        message: Human-readable error message.
    """

    pass


class SafetyHookError(HookError):
    """Exception raised when a safety hook blocks an operation.

    Attributes:
        message: Human-readable error message.
        tool_name: Name of the tool that was blocked.
        blocked_pattern: Pattern that triggered the block.
    """

    def __init__(
        self,
        message: str,
        tool_name: str | None = None,
        blocked_pattern: str | None = None,
    ) -> None:
        """Initialize the SafetyHookError.

        Args:
            message: Human-readable error message.
            tool_name: Name of the tool that was blocked.
            blocked_pattern: Pattern that triggered the block.
        """
        self.tool_name = tool_name
        self.blocked_pattern = blocked_pattern
        super().__init__(message)


class HookConfigError(HookError):
    """Exception raised for hook configuration errors.

    Attributes:
        message: Human-readable error message.
        field: Optional field name that caused the error.
        value: Optional value that failed validation.
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any = None,
    ) -> None:
        """Initialize the HookConfigError.

        Args:
            message: Human-readable error message.
            field: Optional field name that caused the error.
            value: Optional value that failed validation.
        """
        self.field = field
        self.value = value
        super().__init__(message)
