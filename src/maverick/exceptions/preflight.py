"""Preflight validation exceptions.

This module provides exception classes for preflight validation failures.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from maverick.exceptions.base import MaverickError

if TYPE_CHECKING:
    from maverick.runners.preflight import PreflightResult

__all__ = ["PreflightValidationError"]


class PreflightValidationError(MaverickError):
    """Raised when preflight validation fails.

    This exception is raised when one or more preflight checks fail,
    preventing a workflow from proceeding.

    Attributes:
        result: The PreflightResult containing failure details.

    Example:
        >>> if not preflight_result.success:
        ...     raise PreflightValidationError(preflight_result)
    """

    def __init__(self, result: PreflightResult) -> None:
        """Initialize the preflight validation error.

        Args:
            result: The PreflightResult containing failure details.
        """
        self.result = result
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format the error message from the preflight result.

        Returns:
            A formatted string describing all failures and warnings.
        """
        failed_count = len(self.result.failed_components)
        lines = [
            f"Preflight validation failed ({failed_count} components):",
            "",
        ]
        for error in self.result.all_errors:
            lines.append(f"  ✗ {error}")
        if self.result.all_warnings:
            lines.append("")
            lines.append("Warnings:")
            for warning in self.result.all_warnings:
                lines.append(f"  ⚠ {warning}")
        return "\n".join(lines)
