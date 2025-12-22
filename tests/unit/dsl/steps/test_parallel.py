"""Tests for ParallelStep class."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from maverick.dsl.context import WorkflowContext
from maverick.dsl.results import StepResult
from maverick.dsl.steps.base import StepDefinition
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
    return WorkflowContext(inputs={})


class TestParallelStep:
    """Tests for ParallelStep class."""

    # T071: parallel executes sequentially, returns ParallelResult
    async def test_parallel_executes_returns_result(
        self, workflow_context: WorkflowContext
    ) -> None:
        """Parallel step should execute all children and return ParallelResult."""
        from maverick.dsl.results import ParallelResult
        from maverick.dsl.steps.parallel import ParallelStep

        step1 = MockStep(name="s1", output="r1")
        step2 = MockStep(name="s2", output="r2")
        parallel = ParallelStep(
            name="parallel_group",
            step_type=StepType.PARALLEL,
            children=(step1, step2),
        )
        result = await parallel.execute(workflow_context)

        assert result.success
        assert isinstance(result.output, ParallelResult)
        assert len(result.output.child_results) == 2
        assert result.output[0].name == "s1"
        assert result.output[0].output == "r1"
        assert result.output[1].name == "s2"
        assert result.output[1].output == "r2"

        # Check that each child result is stored in context
        assert "s1" in workflow_context.results
        assert workflow_context.results["s1"].output == "r1"
        assert "s2" in workflow_context.results
        assert workflow_context.results["s2"].output == "r2"

    # T072: parallel detects duplicate names
    def test_parallel_duplicate_names_fails(self) -> None:
        """Parallel step should raise ValueError if children have duplicate names."""
        from maverick.dsl.steps.parallel import ParallelStep

        step1 = MockStep(name="duplicate", output="r1")
        step2 = MockStep(name="duplicate", output="r2")

        # Should raise ValueError at construction time
        with pytest.raises(ValueError) as exc_info:
            ParallelStep(
                name="parallel_group",
                step_type=StepType.PARALLEL,
                children=(step1, step2),
            )

        # Check error message includes the duplicate name
        assert "duplicate" in str(exc_info.value)
        assert "parallel_group" in str(exc_info.value)

    async def test_parallel_fail_fast(self, workflow_context: WorkflowContext) -> None:
        """Parallel step should stop on first failure."""
        from maverick.dsl.results import ParallelResult
        from maverick.dsl.steps.parallel import ParallelStep

        step1 = MockStep(name="s1", output="r1")
        step2 = MockStep(name="s2", should_fail=True)
        step3 = MockStep(name="s3", output="r3")
        parallel = ParallelStep(
            name="parallel_group",
            step_type=StepType.PARALLEL,
            children=(step1, step2, step3),
        )
        result = await parallel.execute(workflow_context)

        # Overall result should fail
        assert not result.success
        assert isinstance(result.output, ParallelResult)

        # Only first 2 children should have executed
        assert len(result.output.child_results) == 2
        assert result.output[0].name == "s1"
        assert result.output[0].success
        assert result.output[1].name == "s2"
        assert not result.output[1].success

        # s3 should not have executed
        assert "s3" not in workflow_context.results

        # s1 and s2 should be in context
        assert "s1" in workflow_context.results
        assert "s2" in workflow_context.results
