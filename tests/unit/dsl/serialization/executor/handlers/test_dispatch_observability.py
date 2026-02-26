"""Tests for structured observability events in dispatch (T035-T039).

Verifies that dispatch_agent_mode, apply_autonomy_gate, and
_run_deterministic_fallback emit correct structured log events via structlog
with the expected fields and values.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

from maverick.dsl.context import WorkflowContext
from maverick.dsl.executor.config import StepConfig
from maverick.dsl.executor.result import ExecutorResult
from maverick.dsl.serialization.executor.handlers.dispatch import (
    dispatch_agent_mode,
)
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import PythonStepRecord
from maverick.dsl.types import AutonomyLevel, StepMode

# ---------------------------------------------------------------------------
# Helpers / Factories
# ---------------------------------------------------------------------------

_DISPATCH_LOGGER = "maverick.dsl.serialization.executor.handlers.dispatch.logger"
_PYTHON_STEP_LOGGER = "maverick.dsl.serialization.executor.handlers.python_step.logger"


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
        action_fn = lambda **kw: {"result": "deterministic", **kw}  # noqa: E731
    registry.actions.register(action_name, action_fn)
    return registry


def _make_mock_executor(output: Any = "agent_output") -> AsyncMock:
    """Create a mock StepExecutor that returns a successful ExecutorResult."""
    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(
        return_value=ExecutorResult(
            output=output,
            success=True,
            usage=None,
            events=(),
        )
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


def _find_log_calls(
    mock_logger: MagicMock,
    event_name: str,
    level: str = "info",
) -> list[call]:
    """Find all log calls matching a given event name.

    Args:
        mock_logger: The patched logger mock.
        event_name: The structlog event name (first positional arg).
        level: The log level method name (info, warning, etc.).

    Returns:
        List of matching call objects.
    """
    method = getattr(mock_logger, level)
    return [c for c in method.call_args_list if c.args and c.args[0] == event_name]


# ---------------------------------------------------------------------------
# T035: dispatch.mode_selected event (via python_step.agent_dispatch)
# ---------------------------------------------------------------------------


class TestDispatchModeSelectedEvent:
    """T035: Mode selection event emitted."""

    async def test_agent_dispatch_log_emitted(self) -> None:
        """python_step.agent_dispatch logged when mode=AGENT."""
        from maverick.dsl.serialization.executor.handlers.python_step import (
            execute_python_step,
        )

        mock_executor = _make_mock_executor(output="agent_out")
        registry = _make_registry()
        step = _make_step()
        context = _make_context(step_executor=mock_executor)
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER)

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
                return_value="Test intent.",
            ),
            patch(_PYTHON_STEP_LOGGER) as mock_ps_logger,
            patch(_DISPATCH_LOGGER),
        ):
            await execute_python_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                config=step_config,
            )

        # python_step.agent_dispatch should have been logged
        calls = _find_log_calls(
            mock_ps_logger, "python_step.agent_dispatch", level="info"
        )
        assert len(calls) >= 1, (
            f"Expected 'python_step.agent_dispatch' log call, "
            f"got: {mock_ps_logger.info.call_args_list}"
        )
        kwargs = calls[0].kwargs
        assert kwargs["step_name"] == "test_step"
        assert kwargs["action"] == "my_action"
        assert kwargs["autonomy"] == "approver"

    async def test_agent_dispatch_log_includes_autonomy_level(self) -> None:
        """python_step.agent_dispatch includes the resolved autonomy level."""
        from maverick.dsl.serialization.executor.handlers.python_step import (
            execute_python_step,
        )

        mock_executor = _make_mock_executor(output="collab_out")
        action_fn = lambda **kw: {"result": "det"}  # noqa: E731
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=mock_executor)
        step_config = StepConfig(
            mode=StepMode.AGENT, autonomy=AutonomyLevel.COLLABORATOR
        )

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
                return_value="Collab intent.",
            ),
            patch(_PYTHON_STEP_LOGGER) as mock_ps_logger,
            patch(_DISPATCH_LOGGER),
        ):
            await execute_python_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                config=step_config,
            )

        calls = _find_log_calls(
            mock_ps_logger, "python_step.agent_dispatch", level="info"
        )
        assert len(calls) >= 1
        assert calls[0].kwargs["autonomy"] == "collaborator"


# ---------------------------------------------------------------------------
# T036: dispatch.agent_completed event
# ---------------------------------------------------------------------------


class TestDispatchAgentCompletedEvent:
    """T036: Agent completed event emitted with duration and acceptance."""

    async def test_agent_completed_event_fields(self) -> None:
        """dispatch.agent_completed emitted after successful agent execution."""
        mock_executor = _make_mock_executor(output="approved_result")
        registry = _make_registry()
        step = _make_step()
        context = _make_context(step_executor=mock_executor)
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER)

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
                return_value="Intent text.",
            ),
            patch(_DISPATCH_LOGGER) as mock_logger,
        ):
            await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        calls = _find_log_calls(mock_logger, "dispatch.agent_completed", level="info")
        assert len(calls) >= 1, (
            f"Expected 'dispatch.agent_completed' log call, "
            f"got: {mock_logger.info.call_args_list}"
        )
        kwargs = calls[0].kwargs
        assert kwargs["step_name"] == "test_step"
        assert kwargs["action"] == "my_action"
        assert kwargs["autonomy"] == "approver"
        assert "duration_ms" in kwargs
        assert isinstance(kwargs["duration_ms"], int)
        assert kwargs["duration_ms"] >= 0
        assert kwargs["accepted"] is True

    async def test_agent_completed_event_with_collaborator(self) -> None:
        """dispatch.agent_completed emitted for Collaborator autonomy."""
        det_result = {"result": "deterministic"}
        action_fn = lambda **kw: det_result  # noqa: E731
        mock_executor = _make_mock_executor(output=det_result)
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=mock_executor)
        step_config = StepConfig(
            mode=StepMode.AGENT, autonomy=AutonomyLevel.COLLABORATOR
        )

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
                return_value="Collab intent.",
            ),
            patch(_DISPATCH_LOGGER) as mock_logger,
        ):
            await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        calls = _find_log_calls(mock_logger, "dispatch.agent_completed", level="info")
        assert len(calls) >= 1
        kwargs = calls[0].kwargs
        assert kwargs["autonomy"] == "collaborator"


# ---------------------------------------------------------------------------
# T037: dispatch.autonomy_validation event
# ---------------------------------------------------------------------------


class TestDispatchAutonomyValidationEvent:
    """T037: Autonomy validation event emitted."""

    async def test_autonomy_validation_event_approver(self) -> None:
        """dispatch.autonomy_validation emitted for Approver with outcome=accepted."""
        mock_executor = _make_mock_executor(output="approved")
        registry = _make_registry()
        step = _make_step()
        context = _make_context(step_executor=mock_executor)
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER)

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
                return_value="Approve intent.",
            ),
            patch(_DISPATCH_LOGGER) as mock_logger,
        ):
            await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        calls = _find_log_calls(
            mock_logger, "dispatch.autonomy_validation", level="info"
        )
        assert len(calls) >= 1, (
            f"Expected 'dispatch.autonomy_validation' log call, "
            f"got: {mock_logger.info.call_args_list}"
        )
        kwargs = calls[0].kwargs
        assert kwargs["step_name"] == "test_step"
        assert kwargs["autonomy"] == "approver"
        assert kwargs["outcome"] == "accepted"

    async def test_autonomy_validation_event_collaborator_accepted(self) -> None:
        """Collaborator autonomy_validation emitted with outcome=accepted."""
        # Make agent return the same value as deterministic so validation passes
        det_result = {"value": 42}
        action_fn = lambda **kw: det_result  # noqa: E731
        mock_executor = _make_mock_executor(output=det_result)
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=mock_executor)
        step_config = StepConfig(
            mode=StepMode.AGENT, autonomy=AutonomyLevel.COLLABORATOR
        )

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
                return_value="Collab intent.",
            ),
            patch(_DISPATCH_LOGGER) as mock_logger,
        ):
            await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        calls = _find_log_calls(
            mock_logger, "dispatch.autonomy_validation", level="info"
        )
        assert len(calls) >= 1
        kwargs = calls[0].kwargs
        assert kwargs["step_name"] == "test_step"
        assert kwargs["autonomy"] == "collaborator"
        assert kwargs["outcome"] == "accepted"

    async def test_autonomy_validation_event_collaborator_rejected(self) -> None:
        """Collaborator autonomy_validation emitted with outcome=rejected."""
        # Agent returns different value than deterministic
        action_fn = lambda **kw: {"value": "deterministic"}  # noqa: E731
        mock_executor = _make_mock_executor(output={"value": "agent_different"})
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=mock_executor)
        step_config = StepConfig(
            mode=StepMode.AGENT, autonomy=AutonomyLevel.COLLABORATOR
        )

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
                return_value="Collab intent.",
            ),
            patch(_DISPATCH_LOGGER) as mock_logger,
        ):
            await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        calls = _find_log_calls(
            mock_logger, "dispatch.autonomy_validation", level="info"
        )
        assert len(calls) >= 1
        kwargs = calls[0].kwargs
        assert kwargs["step_name"] == "test_step"
        assert kwargs["autonomy"] == "collaborator"
        assert kwargs["outcome"] == "rejected"

    async def test_autonomy_validation_event_consultant_verified(self) -> None:
        """dispatch.autonomy_validation emitted for Consultant with outcome=verified."""
        mock_executor = _make_mock_executor(output="consultant_out")
        registry = _make_registry()
        step = _make_step()
        context = _make_context(step_executor=mock_executor)
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.CONSULTANT)

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
                return_value="Consult intent.",
            ),
            patch(_DISPATCH_LOGGER) as mock_logger,
        ):
            await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        calls = _find_log_calls(
            mock_logger, "dispatch.autonomy_validation", level="info"
        )
        assert len(calls) >= 1
        kwargs = calls[0].kwargs
        assert kwargs["step_name"] == "test_step"
        assert kwargs["autonomy"] == "consultant"
        assert kwargs["outcome"] == "verified"


# ---------------------------------------------------------------------------
# T038: dispatch.fallback event
# ---------------------------------------------------------------------------


class TestDispatchFallbackEvent:
    """T038: Fallback event emitted with failure reason."""

    async def test_fallback_event_on_exception(self) -> None:
        """dispatch.fallback emitted with reason=exception on agent error."""
        failing_executor = AsyncMock()
        failing_executor.execute = AsyncMock(side_effect=RuntimeError("agent exploded"))
        action_fn = lambda **kw: "fallback_result"  # noqa: E731
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=failing_executor)
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER)

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
                return_value="Fail intent.",
            ),
            patch(_DISPATCH_LOGGER) as mock_logger,
        ):
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        # Verify fallback event was emitted
        calls = _find_log_calls(mock_logger, "dispatch.fallback", level="warning")
        assert len(calls) >= 1, (
            f"Expected 'dispatch.fallback' warning log call, "
            f"got info={mock_logger.info.call_args_list}, "
            f"warning={mock_logger.warning.call_args_list}"
        )
        kwargs = calls[0].kwargs
        assert kwargs["step_name"] == "test_step"
        assert kwargs["action"] == "my_action"
        assert kwargs["reason"] == "exception"
        assert "duration_ms" in kwargs
        assert "error" in kwargs

        # Verify fallback was actually used
        assert result.fallback_used is True

    async def test_fallback_event_on_timeout(self) -> None:
        """dispatch.fallback emitted with reason=timeout on agent timeout."""

        async def slow_execute(**kwargs: Any) -> ExecutorResult:
            await asyncio.sleep(10)  # Will be cancelled by timeout
            return ExecutorResult(output="never", success=True, usage=None, events=())

        slow_executor = AsyncMock()
        slow_executor.execute = AsyncMock(side_effect=slow_execute)

        action_fn = lambda **kw: "timeout_fallback"  # noqa: E731
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=slow_executor)
        # Set a very short timeout to trigger TimeoutError
        step_config = StepConfig(
            mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER, timeout=1
        )

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
                return_value="Timeout intent.",
            ),
            patch(_DISPATCH_LOGGER) as mock_logger,
        ):
            # Manually simulate timeout by making executor raise TimeoutError
            slow_executor.execute = AsyncMock(side_effect=TimeoutError())
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        calls = _find_log_calls(mock_logger, "dispatch.fallback", level="warning")
        assert len(calls) >= 1, (
            f"Expected 'dispatch.fallback' warning log call with reason=timeout, "
            f"got: {mock_logger.warning.call_args_list}"
        )
        kwargs = calls[0].kwargs
        assert kwargs["step_name"] == "test_step"
        assert kwargs["action"] == "my_action"
        assert kwargs["reason"] == "timeout"
        assert "duration_ms" in kwargs

        assert result.fallback_used is True

    async def test_fallback_event_includes_error_message(self) -> None:
        """dispatch.fallback includes the original error string."""
        failing_executor = AsyncMock()
        failing_executor.execute = AsyncMock(
            side_effect=ValueError("validation failed: bad input")
        )
        action_fn = lambda **kw: "safe_result"  # noqa: E731
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=failing_executor)
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER)

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
                return_value="Error intent.",
            ),
            patch(_DISPATCH_LOGGER) as mock_logger,
        ):
            await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        calls = _find_log_calls(mock_logger, "dispatch.fallback", level="warning")
        assert len(calls) >= 1
        kwargs = calls[0].kwargs
        assert "validation failed: bad input" in kwargs["error"]


# ---------------------------------------------------------------------------
# T039: dispatch.deterministic_completed event
# ---------------------------------------------------------------------------


class TestDispatchDeterministicCompletedEvent:
    """T039: Deterministic completed event emitted."""

    async def test_deterministic_completed_event(self) -> None:
        """dispatch.deterministic_completed emitted after deterministic run."""
        action_fn = lambda **kw: "det_output"  # noqa: E731
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=None)  # No executor -> fallback
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER)

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
                return_value="Some intent.",
            ),
            patch(_DISPATCH_LOGGER) as mock_logger,
        ):
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        calls = _find_log_calls(
            mock_logger, "dispatch.deterministic_completed", level="info"
        )
        assert len(calls) >= 1, (
            f"Expected 'dispatch.deterministic_completed' log call, "
            f"got: {mock_logger.info.call_args_list}"
        )
        kwargs = calls[0].kwargs
        assert kwargs["step_name"] == "test_step"
        assert "duration_ms" in kwargs
        assert isinstance(kwargs["duration_ms"], int)
        assert kwargs["duration_ms"] >= 0

        # Verify the result is deterministic
        assert result.mode_used == StepMode.DETERMINISTIC
        assert result.output == "det_output"

    async def test_deterministic_completed_on_operator_autonomy(self) -> None:
        """dispatch.deterministic_completed emitted for Operator autonomy fallback."""
        action_fn = lambda **kw: "operator_output"  # noqa: E731
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=_make_mock_executor())
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.OPERATOR)

        with patch(_DISPATCH_LOGGER) as mock_logger:
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        calls = _find_log_calls(
            mock_logger, "dispatch.deterministic_completed", level="info"
        )
        assert len(calls) >= 1
        kwargs = calls[0].kwargs
        assert kwargs["step_name"] == "test_step"
        assert "duration_ms" in kwargs

        assert result.mode_used == StepMode.DETERMINISTIC
        assert result.fallback_used is True

    async def test_deterministic_completed_on_agent_failure_fallback(self) -> None:
        """deterministic_completed emitted after agent failure fallback."""
        failing_executor = AsyncMock()
        failing_executor.execute = AsyncMock(side_effect=RuntimeError("agent crashed"))
        action_fn = lambda **kw: "recovered"  # noqa: E731
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=failing_executor)
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER)

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
                return_value="Crash intent.",
            ),
            patch(_DISPATCH_LOGGER) as mock_logger,
        ):
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        # Both dispatch.fallback and dispatch.deterministic_completed should be logged
        fallback_calls = _find_log_calls(
            mock_logger, "dispatch.fallback", level="warning"
        )
        assert len(fallback_calls) >= 1

        det_calls = _find_log_calls(
            mock_logger, "dispatch.deterministic_completed", level="info"
        )
        assert len(det_calls) >= 1
        assert det_calls[0].kwargs["step_name"] == "test_step"
        assert "duration_ms" in det_calls[0].kwargs

        assert result.fallback_used is True
        assert result.output == "recovered"

    async def test_deterministic_completed_duration_non_negative(self) -> None:
        """dispatch.deterministic_completed duration_ms is always non-negative."""
        action_fn = lambda **kw: 99  # noqa: E731
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=None)
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.CONSULTANT)

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
                return_value="Quick intent.",
            ),
            patch(_DISPATCH_LOGGER) as mock_logger,
        ):
            await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        calls = _find_log_calls(
            mock_logger, "dispatch.deterministic_completed", level="info"
        )
        assert len(calls) >= 1
        assert calls[0].kwargs["duration_ms"] >= 0
