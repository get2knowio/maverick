"""Tests for dispatch_agent_mode fallback safety (T022-T027).

Verifies that dispatch_agent_mode correctly falls back to deterministic
execution when the agent executor raises, times out, or produces invalid
results, and that errors propagate when both agent and deterministic fail.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from maverick.dsl.context import WorkflowContext
from maverick.dsl.executor.config import StepConfig
from maverick.dsl.executor.result import ExecutorResult
from maverick.dsl.serialization.executor.handlers.dispatch import (
    DispatchResult,
    dispatch_agent_mode,
)
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import PythonStepRecord
from maverick.dsl.types import AutonomyLevel, StepMode

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_step(
    name: str = "test_step",
    action: str = "my_action",
) -> PythonStepRecord:
    """Create a minimal PythonStepRecord for testing."""
    return PythonStepRecord(name=name, action=action)


def _make_registry(
    action_name: str = "my_action",
    action_fn: Any = None,
) -> ComponentRegistry:
    """Create a ComponentRegistry with a single registered action."""
    registry = ComponentRegistry()
    if action_fn is None:
        action_fn = lambda **kw: {"result": "deterministic"}  # noqa: E731
    registry.actions.register(action_name, action_fn)
    return registry


def _make_failing_executor(
    error: Exception | None = None,
) -> AsyncMock:
    """Create a mock StepExecutor whose execute() raises an exception."""
    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(
        side_effect=error or RuntimeError("agent failed"),
    )
    return mock_executor


def _make_hanging_executor() -> AsyncMock:
    """Create a mock StepExecutor that never completes (timeout)."""

    async def _hang(**kwargs: Any) -> ExecutorResult:
        await asyncio.sleep(100)
        # Should never reach here due to timeout
        return ExecutorResult(output="unreachable", success=True, usage=None, events=())

    mock_executor = AsyncMock()
    mock_executor.execute = _hang
    return mock_executor


def _make_mock_executor(output: Any = "agent_output") -> AsyncMock:
    """Create a mock StepExecutor that returns a successful ExecutorResult."""
    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(
        return_value=ExecutorResult(
            output=output,
            success=True,
            usage=None,
            events=(),
        ),
    )
    return mock_executor


def _make_context(
    inputs: dict[str, Any] | None = None,
    step_executor: Any = None,
) -> WorkflowContext:
    """Create a WorkflowContext with optional overrides."""
    return WorkflowContext(
        inputs=inputs or {},
        step_executor=step_executor,
    )


# ---------------------------------------------------------------------------
# T022: Fallback on StepExecutor exception
# ---------------------------------------------------------------------------


class TestFallbackOnExecutorException:
    """T022: Agent exception triggers deterministic fallback."""

    async def test_fallback_on_executor_exception(self) -> None:
        """Agent exception triggers deterministic fallback."""
        failing_executor = _make_failing_executor(RuntimeError("agent blew up"))
        action_fn = lambda **kw: {"result": "deterministic_output"}  # noqa: E731
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=failing_executor)
        step_config = StepConfig(
            mode=StepMode.AGENT,
            autonomy=AutonomyLevel.APPROVER,
        )

        with patch(
            "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
            return_value="Test intent",
        ):
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        assert isinstance(result, DispatchResult)
        assert result.fallback_used is True
        assert result.mode_used == StepMode.DETERMINISTIC
        assert result.output == {"result": "deterministic_output"}


# ---------------------------------------------------------------------------
# T023: Fallback on StepExecutor timeout
# ---------------------------------------------------------------------------


class TestFallbackOnExecutorTimeout:
    """T023: Agent timeout triggers deterministic fallback."""

    async def test_fallback_on_executor_timeout(self) -> None:
        """Agent timeout triggers deterministic fallback."""
        hanging_executor = _make_hanging_executor()
        action_fn = lambda **kw: {"result": "timeout_fallback"}  # noqa: E731
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=hanging_executor)
        step_config = StepConfig(
            mode=StepMode.AGENT,
            autonomy=AutonomyLevel.APPROVER,
            timeout=1,
        )

        with patch(
            "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
            return_value="Test intent",
        ):
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        assert isinstance(result, DispatchResult)
        assert result.fallback_used is True
        assert result.mode_used == StepMode.DETERMINISTIC
        assert result.output == {"result": "timeout_fallback"}


# ---------------------------------------------------------------------------
# T024: Fallback on agent result schema violation
# ---------------------------------------------------------------------------


class TestFallbackOnSchemaViolation:
    """T024: Schema violation in agent result is caught by autonomy gate."""

    async def test_fallback_on_schema_violation(self) -> None:
        """Schema violation in agent result is caught by autonomy gate.

        When COLLABORATOR autonomy compares agent result against deterministic
        output and they differ, the deterministic result is used instead.
        """
        # Agent returns a bad/different result
        mock_executor = _make_mock_executor(output={"wrong": "schema"})

        # Deterministic action returns the correct result
        action_fn = lambda **kw: {"correct": "output"}  # noqa: E731
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=mock_executor)
        step_config = StepConfig(
            mode=StepMode.AGENT,
            autonomy=AutonomyLevel.COLLABORATOR,
        )

        with patch(
            "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
            return_value="Test intent",
        ):
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        assert isinstance(result, DispatchResult)
        assert result.agent_result_accepted is False
        assert result.output == {"correct": "output"}
        assert result.autonomy_level == AutonomyLevel.COLLABORATOR


# ---------------------------------------------------------------------------
# T025: Fallback reuses already-resolved inputs
# ---------------------------------------------------------------------------


class TestFallbackReusesResolvedInputs:
    """T025: Fallback deterministic handler receives the SAME resolved_inputs."""

    async def test_fallback_reuses_resolved_inputs(self) -> None:
        """Fallback deterministic handler receives the SAME resolved_inputs."""
        captured_inputs: list[dict[str, Any]] = []

        def tracking_action(**kw: Any) -> dict[str, Any]:
            captured_inputs.append(dict(kw))
            return {"tracked": True}

        failing_executor = _make_failing_executor(RuntimeError("agent failed"))
        registry = _make_registry(action_fn=tracking_action)
        step = _make_step()
        context = _make_context(step_executor=failing_executor)
        step_config = StepConfig(
            mode=StepMode.AGENT,
            autonomy=AutonomyLevel.APPROVER,
        )
        resolved = {"x": 42, "name": "hello"}

        with patch(
            "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
            return_value="Test intent",
        ):
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs=resolved,
                context=context,
                registry=registry,
                step_config=step_config,
            )

        assert result.fallback_used is True
        assert len(captured_inputs) == 1
        assert captured_inputs[0] == resolved


# ---------------------------------------------------------------------------
# T026: Error propagates when no deterministic handler exists
# ---------------------------------------------------------------------------


class TestErrorPropagatesWhenNoDeterministicHandler:
    """T026: When deterministic handler also fails, error propagates as RuntimeError."""

    async def test_error_propagates_when_no_deterministic_handler(self) -> None:
        """When deterministic handler also fails, error propagates as RuntimeError."""
        failing_executor = _make_failing_executor(RuntimeError("agent boom"))

        def broken_action(**kw: Any) -> None:
            raise TypeError("deterministic also broken")

        registry = _make_registry(action_fn=broken_action)
        step = _make_step()
        context = _make_context(step_executor=failing_executor)
        step_config = StepConfig(
            mode=StepMode.AGENT,
            autonomy=AutonomyLevel.APPROVER,
        )

        with patch(
            "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
            return_value="Test intent",
        ):
            with pytest.raises(RuntimeError, match="Both agent and deterministic"):
                await dispatch_agent_mode(
                    step=step,
                    resolved_inputs={},
                    context=context,
                    registry=registry,
                    step_config=step_config,
                )


# ---------------------------------------------------------------------------
# T027: Both agent AND deterministic fail -> RuntimeError with both messages
# ---------------------------------------------------------------------------


class TestBothAgentAndDeterministicFail:
    """T027: When both fail, RuntimeError includes both error messages."""

    async def test_both_agent_and_deterministic_fail(self) -> None:
        """When both fail, RuntimeError includes both error messages."""
        failing_executor = _make_failing_executor(ValueError("agent failed"))

        def broken_action(**kw: Any) -> None:
            raise TypeError("det failed")

        registry = _make_registry(action_fn=broken_action)
        step = _make_step()
        context = _make_context(step_executor=failing_executor)
        step_config = StepConfig(
            mode=StepMode.AGENT,
            autonomy=AutonomyLevel.APPROVER,
        )

        with patch(
            "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
            return_value="Test intent",
        ):
            with pytest.raises(RuntimeError) as exc_info:
                await dispatch_agent_mode(
                    step=step,
                    resolved_inputs={},
                    context=context,
                    registry=registry,
                    step_config=step_config,
                )

        error_msg = str(exc_info.value)
        assert "agent failed" in error_msg
        assert "det failed" in error_msg
