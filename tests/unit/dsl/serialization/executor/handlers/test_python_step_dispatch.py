"""Tests for mode-aware dispatch in execute_python_step (T006-T009).

Verifies that execute_python_step correctly routes execution based on
StepConfig.mode — defaulting to deterministic, and delegating to
dispatch_agent_mode when mode is AGENT.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.dsl.context import WorkflowContext
from maverick.dsl.executor.config import StepConfig
from maverick.dsl.serialization.executor.handlers.dispatch import (
    DispatchResult,
)
from maverick.dsl.serialization.executor.handlers.python_step import (
    execute_python_step,
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
    config: dict[str, Any] | None = None,
) -> PythonStepRecord:
    """Create a minimal PythonStepRecord for testing."""
    return PythonStepRecord(name=name, action=action, config=config)


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


def _make_context(
    inputs: dict[str, Any] | None = None,
    step_executor: Any = None,
    maverick_config: Any = None,
) -> WorkflowContext:
    """Create a WorkflowContext with optional overrides."""
    return WorkflowContext(
        inputs=inputs or {},
        step_executor=step_executor,
        maverick_config=maverick_config,
    )


# ---------------------------------------------------------------------------
# T006: No mode/autonomy config defaults to DETERMINISTIC+OPERATOR
# ---------------------------------------------------------------------------


class TestDefaultDeterministic:
    """T006: No mode/autonomy config -> deterministic with zero behavior change."""

    async def test_no_config_calls_action_directly(self) -> None:
        """With no StepConfig, execute_python_step calls action directly."""
        action_fn = MagicMock(return_value={"status": "ok"})
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context()

        result = await execute_python_step(
            step=step,
            resolved_inputs={"key": "value"},
            context=context,
            registry=registry,
            config=None,
        )

        action_fn.assert_called_once_with(key="value")
        assert result == {"status": "ok"}

    async def test_default_step_config_calls_action_directly(self) -> None:
        """With default StepConfig (mode=None), action is called directly."""
        action_fn = MagicMock(return_value=42)
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context()

        # Default StepConfig has mode=None which should infer DETERMINISTIC for python
        result = await execute_python_step(
            step=step,
            resolved_inputs={},
            context=context,
            registry=registry,
            config=StepConfig(),
        )

        action_fn.assert_called_once_with()
        assert result == 42

    async def test_explicit_deterministic_mode_calls_action_directly(self) -> None:
        """StepConfig(mode=DETERMINISTIC) explicitly runs deterministic path."""
        action_fn = MagicMock(return_value="hello")
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context()

        result = await execute_python_step(
            step=step,
            resolved_inputs={"greeting": "hi"},
            context=context,
            registry=registry,
            config=StepConfig(mode=StepMode.DETERMINISTIC),
        )

        action_fn.assert_called_once_with(greeting="hi")
        assert result == "hello"


# ---------------------------------------------------------------------------
# T007: mode: deterministic regression
# ---------------------------------------------------------------------------


class TestDeterministicModeRegression:
    """T007: mode=deterministic calls action directly (regression)."""

    async def test_deterministic_with_async_action(self) -> None:
        """Deterministic mode awaits async actions correctly."""

        async def async_action(**kwargs: Any) -> dict[str, Any]:
            return {"async": True, **kwargs}

        registry = _make_registry(action_fn=async_action)
        step = _make_step()
        context = _make_context()

        result = await execute_python_step(
            step=step,
            resolved_inputs={"x": 1},
            context=context,
            registry=registry,
            config=StepConfig(mode=StepMode.DETERMINISTIC),
        )

        assert result == {"async": True, "x": 1}

    async def test_deterministic_does_not_call_dispatch(self) -> None:
        """Deterministic mode never invokes dispatch_agent_mode."""
        action_fn = MagicMock(return_value="det")
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context()

        with patch(
            "maverick.dsl.serialization.executor.handlers.python_step.dispatch_agent_mode"
        ) as mock_dispatch:
            result = await execute_python_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                config=StepConfig(mode=StepMode.DETERMINISTIC),
            )

        mock_dispatch.assert_not_called()
        assert result == "det"

    async def test_deterministic_preserves_failure_dict(self) -> None:
        """Deterministic mode still raises on success=False dicts."""
        action_fn = MagicMock(return_value={"success": False, "error": "boom"})
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context()

        with pytest.raises(RuntimeError, match="boom"):
            await execute_python_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                config=StepConfig(mode=StepMode.DETERMINISTIC),
            )


# ---------------------------------------------------------------------------
# T008: mode: agent delegates to dispatch_agent_mode
# ---------------------------------------------------------------------------


class TestAgentModeDispatch:
    """T008: mode=agent delegates to dispatch_agent_mode."""

    async def test_agent_mode_calls_dispatch(self) -> None:
        """Agent mode delegates to dispatch_agent_mode and returns its output."""
        action_fn = MagicMock(return_value="det_value")
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context()

        dispatch_result = DispatchResult(
            output="agent_value",
            mode_used=StepMode.AGENT,
            fallback_used=False,
            autonomy_level=AutonomyLevel.APPROVER,
            agent_result_accepted=True,
            validation_details=None,
        )

        with patch(
            "maverick.dsl.serialization.executor.handlers.python_step.dispatch_agent_mode",
            new_callable=AsyncMock,
            return_value=dispatch_result,
        ) as mock_dispatch:
            result = await execute_python_step(
                step=step,
                resolved_inputs={"a": 1},
                context=context,
                registry=registry,
                config=StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER),
            )

        mock_dispatch.assert_awaited_once()
        # execute_python_step returns DispatchResult.output, not the full DispatchResult
        assert result == "agent_value"

    async def test_agent_mode_does_not_call_action_directly(self) -> None:
        """Agent mode should NOT call the action directly."""
        action_fn = MagicMock(return_value="should_not_be_called")
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context()

        dispatch_result = DispatchResult(
            output="from_agent",
            mode_used=StepMode.AGENT,
            fallback_used=False,
            autonomy_level=AutonomyLevel.APPROVER,
            agent_result_accepted=True,
            validation_details=None,
        )

        with patch(
            "maverick.dsl.serialization.executor.handlers.python_step.dispatch_agent_mode",
            new_callable=AsyncMock,
            return_value=dispatch_result,
        ):
            result = await execute_python_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                config=StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER),
            )

        # The action should NOT be called in agent mode
        action_fn.assert_not_called()
        assert result == "from_agent"

    async def test_agent_mode_passes_step_config(self) -> None:
        """Agent mode passes the StepConfig to dispatch_agent_mode."""
        action_fn = MagicMock(return_value="det")
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context()

        step_config = StepConfig(
            mode=StepMode.AGENT,
            autonomy=AutonomyLevel.COLLABORATOR,
            timeout=120,
        )

        dispatch_result = DispatchResult(
            output="agent_out",
            mode_used=StepMode.AGENT,
            fallback_used=False,
            autonomy_level=AutonomyLevel.COLLABORATOR,
            agent_result_accepted=True,
            validation_details=None,
        )

        with patch(
            "maverick.dsl.serialization.executor.handlers.python_step.dispatch_agent_mode",
            new_callable=AsyncMock,
            return_value=dispatch_result,
        ) as mock_dispatch:
            await execute_python_step(
                step=step,
                resolved_inputs={"x": 1},
                context=context,
                registry=registry,
                config=step_config,
            )

        call_kwargs = mock_dispatch.call_args.kwargs
        assert call_kwargs["step_config"] is step_config

    async def test_force_deterministic_overrides_agent_mode(self) -> None:
        """force_deterministic in context.inputs overrides agent mode."""
        action_fn = MagicMock(return_value="forced_det")
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(inputs={"force_deterministic": True})

        with patch(
            "maverick.dsl.serialization.executor.handlers.python_step.dispatch_agent_mode",
            new_callable=AsyncMock,
        ) as mock_dispatch:
            result = await execute_python_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                config=StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER),
            )

        # Should NOT dispatch to agent when force_deterministic is set
        mock_dispatch.assert_not_called()
        action_fn.assert_called_once()
        assert result == "forced_det"


# ---------------------------------------------------------------------------
# T009: Non-PYTHON step types don't break with mode config
# ---------------------------------------------------------------------------


class TestNonPythonStepSafety:
    """T009: execute_python_step only handles PythonStepRecord."""

    async def test_handler_works_without_mode_config(self) -> None:
        """Handler works normally when no config is provided."""
        action_fn = MagicMock(return_value="works")
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context()

        result = await execute_python_step(
            step=step,
            resolved_inputs={},
            context=context,
            registry=registry,
        )

        assert result == "works"

    async def test_force_deterministic_string_true(self) -> None:
        """force_deterministic='true' (string) also overrides agent mode."""
        action_fn = MagicMock(return_value="forced_det_str")
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(inputs={"force_deterministic": "true"})

        with patch(
            "maverick.dsl.serialization.executor.handlers.python_step.dispatch_agent_mode",
            new_callable=AsyncMock,
        ) as mock_dispatch:
            result = await execute_python_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                config=StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER),
            )

        mock_dispatch.assert_not_called()
        action_fn.assert_called_once()
        assert result == "forced_det_str"

    async def test_force_deterministic_string_false_allows_agent(self) -> None:
        """force_deterministic='false' (string) does NOT block agent mode."""
        action_fn = MagicMock(return_value="det_value")
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(inputs={"force_deterministic": "false"})

        dispatch_result = DispatchResult(
            output="agent_value",
            mode_used=StepMode.AGENT,
            fallback_used=False,
            autonomy_level=AutonomyLevel.APPROVER,
            agent_result_accepted=True,
            validation_details=None,
        )

        with patch(
            "maverick.dsl.serialization.executor.handlers.python_step.dispatch_agent_mode",
            new_callable=AsyncMock,
            return_value=dispatch_result,
        ) as mock_dispatch:
            result = await execute_python_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                config=StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER),
            )

        # String "false" should NOT force deterministic — agent dispatch should proceed
        mock_dispatch.assert_awaited_once()
        action_fn.assert_not_called()
        assert result == "agent_value"

    async def test_force_deterministic_bool_false_allows_agent(self) -> None:
        """force_deterministic=False (bool) does NOT block agent mode."""
        action_fn = MagicMock(return_value="det_value")
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(inputs={"force_deterministic": False})

        dispatch_result = DispatchResult(
            output="agent_value",
            mode_used=StepMode.AGENT,
            fallback_used=False,
            autonomy_level=AutonomyLevel.APPROVER,
            agent_result_accepted=True,
            validation_details=None,
        )

        with patch(
            "maverick.dsl.serialization.executor.handlers.python_step.dispatch_agent_mode",
            new_callable=AsyncMock,
            return_value=dispatch_result,
        ) as mock_dispatch:
            result = await execute_python_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                config=StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER),
            )

        mock_dispatch.assert_awaited_once()
        action_fn.assert_not_called()
        assert result == "agent_value"

    async def test_handler_ignores_non_step_config_objects(self) -> None:
        """Handler still works when config is not a StepConfig (e.g., plain dict)."""
        action_fn = MagicMock(return_value="still_works")
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context()

        # Passing a plain dict as config (legacy behavior)
        result = await execute_python_step(
            step=step,
            resolved_inputs={},
            context=context,
            registry=registry,
            config={"some": "legacy_config"},
        )

        action_fn.assert_called_once()
        assert result == "still_works"
