"""Unit tests for DSL result types.

Tests for StepResult, WorkflowResult, and SubWorkflowInvocationResult.
"""

from __future__ import annotations

import pytest

from maverick.dsl import StepResult, StepType, WorkflowResult


class TestStepResult:
    """Test suite for StepResult dataclass."""

    def test_successful_creation(self) -> None:
        """Test creating a successful StepResult."""
        result = StepResult(
            name="test_step",
            step_type=StepType.PYTHON,
            success=True,
            output="test output",
            duration_ms=100,
            error=None,
        )
        assert result.name == "test_step"
        assert result.step_type == StepType.PYTHON
        assert result.success is True
        assert result.output == "test output"
        assert result.duration_ms == 100
        assert result.error is None

    def test_failed_creation_with_error(self) -> None:
        """Test creating a failed StepResult with error message."""
        result = StepResult(
            name="failed_step",
            step_type=StepType.AGENT,
            success=False,
            output=None,
            duration_ms=50,
            error="Something went wrong",
        )
        assert result.name == "failed_step"
        assert result.step_type == StepType.AGENT
        assert result.success is False
        assert result.output is None
        assert result.duration_ms == 50
        assert result.error == "Something went wrong"

    def test_validation_duration_ms_negative(self) -> None:
        """Test that negative duration_ms raises ValueError."""
        with pytest.raises(ValueError, match="duration_ms must be non-negative"):
            StepResult(
                name="test_step",
                step_type=StepType.PYTHON,
                success=True,
                output="test",
                duration_ms=-1,
                error=None,
            )

    def test_validation_duration_ms_zero_allowed(self) -> None:
        """Test that zero duration_ms is allowed."""
        result = StepResult(
            name="instant_step",
            step_type=StepType.PYTHON,
            success=True,
            output="instant",
            duration_ms=0,
            error=None,
        )
        assert result.duration_ms == 0

    def test_validation_failed_step_requires_error(self) -> None:
        """Test that failed steps must have an error message."""
        with pytest.raises(ValueError, match="Failed steps must have an error message"):
            StepResult(
                name="failed_step",
                step_type=StepType.PYTHON,
                success=False,
                output=None,
                duration_ms=100,
                error=None,
            )

    def test_successful_step_can_have_no_error(self) -> None:
        """Test that successful steps can have error=None."""
        result = StepResult(
            name="success_step",
            step_type=StepType.PYTHON,
            success=True,
            output="success",
            duration_ms=100,
            error=None,
        )
        assert result.error is None

    def test_to_dict_basic(self) -> None:
        """Test to_dict() method with basic output types."""
        result = StepResult(
            name="test_step",
            step_type=StepType.PYTHON,
            success=True,
            output="simple string",
            duration_ms=100,
            error=None,
        )
        result_dict = result.to_dict()
        assert result_dict == {
            "name": "test_step",
            "step_type": "python",
            "success": True,
            "output": "simple string",
            "duration_ms": 100,
            "error": None,
        }

    def test_to_dict_with_error(self) -> None:
        """Test to_dict() method with error message."""
        result = StepResult(
            name="failed_step",
            step_type=StepType.AGENT,
            success=False,
            output=None,
            duration_ms=50,
            error="Test error",
        )
        result_dict = result.to_dict()
        assert result_dict["error"] == "Test error"
        assert result_dict["success"] is False

    def test_serialize_output_primitives(self) -> None:
        """Test output serialization for primitive types."""
        # String
        result = StepResult(
            name="s",
            step_type=StepType.PYTHON,
            success=True,
            output="test",
            duration_ms=1,
        )
        assert result.to_dict()["output"] == "test"

        # Integer
        result = StepResult(
            name="i", step_type=StepType.PYTHON, success=True, output=42, duration_ms=1
        )
        assert result.to_dict()["output"] == 42

        # Float
        result = StepResult(
            name="f",
            step_type=StepType.PYTHON,
            success=True,
            output=3.14,
            duration_ms=1,
        )
        assert result.to_dict()["output"] == 3.14

        # Boolean
        result = StepResult(
            name="b",
            step_type=StepType.PYTHON,
            success=True,
            output=True,
            duration_ms=1,
        )
        assert result.to_dict()["output"] is True

        # None
        result = StepResult(
            name="n",
            step_type=StepType.PYTHON,
            success=True,
            output=None,
            duration_ms=1,
        )
        assert result.to_dict()["output"] is None

    def test_serialize_output_list(self) -> None:
        """Test output serialization for lists."""
        result = StepResult(
            name="list_step",
            step_type=StepType.PYTHON,
            success=True,
            output=[1, "two", 3.0, True, None],
            duration_ms=10,
        )
        assert result.to_dict()["output"] == [1, "two", 3.0, True, None]

    def test_serialize_output_dict(self) -> None:
        """Test output serialization for dictionaries."""
        result = StepResult(
            name="dict_step",
            step_type=StepType.PYTHON,
            success=True,
            output={"key1": "value1", "key2": 42, "key3": None},
            duration_ms=10,
        )
        assert result.to_dict()["output"] == {
            "key1": "value1",
            "key2": 42,
            "key3": None,
        }

    def test_serialize_output_nested_structures(self) -> None:
        """Test output serialization for nested lists and dicts.

        Note: _serialize_item doesn't recursively handle nested collections,
        so nested dicts/lists within dict values are converted to strings.
        """
        result = StepResult(
            name="nested_step",
            step_type=StepType.PYTHON,
            success=True,
            output={
                "list": [1, 2, {"nested": "value"}],
                "dict": {"a": 1, "b": [2, 3]},
            },
            duration_ms=10,
        )
        output = result.to_dict()["output"]
        # Nested collections in dict values are stringified by _serialize_item
        assert output["list"] == "[1, 2, {'nested': 'value'}]"
        assert output["dict"] == "{'a': 1, 'b': [2, 3]}"

    def test_serialize_output_object_with_to_dict(self) -> None:
        """Test output serialization for objects with to_dict() method."""

        class CustomObject:
            def to_dict(self) -> dict:
                return {"custom": "serialized"}

        result = StepResult(
            name="custom_step",
            step_type=StepType.PYTHON,
            success=True,
            output=CustomObject(),
            duration_ms=10,
        )
        assert result.to_dict()["output"] == {"custom": "serialized"}

    def test_serialize_output_list_with_to_dict_objects(self) -> None:
        """Test output serialization for lists containing objects with to_dict()."""

        class CustomObject:
            def __init__(self, value: str):
                self.value = value

            def to_dict(self) -> dict:
                return {"value": self.value}

        result = StepResult(
            name="list_custom_step",
            step_type=StepType.PYTHON,
            success=True,
            output=[CustomObject("a"), CustomObject("b")],
            duration_ms=10,
        )
        assert result.to_dict()["output"] == [
            {"value": "a"},
            {"value": "b"},
        ]

    def test_serialize_output_unknown_type(self) -> None:
        """Test output serialization for unknown types converts to string."""

        class CustomClass:
            def __repr__(self) -> str:
                return "CustomClass()"

        result = StepResult(
            name="unknown_step",
            step_type=StepType.PYTHON,
            success=True,
            output=CustomClass(),
            duration_ms=10,
        )
        assert result.to_dict()["output"] == "CustomClass()"

    def test_serialize_output_list_with_unknown_types(self) -> None:
        """Test output serialization for lists with unknown types."""

        class CustomClass:
            def __repr__(self) -> str:
                return "Custom"

        result = StepResult(
            name="mixed_list",
            step_type=StepType.PYTHON,
            success=True,
            output=[1, "two", CustomClass()],
            duration_ms=10,
        )
        assert result.to_dict()["output"] == [1, "two", "Custom"]

    def test_frozen_dataclass(self) -> None:
        """Test that StepResult is immutable (frozen)."""
        result = StepResult(
            name="test",
            step_type=StepType.PYTHON,
            success=True,
            output="test",
            duration_ms=10,
        )
        with pytest.raises(Exception):  # FrozenInstanceError in dataclass
            result.name = "modified"  # type: ignore[misc]


