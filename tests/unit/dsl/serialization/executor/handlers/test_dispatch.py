"""Tests for dispatch_agent_mode and build_agent_prompt (T010-T011).

Verifies that dispatch_agent_mode constructs the correct prompt from
intent + resolved inputs, delegates to StepExecutor, and returns a
DispatchResult with correct metadata.
"""

from __future__ import annotations

import dataclasses
from typing import Any
from unittest.mock import AsyncMock, patch

from pydantic import BaseModel

from maverick.dsl.context import WorkflowContext
from maverick.dsl.executor.config import StepConfig
from maverick.dsl.executor.result import ExecutorResult
from maverick.dsl.serialization.executor.handlers.dispatch import (
    DispatchResult,
    _structurally_equivalent,
    apply_autonomy_gate,
    build_agent_prompt,
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


# ---------------------------------------------------------------------------
# T010: dispatch_agent_mode constructs prompt and calls StepExecutor
# ---------------------------------------------------------------------------


class TestDispatchAgentModePromptAndExecution:
    """T010: dispatch_agent_mode builds prompt from intent + inputs, calls executor."""

    async def test_builds_prompt_from_intent_and_inputs(self) -> None:
        """dispatch_agent_mode passes intent-derived prompt to StepExecutor."""
        mock_executor = _make_mock_executor(output={"data": "from_agent"})
        registry = _make_registry()
        step = _make_step()
        context = _make_context(step_executor=mock_executor)
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER)

        with patch(
            "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
            return_value="Do something useful with the data.",
        ):
            await dispatch_agent_mode(
                step=step,
                resolved_inputs={"key": "value"},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        # Verify StepExecutor.execute was called
        mock_executor.execute.assert_awaited_once()

        call_kwargs = mock_executor.execute.call_args.kwargs
        assert call_kwargs["step_name"] == "test_step"
        assert call_kwargs["agent_name"] == "dispatch"

        # Verify intent appears in instructions
        assert "Do something useful with the data." in call_kwargs["instructions"]

        # Verify resolved inputs appear in prompt
        assert '"key": "value"' in call_kwargs["prompt"]

    async def test_calls_step_executor_execute(self) -> None:
        """dispatch_agent_mode calls context.step_executor.execute()."""
        mock_executor = _make_mock_executor()
        registry = _make_registry()
        step = _make_step()
        context = _make_context(step_executor=mock_executor)
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER)

        with patch(
            "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
            return_value="Test intent description.",
        ):
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        mock_executor.execute.assert_awaited_once()
        assert isinstance(result, DispatchResult)

    async def test_falls_back_when_no_intent(self) -> None:
        """dispatch_agent_mode falls back to deterministic when no intent found."""
        action_fn = lambda **kw: "deterministic_result"  # noqa: E731
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=_make_mock_executor())
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER)

        with patch(
            "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
            return_value=None,
        ):
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        assert result.fallback_used is True
        assert result.mode_used == StepMode.DETERMINISTIC
        assert result.output == "deterministic_result"

    async def test_falls_back_when_no_step_executor(self) -> None:
        """dispatch_agent_mode falls back when no step_executor on context."""
        action_fn = lambda **kw: "fallback_result"  # noqa: E731
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=None)
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER)

        with patch(
            "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
            return_value="Some intent",
        ):
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        assert result.fallback_used is True
        assert result.mode_used == StepMode.DETERMINISTIC
        assert result.output == "fallback_result"

    async def test_operator_autonomy_falls_back(self) -> None:
        """dispatch_agent_mode falls back for OPERATOR autonomy (defense-in-depth)."""
        action_fn = lambda **kw: "operator_fallback"  # noqa: E731
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=_make_mock_executor())
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.OPERATOR)

        # Operator should never reach agent path. get_intent should not even be called.
        result = await dispatch_agent_mode(
            step=step,
            resolved_inputs={},
            context=context,
            registry=registry,
            step_config=step_config,
        )

        assert result.fallback_used is True
        assert result.mode_used == StepMode.DETERMINISTIC
        assert result.output == "operator_fallback"


