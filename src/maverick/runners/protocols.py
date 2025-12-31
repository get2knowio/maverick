"""Protocol definitions for runner validation.

This module defines protocols that runners can implement to support
environment validation capabilities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from maverick.runners.preflight import ValidationResult

__all__ = ["ValidatableRunner"]


@runtime_checkable
class ValidatableRunner(Protocol):
    """Protocol for runners that support environment validation.

    Any runner class that implements an async validate() method
    returning ValidationResult satisfies this protocol.

    Example:
        A runner implementing this protocol::

            class GitRunner:
                async def validate(self) -> ValidationResult:
                    # Check git is available
                    ...
                    return ValidationResult(success=True)

        Using the protocol for type hints::

            async def validate_runners(
                runners: Sequence[ValidatableRunner],
            ) -> list[ValidationResult]:
                return [await r.validate() for r in runners]
    """

    async def validate(self) -> ValidationResult:
        """Validate that required tools and configuration are available.

        Returns:
            ValidationResult with success status and any errors/warnings.

        Note:
            This method should NOT raise exceptions for validation failures.
            Failures should be captured in the ValidationResult.errors tuple.
        """
        ...
