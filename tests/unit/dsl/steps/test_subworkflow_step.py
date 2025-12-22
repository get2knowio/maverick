"""Unit tests for SubWorkflowStep class.

This module tests the SubWorkflowStep class that executes sub-workflows
within workflow execution.

TDD Note: These tests are written FIRST and will FAIL until implementation
is complete. They define the expected behavior of SubWorkflowStep.
"""

from __future__ import annotations

from typing import Any

import pytest

from maverick.dsl import (
    StepResult,
    StepType,
    SubWorkflowInvocationResult,
    WorkflowContext,
    step,
    workflow,
)
from maverick.dsl.steps.subworkflow import SubWorkflowStep


# Test workflow fixtures
@workflow(name="simple-workflow", description="Simple test workflow")
def simple_workflow(value: int):
    """Simple workflow that doubles a value."""
    result = yield step("double").python(action=lambda x: x * 2, args=(value,))
    return result


@workflow(name="multi-step-workflow", description="Multi-step test workflow")
def multi_step_workflow(a: int, b: int):
    """Workflow with multiple steps."""
    sum_result = yield step("sum").python(action=lambda x, y: x + y, args=(a, b))
    product_result = yield step("product").python(
        action=lambda x, y: x * y, args=(a, b)
    )
    return {"sum": sum_result, "product": product_result}


@workflow(name="failing-workflow", description="Workflow that fails")
def failing_workflow():
    """Workflow that raises an error."""

    def fail():
        raise ValueError("Intentional failure")

    yield step("fail").python(action=fail)


@workflow(name="nested-workflow", description="Workflow that calls sub-workflow")
def nested_workflow(value: int):
    """Workflow that calls another workflow."""
    result = yield step("call-simple").subworkflow(
        workflow=simple_workflow, inputs={"value": value}
    )
    return result


class TestSubWorkflowStepCreation:
    """Test SubWorkflowStep instantiation and properties."""

    def test_creation_with_workflow_function_and_inputs(self) -> None:
        """Test creating SubWorkflowStep with workflow function and inputs."""
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=simple_workflow,
            inputs={"value": 5},
        )

        assert step_instance.name == "test-step"
        assert step_instance.workflow is simple_workflow
        assert step_instance.inputs == {"value": 5}
        assert step_instance.step_type == StepType.SUBWORKFLOW

    def test_creation_with_empty_inputs(self) -> None:
        """Test creating SubWorkflowStep with no inputs."""
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=simple_workflow,
        )

        assert step_instance.name == "test-step"
        assert step_instance.workflow is simple_workflow
        assert step_instance.inputs == {}
        assert step_instance.step_type == StepType.SUBWORKFLOW

    def test_step_type_is_always_subworkflow(self) -> None:
        """Test that step_type is always StepType.SUBWORKFLOW."""
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=simple_workflow,
            inputs={},
        )

        assert step_instance.step_type == StepType.SUBWORKFLOW

    def test_subworkflow_step_is_frozen(self) -> None:
        """Test that SubWorkflowStep is immutable (frozen=True)."""
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=simple_workflow,
            inputs={},
        )

        # Attempt to modify should raise error
        with pytest.raises((AttributeError, TypeError)):
            step_instance.name = "modified"

    def test_subworkflow_step_has_slots(self) -> None:
        """Test that SubWorkflowStep declares __slots__ for memory efficiency."""
        SubWorkflowStep(
            name="test-step",
            workflow=simple_workflow,
            inputs={},
        )

        # Dataclass with slots=True declares __slots__
        assert hasattr(SubWorkflowStep, "__slots__")

    def test_creation_with_workflow_def_attribute(self) -> None:
        """Test with workflow that has __workflow_def__ attribute."""
        # The @workflow decorator adds __workflow_def__
        assert hasattr(simple_workflow, "__workflow_def__")
        assert simple_workflow.__workflow_def__.name == "simple-workflow"

        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=simple_workflow,
            inputs={"value": 10},
        )

        assert step_instance.workflow is simple_workflow


class TestSubWorkflowStepToDict:
    """Test SubWorkflowStep.to_dict() serialization."""

    def test_to_dict_returns_expected_structure(self) -> None:
        """Test that to_dict() returns correct structure."""
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=simple_workflow,
            inputs={"value": 5, "other": "data"},
        )

        result = step_instance.to_dict()

        assert result["name"] == "test-step"
        assert result["step_type"] == "subworkflow"
        assert result["workflow"] == "simple-workflow"
        assert set(result["inputs_keys"]) == {"value", "other"}

    def test_to_dict_with_empty_inputs(self) -> None:
        """Test to_dict() with empty inputs."""
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=simple_workflow,
            inputs={},
        )

        result = step_instance.to_dict()

        assert result["inputs_keys"] == []

    def test_to_dict_returns_workflow_name_from_workflow_def(self) -> None:
        """Test that to_dict() extracts workflow name from __workflow_def__."""
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=multi_step_workflow,
            inputs={"a": 1, "b": 2},
        )

        result = step_instance.to_dict()

        assert result["workflow"] == "multi-step-workflow"
        assert result["inputs_keys"] == ["a", "b"]