# ---------------------------------------------------------------------------
# T011: dispatch_agent_mode returns DispatchResult with correct metadata
# ---------------------------------------------------------------------------


class TestDispatchResultMetadata:
    """T011: dispatch_agent_mode returns DispatchResult with correct fields."""

    async def test_approver_result_metadata(self) -> None:
        """Approver autonomy: agent result accepted directly."""
        mock_executor = _make_mock_executor(output="approved_output")
        registry = _make_registry()
        step = _make_step()
        context = _make_context(step_executor=mock_executor)
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER)

        with patch(
            "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
            return_value="Approve this step.",
        ):
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        assert isinstance(result, DispatchResult)
        assert result.output == "approved_output"
        assert result.mode_used == StepMode.AGENT
        assert result.fallback_used is False
        assert result.autonomy_level == AutonomyLevel.APPROVER
        assert result.agent_result_accepted is True
        assert result.validation_details is not None

    async def test_dispatch_result_to_dict(self) -> None:
        """DispatchResult.to_dict() returns serializable metadata."""
        result = DispatchResult(
            output="test",
            mode_used=StepMode.AGENT,
            fallback_used=False,
            autonomy_level=AutonomyLevel.COLLABORATOR,
            agent_result_accepted=True,
            validation_details="Collaborator: agent result matches",
        )

        d = result.to_dict()

        assert d["mode_used"] == "agent"
        assert d["fallback_used"] is False
        assert d["autonomy_level"] == "collaborator"
        assert d["agent_result_accepted"] is True
        assert "Collaborator" in d["validation_details"]

    async def test_fallback_result_metadata(self) -> None:
        """Fallback result has correct metadata."""
        action_fn = lambda **kw: "fallback_out"  # noqa: E731
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=None)
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.CONSULTANT)

        with patch(
            "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
            return_value="Intent here.",
        ):
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        assert result.mode_used == StepMode.DETERMINISTIC
        assert result.fallback_used is True
        assert result.agent_result_accepted is False
        assert result.validation_details is not None


# ---------------------------------------------------------------------------
# build_agent_prompt unit tests
# ---------------------------------------------------------------------------


class TestBuildAgentPrompt:
    """Tests for the build_agent_prompt helper."""

    def test_basic_prompt_construction(self) -> None:
        """Intent and inputs appear in instructions and prompt."""
        instructions, prompt = build_agent_prompt(
            intent="Format a greeting message.",
            resolved_inputs={"name": "World"},
        )

        assert "Format a greeting message." in instructions
        assert '"name": "World"' in prompt

    def test_prompt_suffix_appended(self) -> None:
        """prompt_suffix is appended to instructions."""
        instructions, _ = build_agent_prompt(
            intent="Do something.",
            resolved_inputs={},
            prompt_suffix="Additional guidance here.",
        )

        assert "Additional guidance here." in instructions

    def test_prompt_file_content_appended(self) -> None:
        """prompt_file_content is appended to instructions."""
        instructions, _ = build_agent_prompt(
            intent="Do something.",
            resolved_inputs={},
            prompt_file_content="Content from file.",
        )

        assert "Content from file." in instructions

    def test_returns_tuple(self) -> None:
        """build_agent_prompt returns a tuple of (instructions, prompt)."""
        result = build_agent_prompt(
            intent="Test intent.",
            resolved_inputs={"x": 1},
        )

        assert isinstance(result, tuple)
        assert len(result) == 2
        instructions, prompt = result
        assert isinstance(instructions, str)
        assert isinstance(prompt, str)


# ---------------------------------------------------------------------------
# T014: apply_autonomy_gate at Operator level
# ---------------------------------------------------------------------------


class TestAutonomyGateOperator:
    """T014: Operator is caught upstream; apply_autonomy_gate rejects it."""

    async def test_operator_raises_value_error(self) -> None:
        """Operator autonomy should never reach apply_autonomy_gate directly.

        Operator is intercepted by dispatch_agent_mode(). If it somehow
        reaches apply_autonomy_gate, a ValueError is raised as a safety net.
        """
        import pytest

        action_fn = lambda **kw: "det_result"  # noqa: E731

        with pytest.raises(ValueError, match="Unknown autonomy level"):
            await apply_autonomy_gate(
                agent_result="agent_result",
                autonomy_level=AutonomyLevel.OPERATOR,
                deterministic_action=action_fn,
                resolved_inputs={},
                step_name="test_step",
            )