class TestWorkflowResult:
    """Test suite for WorkflowResult dataclass."""

    def test_successful_creation(self) -> None:
        """Test creating a successful WorkflowResult."""
        step1 = StepResult(
            name="step1",
            step_type=StepType.PYTHON,
            success=True,
            output="output1",
            duration_ms=50,
        )
        step2 = StepResult(
            name="step2",
            step_type=StepType.AGENT,
            success=True,
            output="output2",
            duration_ms=100,
        )

        result = WorkflowResult(
            workflow_name="test_workflow",
            success=True,
            step_results=(step1, step2),
            total_duration_ms=150,
            final_output="workflow complete",
        )

        assert result.workflow_name == "test_workflow"
        assert result.success is True
        assert len(result.step_results) == 2
        assert result.total_duration_ms == 150
        assert result.final_output == "workflow complete"

    def test_failed_workflow_creation(self) -> None:
        """Test creating a failed WorkflowResult."""
        step1 = StepResult(
            name="step1",
            step_type=StepType.PYTHON,
            success=True,
            output="output1",
            duration_ms=50,
        )
        step2 = StepResult(
            name="step2",
            step_type=StepType.AGENT,
            success=False,
            output=None,
            duration_ms=25,
            error="Agent failed",
        )

        result = WorkflowResult(
            workflow_name="failed_workflow",
            success=False,
            step_results=(step1, step2),
            total_duration_ms=75,
            final_output=None,
        )

        assert result.workflow_name == "failed_workflow"
        assert result.success is False
        assert len(result.step_results) == 2

    def test_validation_total_duration_ms_negative(self) -> None:
        """Test that negative total_duration_ms raises ValueError."""
        with pytest.raises(ValueError, match="total_duration_ms must be non-negative"):
            WorkflowResult(
                workflow_name="test",
                success=True,
                step_results=(),
                total_duration_ms=-1,
                final_output=None,
            )

    def test_validation_total_duration_ms_zero_allowed(self) -> None:
        """Test that zero total_duration_ms is allowed."""
        result = WorkflowResult(
            workflow_name="instant_workflow",
            success=True,
            step_results=(),
            total_duration_ms=0,
            final_output=None,
        )
        assert result.total_duration_ms == 0

    def test_to_dict_basic(self) -> None:
        """Test to_dict() method produces correct output."""
        step1 = StepResult(
            name="step1",
            step_type=StepType.PYTHON,
            success=True,
            output="output1",
            duration_ms=50,
        )

        result = WorkflowResult(
            workflow_name="test_workflow",
            success=True,
            step_results=(step1,),
            total_duration_ms=50,
            final_output="done",
        )

        result_dict = result.to_dict()
        assert result_dict["workflow_name"] == "test_workflow"
        assert result_dict["success"] is True
        assert result_dict["total_duration_ms"] == 50
        assert result_dict["final_output"] == "done"
        assert len(result_dict["step_results"]) == 1
        assert result_dict["step_results"][0]["name"] == "step1"

    def test_to_dict_multiple_steps(self) -> None:
        """Test to_dict() serializes all step results."""
        steps = tuple(
            StepResult(
                name=f"step{i}",
                step_type=StepType.PYTHON,
                success=True,
                output=f"output{i}",
                duration_ms=10,
            )
            for i in range(3)
        )

        result = WorkflowResult(
            workflow_name="multi_step",
            success=True,
            step_results=steps,
            total_duration_ms=30,
            final_output="complete",
        )

        result_dict = result.to_dict()
        assert len(result_dict["step_results"]) == 3
        for i, step_dict in enumerate(result_dict["step_results"]):
            assert step_dict["name"] == f"step{i}"
            assert step_dict["output"] == f"output{i}"

    def test_to_dict_final_output_converted_to_string(self) -> None:
        """Test that final_output is converted to string in to_dict()."""
        result = WorkflowResult(
            workflow_name="test",
            success=True,
            step_results=(),
            total_duration_ms=10,
            final_output={"complex": "object"},
        )
        result_dict = result.to_dict()
        assert isinstance(result_dict["final_output"], str)
        assert "complex" in result_dict["final_output"]

    def test_failed_step_property_returns_first_failed(self) -> None:
        """Test failed_step property returns first failed step."""
        step1 = StepResult(
            name="step1",
            step_type=StepType.PYTHON,
            success=True,
            output="ok",
            duration_ms=10,
        )
        step2 = StepResult(
            name="step2",
            step_type=StepType.AGENT,
            success=False,
            output=None,
            duration_ms=5,
            error="First error",
        )
        step3 = StepResult(
            name="step3",
            step_type=StepType.VALIDATE,
            success=False,
            output=None,
            duration_ms=3,
            error="Second error",
        )

        result = WorkflowResult(
            workflow_name="test",
            success=False,
            step_results=(step1, step2, step3),
            total_duration_ms=18,
            final_output=None,
        )

        failed = result.failed_step
        assert failed is not None
        assert failed.name == "step2"
        assert failed.error == "First error"

    def test_failed_step_property_returns_none_on_success(self) -> None:
        """Test failed_step property returns None when all steps succeed."""
        steps = tuple(
            StepResult(
                name=f"step{i}",
                step_type=StepType.PYTHON,
                success=True,
                output=f"ok{i}",
                duration_ms=10,
            )
            for i in range(3)
        )

        result = WorkflowResult(
            workflow_name="test",
            success=True,
            step_results=steps,
            total_duration_ms=30,
            final_output="done",
        )

        assert result.failed_step is None

    def test_failed_step_property_empty_steps(self) -> None:
        """Test failed_step property with no steps."""
        result = WorkflowResult(
            workflow_name="empty",
            success=True,
            step_results=(),
            total_duration_ms=0,
            final_output=None,
        )
        assert result.failed_step is None

    def test_frozen_dataclass(self) -> None:
        """Test that WorkflowResult is immutable (frozen)."""
        result = WorkflowResult(
            workflow_name="test",
            success=True,
            step_results=(),
            total_duration_ms=10,
            final_output=None,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            result.workflow_name = "modified"  # type: ignore[misc]
