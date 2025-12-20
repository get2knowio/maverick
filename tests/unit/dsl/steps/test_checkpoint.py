"""Tests for CheckpointStep class."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from maverick.dsl.context import WorkflowContext
from maverick.dsl.results import StepResult
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.steps.checkpoint import CheckpointStep
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
    return WorkflowContext(inputs={"source": "test"})


class TestCheckpointStep:
    """Tests for CheckpointStep class."""

    # T073: checkpoint marks step for checkpointing
    async def test_checkpoint_marks_step(
        self, workflow_context: WorkflowContext
    ) -> None:
        """CheckpointStep should mark step for checkpointing."""
        inner = MockStep(name="inner_step", output="result_value")
        checkpoint_step = CheckpointStep(inner=inner)

        assert checkpoint_step.is_checkpoint is True
        assert checkpoint_step.name == "inner_step"
        assert checkpoint_step.step_type == inner.step_type

        result = await checkpoint_step.execute(workflow_context)
        assert result.success
        assert result.output == "result_value"
