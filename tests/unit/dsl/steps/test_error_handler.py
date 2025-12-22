"""Tests for ErrorHandlerStep wrapper class."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from maverick.dsl.context import WorkflowContext
from maverick.dsl.results import SkipMarker, StepResult
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.steps.error_handler import ErrorHandlerStep
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
    return WorkflowContext(inputs={"source": "primary"})


class TestErrorHandlerStep:
    """Tests for ErrorHandlerStep wrapper class."""

    # T045: on_error fallback succeeds
    async def test_on_error_fallback_succeeds(
        self, workflow_context: WorkflowContext
    ) -> None:
        """When primary fails and fallback succeeds, result should be success."""
        primary = MockStep(name="primary", should_fail=True)
        fallback = MockStep(name="fallback", output="fallback_output")

        def handler(ctx: WorkflowContext, failed_result: StepResult) -> StepDefinition:
            return fallback

        wrapped = ErrorHandlerStep(
            inner=primary,
            on_error_handler=handler,
        )

        result = await wrapped.execute(workflow_context)

        assert result.success is True
        assert result.output == "fallback_output"

    # T045: fallback fails
    async def test_fallback_fails(self, workflow_context: WorkflowContext) -> None:
        """When both primary and fallback fail, result should be failure."""
        primary = MockStep(name="primary", should_fail=True)
        fallback = MockStep(name="fallback", should_fail=True)

        def handler(ctx: WorkflowContext, failed_result: StepResult) -> StepDefinition:
            return fallback

        wrapped = ErrorHandlerStep(
            inner=primary,
            on_error_handler=handler,
        )

        result = await wrapped.execute(workflow_context)

        assert result.success is False

    # T046: skip_on_error converts failure to skip
    async def test_skip_on_error_converts_failure(
        self, workflow_context: WorkflowContext
    ) -> None:
        """When step fails with skip_on_error, should return SkipMarker."""
        primary = MockStep(name="primary", should_fail=True)

        wrapped = ErrorHandlerStep(
            inner=primary,
            skip_on_error=True,
        )

        result = await wrapped.execute(workflow_context)

        assert result.success is True
        assert isinstance(result.output, SkipMarker)
        assert result.output.reason == "error_skipped"

    async def test_skip_on_error_success_passes_through(
        self, workflow_context: WorkflowContext
    ) -> None:
        """When step succeeds with skip_on_error, result passes through."""
        primary = MockStep(name="primary", output="success_output")

        wrapped = ErrorHandlerStep(
            inner=primary,
            skip_on_error=True,
        )

        result = await wrapped.execute(workflow_context)

        assert result.success is True
        assert result.output == "success_output"
