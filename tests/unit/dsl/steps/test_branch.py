"""Tests for BranchStep class."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from maverick.dsl.context import WorkflowContext
from maverick.dsl.results import BranchResult, StepResult
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.steps.branch import BranchOption, BranchStep
from maverick.dsl.types import StepType


@dataclass(frozen=True, slots=True)
class MockStep(StepDefinition):
    """Mock step for testing."""

    name: str = "mock_step"
    step_type: StepType = StepType.PYTHON
    output: Any = "mock_output"

    async def execute(self, context: WorkflowContext) -> StepResult:
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
    return WorkflowContext(inputs={"order_type": "express", "amount": 500})


@pytest.fixture
def large_order_context() -> WorkflowContext:
    """Create context for large order testing."""
    return WorkflowContext(inputs={"order_type": "standard", "amount": 1500})


class TestBranchStep:
    """Tests for BranchStep class."""

    # T026: first branch matches
    async def test_first_branch_matches(
        self, workflow_context: WorkflowContext
    ) -> None:
        """When first branch predicate matches, its step should execute."""
        # Create branch with 2 options where first matches
        first_step = MockStep(name="express_step", output="express_result")
        second_step = MockStep(name="standard_step", output="standard_result")

        branch = BranchStep(
            name="order_branch",
            options=(
                BranchOption(
                    predicate=lambda ctx: ctx.inputs.get("order_type") == "express",
                    step=first_step,
                ),
                BranchOption(
                    predicate=lambda ctx: ctx.inputs.get("order_type") == "standard",
                    step=second_step,
                ),
            ),
        )

        result = await branch.execute(workflow_context)

        assert result.success is True
        assert isinstance(result.output, BranchResult)
        assert result.output.selected_index == 0
        assert result.output.selected_step_name == "express_step"
        assert result.output.inner_output == "express_result"

    # T026: later branch matches
    async def test_later_branch_matches(
        self, large_order_context: WorkflowContext
    ) -> None:
        """When later branch predicate matches, its step should execute."""
        # Create branch where first predicate returns False, second returns True
        express_step = MockStep(name="express_step", output="express_result")
        large_order_step = MockStep(name="large_order_step", output="large_result")

        branch = BranchStep(
            name="order_branch",
            options=(
                BranchOption(
                    predicate=lambda ctx: ctx.inputs.get("order_type") == "express",
                    step=express_step,
                ),
                BranchOption(
                    predicate=lambda ctx: ctx.inputs.get("amount", 0) > 1000,
                    step=large_order_step,
                ),
            ),
        )

        result = await branch.execute(large_order_context)

        assert result.success is True
        assert isinstance(result.output, BranchResult)
        assert result.output.selected_index == 1
        assert result.output.selected_step_name == "large_order_step"
        assert result.output.inner_output == "large_result"

    # T027: no branch matches fails
    async def test_no_branch_matches_fails(
        self, workflow_context: WorkflowContext
    ) -> None:
        """When no branch matches, workflow should fail."""
        # Create branch where all predicates return False
        step1 = MockStep(name="step1", output="output1")
        step2 = MockStep(name="step2", output="output2")

        branch = BranchStep(
            name="failing_branch",
            options=(
                BranchOption(
                    predicate=lambda ctx: ctx.inputs.get("order_type") == "premium",
                    step=step1,
                ),
                BranchOption(
                    predicate=lambda ctx: ctx.inputs.get("amount", 0) > 10000,
                    step=step2,
                ),
            ),
        )

        result = await branch.execute(workflow_context)

        assert result.success is False
        assert result.output is None
        assert result.error is not None
        assert "No branch predicate matched" in result.error

    # T027: branch with missing step result
    async def test_branch_result_structure(
        self, workflow_context: WorkflowContext
    ) -> None:
        """BranchResult should contain selected_index, selected_step_name,
        and inner_output."""
        # Verify BranchResult has correct structure
        step = MockStep(name="test_step", output="test_output")

        branch = BranchStep(
            name="structure_test",
            options=(
                BranchOption(
                    predicate=lambda ctx: True,
                    step=step,
                ),
            ),
        )

        result = await branch.execute(workflow_context)

        assert result.success is True
        assert isinstance(result.output, BranchResult)

        # Verify BranchResult structure
        branch_result = result.output
        assert hasattr(branch_result, "selected_index")
        assert hasattr(branch_result, "selected_step_name")
        assert hasattr(branch_result, "inner_output")

        assert branch_result.selected_index == 0
        assert branch_result.selected_step_name == "test_step"
        assert branch_result.inner_output == "test_output"

    async def test_catch_all_branch(self, workflow_context: WorkflowContext) -> None:
        """Catch-all branch (lambda ctx: True) should always match."""
        # Create branch with catch-all as last option
        step1 = MockStep(name="specific_step", output="specific_result")
        catch_all_step = MockStep(name="catch_all_step", output="catch_all_result")

        branch = BranchStep(
            name="catch_all_branch",
            options=(
                BranchOption(
                    predicate=lambda ctx: ctx.inputs.get("order_type") == "premium",
                    step=step1,
                ),
                BranchOption(
                    predicate=lambda ctx: True,  # Catch-all
                    step=catch_all_step,
                ),
            ),
        )

        result = await branch.execute(workflow_context)

        assert result.success is True
        assert isinstance(result.output, BranchResult)
        assert result.output.selected_index == 1
        assert result.output.selected_step_name == "catch_all_step"
        assert result.output.inner_output == "catch_all_result"
