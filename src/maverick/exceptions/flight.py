"""Flight Plan and Work Unit exceptions.

Exceptions for loading, parsing, and resolving flight plan documents
and work unit dependency graphs.
"""

from __future__ import annotations

from pathlib import Path

from maverick.exceptions.base import MaverickError


class FlightError(MaverickError):
    """Base exception for flight package operations.

    Attributes:
        message: Human-readable error message.
    """


class FlightPlanParseError(FlightError):
    """YAML/Markdown parsing failure.

    Attributes:
        message: Human-readable error message.
        path: Path to the file that failed to parse (if applicable).
        field: Specific field or section that caused the parse error.
        error_kind: Structured error kind for programmatic classification
            (e.g. ``"missing_opening_delimiter"``).  Defaults to ``None``
            for backward compatibility.
    """

    def __init__(
        self,
        message: str,
        *,
        path: Path | None = None,
        field: str | None = None,
        error_kind: str | None = None,
    ) -> None:
        self.path = path
        self.field = field
        self.error_kind = error_kind
        super().__init__(message)


class FlightPlanValidationError(FlightError):
    """Model validation failure for Flight Plan documents.

    Attributes:
        message: Human-readable error message.
        path: Path to the file that failed validation (if applicable).
        field: Specific field that failed validation.
    """

    def __init__(
        self,
        message: str,
        *,
        path: Path | None = None,
        field: str | None = None,
    ) -> None:
        self.path = path
        self.field = field
        super().__init__(message)


class FlightPlanNotFoundError(FlightError):
    """Flight Plan file not found.

    Attributes:
        message: Human-readable error message.
        path: The path that was not found.
    """

    def __init__(
        self,
        message: str,
        *,
        path: Path | None = None,
    ) -> None:
        self.path = path
        super().__init__(message)


class WorkUnitNotFoundError(FlightError):
    """Work Unit file not found.

    Attributes:
        message: Human-readable error message.
        path: The path that was not found.
    """

    def __init__(
        self,
        message: str,
        *,
        path: Path | None = None,
    ) -> None:
        self.path = path
        super().__init__(message)


class WorkUnitValidationError(FlightError):
    """Work Unit model validation failure.

    Attributes:
        message: Human-readable error message.
        path: Path to the file that failed validation (if applicable).
        field: Specific field that failed validation.
    """

    def __init__(
        self,
        message: str,
        *,
        path: Path | None = None,
        field: str | None = None,
    ) -> None:
        self.path = path
        self.field = field
        super().__init__(message)


class WorkUnitDependencyError(FlightError):
    """Work Unit dependency resolution failure.

    Attributes:
        message: Human-readable error message.
        cycle: List of Work Unit IDs forming a dependency cycle.
        missing_id: The dependency ID that was not found.
    """

    def __init__(
        self,
        message: str,
        *,
        cycle: list[str] | None = None,
        missing_id: str | None = None,
    ) -> None:
        self.cycle = cycle
        self.missing_id = missing_id
        super().__init__(message)


__all__ = [
    "FlightError",
    "FlightPlanNotFoundError",
    "FlightPlanParseError",
    "FlightPlanValidationError",
    "WorkUnitDependencyError",
    "WorkUnitNotFoundError",
    "WorkUnitValidationError",
]
