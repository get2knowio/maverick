"""Tests for RollbackStep wrapper class."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from maverick.dsl.context import WorkflowContext
from maverick.dsl.results import StepResult
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.steps.rollback import RollbackStep
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
    return WorkflowContext(inputs={"name": "test_resource"})


class TestRollbackStep:
    """Tests for RollbackStep wrapper class."""

    # T047: rollback registered on success
    async def test_rollback_registered_on_success(
        self, workflow_context: WorkflowContext
    ) -> None:
        """When step succeeds, rollback should be registered in context."""
        mock = MockStep(name="create_resource", output="resource_id")

        rollback_called = []
        def cleanup(ctx):
            rollback_called.append(True)

        wrapped = RollbackStep(inner=mock, rollback_action=cleanup)

        result = await wrapped.execute(workflow_context)

        assert result.success is True
        assert len(workflow_context._pending_rollbacks) == 1
        assert workflow_context._pending_rollbacks[0].step_name == "create_resource"

    # T047: rollback not registered on failure
    async def test_rollback_not_registered_on_failure(
        self, workflow_context: WorkflowContext
    ) -> None:
        """When step fails, rollback should NOT be registered."""
        mock = MockStep(name="create_resource", should_fail=True)

        rollback_called = []
        def cleanup(ctx):
            rollback_called.append(True)

        wrapped = RollbackStep(inner=mock, rollback_action=cleanup)

        result = await wrapped.execute(workflow_context)

        assert result.success is False
        assert len(workflow_context._pending_rollbacks) == 0

    # T048: rollbacks run in reverse order (tested at engine level)
    # T048: continue on rollback error (tested at engine level)