# ---------------------------------------------------------------------------
# T015: apply_autonomy_gate at Collaborator level
# ---------------------------------------------------------------------------


class TestAutonomyGateCollaborator:
    """T015: Collaborator re-executes deterministic and compares."""

    async def test_collaborator_accepts_matching_result(self) -> None:
        """Collaborator accepts when agent matches deterministic."""
        action_fn = lambda **kw: {"key": "shared_value"}  # noqa: E731

        result = await apply_autonomy_gate(
            agent_result={"key": "shared_value"},
            autonomy_level=AutonomyLevel.COLLABORATOR,
            deterministic_action=action_fn,
            resolved_inputs={},
            step_name="test_step",
        )

        assert isinstance(result, DispatchResult)
        assert result.output == {"key": "shared_value"}
        assert result.mode_used == StepMode.AGENT
        assert result.fallback_used is False
        assert result.autonomy_level == AutonomyLevel.COLLABORATOR
        assert result.agent_result_accepted is True
        assert result.validation_details is not None
        assert "matches" in result.validation_details

    async def test_collaborator_rejects_mismatched_result(self) -> None:
        """Collaborator rejects when agent differs from deterministic."""
        action_fn = lambda **kw: "det_value"  # noqa: E731

        result = await apply_autonomy_gate(
            agent_result="agent_value",
            autonomy_level=AutonomyLevel.COLLABORATOR,
            deterministic_action=action_fn,
            resolved_inputs={},
            step_name="test_step",
        )

        assert isinstance(result, DispatchResult)
        assert result.output == "det_value"
        assert result.mode_used == StepMode.DETERMINISTIC
        assert result.fallback_used is False
        assert result.autonomy_level == AutonomyLevel.COLLABORATOR
        assert result.agent_result_accepted is False
        assert result.validation_details is not None
        assert "differs" in result.validation_details


# ---------------------------------------------------------------------------
# T016: apply_autonomy_gate at Collaborator with side effects
# ---------------------------------------------------------------------------


class TestAutonomyGateCollaboratorSideEffect:
    """T016: Collaborator on side-effecting action auto-downgrades to Consultant."""

    async def test_side_effect_action_downgrades_to_consultant(self) -> None:
        """Side-effecting action at Collaborator downgrades."""

        def action_with_side_effects(**kw: Any) -> str:
            return "result"

        class _Metadata:
            has_side_effects = True

        action_with_side_effects._metadata = _Metadata()  # type: ignore[attr-defined]

        result = await apply_autonomy_gate(
            agent_result="agent_result",
            autonomy_level=AutonomyLevel.COLLABORATOR,
            deterministic_action=action_with_side_effects,
            resolved_inputs={},
            step_name="test_step",
        )

        assert isinstance(result, DispatchResult)
        # Should be accepted (Consultant accepts agent result)
        assert result.agent_result_accepted is True
        assert result.mode_used == StepMode.AGENT
        # Autonomy level should reflect Consultant (the downgrade target)
        assert result.autonomy_level == AutonomyLevel.CONSULTANT
        assert result.validation_details is not None
        assert "Consultant" in result.validation_details


# ---------------------------------------------------------------------------
# T017: apply_autonomy_gate at Consultant level
# ---------------------------------------------------------------------------


