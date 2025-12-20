"""Tests for RetryStep wrapper class."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest

from maverick.dsl.context import WorkflowContext
from maverick.dsl.results import StepResult
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.steps.retry import RetryStep
from maverick.dsl.types import StepType


@dataclass(frozen=True, slots=True)
class FlakyStep(StepDefinition):
    """Mock step that fails N times before succeeding."""

    name: str = "flaky_step"
    step_type: StepType = StepType.PYTHON
    fail_count: int = 2  # Fail this many times before success
    output: Any = "success_output"
    _attempt_counter: list[int] | None = None  # Mutable counter

    def __post_init__(self) -> None:
        if self._attempt_counter is None:
            object.__setattr__(self, "_attempt_counter", [0])

    async def execute(self, context: WorkflowContext) -> StepResult:
        self._attempt_counter[0] += 1
        if self._attempt_counter[0] <= self.fail_count:
            return StepResult(
                name=self.name,
                step_type=self.step_type,
                success=False,
                output=None,
                duration_ms=10,
                error=f"Attempt {self._attempt_counter[0]} failed",
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
    return WorkflowContext(inputs={"url": "https://example.com"})


class TestRetryStep:
    """Tests for RetryStep wrapper class."""

    # T043: retry succeeds after N attempts
    async def test_retry_succeeds_after_attempts(
        self, workflow_context: WorkflowContext
    ) -> None:
        """Step should succeed after retrying past initial failures."""
        flaky = FlakyStep(fail_count=2, output="success_output")
        retry_step = RetryStep(
            inner=flaky,
            max_attempts=3,
            backoff_base=0.001,  # Fast for tests
            jitter=False,
        )

        result = await retry_step.execute(workflow_context)

        assert result.success is True
        assert result.output == "success_output"

    # T043: retry exhausts all attempts
    async def test_retry_exhausts_all_attempts(
        self, workflow_context: WorkflowContext
    ) -> None:
        """Step should fail after exhausting all retry attempts."""
        flaky = FlakyStep(fail_count=5, output=None)
        retry_step = RetryStep(
            inner=flaky,
            max_attempts=3,
            backoff_base=0.001,  # Fast for tests
            jitter=False,
        )

        result = await retry_step.execute(workflow_context)

        assert result.success is False

    # T043: step succeeds on first attempt (no retry triggered)
    async def test_succeeds_first_attempt_no_retry(
        self, workflow_context: WorkflowContext
    ) -> None:
        """When step succeeds first time, no retries should occur."""
        flaky = FlakyStep(fail_count=0, output="success_output")
        retry_step = RetryStep(
            inner=flaky,
            max_attempts=3,
            backoff_base=0.001,  # Fast for tests
            jitter=False,
        )

        result = await retry_step.execute(workflow_context)

        assert result.success is True
        assert result.output == "success_output"

    # T044: exponential backoff timing
    async def test_exponential_backoff_timing(
        self, workflow_context: WorkflowContext
    ) -> None:
        """Verify delays follow exponential backoff pattern."""
        flaky = FlakyStep(fail_count=5, output=None)  # Fail all attempts
        retry_step = RetryStep(
            inner=flaky,
            max_attempts=3,
            backoff_base=1.0,
            jitter=False,
        )

        with patch("asyncio.sleep") as mock_sleep:
            await retry_step.execute(workflow_context)

            # Should have 2 sleep calls (after attempt 1 and 2)
            # Exponential backoff: 1.0 * 2^0 = 1.0, 1.0 * 2^1 = 2.0
            assert mock_sleep.call_count == 2
            calls = [call[0][0] for call in mock_sleep.call_args_list]
            assert calls[0] == 1.0  # After 1st attempt
            assert calls[1] == 2.0  # After 2nd attempt

    # T044: jitter applied
    async def test_jitter_applied(
        self, workflow_context: WorkflowContext
    ) -> None:
        """Verify jitter is applied to backoff delays."""
        flaky = FlakyStep(fail_count=5, output=None)  # Fail all attempts
        retry_step = RetryStep(
            inner=flaky,
            max_attempts=3,
            backoff_base=1.0,
            jitter=True,
        )

        # Mock random.random to return a fixed value
        # Jitter calculation: delay *= 0.5 + random.random()
        # If random.random() returns 0.3, multiplier is 0.8
        with patch("asyncio.sleep") as mock_sleep, patch(
            "random.random", return_value=0.3
        ):
            await retry_step.execute(workflow_context)

            # Should have 2 sleep calls with jitter applied
            assert mock_sleep.call_count == 2
            calls = [call[0][0] for call in mock_sleep.call_args_list]
            # First delay: 1.0 * 0.8 = 0.8
            # Second delay: 2.0 * 0.8 = 1.6
            assert calls[0] == pytest.approx(0.8)
            assert calls[1] == pytest.approx(1.6)
