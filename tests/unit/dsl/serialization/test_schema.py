"""Tests for workflow serialization schema models.

This module tests the Pydantic schema models used for workflow file validation,
including validation error/warning/result dataclasses.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from maverick.dsl.serialization.schema import (
    AgentStepRecord,
    BranchOptionRecord,
    BranchStepRecord,
    GenerateStepRecord,
    InputDefinition,
    InputType,
    LoopStepRecord,
    PythonStepRecord,
    StepRecord,
    SubWorkflowStepRecord,
    ValidateStepRecord,
    ValidationError,
    ValidationResult,
    ValidationWarning,
)
from maverick.dsl.types import StepType

# =============================================================================
# InputType Tests
# =============================================================================


class TestInputType:
    """Test suite for InputType enum."""

    def test_all_enum_values_exist(self) -> None:
        """Test that all expected enum values are defined."""
        assert hasattr(InputType, "STRING")
        assert hasattr(InputType, "INTEGER")
        assert hasattr(InputType, "BOOLEAN")
        assert hasattr(InputType, "FLOAT")
        assert hasattr(InputType, "OBJECT")
        assert hasattr(InputType, "ARRAY")

    def test_enum_values_are_strings(self) -> None:
        """Test that enum values are strings with expected values."""
        assert InputType.STRING == "string"
        assert InputType.INTEGER == "integer"
        assert InputType.BOOLEAN == "boolean"
        assert InputType.FLOAT == "float"
        assert InputType.OBJECT == "object"
        assert InputType.ARRAY == "array"

    def test_enum_values_match_expected_strings(self) -> None:
        """Test that .value attribute returns expected strings."""
        assert InputType.STRING.value == "string"
        assert InputType.INTEGER.value == "integer"
        assert InputType.BOOLEAN.value == "boolean"
        assert InputType.FLOAT.value == "float"
        assert InputType.OBJECT.value == "object"
        assert InputType.ARRAY.value == "array"

    def test_can_use_in_fstrings(self) -> None:
        """Test that enum values work correctly in f-strings."""
        input_type = InputType.STRING
        result = f"Input type: {input_type}"
        # StrEnum format varies by Python version:
        # - Python 3.10: returns the value ("string")
        # - Python 3.11+: returns "ClassName.MEMBER_NAME"
        assert "string" in result.lower()

        # Test with .value explicitly to get the string value
        result_explicit = f"Input type: {input_type.value}"
        assert result_explicit == "Input type: string"

    def test_can_use_in_comparisons(self) -> None:
        """Test that enum values work in equality comparisons."""
        assert InputType.STRING == InputType.STRING
        assert InputType.STRING != InputType.INTEGER

        # Test comparison with string values
        assert InputType.STRING == "string"
        assert InputType.INTEGER == "integer"
        assert InputType.STRING != "integer"

    def test_enum_iteration(self) -> None:
        """Test that all enum values can be iterated."""
        all_types = list(InputType)
        assert len(all_types) == 6
        assert InputType.STRING in all_types
        assert InputType.INTEGER in all_types
        assert InputType.BOOLEAN in all_types
        assert InputType.FLOAT in all_types
        assert InputType.OBJECT in all_types
        assert InputType.ARRAY in all_types

    def test_enum_membership(self) -> None:
        """Test enum membership checks."""
        assert "string" in InputType._value2member_map_
        assert "integer" in InputType._value2member_map_
        assert "boolean" in InputType._value2member_map_
        assert "float" in InputType._value2member_map_
        assert "object" in InputType._value2member_map_
        assert "array" in InputType._value2member_map_
        assert "invalid" not in InputType._value2member_map_

    def test_enum_from_string_value(self) -> None:
        """Test creating enum instances from string values."""
        assert InputType("string") == InputType.STRING
        assert InputType("integer") == InputType.INTEGER
        assert InputType("boolean") == InputType.BOOLEAN
        assert InputType("float") == InputType.FLOAT
        assert InputType("object") == InputType.OBJECT
        assert InputType("array") == InputType.ARRAY

    def test_invalid_enum_value_raises_error(self) -> None:
        """Test that invalid enum values raise ValueError."""
        with pytest.raises(ValueError):
            InputType("invalid")

    def test_enum_is_hashable(self) -> None:
        """Test that enum values can be used as dict keys."""
        mapping = {
            InputType.STRING: "String type",
            InputType.INTEGER: "Integer type",
            InputType.BOOLEAN: "Boolean type",
        }
        assert mapping[InputType.STRING] == "String type"
        assert mapping[InputType.INTEGER] == "Integer type"
        assert mapping[InputType.BOOLEAN] == "Boolean type"


# =============================================================================
# InputDefinition Tests
# =============================================================================


class TestInputDefinition:
    """Test suite for InputDefinition model."""

    def test_minimal_required_input(self) -> None:
        """Test creating a minimal required input definition."""
        input_def = InputDefinition(type=InputType.STRING)
        assert input_def.type == InputType.STRING
        assert input_def.required is True
        assert input_def.default is None
        assert input_def.description == ""

    def test_minimal_optional_input_with_default(self) -> None:
        """Test creating an optional input with a default value."""
        input_def = InputDefinition(
            type=InputType.STRING, required=False, default="default_value"
        )
        assert input_def.type == InputType.STRING
        assert input_def.required is False
        assert input_def.default == "default_value"
        assert input_def.description == ""

    def test_full_input_definition(self) -> None:
        """Test creating a complete input definition with all fields."""
        input_def = InputDefinition(
            type=InputType.INTEGER,
            required=False,
            default=42,
            description="The answer to everything",
        )
        assert input_def.type == InputType.INTEGER
        assert input_def.required is False
        assert input_def.default == 42
        assert input_def.description == "The answer to everything"

    def test_string_type_with_default(self) -> None:
        """Test string input with default value."""
        input_def = InputDefinition(
            type=InputType.STRING, required=False, default="hello"
        )
        assert input_def.type == InputType.STRING
        assert input_def.default == "hello"

    def test_integer_type_with_default(self) -> None:
        """Test integer input with default value."""
        input_def = InputDefinition(type=InputType.INTEGER, required=False, default=123)
        assert input_def.type == InputType.INTEGER
        assert input_def.default == 123

    def test_boolean_type_with_default(self) -> None:
        """Test boolean input with default value."""
        input_def = InputDefinition(
            type=InputType.BOOLEAN, required=False, default=True
        )
        assert input_def.type == InputType.BOOLEAN
        assert input_def.default is True

    def test_float_type_with_default(self) -> None:
        """Test float input with default value."""
        input_def = InputDefinition(type=InputType.FLOAT, required=False, default=3.14)
        assert input_def.type == InputType.FLOAT
        assert input_def.default == 3.14

    def test_object_type_with_default(self) -> None:
        """Test object input with default value."""
        default_obj = {"key": "value", "nested": {"data": 123}}
        input_def = InputDefinition(
            type=InputType.OBJECT, required=False, default=default_obj
        )
        assert input_def.type == InputType.OBJECT
        assert input_def.default == default_obj

    def test_array_type_with_default(self) -> None:
        """Test array input with default value."""
        default_array = [1, 2, 3, "four", {"five": 5}]
        input_def = InputDefinition(
            type=InputType.ARRAY, required=False, default=default_array
        )
        assert input_def.type == InputType.ARRAY
        assert input_def.default == default_array

    def test_required_true_with_none_default_is_valid(self) -> None:
        """Test that required=True with default=None is valid."""
        input_def = InputDefinition(type=InputType.STRING, required=True, default=None)
        assert input_def.required is True
        assert input_def.default is None

    def test_required_true_with_explicit_default_raises_error(self) -> None:
        """Test that required=True with non-None default raises ValidationError."""
        with pytest.raises(PydanticValidationError) as exc_info:
            InputDefinition(type=InputType.STRING, required=True, default="not_allowed")

        # Check that the error message mentions the validation issue
        error_msg = str(exc_info.value)
        assert "Required inputs cannot have default values" in error_msg

    def test_required_true_with_integer_default_raises_error(self) -> None:
        """Test that required=True with integer default raises ValidationError."""
        with pytest.raises(PydanticValidationError) as exc_info:
            InputDefinition(type=InputType.INTEGER, required=True, default=42)

        error_msg = str(exc_info.value)
        assert "Required inputs cannot have default values" in error_msg

    def test_required_true_with_boolean_default_raises_error(self) -> None:
        """Test that required=True with boolean default raises ValidationError."""
        with pytest.raises(PydanticValidationError) as exc_info:
            InputDefinition(type=InputType.BOOLEAN, required=True, default=False)

        error_msg = str(exc_info.value)
        assert "Required inputs cannot have default values" in error_msg

    def test_required_true_with_empty_string_default_raises_error(self) -> None:
        """Test that required=True with empty string default raises ValidationError."""
        with pytest.raises(PydanticValidationError) as exc_info:
            InputDefinition(type=InputType.STRING, required=True, default="")

        error_msg = str(exc_info.value)
        assert "Required inputs cannot have default values" in error_msg

    def test_required_true_with_zero_default_raises_error(self) -> None:
        """Test that required=True with zero default raises ValidationError."""
        with pytest.raises(PydanticValidationError) as exc_info:
            InputDefinition(type=InputType.INTEGER, required=True, default=0)

        error_msg = str(exc_info.value)
        assert "Required inputs cannot have default values" in error_msg

    def test_required_true_with_empty_array_default_raises_error(self) -> None:
        """Test that required=True with empty array default raises ValidationError."""
        with pytest.raises(PydanticValidationError) as exc_info:
            InputDefinition(type=InputType.ARRAY, required=True, default=[])

        error_msg = str(exc_info.value)
        assert "Required inputs cannot have default values" in error_msg

    def test_required_true_with_empty_object_default_raises_error(self) -> None:
        """Test that required=True with empty object default raises ValidationError."""
        with pytest.raises(PydanticValidationError) as exc_info:
            InputDefinition(type=InputType.OBJECT, required=True, default={})

        error_msg = str(exc_info.value)
        assert "Required inputs cannot have default values" in error_msg

    def test_optional_input_without_default_is_valid(self) -> None:
        """Test that required=False without a default is valid."""
        input_def = InputDefinition(type=InputType.STRING, required=False)
        assert input_def.required is False
        assert input_def.default is None

    def test_can_create_from_dict(self) -> None:
        """Test creating InputDefinition from a dictionary."""
        data = {
            "type": "string",
            "required": False,
            "default": "test",
            "description": "A test input",
        }
        input_def = InputDefinition(**data)
        assert input_def.type == InputType.STRING
        assert input_def.required is False
        assert input_def.default == "test"
        assert input_def.description == "A test input"

    def test_can_serialize_to_dict(self) -> None:
        """Test serializing InputDefinition to a dictionary."""
        input_def = InputDefinition(
            type=InputType.INTEGER,
            required=False,
            default=100,
            description="Count",
        )
        data = input_def.model_dump()
        assert data["type"] == InputType.INTEGER
        assert data["required"] is False
        assert data["default"] == 100
        assert data["description"] == "Count"

    def test_can_serialize_to_json(self) -> None:
        """Test serializing InputDefinition to JSON."""
        input_def = InputDefinition(
            type=InputType.BOOLEAN,
            required=False,
            default=True,
            description="Enable feature",
        )
        json_str = input_def.model_dump_json()
        assert "boolean" in json_str
        assert "true" in json_str.lower()
        assert "Enable feature" in json_str

    def test_type_field_is_required(self) -> None:
        """Test that type field is required."""
        with pytest.raises(PydanticValidationError) as exc_info:
            InputDefinition(required=False, default="test")  # type: ignore

        error_msg = str(exc_info.value)
        assert "type" in error_msg.lower()

    def test_invalid_type_value_raises_error(self) -> None:
        """Test that invalid type values raise ValidationError."""
        with pytest.raises(PydanticValidationError):
            InputDefinition(type="invalid_type")  # type: ignore

    def test_description_defaults_to_empty_string(self) -> None:
        """Test that description defaults to empty string when not provided."""
        input_def = InputDefinition(type=InputType.STRING)
        assert input_def.description == ""

    def test_description_can_be_multiline(self) -> None:
        """Test that description can contain multiline text."""
        description = """This is a multiline
        description that spans
        multiple lines."""
        input_def = InputDefinition(type=InputType.STRING, description=description)
        assert input_def.description == description

    def test_default_can_be_complex_object(self) -> None:
        """Test that default can be a complex nested object."""
        complex_default = {
            "level1": {"level2": {"level3": ["a", "b", "c"], "number": 123}},
            "items": [1, 2, {"key": "value"}],
        }
        input_def = InputDefinition(
            type=InputType.OBJECT, required=False, default=complex_default
        )
        assert input_def.default == complex_default

    def test_default_can_be_nested_array(self) -> None:
        """Test that default can be a nested array."""
        nested_array = [
            [1, 2, 3],
            ["a", "b", "c"],
            [{"key": "value"}, {"other": 123}],
        ]
        input_def = InputDefinition(
            type=InputType.ARRAY, required=False, default=nested_array
        )
        assert input_def.default == nested_array

    def test_boolean_false_default_is_allowed(self) -> None:
        """Test that False is a valid default for boolean inputs."""
        input_def = InputDefinition(
            type=InputType.BOOLEAN, required=False, default=False
        )
        assert input_def.default is False
        assert input_def.default is not None

    def test_zero_default_is_allowed_when_optional(self) -> None:
        """Test that 0 is a valid default for numeric inputs when optional."""
        input_def = InputDefinition(type=InputType.INTEGER, required=False, default=0)
        assert input_def.default == 0

    def test_empty_string_default_is_allowed_when_optional(self) -> None:
        """Test that empty string is a valid default when optional."""
        input_def = InputDefinition(type=InputType.STRING, required=False, default="")
        assert input_def.default == ""

    def test_empty_collection_defaults_are_allowed_when_optional(self) -> None:
        """Test that empty collections are valid defaults when optional."""
        # Empty array
        input_def_array = InputDefinition(
            type=InputType.ARRAY, required=False, default=[]
        )
        assert input_def_array.default == []

        # Empty object
        input_def_object = InputDefinition(
            type=InputType.OBJECT, required=False, default={}
        )
        assert input_def_object.default == {}

    def test_model_equality(self) -> None:
        """Test that InputDefinition instances can be compared for equality."""
        input_def1 = InputDefinition(
            type=InputType.STRING,
            required=False,
            default="test",
            description="A test",
        )
        input_def2 = InputDefinition(
            type=InputType.STRING,
            required=False,
            default="test",
            description="A test",
        )
        input_def3 = InputDefinition(
            type=InputType.STRING,
            required=False,
            default="different",
            description="A test",
        )

        assert input_def1 == input_def2
        assert input_def1 != input_def3

    def test_model_immutability_via_copy(self) -> None:
        """Test that InputDefinition can be safely copied."""
        original = InputDefinition(
            type=InputType.OBJECT, required=False, default={"key": "value"}
        )
        copied = original.model_copy()

        assert original == copied
        assert original is not copied

    def test_type_coercion_from_string(self) -> None:
        """Test that type field accepts string values and coerces to enum."""
        input_def = InputDefinition(type="string")  # type: ignore
        assert input_def.type == InputType.STRING
        assert isinstance(input_def.type, InputType)


# =============================================================================
# ValidationError Tests
# =============================================================================


class TestValidationError:
    """Tests for ValidationError dataclass."""

    def test_create_validation_error_with_all_fields(self):
        """Test creating a ValidationError with all fields."""
        error = ValidationError(
            code="E001",
            message="Invalid step type",
            path="steps[0].type",
            suggestion=(
                "Use one of: python, agent, generate, validate, "
                "subworkflow, branch, parallel"
            ),
        )

        assert error.code == "E001"
        assert error.message == "Invalid step type"
        assert error.path == "steps[0].type"
        assert error.suggestion == (
            "Use one of: python, agent, generate, validate, "
            "subworkflow, branch, parallel"
        )

    def test_create_validation_error_without_suggestion(self):
        """Test creating a ValidationError without optional suggestion."""
        error = ValidationError(
            code="E002",
            message="Missing required field",
            path="steps[1].agent",
        )

        assert error.code == "E002"
        assert error.message == "Missing required field"
        assert error.path == "steps[1].agent"
        assert error.suggestion == ""

    def test_validation_error_is_immutable(self):
        """Test that ValidationError is frozen (immutable)."""
        error = ValidationError(
            code="E003",
            message="Test error",
            path="test.path",
        )

        with pytest.raises(AttributeError, match="cannot assign to field"):
            error.code = "E999"

        with pytest.raises(AttributeError, match="cannot assign to field"):
            error.message = "Modified message"

        with pytest.raises(AttributeError, match="cannot assign to field"):
            error.path = "modified.path"

        with pytest.raises(AttributeError, match="cannot assign to field"):
            error.suggestion = "Modified suggestion"

    def test_validation_error_equality(self):
        """Test that ValidationError instances are comparable."""
        error1 = ValidationError(
            code="E001",
            message="Test error",
            path="test.path",
            suggestion="Fix it",
        )
        error2 = ValidationError(
            code="E001",
            message="Test error",
            path="test.path",
            suggestion="Fix it",
        )
        error3 = ValidationError(
            code="E002",
            message="Different error",
            path="test.path",
        )

        assert error1 == error2
        assert error1 != error3

    def test_validation_error_hashable(self):
        """Test that ValidationError is hashable (can be used in sets/dicts)."""
        error1 = ValidationError(
            code="E001",
            message="Test error",
            path="test.path",
        )
        error2 = ValidationError(
            code="E002",
            message="Another error",
            path="test.path",
        )

        # Should be able to add to a set
        error_set = {error1, error2}
        assert len(error_set) == 2
        assert error1 in error_set
        assert error2 in error_set

    def test_validation_error_repr(self):
        """Test ValidationError string representation."""
        error = ValidationError(
            code="E001",
            message="Test error",
            path="test.path",
            suggestion="Fix suggestion",
        )

        repr_str = repr(error)
        assert "ValidationError" in repr_str
        assert "E001" in repr_str
        assert "Test error" in repr_str


# =============================================================================
# ValidationWarning Tests
# =============================================================================


class TestValidationWarning:
    """Tests for ValidationWarning dataclass."""

    def test_create_validation_warning(self):
        """Test creating a ValidationWarning."""
        warning = ValidationWarning(
            code="W001",
            message="Unused input parameter",
            path="inputs.unused_param",
        )

        assert warning.code == "W001"
        assert warning.message == "Unused input parameter"
        assert warning.path == "inputs.unused_param"

    def test_validation_warning_is_immutable(self):
        """Test that ValidationWarning is frozen (immutable)."""
        warning = ValidationWarning(
            code="W001",
            message="Test warning",
            path="test.path",
        )

        with pytest.raises(AttributeError, match="cannot assign to field"):
            warning.code = "W999"

        with pytest.raises(AttributeError, match="cannot assign to field"):
            warning.message = "Modified message"

        with pytest.raises(AttributeError, match="cannot assign to field"):
            warning.path = "modified.path"

    def test_validation_warning_equality(self):
        """Test that ValidationWarning instances are comparable."""
        warning1 = ValidationWarning(
            code="W001",
            message="Test warning",
            path="test.path",
        )
        warning2 = ValidationWarning(
            code="W001",
            message="Test warning",
            path="test.path",
        )
        warning3 = ValidationWarning(
            code="W002",
            message="Different warning",
            path="test.path",
        )

        assert warning1 == warning2
        assert warning1 != warning3

    def test_validation_warning_hashable(self):
        """Test that ValidationWarning is hashable (can be used in sets/dicts)."""
        warning1 = ValidationWarning(
            code="W001",
            message="Test warning",
            path="test.path",
        )
        warning2 = ValidationWarning(
            code="W002",
            message="Another warning",
            path="test.path",
        )

        # Should be able to add to a set
        warning_set = {warning1, warning2}
        assert len(warning_set) == 2
        assert warning1 in warning_set
        assert warning2 in warning_set

    def test_validation_warning_repr(self):
        """Test ValidationWarning string representation."""
        warning = ValidationWarning(
            code="W001",
            message="Test warning",
            path="test.path",
        )

        repr_str = repr(warning)
        assert "ValidationWarning" in repr_str
        assert "W001" in repr_str
        assert "Test warning" in repr_str


# =============================================================================
# ValidationResult Tests
# =============================================================================


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_create_valid_result_empty(self):
        """Test creating a valid ValidationResult with no errors or warnings."""
        result = ValidationResult(
            valid=True,
            errors=(),
            warnings=(),
        )

        assert result.valid is True
        assert result.errors == ()
        assert result.warnings == ()
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_create_valid_result_with_warnings(self):
        """Test creating a valid ValidationResult with warnings but no errors."""
        warning1 = ValidationWarning(
            code="W001",
            message="Unused input",
            path="inputs.param1",
        )
        warning2 = ValidationWarning(
            code="W002",
            message="Deprecated syntax",
            path="steps[0].action",
        )

        result = ValidationResult(
            valid=True,
            errors=(),
            warnings=(warning1, warning2),
        )

        assert result.valid is True
        assert result.errors == ()
        assert len(result.warnings) == 2
        assert result.warnings[0] == warning1
        assert result.warnings[1] == warning2

    def test_create_invalid_result_with_errors(self):
        """Test creating an invalid ValidationResult with errors."""
        error1 = ValidationError(
            code="E001",
            message="Missing required field",
            path="steps[0].agent",
            suggestion="Add the 'agent' field",
        )
        error2 = ValidationError(
            code="E002",
            message="Invalid type",
            path="steps[1].type",
        )

        result = ValidationResult(
            valid=False,
            errors=(error1, error2),
            warnings=(),
        )

        assert result.valid is False
        assert len(result.errors) == 2
        assert result.errors[0] == error1
        assert result.errors[1] == error2
        assert result.warnings == ()

    def test_create_invalid_result_with_errors_and_warnings(self):
        """Test creating an invalid ValidationResult with both errors and warnings."""
        error = ValidationError(
            code="E001",
            message="Invalid configuration",
            path="inputs.config",
        )
        warning = ValidationWarning(
            code="W001",
            message="Consider updating",
            path="version",
        )

        result = ValidationResult(
            valid=False,
            errors=(error,),
            warnings=(warning,),
        )

        assert result.valid is False
        assert len(result.errors) == 1
        assert len(result.warnings) == 1
        assert result.errors[0] == error
        assert result.warnings[0] == warning

    def test_validation_result_is_immutable(self):
        """Test that ValidationResult is frozen (immutable)."""
        result = ValidationResult(
            valid=True,
            errors=(),
            warnings=(),
        )

        with pytest.raises(AttributeError, match="cannot assign to field"):
            result.valid = False

        with pytest.raises(AttributeError, match="cannot assign to field"):
            result.errors = (ValidationError("E001", "Error", "path"),)

        with pytest.raises(AttributeError, match="cannot assign to field"):
            result.warnings = (ValidationWarning("W001", "Warning", "path"),)

    def test_validation_result_tuples_are_immutable(self):
        """Test that errors and warnings tuples cannot be modified."""
        error = ValidationError(
            code="E001",
            message="Test error",
            path="test.path",
        )
        result = ValidationResult(
            valid=False,
            errors=(error,),
            warnings=(),
        )

        # Tuples are immutable
        with pytest.raises(TypeError):
            result.errors[0] = ValidationError("E002", "Different", "path")

        with pytest.raises(AttributeError):
            result.errors.append(error)

    def test_validation_result_equality(self):
        """Test that ValidationResult instances are comparable."""
        error = ValidationError(
            code="E001",
            message="Test error",
            path="test.path",
        )
        warning = ValidationWarning(
            code="W001",
            message="Test warning",
            path="test.path",
        )

        result1 = ValidationResult(
            valid=False,
            errors=(error,),
            warnings=(warning,),
        )
        result2 = ValidationResult(
            valid=False,
            errors=(error,),
            warnings=(warning,),
        )
        result3 = ValidationResult(
            valid=True,
            errors=(),
            warnings=(warning,),
        )

        assert result1 == result2
        assert result1 != result3

    def test_validation_result_hashable(self):
        """Test that ValidationResult is hashable (can be used in sets/dicts)."""
        result1 = ValidationResult(
            valid=True,
            errors=(),
            warnings=(),
        )
        result2 = ValidationResult(
            valid=False,
            errors=(ValidationError("E001", "Error", "path"),),
            warnings=(),
        )

        # Should be able to add to a set
        result_set = {result1, result2}
        assert len(result_set) == 2
        assert result1 in result_set
        assert result2 in result_set

    def test_validation_result_repr(self):
        """Test ValidationResult string representation."""
        error = ValidationError(
            code="E001",
            message="Test error",
            path="test.path",
        )
        result = ValidationResult(
            valid=False,
            errors=(error,),
            warnings=(),
        )

        repr_str = repr(result)
        assert "ValidationResult" in repr_str
        assert "valid=False" in repr_str

    def test_validation_result_empty_tuples(self):
        """Test that empty tuples work correctly for errors and warnings."""
        result = ValidationResult(
            valid=True,
            errors=(),
            warnings=(),
        )

        # Empty tuples should be falsy in boolean context
        assert not result.errors
        assert not result.warnings

        # But should still be tuples
        assert isinstance(result.errors, tuple)
        assert isinstance(result.warnings, tuple)


# =============================================================================
# StepRecord Base Class Tests
# =============================================================================


class TestStepRecordBase:
    """Test StepRecord base class validation."""

    def test_valid_base_step(self):
        """Test creating a valid base StepRecord."""
        step = StepRecord(name="test_step", type=StepType.PYTHON)
        assert step.name == "test_step"
        assert step.type == StepType.PYTHON
        assert step.when is None

    def test_step_with_condition(self):
        """Test StepRecord with when condition."""
        step = StepRecord(
            name="conditional_step",
            type=StepType.AGENT,
            when="state.some_var == true",
        )
        assert step.when == "state.some_var == true"

    def test_empty_name_fails(self):
        """Test that empty step name raises validation error."""
        # Pydantic's min_length validator fires before our custom validator
        with pytest.raises(Exception, match="String should have at least 1 character"):
            StepRecord(name="", type=StepType.PYTHON)

    def test_whitespace_name_fails(self):
        """Test that whitespace-only step name raises validation error."""
        with pytest.raises(Exception, match="Step name cannot be empty"):
            StepRecord(name="   ", type=StepType.PYTHON)

    def test_missing_name_fails(self):
        """Test that missing name raises validation error."""
        with pytest.raises(Exception):
            StepRecord(type=StepType.PYTHON)

    def test_missing_type_fails(self):
        """Test that missing type raises validation error."""
        with pytest.raises(Exception):
            StepRecord(name="test")


# =============================================================================
# PythonStepRecord Tests
# =============================================================================


class TestPythonStepRecord:
    """Test PythonStepRecord model."""

    def test_minimal_python_step(self):
        """Test minimal PythonStepRecord with only action."""
        step = PythonStepRecord(name="run_python", action="my_module.my_function")
        assert step.name == "run_python"
        assert step.type == StepType.PYTHON
        assert step.action == "my_module.my_function"
        assert step.args == []
        assert step.kwargs == {}

    def test_python_step_with_args(self):
        """Test PythonStepRecord with positional arguments."""
        step = PythonStepRecord(
            name="run_with_args",
            action="my_function",
            args=["arg1", 42, True],
        )
        assert step.args == ["arg1", 42, True]

    def test_python_step_with_kwargs(self):
        """Test PythonStepRecord with keyword arguments."""
        step = PythonStepRecord(
            name="run_with_kwargs",
            action="my_function",
            kwargs={"key1": "value1", "key2": 123},
        )
        assert step.kwargs == {"key1": "value1", "key2": 123}

    def test_python_step_with_args_and_kwargs(self):
        """Test PythonStepRecord with both args and kwargs."""
        step = PythonStepRecord(
            name="run_full",
            action="my_function",
            args=["positional"],
            kwargs={"keyword": "value"},
        )
        assert step.args == ["positional"]
        assert step.kwargs == {"keyword": "value"}

    def test_python_step_with_expression_args(self):
        """Test PythonStepRecord with expression in arguments."""
        step = PythonStepRecord(
            name="run_expr",
            action="my_function",
            args=["${state.var1}"],
            kwargs={"key": "${inputs.param}"},
        )
        assert step.args == ["${state.var1}"]
        assert step.kwargs == {"key": "${inputs.param}"}

    def test_empty_action_fails(self):
        """Test that empty action raises validation error."""
        with pytest.raises(Exception):
            PythonStepRecord(name="test", action="")


# =============================================================================
# AgentStepRecord Tests
# =============================================================================


class TestAgentStepRecord:
    """Test AgentStepRecord model."""

    def test_minimal_agent_step(self):
        """Test minimal AgentStepRecord with only agent name."""
        step = AgentStepRecord(name="run_agent", agent="code_reviewer")
        assert step.name == "run_agent"
        assert step.type == StepType.AGENT
        assert step.agent == "code_reviewer"
        assert step.context == {}

    def test_agent_step_with_dict_context(self):
        """Test AgentStepRecord with dictionary context."""
        step = AgentStepRecord(
            name="review",
            agent="code_reviewer",
            context={"files": ["a.py", "b.py"], "severity": "high"},
        )
        assert step.context == {"files": ["a.py", "b.py"], "severity": "high"}

    def test_agent_step_with_context_builder(self):
        """Test AgentStepRecord with context builder name."""
        step = AgentStepRecord(
            name="review",
            agent="code_reviewer",
            context="review_context_builder",
        )
        assert step.context == "review_context_builder"

    def test_empty_agent_fails(self):
        """Test that empty agent name raises validation error."""
        with pytest.raises(Exception):
            AgentStepRecord(name="test", agent="")


# =============================================================================
# GenerateStepRecord Tests
# =============================================================================


class TestGenerateStepRecord:
    """Test GenerateStepRecord model."""

    def test_minimal_generate_step(self):
        """Test minimal GenerateStepRecord with only generator name."""
        step = GenerateStepRecord(name="gen_docs", generator="doc_generator")
        assert step.name == "gen_docs"
        assert step.type == StepType.GENERATE
        assert step.generator == "doc_generator"
        assert step.context == {}

    def test_generate_step_with_dict_context(self):
        """Test GenerateStepRecord with dictionary context."""
        step = GenerateStepRecord(
            name="gen",
            generator="pr_body_generator",
            context={"changes": ["feat1", "feat2"]},
        )
        assert step.context == {"changes": ["feat1", "feat2"]}

    def test_generate_step_with_context_builder(self):
        """Test GenerateStepRecord with context builder name."""
        step = GenerateStepRecord(
            name="gen",
            generator="pr_body_generator",
            context="pr_context_builder",
        )
        assert step.context == "pr_context_builder"

    def test_empty_generator_fails(self):
        """Test that empty generator name raises validation error."""
        with pytest.raises(Exception):
            GenerateStepRecord(name="test", generator="")


# =============================================================================
# ValidateStepRecord Tests
# =============================================================================


class TestValidateStepRecord:
    """Test ValidateStepRecord model."""

    def test_minimal_validate_step(self):
        """Test minimal ValidateStepRecord with stage list."""
        step = ValidateStepRecord(
            name="validate",
            stages=["lint", "test"],
        )
        assert step.name == "validate"
        assert step.type == StepType.VALIDATE
        assert step.stages == ["lint", "test"]
        assert step.retry == 3  # default
        assert step.on_failure is None

    def test_validate_step_with_config_key(self):
        """Test ValidateStepRecord with config key for stages."""
        step = ValidateStepRecord(
            name="validate",
            stages="validation_config",
        )
        assert step.stages == "validation_config"

    def test_validate_step_with_custom_retry(self):
        """Test ValidateStepRecord with custom retry count."""
        step = ValidateStepRecord(
            name="validate",
            stages=["lint"],
            retry=5,
        )
        assert step.retry == 5

    def test_validate_step_with_zero_retry(self):
        """Test ValidateStepRecord with retry disabled."""
        step = ValidateStepRecord(
            name="validate",
            stages=["lint"],
            retry=0,
        )
        assert step.retry == 0

    def test_validate_step_with_on_failure(self):
        """Test ValidateStepRecord with on_failure step."""
        failure_step = PythonStepRecord(
            name="fix_issues",
            action="auto_fix",
        )
        step = ValidateStepRecord(
            name="validate",
            stages=["lint"],
            on_failure=failure_step,
        )
        assert step.on_failure == failure_step
        assert step.on_failure.name == "fix_issues"

    def test_negative_retry_fails(self):
        """Test that negative retry count raises validation error."""
        with pytest.raises(Exception):
            ValidateStepRecord(
                name="validate",
                stages=["lint"],
                retry=-1,
            )


# =============================================================================
# SubWorkflowStepRecord Tests
# =============================================================================


class TestSubWorkflowStepRecord:
    """Test SubWorkflowStepRecord model."""

    def test_minimal_subworkflow_step(self):
        """Test minimal SubWorkflowStepRecord with only workflow name."""
        step = SubWorkflowStepRecord(
            name="run_sub",
            workflow="nested_workflow",
        )
        assert step.name == "run_sub"
        assert step.type == StepType.SUBWORKFLOW
        assert step.workflow == "nested_workflow"
        assert step.inputs == {}

    def test_subworkflow_step_with_inputs(self):
        """Test SubWorkflowStepRecord with input values."""
        step = SubWorkflowStepRecord(
            name="run_sub",
            workflow="nested_workflow",
            inputs={"param1": "value1", "param2": 42},
        )
        assert step.inputs == {"param1": "value1", "param2": 42}

    def test_subworkflow_step_with_expression_inputs(self):
        """Test SubWorkflowStepRecord with expression inputs."""
        step = SubWorkflowStepRecord(
            name="run_sub",
            workflow="nested_workflow",
            inputs={"param": "${state.value}"},
        )
        assert step.inputs == {"param": "${state.value}"}

    def test_empty_workflow_fails(self):
        """Test that empty workflow name raises validation error."""
        with pytest.raises(Exception):
            SubWorkflowStepRecord(name="test", workflow="")


# =============================================================================
# BranchOptionRecord Tests
# =============================================================================


class TestBranchOptionRecord:
    """Test BranchOptionRecord model."""

    def test_valid_branch_option(self):
        """Test creating a valid BranchOptionRecord."""
        step = PythonStepRecord(name="do_something", action="func")
        option = BranchOptionRecord(when="state.x > 10", step=step)
        assert option.when == "state.x > 10"
        assert option.step == step

    def test_branch_option_with_nested_step(self):
        """Test BranchOptionRecord with different step types."""
        agent_step = AgentStepRecord(name="run_agent", agent="reviewer")
        option = BranchOptionRecord(when="state.needs_review", step=agent_step)
        assert option.step.type == StepType.AGENT

    def test_empty_when_fails(self):
        """Test that empty when condition raises validation error."""
        step = PythonStepRecord(name="do_something", action="func")
        with pytest.raises(Exception):
            BranchOptionRecord(when="", step=step)


# =============================================================================
# BranchStepRecord Tests
# =============================================================================


class TestBranchStepRecord:
    """Test BranchStepRecord model."""

    def test_minimal_branch_step(self):
        """Test minimal BranchStepRecord with single option."""
        option = BranchOptionRecord(
            when="state.x > 0",
            step=PythonStepRecord(name="positive", action="handle_positive"),
        )
        step = BranchStepRecord(name="branch", options=[option])
        assert step.name == "branch"
        assert step.type == StepType.BRANCH
        assert len(step.options) == 1
        assert step.options[0].when == "state.x > 0"

    def test_branch_step_with_multiple_options(self):
        """Test BranchStepRecord with multiple options."""
        options = [
            BranchOptionRecord(
                when="state.x > 0",
                step=PythonStepRecord(name="positive", action="handle_positive"),
            ),
            BranchOptionRecord(
                when="state.x < 0",
                step=PythonStepRecord(name="negative", action="handle_negative"),
            ),
            BranchOptionRecord(
                when="state.x == 0",
                step=PythonStepRecord(name="zero", action="handle_zero"),
            ),
        ]
        step = BranchStepRecord(name="branch", options=options)
        assert len(step.options) == 3
        assert step.options[0].step.name == "positive"
        assert step.options[1].step.name == "negative"
        assert step.options[2].step.name == "zero"

    def test_branch_step_with_nested_agent(self):
        """Test BranchStepRecord with agent step in option."""
        option = BranchOptionRecord(
            when="state.needs_review",
            step=AgentStepRecord(name="review", agent="code_reviewer"),
        )
        step = BranchStepRecord(name="branch", options=[option])
        assert step.options[0].step.type == StepType.AGENT

    def test_branch_step_with_nested_branch(self):
        """Test BranchStepRecord with nested branch step."""
        inner_option = BranchOptionRecord(
            when="state.y > 0",
            step=PythonStepRecord(name="inner", action="inner_func"),
        )
        inner_branch = BranchStepRecord(name="inner_branch", options=[inner_option])
        outer_option = BranchOptionRecord(
            when="state.x > 0",
            step=inner_branch,
        )
        outer_step = BranchStepRecord(name="outer_branch", options=[outer_option])

        assert outer_step.options[0].step.type == StepType.BRANCH
        nested_branch = outer_step.options[0].step
        assert isinstance(nested_branch, BranchStepRecord)
        assert nested_branch.name == "inner_branch"

    def test_empty_options_fails(self):
        """Test that empty options list raises validation error."""
        with pytest.raises(Exception):
            BranchStepRecord(name="branch", options=[])


# =============================================================================
# LoopStepRecord Tests
# =============================================================================


class TestLoopStepRecord:
    """Test LoopStepRecord model."""

    def test_minimal_loop_step(self):
        """Test minimal LoopStepRecord with single step."""
        steps = [PythonStepRecord(name="task1", action="func1")]
        step = LoopStepRecord(name="parallel", steps=steps)
        assert step.name == "parallel"
        assert step.type == StepType.LOOP
        assert len(step.steps) == 1
        assert step.steps[0].name == "task1"

    def test_loop_step_with_multiple_steps(self):
        """Test LoopStepRecord with multiple steps."""
        steps = [
            PythonStepRecord(name="task1", action="func1"),
            PythonStepRecord(name="task2", action="func2"),
            AgentStepRecord(name="task3", agent="reviewer"),
        ]
        step = LoopStepRecord(name="parallel", steps=steps)
        assert len(step.steps) == 3
        assert step.steps[0].type == StepType.PYTHON
        assert step.steps[1].type == StepType.PYTHON
        assert step.steps[2].type == StepType.AGENT

    def test_loop_step_with_nested_parallel(self):
        """Test LoopStepRecord with nested parallel step."""
        inner_steps = [
            PythonStepRecord(name="inner1", action="func1"),
            PythonStepRecord(name="inner2", action="func2"),
        ]
        inner_parallel = LoopStepRecord(name="inner_parallel", steps=inner_steps)
        outer_steps = [
            inner_parallel,
            PythonStepRecord(name="outer_task", action="func3"),
        ]
        outer_step = LoopStepRecord(name="outer_parallel", steps=outer_steps)

        assert len(outer_step.steps) == 2
        assert outer_step.steps[0].type == StepType.LOOP
        nested_parallel = outer_step.steps[0]
        assert isinstance(nested_parallel, LoopStepRecord)
        assert len(nested_parallel.steps) == 2

    def test_duplicate_step_names_fails(self):
        """Test that duplicate step names raise validation error."""
        steps = [
            PythonStepRecord(name="task", action="func1"),
            PythonStepRecord(name="task", action="func2"),
        ]
        with pytest.raises(Exception, match="Duplicate step names in loop block"):
            LoopStepRecord(name="loop", steps=steps)

    def test_empty_steps_fails(self):
        """Test that empty steps list raises validation error."""
        with pytest.raises(Exception):
            LoopStepRecord(name="loop", steps=[])

    def test_parallel_true_shorthand(self):
        """Test that parallel: true is valid and sets unlimited concurrency."""
        steps = [PythonStepRecord(name="task1", action="func1")]
        step = LoopStepRecord(name="loop", steps=steps, parallel=True)
        assert step.parallel is True
        assert step.max_concurrency == 1  # Default value preserved
        assert step.get_effective_max_concurrency() == 0  # Resolves to unlimited

    def test_parallel_false_shorthand(self):
        """Test that parallel: false is valid and sets sequential execution."""
        steps = [PythonStepRecord(name="task1", action="func1")]
        step = LoopStepRecord(name="loop", steps=steps, parallel=False)
        assert step.parallel is False
        assert step.max_concurrency == 1  # Default value preserved
        assert step.get_effective_max_concurrency() == 1  # Resolves to sequential

    def test_parallel_none_uses_max_concurrency(self):
        """Test that parallel: None (default) uses max_concurrency."""
        steps = [PythonStepRecord(name="task1", action="func1")]
        step = LoopStepRecord(name="loop", steps=steps, max_concurrency=3)
        assert step.parallel is None
        assert step.max_concurrency == 3
        assert step.get_effective_max_concurrency() == 3

    def test_parallel_and_max_concurrency_mutually_exclusive(self):
        """Test that specifying both parallel and max_concurrency raises error."""
        steps = [PythonStepRecord(name="task1", action="func1")]
        with pytest.raises(
            Exception,
            match="Cannot specify both 'parallel' and 'max_concurrency'",
        ):
            LoopStepRecord(
                name="loop", steps=steps, parallel=True, max_concurrency=3
            )

    def test_parallel_true_with_default_max_concurrency_is_valid(self):
        """Test that parallel: true with default max_concurrency is valid."""
        steps = [PythonStepRecord(name="task1", action="func1")]
        # max_concurrency defaults to 1, so parallel=True should be allowed
        step = LoopStepRecord(name="loop", steps=steps, parallel=True)
        assert step.parallel is True
        assert step.max_concurrency == 1  # Default
        assert step.get_effective_max_concurrency() == 0  # Unlimited

    def test_parallel_false_with_default_max_concurrency_is_valid(self):
        """Test that parallel: false with default max_concurrency is valid."""
        steps = [PythonStepRecord(name="task1", action="func1")]
        step = LoopStepRecord(name="loop", steps=steps, parallel=False)
        assert step.parallel is False
        assert step.max_concurrency == 1
        assert step.get_effective_max_concurrency() == 1  # Sequential

    def test_default_behavior_is_sequential(self):
        """Test default behavior (no parallel, no max_concurrency) is sequential."""
        steps = [PythonStepRecord(name="task1", action="func1")]
        step = LoopStepRecord(name="loop", steps=steps)
        assert step.parallel is None
        assert step.max_concurrency == 1
        assert step.get_effective_max_concurrency() == 1  # Sequential


# =============================================================================
# Discriminated Union Tests
# =============================================================================


class TestStepRecordUnion:
    """Test discriminated union parsing via type field."""

    def test_parse_python_step_from_dict(self):
        """Test parsing dict to PythonStepRecord via type discriminator."""
        data = {
            "name": "run",
            "type": "python",
            "action": "my_func",
        }
        from pydantic import TypeAdapter

        from maverick.dsl.serialization.schema import StepRecordUnion

        adapter = TypeAdapter(StepRecordUnion)
        step = adapter.validate_python(data)
        assert isinstance(step, PythonStepRecord)
        assert step.name == "run"
        assert step.action == "my_func"

    def test_parse_agent_step_from_dict(self):
        """Test parsing dict to AgentStepRecord via type discriminator."""
        data = {
            "name": "review",
            "type": "agent",
            "agent": "code_reviewer",
        }
        from pydantic import TypeAdapter

        from maverick.dsl.serialization.schema import StepRecordUnion

        adapter = TypeAdapter(StepRecordUnion)
        step = adapter.validate_python(data)
        assert isinstance(step, AgentStepRecord)
        assert step.agent == "code_reviewer"

    def test_parse_generate_step_from_dict(self):
        """Test parsing dict to GenerateStepRecord via type discriminator."""
        data = {
            "name": "gen",
            "type": "generate",
            "generator": "doc_gen",
        }
        from pydantic import TypeAdapter

        from maverick.dsl.serialization.schema import StepRecordUnion

        adapter = TypeAdapter(StepRecordUnion)
        step = adapter.validate_python(data)
        assert isinstance(step, GenerateStepRecord)
        assert step.generator == "doc_gen"

    def test_parse_validate_step_from_dict(self):
        """Test parsing dict to ValidateStepRecord via type discriminator."""
        data = {
            "name": "validate",
            "type": "validate",
            "stages": ["lint", "test"],
        }
        from pydantic import TypeAdapter

        from maverick.dsl.serialization.schema import StepRecordUnion

        adapter = TypeAdapter(StepRecordUnion)
        step = adapter.validate_python(data)
        assert isinstance(step, ValidateStepRecord)
        assert step.stages == ["lint", "test"]

    def test_parse_subworkflow_step_from_dict(self):
        """Test parsing dict to SubWorkflowStepRecord via type discriminator."""
        data = {
            "name": "sub",
            "type": "subworkflow",
            "workflow": "nested",
        }
        from pydantic import TypeAdapter

        from maverick.dsl.serialization.schema import StepRecordUnion

        adapter = TypeAdapter(StepRecordUnion)
        step = adapter.validate_python(data)
        assert isinstance(step, SubWorkflowStepRecord)
        assert step.workflow == "nested"

    def test_parse_branch_step_from_dict(self):
        """Test parsing dict to BranchStepRecord via type discriminator."""
        data = {
            "name": "branch",
            "type": "branch",
            "options": [
                {
                    "when": "state.x > 0",
                    "step": {"name": "positive", "type": "python", "action": "func"},
                }
            ],
        }
        from pydantic import TypeAdapter

        from maverick.dsl.serialization.schema import StepRecordUnion

        adapter = TypeAdapter(StepRecordUnion)
        step = adapter.validate_python(data)
        assert isinstance(step, BranchStepRecord)
        assert len(step.options) == 1
        assert isinstance(step.options[0].step, PythonStepRecord)

    def test_parse_loop_step_from_dict(self):
        """Test parsing dict to LoopStepRecord via type discriminator."""
        data = {
            "name": "loop",
            "type": "loop",
            "steps": [
                {"name": "task1", "type": "python", "action": "func1"},
                {"name": "task2", "type": "agent", "agent": "reviewer"},
            ],
        }
        from pydantic import TypeAdapter

        from maverick.dsl.serialization.schema import StepRecordUnion

        adapter = TypeAdapter(StepRecordUnion)
        step = adapter.validate_python(data)
        assert isinstance(step, LoopStepRecord)
        assert len(step.steps) == 2
        assert isinstance(step.steps[0], PythonStepRecord)
        assert isinstance(step.steps[1], AgentStepRecord)

    def test_parse_invalid_type_fails(self):
        """Test that invalid type field raises validation error."""
        data = {
            "name": "test",
            "type": "invalid_type",
        }
        from pydantic import TypeAdapter

        from maverick.dsl.serialization.schema import StepRecordUnion

        adapter = TypeAdapter(StepRecordUnion)
        with pytest.raises(Exception):
            adapter.validate_python(data)

    def test_parse_missing_type_fails(self):
        """Test that missing type field raises validation error."""
        data = {
            "name": "test",
            "action": "func",
        }
        from pydantic import TypeAdapter

        from maverick.dsl.serialization.schema import StepRecordUnion

        adapter = TypeAdapter(StepRecordUnion)
        with pytest.raises(Exception):
            adapter.validate_python(data)


# =============================================================================
# Complex Nested Structure Tests
# =============================================================================


class TestNestedStructures:
    """Test complex nested step structures."""

    def test_deeply_nested_branch_in_parallel(self):
        """Test parallel step containing branch step with nested options."""
        data = {
            "name": "complex",
            "type": "loop",
            "steps": [
                {
                    "name": "branch_task",
                    "type": "branch",
                    "options": [
                        {
                            "when": "state.x > 0",
                            "step": {
                                "name": "nested_parallel",
                                "type": "loop",
                                "steps": [
                                    {"name": "task1", "type": "python", "action": "f1"},
                                    {"name": "task2", "type": "python", "action": "f2"},
                                ],
                            },
                        }
                    ],
                },
                {"name": "simple_task", "type": "python", "action": "simple"},
            ],
        }
        from pydantic import TypeAdapter

        from maverick.dsl.serialization.schema import StepRecordUnion

        adapter = TypeAdapter(StepRecordUnion)
        step = adapter.validate_python(data)

        # Verify structure
        assert isinstance(step, LoopStepRecord)
        assert len(step.steps) == 2

        # First parallel step is a branch
        branch_step = step.steps[0]
        assert isinstance(branch_step, BranchStepRecord)

        # Branch contains a nested parallel
        nested_parallel = branch_step.options[0].step
        assert isinstance(nested_parallel, LoopStepRecord)
        assert len(nested_parallel.steps) == 2

    def test_validate_step_with_nested_on_failure(self):
        """Test validate step with complex on_failure branch."""
        data = {
            "name": "validate",
            "type": "validate",
            "stages": ["lint"],
            "on_failure": {
                "name": "fix_branch",
                "type": "branch",
                "options": [
                    {
                        "when": "state.auto_fix_available",
                        "step": {"name": "auto_fix", "type": "python", "action": "fix"},
                    },
                    {
                        "when": "true",
                        "step": {
                            "name": "manual_review",
                            "type": "agent",
                            "agent": "reviewer",
                        },
                    },
                ],
            },
        }
        from pydantic import TypeAdapter

        from maverick.dsl.serialization.schema import StepRecordUnion

        adapter = TypeAdapter(StepRecordUnion)
        step = adapter.validate_python(data)

        assert isinstance(step, ValidateStepRecord)
        assert isinstance(step.on_failure, BranchStepRecord)
        assert len(step.on_failure.options) == 2
        assert isinstance(step.on_failure.options[0].step, PythonStepRecord)
        assert isinstance(step.on_failure.options[1].step, AgentStepRecord)

    def test_branch_with_all_step_types(self):
        """Test branch step with options containing all step types."""
        data = {
            "name": "multi_branch",
            "type": "branch",
            "options": [
                {
                    "when": "state.type == 'python'",
                    "step": {"name": "py", "type": "python", "action": "func"},
                },
                {
                    "when": "state.type == 'agent'",
                    "step": {"name": "ag", "type": "agent", "agent": "reviewer"},
                },
                {
                    "when": "state.type == 'generate'",
                    "step": {"name": "gen", "type": "generate", "generator": "gen"},
                },
                {
                    "when": "state.type == 'validate'",
                    "step": {"name": "val", "type": "validate", "stages": ["lint"]},
                },
                {
                    "when": "state.type == 'subworkflow'",
                    "step": {"name": "sub", "type": "subworkflow", "workflow": "wf"},
                },
            ],
        }
        from pydantic import TypeAdapter

        from maverick.dsl.serialization.schema import StepRecordUnion

        adapter = TypeAdapter(StepRecordUnion)
        step = adapter.validate_python(data)

        assert isinstance(step, BranchStepRecord)
        assert len(step.options) == 5
        assert isinstance(step.options[0].step, PythonStepRecord)
        assert isinstance(step.options[1].step, AgentStepRecord)
        assert isinstance(step.options[2].step, GenerateStepRecord)
        assert isinstance(step.options[3].step, ValidateStepRecord)
        assert isinstance(step.options[4].step, SubWorkflowStepRecord)