class TestAutonomyGateConsultant:
    """T017: Consultant verifies output contract and accepts."""

    async def test_consultant_accepts_with_verified_contract(self) -> None:
        """Consultant verifies output and accepts agent result."""

        # Explicit return annotation (avoid __future__ stringification)
        def typed_action(**kw: Any) -> dict:  # noqa: UP006
            return {"key": "value"}

        # Force the return annotation to be the actual type, not a string
        typed_action.__annotations__["return"] = dict

        result = await apply_autonomy_gate(
            agent_result={"key": "value"},
            autonomy_level=AutonomyLevel.CONSULTANT,
            deterministic_action=typed_action,
            resolved_inputs={},
            step_name="test_step",
        )

        assert isinstance(result, DispatchResult)
        assert result.output == {"key": "value"}
        assert result.mode_used == StepMode.AGENT
        assert result.fallback_used is False
        assert result.autonomy_level == AutonomyLevel.CONSULTANT
        assert result.agent_result_accepted is True
        assert result.validation_details is not None
        assert "verified" in result.validation_details
        # No discrepancies when types match
        assert "discrepancies" not in result.validation_details

    async def test_consultant_logs_discrepancies(self) -> None:
        """Consultant logs type discrepancies but still accepts."""

        # Explicit return annotation (avoid __future__ stringification)
        def typed_action(**kw: Any) -> dict:  # noqa: UP006
            return {"key": "value"}

        # Force the return annotation to be the actual type, not a string
        typed_action.__annotations__["return"] = dict

        result = await apply_autonomy_gate(
            agent_result="not_a_dict",
            autonomy_level=AutonomyLevel.CONSULTANT,
            deterministic_action=typed_action,
            resolved_inputs={},
            step_name="test_step",
        )

        assert isinstance(result, DispatchResult)
        # Consultant still accepts, but with discrepancies noted
        assert result.output == "not_a_dict"
        assert result.mode_used == StepMode.AGENT
        assert result.agent_result_accepted is True
        assert result.autonomy_level == AutonomyLevel.CONSULTANT
        assert result.validation_details is not None
        assert "discrepancies" in result.validation_details
        assert "dict" in result.validation_details
        assert "str" in result.validation_details


# ---------------------------------------------------------------------------
# T018: apply_autonomy_gate at Approver level
# ---------------------------------------------------------------------------


class TestAutonomyGateApprover:
    """T018: Approver accepts agent result directly."""

    async def test_approver_accepts_directly(self) -> None:
        """Approver accepts agent result without validation."""
        action_fn = lambda **kw: "unused_deterministic"  # noqa: E731

        result = await apply_autonomy_gate(
            agent_result="agent_output",
            autonomy_level=AutonomyLevel.APPROVER,
            deterministic_action=action_fn,
            resolved_inputs={},
            step_name="test_step",
        )

        assert isinstance(result, DispatchResult)
        assert result.output == "agent_output"
        assert result.mode_used == StepMode.AGENT
        assert result.fallback_used is False
        assert result.autonomy_level == AutonomyLevel.APPROVER
        assert result.agent_result_accepted is True
        assert result.validation_details is not None
        assert "Approver" in result.validation_details


# ---------------------------------------------------------------------------
# T019: _structurally_equivalent with various types
# ---------------------------------------------------------------------------


class TestStructurallyEquivalent:
    """T019: _structurally_equivalent with various types."""

    def test_equal_dicts(self) -> None:
        """Equal dicts are structurally equivalent."""
        assert (
            _structurally_equivalent(
                {"a": 1, "b": "two"},
                {"a": 1, "b": "two"},
            )
            is True
        )

    def test_different_dicts(self) -> None:
        """Dicts with different values are not equivalent."""
        assert (
            _structurally_equivalent(
                {"a": 1, "b": "two"},
                {"a": 1, "b": "three"},
            )
            is False
        )

    def test_equal_lists(self) -> None:
        """Equal lists are structurally equivalent."""
        assert _structurally_equivalent([1, 2, 3], [1, 2, 3]) is True

    def test_different_lists(self) -> None:
        """Lists with different elements are not equivalent."""
        assert _structurally_equivalent([1, 2, 3], [1, 2, 4]) is False

    def test_dataclass_comparison(self) -> None:
        """Dataclasses with same field values are structurally equivalent."""

        @dataclasses.dataclass
        class Point:
            x: int
            y: int

        assert _structurally_equivalent(Point(1, 2), Point(1, 2)) is True
        assert _structurally_equivalent(Point(1, 2), Point(3, 4)) is False

    def test_pydantic_model_comparison(self) -> None:
        """Pydantic models with same field values are structurally equivalent."""

        class Item(BaseModel):
            name: str
            count: int

        assert (
            _structurally_equivalent(
                Item(name="a", count=1),
                Item(name="a", count=1),
            )
            is True
        )
        assert (
            _structurally_equivalent(
                Item(name="a", count=1),
                Item(name="b", count=2),
            )
            is False
        )

    def test_type_mismatch(self) -> None:
        """Values of different types are not structurally equivalent."""
        assert _structurally_equivalent({"a": 1}, [1]) is False
        assert _structurally_equivalent(42, "42") is False

    def test_nested_structures(self) -> None:
        """Nested structures are compared recursively."""
        a = {"outer": {"inner": [1, 2, {"deep": True}]}}
        b = {"outer": {"inner": [1, 2, {"deep": True}]}}
        c = {"outer": {"inner": [1, 2, {"deep": False}]}}

        assert _structurally_equivalent(a, b) is True
        assert _structurally_equivalent(a, c) is False