class TestSubWorkflowStepExecute:
    """Test SubWorkflowStep.execute() method."""

    @pytest.mark.asyncio
    async def test_execute_runs_subworkflow_and_returns_result(self) -> None:
        """Test that execute() runs sub-workflow and returns result."""
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=simple_workflow,
            inputs={"value": 5},
        )
        context = WorkflowContext(inputs={}, results={})

        result = await step_instance.execute(context)

        assert isinstance(result, StepResult)
        assert result.name == "test-step"
        assert result.step_type == StepType.SUBWORKFLOW
        assert result.success is True
        assert result.duration_ms >= 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_execute_returns_subworkflow_invocation_result_as_output(
        self,
    ) -> None:
        """Test that execute() returns SubWorkflowInvocationResult as output."""
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=simple_workflow,
            inputs={"value": 5},
        )
        context = WorkflowContext(inputs={}, results={})

        result = await step_instance.execute(context)

        assert isinstance(result.output, SubWorkflowInvocationResult)
        assert result.output.final_output == 10  # 5 * 2
        assert result.output.workflow_result.workflow_name == "simple-workflow"
        assert result.output.workflow_result.success is True

    @pytest.mark.asyncio
    async def test_execute_passes_inputs_to_subworkflow(self) -> None:
        """Test that execute() passes inputs to sub-workflow."""
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=multi_step_workflow,
            inputs={"a": 3, "b": 4},
        )
        context = WorkflowContext(inputs={}, results={})

        result = await step_instance.execute(context)

        assert result.success is True
        assert isinstance(result.output, SubWorkflowInvocationResult)
        assert result.output.final_output == {"sum": 7, "product": 12}

    @pytest.mark.asyncio
    async def test_execute_with_different_input_values(self) -> None:
        """Test execute() with different input values."""
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=simple_workflow,
            inputs={"value": 10},
        )
        context = WorkflowContext(inputs={}, results={})

        result = await step_instance.execute(context)

        assert result.success is True
        assert result.output.final_output == 20  # 10 * 2

    @pytest.mark.asyncio
    async def test_execute_with_empty_inputs(self) -> None:
        """Test execute() with workflow that has no required inputs."""

        @workflow(name="no-input-workflow", description="No inputs required")
        def no_input_workflow():
            result = yield step("constant").python(action=lambda: 42)
            return result

        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=no_input_workflow,
            inputs={},
        )
        context = WorkflowContext(inputs={}, results={})

        result = await step_instance.execute(context)

        assert result.success is True
        assert result.output.final_output == 42


class TestSubWorkflowStepExecuteFailure:
    """Test SubWorkflowStep.execute() failure handling."""

    @pytest.mark.asyncio
    async def test_subworkflow_failure_is_captured_in_step_result(self) -> None:
        """Test that sub-workflow failure is captured in StepResult."""
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=failing_workflow,
            inputs={},
        )
        context = WorkflowContext(inputs={}, results={})

        result = await step_instance.execute(context)

        assert isinstance(result, StepResult)
        assert result.success is False
        assert result.output is not None  # SubWorkflowInvocationResult
        assert isinstance(result.output, SubWorkflowInvocationResult)
        assert result.output.workflow_result.success is False
        assert result.error is not None
        assert "failing-workflow" in result.error
        assert "failed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_captures_workflow_execution_error(self) -> None:
        """Test that execute() captures workflow execution errors."""
        # Create a workflow that will cause an execution error (e.g., missing inputs)
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=multi_step_workflow,
            inputs={},  # Missing required 'a' and 'b' inputs
        )
        context = WorkflowContext(inputs={}, results={})

        result = await step_instance.execute(context)

        # Should capture the error gracefully
        assert result.success is False
        assert result.error is not None
        assert "test-step" in result.error

    @pytest.mark.asyncio
    async def test_execute_duration_recorded_on_failure(self) -> None:
        """Test that execution duration is recorded even on failure."""
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=failing_workflow,
            inputs={},
        )
        context = WorkflowContext(inputs={}, results={})

        result = await step_instance.execute(context)

        assert result.success is False
        assert result.duration_ms >= 0


