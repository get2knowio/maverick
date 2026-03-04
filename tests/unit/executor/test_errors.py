"""Tests for ExecutorError and OutputSchemaValidationError."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from maverick.exceptions import MaverickError
from maverick.executor.errors import ExecutorError, OutputSchemaValidationError


class _SampleSchema(BaseModel):
    """Sample Pydantic model for testing."""

    name: str
    value: int


class TestExecutorError:
    """Tests for ExecutorError base class."""

    def test_inherits_from_maverick_error(self) -> None:
        """ExecutorError inherits from MaverickError."""
        assert issubclass(ExecutorError, MaverickError)

    def test_inherits_from_exception(self) -> None:
        """ExecutorError is an Exception."""
        assert issubclass(ExecutorError, Exception)

    def test_can_raise_and_catch(self) -> None:
        """ExecutorError can be raised and caught."""
        with pytest.raises(ExecutorError):
            raise ExecutorError("test error")

    def test_can_catch_as_maverick_error(self) -> None:
        """ExecutorError can be caught as MaverickError."""
        with pytest.raises(MaverickError):
            raise ExecutorError("test error")


class TestOutputSchemaValidationError:
    """Tests for OutputSchemaValidationError."""

    @pytest.fixture
    def validation_error(self) -> ValidationError:
        """Create a real Pydantic ValidationError for testing."""
        try:
            _SampleSchema.model_validate({"name": 123, "value": "not-an-int"})
            pytest.fail("Should have raised ValidationError")
        except ValidationError as e:
            return e

    def test_inherits_from_executor_error(self) -> None:
        """OutputSchemaValidationError inherits from ExecutorError."""
        assert issubclass(OutputSchemaValidationError, ExecutorError)

    def test_inherits_from_maverick_error(self) -> None:
        """OutputSchemaValidationError inherits from MaverickError."""
        assert issubclass(OutputSchemaValidationError, MaverickError)

    def test_stores_step_name(self, validation_error: ValidationError) -> None:
        """OutputSchemaValidationError stores step_name."""
        exc = OutputSchemaValidationError(
            step_name="my_step",
            schema_type=_SampleSchema,
            validation_errors=validation_error,
        )
        assert exc.step_name == "my_step"

    def test_stores_schema_type(self, validation_error: ValidationError) -> None:
        """OutputSchemaValidationError stores schema_type."""
        exc = OutputSchemaValidationError(
            step_name="my_step",
            schema_type=_SampleSchema,
            validation_errors=validation_error,
        )
        assert exc.schema_type is _SampleSchema

    def test_stores_validation_errors(self, validation_error: ValidationError) -> None:
        """OutputSchemaValidationError stores validation_errors."""
        exc = OutputSchemaValidationError(
            step_name="my_step",
            schema_type=_SampleSchema,
            validation_errors=validation_error,
        )
        assert exc.validation_errors is validation_error

    def test_str_includes_step_name(self, validation_error: ValidationError) -> None:
        """str() message includes step name."""
        exc = OutputSchemaValidationError(
            step_name="failing_step",
            schema_type=_SampleSchema,
            validation_errors=validation_error,
        )
        assert "failing_step" in str(exc)

    def test_str_includes_schema_class_name(
        self, validation_error: ValidationError
    ) -> None:
        """str() message includes schema class name."""
        exc = OutputSchemaValidationError(
            step_name="my_step",
            schema_type=_SampleSchema,
            validation_errors=validation_error,
        )
        assert "_SampleSchema" in str(exc)

    def test_can_catch_as_executor_error(
        self, validation_error: ValidationError
    ) -> None:
        """OutputSchemaValidationError can be caught as ExecutorError."""
        with pytest.raises(ExecutorError):
            raise OutputSchemaValidationError(
                step_name="step",
                schema_type=_SampleSchema,
                validation_errors=validation_error,
            )