# ---------------------------------------------------------------------------
# T043: Edge case — mode: agent with no intent falls back with warning
# ---------------------------------------------------------------------------


class TestEdgeCaseNoIntentWarning:
    """T043: mode=agent with no intent description falls back with warning."""

    async def test_no_intent_falls_back_with_warning_log(self) -> None:
        """Fallback on no intent emits dispatch.no_intent warning."""
        action_fn = lambda **kw: "fallback"  # noqa: E731
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=_make_mock_executor())
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER)

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
                return_value=None,
            ),
            patch(
                "maverick.dsl.serialization.executor.handlers.dispatch.logger"
            ) as mock_logger,
        ):
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        assert result.fallback_used is True
        # Verify warning was logged with correct event name
        warning_calls = [
            c
            for c in mock_logger.warning.call_args_list
            if c.args and c.args[0] == "dispatch.no_intent"
        ]
        assert len(warning_calls) >= 1
        assert warning_calls[0].kwargs["step_name"] == "test_step"


# ---------------------------------------------------------------------------
# T044: Edge case — mode: agent with no StepExecutor falls back with warning
# ---------------------------------------------------------------------------


class TestEdgeCaseNoExecutorWarning:
    """T044: mode=agent with no StepExecutor falls back with warning."""

    async def test_no_executor_falls_back_with_warning_log(self) -> None:
        """Fallback on no executor emits dispatch.no_executor warning."""
        action_fn = lambda **kw: "fallback"  # noqa: E731
        registry = _make_registry(action_fn=action_fn)
        step = _make_step()
        context = _make_context(step_executor=None)
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER)

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
                return_value="Some intent",
            ),
            patch(
                "maverick.dsl.serialization.executor.handlers.dispatch.logger"
            ) as mock_logger,
        ):
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        assert result.fallback_used is True
        warning_calls = [
            c
            for c in mock_logger.warning.call_args_list
            if c.args and c.args[0] == "dispatch.no_executor"
        ]
        assert len(warning_calls) >= 1
        assert warning_calls[0].kwargs["step_name"] == "test_step"


# ---------------------------------------------------------------------------
# T056: resolve_prompt() integration hook in dispatch (036-prompt-config)
# ---------------------------------------------------------------------------


