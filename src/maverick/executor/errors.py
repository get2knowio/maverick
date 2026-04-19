"""StepExecutor error hierarchy."""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from maverick.exceptions import MaverickError


class ExecutorError(MaverickError):
    """Base class for StepExecutor errors."""


class OutputSchemaValidationError(ExecutorError):
    """Raised when plain text agent output fails output_schema validation.

    Attributes:
        step_name: Name of the DSL step that produced invalid output.
        schema_type: The Pydantic model class used for validation.
        validation_errors: The Pydantic ValidationError details.
    """

    def __init__(
        self,
        step_name: str,
        schema_type: type[BaseModel],
        validation_errors: ValidationError,
    ) -> None:
        self.step_name = step_name
        self.schema_type = schema_type
        self.validation_errors = validation_errors
        super().__init__(
            f"Step '{step_name}' output failed validation against "
            f"{schema_type.__name__}: {validation_errors}"
        )
