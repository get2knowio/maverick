"""Unit tests for WorkflowContext.

Tests for the WorkflowContext dataclass used for runtime state management.
"""

from __future__ import annotations

from maverick.dsl import StepResult, StepType, WorkflowContext


class TestWorkflowContext:
    """Test suite for WorkflowContext dataclass."""

    def test_creation_with_inputs(self) -> None:
        """Test creating WorkflowContext with inputs."""
        context = WorkflowContext(
            inputs={"branch": "main", "issue_num": 42},
        )
        assert context.inputs == {"branch": "main", "issue_num": 42}
        assert context.results == {}
        assert context.config is None

    def test_creation_with_all_fields(self) -> None:
        """Test creating WorkflowContext with all fields."""
        step_result = StepResult(
            name="step1",
            step_type=StepType.PYTHON,
            success=True,
            output="test",
            duration_ms=10,
        )
        config_obj = {"setting": "value"}

        context = WorkflowContext(
            inputs={"key": "value"},
            results={"step1": step_result},
            config=config_obj,
        )

        assert context.inputs == {"key": "value"}
        assert "step1" in context.results
        assert context.config == {"setting": "value"}

    def test_creation_with_empty_inputs(self) -> None:
        """Test creating WorkflowContext with empty inputs dict."""
        context = WorkflowContext(inputs={})
        assert context.inputs == {}
        assert context.results == {}

    def test_get_step_output_returns_correct_output(self) -> None:
        """Test get_step_output returns the output from a step result."""
        step_result = StepResult(
            name="parse_tasks",
            step_type=StepType.PYTHON,
            success=True,
            output=["task1", "task2", "task3"],
            duration_ms=50,
        )

        context = WorkflowContext(
            inputs={},
            results={"parse_tasks": step_result},
        )

        output = context.get_step_output("parse_tasks")
        assert output == ["task1", "task2", "task3"]

    def test_get_step_output_multiple_steps(self) -> None:
        """Test get_step_output with multiple steps in results."""
        step1 = StepResult(
            name="step1",
            step_type=StepType.PYTHON,
            success=True,
            output="output1",
            duration_ms=10,
        )
        step2 = StepResult(
            name="step2",
            step_type=StepType.AGENT,
            success=True,
            output={"key": "value"},
            duration_ms=20,
        )

        context = WorkflowContext(
            inputs={},
            results={"step1": step1, "step2": step2},
        )

        assert context.get_step_output("step1") == "output1"
        assert context.get_step_output("step2") == {"key": "value"}

    def test_get_step_output_returns_none_for_missing_step(self) -> None:
        """Test get_step_output returns None when step not found (FR-009a)."""
        context = WorkflowContext(inputs={})

        # Per FR-009a, get_step_output returns None for missing steps
        assert context.get_step_output("nonexistent") is None

    def test_get_step_output_returns_none_with_other_steps_present(self) -> None:
        """Test get_step_output returns None for missing step even with other steps."""
        step1 = StepResult(
            name="step1",
            step_type=StepType.PYTHON,
            success=True,
            output="output1",
            duration_ms=10,
        )

        context = WorkflowContext(
            inputs={},
            results={"step1": step1},
        )

        # Per FR-009a, get_step_output returns None for missing steps
        assert context.get_step_output("step2") is None

    def test_results_dict_can_be_modified(self) -> None:
        """Test that the results dict can be modified after creation."""
        context = WorkflowContext(inputs={})
        assert len(context.results) == 0

        # Add a result
        step1 = StepResult(
            name="step1",
            step_type=StepType.PYTHON,
            success=True,
            output="output1",
            duration_ms=10,
        )
        context.results["step1"] = step1
        assert len(context.results) == 1
        assert "step1" in context.results

        # Add another result
        step2 = StepResult(
            name="step2",
            step_type=StepType.AGENT,
            success=True,
            output="output2",
            duration_ms=20,
        )
        context.results["step2"] = step2
        assert len(context.results) == 2
        assert "step2" in context.results

    def test_results_dict_modification_affects_get_step_output(self) -> None:
        """Test that modifying results dict affects get_step_output."""
        context = WorkflowContext(inputs={})

        # Initially, getting output returns None (FR-009a)
        assert context.get_step_output("new_step") is None

        # Add a result
        step = StepResult(
            name="new_step",
            step_type=StepType.PYTHON,
            success=True,
            output="new_output",
            duration_ms=15,
        )
        context.results["new_step"] = step

        # Now it should return the output
        assert context.get_step_output("new_step") == "new_output"

    def test_inputs_dict_is_accessible(self) -> None:
        """Test that inputs dict can be accessed."""
        context = WorkflowContext(
            inputs={"param1": "value1", "param2": 42},
        )
        assert context.inputs["param1"] == "value1"
        assert context.inputs["param2"] == 42

    def test_config_is_accessible(self) -> None:
        """Test that config can be accessed."""
        config_obj = {"database": "postgres", "timeout": 30}
        context = WorkflowContext(
            inputs={},
            config=config_obj,
        )
        assert context.config == config_obj
        assert context.config["database"] == "postgres"

    def test_context_is_mutable(self) -> None:
        """Test that WorkflowContext is mutable (not frozen)."""
        context = WorkflowContext(inputs={})

        # Should be able to modify results
        context.results["new"] = StepResult(
            name="new",
            step_type=StepType.PYTHON,
            success=True,
            output="test",
            duration_ms=1,
        )
        assert "new" in context.results

    def test_get_step_output_with_none_output(self) -> None:
        """Test get_step_output works when output is None."""
        step = StepResult(
            name="step_with_none",
            step_type=StepType.PYTHON,
            success=True,
            output=None,
            duration_ms=5,
        )
        context = WorkflowContext(
            inputs={},
            results={"step_with_none": step},
        )
        assert context.get_step_output("step_with_none") is None

    def test_get_step_output_with_complex_types(self) -> None:
        """Test get_step_output with various complex output types."""
        # List output
        step1 = StepResult(
            name="list_step",
            step_type=StepType.PYTHON,
            success=True,
            output=[1, 2, 3],
            duration_ms=5,
        )

        # Dict output
        step2 = StepResult(
            name="dict_step",
            step_type=StepType.PYTHON,
            success=True,
            output={"nested": {"key": "value"}},
            duration_ms=5,
        )

        # Custom object output
        class CustomOutput:
            def __init__(self, value: str):
                self.value = value

        custom_obj = CustomOutput("test")
        step3 = StepResult(
            name="obj_step",
            step_type=StepType.PYTHON,
            success=True,
            output=custom_obj,
            duration_ms=5,
        )

        context = WorkflowContext(
            inputs={},
            results={
                "list_step": step1,
                "dict_step": step2,
                "obj_step": step3,
            },
        )

        assert context.get_step_output("list_step") == [1, 2, 3]
        assert context.get_step_output("dict_step") == {"nested": {"key": "value"}}
        assert context.get_step_output("obj_step").value == "test"

    def test_context_default_factory_for_results(self) -> None:
        """Test that results dict is created with default_factory."""
        # Creating two contexts should give them independent results dicts
        context1 = WorkflowContext(inputs={})
        context2 = WorkflowContext(inputs={})

        step = StepResult(
            name="step",
            step_type=StepType.PYTHON,
            success=True,
            output="test",
            duration_ms=1,
        )

        context1.results["step"] = step

        # context2 should still have an empty results dict
        assert len(context1.results) == 1
        assert len(context2.results) == 0