class TestSubWorkflowInvocationResultFormat:
    """Test SubWorkflowInvocationResult output format."""

    @pytest.mark.asyncio
    async def test_invocation_result_contains_final_output(self) -> None:
        """Test that SubWorkflowInvocationResult contains final_output."""
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=simple_workflow,
            inputs={"value": 7},
        )
        context = WorkflowContext(inputs={}, results={})

        result = await step_instance.execute(context)

        invocation_result = result.output
        assert isinstance(invocation_result, SubWorkflowInvocationResult)
        assert invocation_result.final_output == 14

    @pytest.mark.asyncio
    async def test_invocation_result_contains_workflow_result(self) -> None:
        """Test that SubWorkflowInvocationResult contains workflow_result."""
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=multi_step_workflow,
            inputs={"a": 5, "b": 3},
        )
        context = WorkflowContext(inputs={}, results={})

        result = await step_instance.execute(context)

        invocation_result = result.output
        assert isinstance(invocation_result, SubWorkflowInvocationResult)
        assert invocation_result.workflow_result.workflow_name == "multi-step-workflow"
        assert invocation_result.workflow_result.success is True
        assert len(invocation_result.workflow_result.step_results) == 2

    @pytest.mark.asyncio
    async def test_invocation_result_to_dict(self) -> None:
        """Test SubWorkflowInvocationResult.to_dict() serialization."""
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=simple_workflow,
            inputs={"value": 3},
        )
        context = WorkflowContext(inputs={}, results={})

        result = await step_instance.execute(context)

        invocation_result = result.output
        result_dict = invocation_result.to_dict()

        assert "final_output" in result_dict
        assert "workflow_name" in result_dict
        assert "success" in result_dict
        assert "step_count" in result_dict
        assert result_dict["workflow_name"] == "simple-workflow"
        assert result_dict["success"] is True
        assert result_dict["step_count"] == 1

    @pytest.mark.asyncio
    async def test_invocation_result_exposes_step_results(self) -> None:
        """Test that SubWorkflowInvocationResult exposes step results."""
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=multi_step_workflow,
            inputs={"a": 2, "b": 3},
        )
        context = WorkflowContext(inputs={}, results={})

        result = await step_instance.execute(context)

        invocation_result = result.output
        step_results = invocation_result.workflow_result.step_results

        assert len(step_results) == 2
        assert step_results[0].name == "sum"
        assert step_results[0].output == 5
        assert step_results[1].name == "product"
        assert step_results[1].output == 6


class TestSubWorkflowStepComplexScenarios:
    """Test SubWorkflowStep with complex scenarios."""

    @pytest.mark.asyncio
    async def test_execute_multiple_times_with_different_inputs(self) -> None:
        """Test that same step can be executed multiple times."""
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=simple_workflow,
            inputs={"value": 5},
        )
        context1 = WorkflowContext(inputs={}, results={})
        context2 = WorkflowContext(inputs={}, results={})

        result1 = await step_instance.execute(context1)
        result2 = await step_instance.execute(context2)

        assert result1.success is True
        assert result2.success is True
        assert result1.output.final_output == 10
        assert result2.output.final_output == 10

    @pytest.mark.asyncio
    async def test_execute_with_complex_workflow_result(self) -> None:
        """Test execute() with workflow that returns complex result."""

        @workflow(name="complex-workflow", description="Returns complex data")
        def complex_workflow(data: dict[str, Any]):
            result = yield step("process").python(
                action=lambda d: {
                    "processed": True,
                    "original": d,
                    "count": len(d),
                },
                args=(data,),
            )
            return result

        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=complex_workflow,
            inputs={"data": {"a": 1, "b": 2, "c": 3}},
        )
        context = WorkflowContext(inputs={}, results={})

        result = await step_instance.execute(context)

        assert result.success is True
        final_output = result.output.final_output
        assert final_output["processed"] is True
        assert final_output["count"] == 3

    @pytest.mark.asyncio
    async def test_execute_with_workflow_that_returns_none(self) -> None:
        """Test execute() with workflow that returns None."""

        @workflow(name="none-workflow", description="Returns None")
        def none_workflow():
            yield step("noop").python(action=lambda: None)
            return None

        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=none_workflow,
            inputs={},
        )
        context = WorkflowContext(inputs={}, results={})

        result = await step_instance.execute(context)

        assert result.success is True
        assert result.output.final_output is None

    @pytest.mark.asyncio
    async def test_step_result_serialization(self) -> None:
        """Test that StepResult from SubWorkflowStep can be serialized."""
        step_instance = SubWorkflowStep(
            name="test-step",
            workflow=simple_workflow,
            inputs={"value": 8},
        )
        context = WorkflowContext(inputs={}, results={})

        result = await step_instance.execute(context)

        # Should be able to serialize to dict
        result_dict = result.to_dict()

        assert result_dict["name"] == "test-step"
        assert result_dict["step_type"] == "subworkflow"
        assert result_dict["success"] is True
        assert "output" in result_dict
        assert result_dict["duration_ms"] >= 0
