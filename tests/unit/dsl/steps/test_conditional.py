"""Tests for ConditionalStep wrapper class."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from maverick.dsl.context import WorkflowContext
from maverick.dsl.results import SkipMarker, StepResult
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.steps.conditional import ConditionalStep
from maverick.dsl.types import StepType


@dataclass(frozen=True, slots=True)
class MockStep(StepDefinition):
    """Mock step for testing."""

    name: str = "mock_step"
    step_type: StepType = StepType.PYTHON
    output: Any = "mock_output"
    should_fail: bool = False

    async def execute(self, context: WorkflowContext) -> StepResult:
        if self.should_fail:
            return StepResult(
                name=self.name,
                step_type=self.step_type,
                success=False,
                output=None,
                duration_ms=10,
                error="Mock failure",
            )
        return StepResult(
            name=self.name,
            step_type=self.step_type,
            success=True,
            output=self.output,
            duration_ms=10,
        )

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "step_type": self.step_type.value}


@pytest.fixture
def workflow_context() -> WorkflowContext:
    """Create a basic workflow context for testing."""
    return WorkflowContext(inputs={"env": "prod", "skip_tests": False})


@pytest.fixture
def mock_step_result() -> StepResult:
    """Create a mock successful step result."""
    return StepResult(
        name="inner_step",
        step_type=StepType.PYTHON,
        success=True,
        output="inner_output",
        duration_ms=100,
    )


class TestConditionalStep:
    """Tests for ConditionalStep wrapper class."""

    # T024: predicate returns True - step executes
    async def test_predicate_true_executes_step(
        self, workflow_context: WorkflowContext
    ) -> None:
        """When predicate returns True, inner step should execute."""
        # Arrange
        mock_step = MockStep(output="expected_output")
        conditional_step = ConditionalStep(
            inner=mock_step,
            predicate=lambda ctx: True,
        )

        # Act
        result = await conditional_step.execute(workflow_context)

        # Assert
        assert result.success is True
        assert result.output == "expected_output"
        assert result.name == "mock_step"
        assert result.step_type == StepType.PYTHON
        assert not isinstance(result.output, SkipMarker)

    # T024: predicate returns False - step skipped
    async def test_predicate_false_skips_step(
        self, workflow_context: WorkflowContext
    ) -> None:
        """When predicate returns False, step should be skipped with SkipMarker."""
        # Arrange
        mock_step = MockStep(output="should_not_see_this")
        conditional_step = ConditionalStep(
            inner=mock_step,
            predicate=lambda ctx: False,
        )

        # Act
        result = await conditional_step.execute(workflow_context)

        # Assert
        assert result.success is True
        assert isinstance(result.output, SkipMarker)
        assert result.output.reason == "predicate_false"
        assert result.name == "mock_step"
        assert result.step_type == StepType.PYTHON

    # T025: predicate raises exception - step skipped
    async def test_predicate_exception_skips_step(
        self, workflow_context: WorkflowContext
    ) -> None:
        """When predicate raises exception, step should be skipped."""
        # Arrange
        def raising_predicate(ctx: WorkflowContext) -> bool:
            raise ValueError("Something went wrong")

        mock_step = MockStep(output="should_not_see_this")
        conditional_step = ConditionalStep(
            inner=mock_step,
            predicate=raising_predicate,
        )

        # Act
        result = await conditional_step.execute(workflow_context)

        # Assert
        assert result.success is True
        assert isinstance(result.output, SkipMarker)
        assert result.output.reason == "predicate_exception"
        assert result.name == "mock_step"
        assert result.step_type == StepType.PYTHON

    # T025: predicate returns non-bool - workflow fails
    async def test_predicate_non_bool_fails(
        self, workflow_context: WorkflowContext
    ) -> None:
        """When predicate returns non-bool, TypeError should be raised."""
        # Arrange
        mock_step = MockStep(output="should_not_see_this")
        conditional_step = ConditionalStep(
            inner=mock_step,
            predicate=lambda ctx: "true",  # String instead of bool
        )

        # Act & Assert
        with pytest.raises(TypeError, match="must return bool, got str"):
            await conditional_step.execute(workflow_context)

    async def test_async_predicate_true(
        self, workflow_context: WorkflowContext
    ) -> None:
        """Async predicates should work correctly when returning True."""
        # Arrange
        async def async_predicate(ctx: WorkflowContext) -> bool:
            return True

        mock_step = MockStep(output="async_output")
        conditional_step = ConditionalStep(
            inner=mock_step,
            predicate=async_predicate,
        )

        # Act
        result = await conditional_step.execute(workflow_context)

        # Assert
        assert result.success is True
        assert result.output == "async_output"
        assert result.name == "mock_step"
        assert result.step_type == StepType.PYTHON
        assert not isinstance(result.output, SkipMarker)

    async def test_async_predicate_false(
        self, workflow_context: WorkflowContext
    ) -> None:
        """Async predicates should work correctly when returning False."""
        # Arrange
        async def async_predicate(ctx: WorkflowContext) -> bool:
            return False

        mock_step = MockStep(output="should_not_see_this")
        conditional_step = ConditionalStep(
            inner=mock_step,
            predicate=async_predicate,
        )

        # Act
        result = await conditional_step.execute(workflow_context)

        # Assert
        assert result.success is True
        assert isinstance(result.output, SkipMarker)
        assert result.output.reason == "predicate_false"
        assert result.name == "mock_step"
        assert result.step_type == StepType.PYTHON
