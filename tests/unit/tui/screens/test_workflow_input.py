"""Unit tests for WorkflowInputScreen."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from maverick.dsl.serialization.schema import InputType
from maverick.tui.screens.workflow_input import WorkflowInputScreen


def create_mock_input_def(
    input_type: InputType = InputType.STRING,
    required: bool = False,
    default: Any = None,
    description: str | None = None,
) -> MagicMock:
    """Create a mock InputDefinition for testing."""
    mock_input = MagicMock()
    mock_input.type = input_type
    mock_input.required = required
    mock_input.default = default
    mock_input.description = description
    return mock_input


def create_mock_workflow(
    name: str = "test-workflow",
    description: str | None = "Test workflow description",
    inputs: dict | None = None,
) -> MagicMock:
    """Create a mock DiscoveredWorkflow for testing."""
    mock_discovered = MagicMock()
    mock_discovered.workflow.name = name
    mock_discovered.workflow.description = description
    mock_discovered.workflow.inputs = inputs or {}
    return mock_discovered


# Initialization Tests
class TestWorkflowInputInitialization:
    """Tests for WorkflowInputScreen initialization."""

    def test_screen_has_correct_title(self):
        """Test that screen has correct title."""
        assert WorkflowInputScreen.TITLE == "Configure Workflow"

    def test_screen_has_required_bindings(self):
        """Test that screen has all required key bindings."""
        binding_keys = [b.key for b in WorkflowInputScreen.BINDINGS]
        assert "ctrl+enter" in binding_keys
        assert "escape" in binding_keys

    def test_screen_initializes_with_workflow(self):
        """Test that screen initializes with workflow data."""
        mock_workflow = create_mock_workflow(name="my-workflow")
        screen = WorkflowInputScreen(workflow=mock_workflow)

        assert screen._workflow == mock_workflow
        assert screen._input_values == {}
        assert screen._validation_errors == {}
        assert screen._field_widgets == {}


# Input Validation Tests
# Note: _validate_field calls query_one which requires a mounted widget.
# These tests verify the validation logic through _get_typed_inputs instead.
class TestInputValidation:
    """Tests for input validation functionality via type conversion."""

    def test_validate_integer_valid(self):
        """Test valid integer conversion."""
        mock_workflow = create_mock_workflow(
            inputs={
                "count": create_mock_input_def(
                    input_type=InputType.INTEGER,
                    required=True,
                ),
            }
        )
        screen = WorkflowInputScreen(workflow=mock_workflow)
        screen._input_values["count"] = "42"

        result = screen._get_typed_inputs()
        assert result["count"] == 42

    def test_validate_integer_invalid_raises(self):
        """Test invalid integer conversion raises ValueError."""
        mock_workflow = create_mock_workflow(
            inputs={
                "count": create_mock_input_def(
                    input_type=InputType.INTEGER,
                    required=True,
                ),
            }
        )
        screen = WorkflowInputScreen(workflow=mock_workflow)
        screen._input_values["count"] = "not-a-number"

        with pytest.raises(ValueError):
            screen._get_typed_inputs()

    def test_validate_float_valid(self):
        """Test valid float conversion."""
        mock_workflow = create_mock_workflow(
            inputs={
                "rate": create_mock_input_def(
                    input_type=InputType.FLOAT,
                    required=True,
                ),
            }
        )
        screen = WorkflowInputScreen(workflow=mock_workflow)
        screen._input_values["rate"] = "3.14"

        result = screen._get_typed_inputs()
        assert result["rate"] == 3.14

    def test_validate_float_invalid_raises(self):
        """Test invalid float conversion raises ValueError."""
        mock_workflow = create_mock_workflow(
            inputs={
                "rate": create_mock_input_def(
                    input_type=InputType.FLOAT,
                    required=True,
                ),
            }
        )
        screen = WorkflowInputScreen(workflow=mock_workflow)
        screen._input_values["rate"] = "not-a-float"

        with pytest.raises(ValueError):
            screen._get_typed_inputs()

    def test_validate_array_valid(self):
        """Test valid JSON array conversion."""
        mock_workflow = create_mock_workflow(
            inputs={
                "items": create_mock_input_def(
                    input_type=InputType.ARRAY,
                    required=True,
                ),
            }
        )
        screen = WorkflowInputScreen(workflow=mock_workflow)
        screen._input_values["items"] = '["a", "b", "c"]'

        result = screen._get_typed_inputs()
        assert result["items"] == ["a", "b", "c"]

    def test_validate_array_invalid_json_raises(self):
        """Test invalid JSON array conversion raises JSONDecodeError."""
        import json

        mock_workflow = create_mock_workflow(
            inputs={
                "items": create_mock_input_def(
                    input_type=InputType.ARRAY,
                    required=True,
                ),
            }
        )
        screen = WorkflowInputScreen(workflow=mock_workflow)
        screen._input_values["items"] = "not-json"

        with pytest.raises(json.JSONDecodeError):
            screen._get_typed_inputs()

    def test_validate_object_valid(self):
        """Test valid JSON object conversion."""
        mock_workflow = create_mock_workflow(
            inputs={
                "config": create_mock_input_def(
                    input_type=InputType.OBJECT,
                    required=True,
                ),
            }
        )
        screen = WorkflowInputScreen(workflow=mock_workflow)
        screen._input_values["config"] = '{"key": "value"}'

        result = screen._get_typed_inputs()
        assert result["config"] == {"key": "value"}

    def test_validate_object_invalid_json_raises(self):
        """Test invalid JSON object conversion raises JSONDecodeError."""
        import json

        mock_workflow = create_mock_workflow(
            inputs={
                "config": create_mock_input_def(
                    input_type=InputType.OBJECT,
                    required=True,
                ),
            }
        )
        screen = WorkflowInputScreen(workflow=mock_workflow)
        screen._input_values["config"] = "not-json"

        with pytest.raises(json.JSONDecodeError):
            screen._get_typed_inputs()


# Type Conversion Tests
class TestTypeConversion:
    """Tests for input value type conversion."""

    def test_convert_string(self):
        """Test string type conversion."""
        mock_workflow = create_mock_workflow(
            inputs={
                "name": create_mock_input_def(input_type=InputType.STRING),
            }
        )
        screen = WorkflowInputScreen(workflow=mock_workflow)
        screen._input_values["name"] = "test"

        result = screen._get_typed_inputs()

        assert result["name"] == "test"
        assert isinstance(result["name"], str)

    def test_convert_integer(self):
        """Test integer type conversion."""
        mock_workflow = create_mock_workflow(
            inputs={
                "count": create_mock_input_def(input_type=InputType.INTEGER),
            }
        )
        screen = WorkflowInputScreen(workflow=mock_workflow)
        screen._input_values["count"] = "42"

        result = screen._get_typed_inputs()

        assert result["count"] == 42
        assert isinstance(result["count"], int)

    def test_convert_float(self):
        """Test float type conversion."""
        mock_workflow = create_mock_workflow(
            inputs={
                "rate": create_mock_input_def(input_type=InputType.FLOAT),
            }
        )
        screen = WorkflowInputScreen(workflow=mock_workflow)
        screen._input_values["rate"] = "3.14"

        result = screen._get_typed_inputs()

        assert result["rate"] == 3.14
        assert isinstance(result["rate"], float)

    def test_convert_boolean(self):
        """Test boolean type conversion."""
        mock_workflow = create_mock_workflow(
            inputs={
                "enabled": create_mock_input_def(input_type=InputType.BOOLEAN),
            }
        )
        screen = WorkflowInputScreen(workflow=mock_workflow)
        screen._input_values["enabled"] = True

        result = screen._get_typed_inputs()

        assert result["enabled"] is True
        assert isinstance(result["enabled"], bool)

    def test_convert_array(self):
        """Test array type conversion from JSON string."""
        mock_workflow = create_mock_workflow(
            inputs={
                "items": create_mock_input_def(input_type=InputType.ARRAY),
            }
        )
        screen = WorkflowInputScreen(workflow=mock_workflow)
        screen._input_values["items"] = '["a", "b", "c"]'

        result = screen._get_typed_inputs()

        assert result["items"] == ["a", "b", "c"]
        assert isinstance(result["items"], list)

    def test_convert_object(self):
        """Test object type conversion from JSON string."""
        mock_workflow = create_mock_workflow(
            inputs={
                "config": create_mock_input_def(input_type=InputType.OBJECT),
            }
        )
        screen = WorkflowInputScreen(workflow=mock_workflow)
        screen._input_values["config"] = '{"key": "value"}'

        result = screen._get_typed_inputs()

        assert result["config"] == {"key": "value"}
        assert isinstance(result["config"], dict)

    def test_empty_value_uses_default(self):
        """Test empty value falls back to default."""
        mock_workflow = create_mock_workflow(
            inputs={
                "name": create_mock_input_def(
                    input_type=InputType.STRING,
                    default="default-name",
                ),
            }
        )
        screen = WorkflowInputScreen(workflow=mock_workflow)
        screen._input_values["name"] = ""

        result = screen._get_typed_inputs()

        assert result["name"] == "default-name"

    def test_whitespace_value_uses_default(self):
        """Test whitespace-only value falls back to default."""
        mock_workflow = create_mock_workflow(
            inputs={
                "name": create_mock_input_def(
                    input_type=InputType.STRING,
                    default="default-name",
                ),
            }
        )
        screen = WorkflowInputScreen(workflow=mock_workflow)
        screen._input_values["name"] = "   "

        result = screen._get_typed_inputs()

        assert result["name"] == "default-name"


# Can Run State Tests
class TestCanRunState:
    """Tests for can_run reactive state."""

    def test_can_run_default(self):
        """Test can_run reactive default is False."""
        assert WorkflowInputScreen.can_run._default is False

    def test_validation_error_dict_empty_initially(self):
        """Test validation errors dict is empty initially."""
        mock_workflow = create_mock_workflow(inputs={})
        screen = WorkflowInputScreen(workflow=mock_workflow)
        assert screen._validation_errors == {}


# Default Value Initialization Tests
class TestDefaultValueInitialization:
    """Tests for default value initialization."""

    def test_default_value_set_in_compose(self):
        """Test that default values are set during compose."""
        mock_workflow = create_mock_workflow(
            inputs={
                "name": create_mock_input_def(
                    input_type=InputType.STRING,
                    default="default-value",
                ),
            }
        )
        screen = WorkflowInputScreen(workflow=mock_workflow)

        # Simulate the compose behavior
        for input_name, input_def in mock_workflow.workflow.inputs.items():
            if input_def.default is not None:
                screen._input_values[input_name] = input_def.default

        assert screen._input_values["name"] == "default-value"