class TestDispatchPromptResolutionHook:
    """T056: dispatch_agent_mode uses resolve_prompt() for registered steps."""

    async def test_registered_step_uses_resolved_prompt(self) -> None:
        """When step.name is in the prompt registry, resolved text is used."""
        mock_executor = _make_mock_executor(output="resolved_output")
        registry = _make_registry()
        # Use "implement" — a step name that IS in the default registry
        step = _make_step(name="implement")
        context = _make_context(step_executor=mock_executor)
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER)

        with patch(
            "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
            return_value="Implement the feature.",
        ):
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={"task": "build widget"},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        assert isinstance(result, DispatchResult)
        assert result.output == "resolved_output"

        # Verify the executor was called with resolved instructions from registry
        call_kwargs = mock_executor.execute.call_args.kwargs
        instructions = call_kwargs["instructions"]
        # The resolved prompt comes from IMPLEMENTER_SYSTEM_PROMPT_TEMPLATE,
        # NOT the intent-based "You are executing a workflow step" prefix
        assert "You are executing a workflow step" not in instructions

    async def test_unregistered_step_falls_back_to_build_agent_prompt(self) -> None:
        """When step.name is NOT in the registry, build_agent_prompt is used."""
        mock_executor = _make_mock_executor(output="fallback_output")
        registry = _make_registry()
        # "test_step" is NOT in the default prompt registry
        step = _make_step(name="test_step")
        context = _make_context(step_executor=mock_executor)
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER)

        with patch(
            "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
            return_value="Do something useful.",
        ):
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={"key": "value"},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        assert isinstance(result, DispatchResult)
        assert result.output == "fallback_output"

        # Verify intent-based instructions were used (build_agent_prompt path)
        call_kwargs = mock_executor.execute.call_args.kwargs
        instructions = call_kwargs["instructions"]
        assert "You are executing a workflow step" in instructions
        assert "Do something useful." in instructions

    async def test_prompt_suffix_applied_via_resolve_prompt(self) -> None:
        """prompt_suffix applied via resolve_prompt for registered steps."""
        mock_executor = _make_mock_executor(output="suffix_output")
        registry = _make_registry()
        step = _make_step(name="commit_message")  # registered with REPLACE policy
        context = _make_context(step_executor=mock_executor)
        step_config = StepConfig(
            mode=StepMode.AGENT,
            autonomy=AutonomyLevel.APPROVER,
            prompt_suffix="Always include ticket number.",
        )

        with patch(
            "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
            return_value="Generate a commit message.",
        ):
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        assert isinstance(result, DispatchResult)
        call_kwargs = mock_executor.execute.call_args.kwargs
        instructions = call_kwargs["instructions"]
        # Suffix should be appended by resolve_prompt
        assert "Always include ticket number." in instructions
        # Should NOT be the intent-based format
        assert "You are executing a workflow step" not in instructions

    async def test_resolution_failure_falls_back_gracefully(self) -> None:
        """If resolve_prompt raises, dispatch falls back to build_agent_prompt."""
        mock_executor = _make_mock_executor(output="graceful_output")
        registry = _make_registry()
        step = _make_step(name="implement")
        context = _make_context(step_executor=mock_executor)
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER)

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
                return_value="Build the thing.",
            ),
            patch(
                "maverick.prompts.defaults.build_default_registry",
                side_effect=RuntimeError("registry construction failed"),
            ),
        ):
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={"x": 1},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        assert isinstance(result, DispatchResult)
        assert result.output == "graceful_output"

        # Should have fallen back to build_agent_prompt
        call_kwargs = mock_executor.execute.call_args.kwargs
        instructions = call_kwargs["instructions"]
        assert "You are executing a workflow step" in instructions
        assert "Build the thing." in instructions

    async def test_resolved_prompt_includes_inputs_in_user_prompt(self) -> None:
        """When resolve_prompt is used, inputs are still passed as the user prompt."""
        mock_executor = _make_mock_executor(output="input_output")
        registry = _make_registry()
        step = _make_step(name="review")  # registered step
        context = _make_context(step_executor=mock_executor)
        step_config = StepConfig(mode=StepMode.AGENT, autonomy=AutonomyLevel.APPROVER)

        with patch(
            "maverick.dsl.serialization.executor.handlers.dispatch.get_intent",
            return_value="Review the code.",
        ):
            result = await dispatch_agent_mode(
                step=step,
                resolved_inputs={"diff": "--- a/file.py\n+++ b/file.py"},
                context=context,
                registry=registry,
                step_config=step_config,
            )

        assert isinstance(result, DispatchResult)
        call_kwargs = mock_executor.execute.call_args.kwargs
        prompt = call_kwargs["prompt"]
        assert "diff" in prompt
        assert "file.py" in prompt
