"""Tests for prompt resolution hooks in execute_agent_step (036-prompt-config).

Verifies that execute_agent_step integrates with the prompt registry
to resolve default prompts for registered step names, applies user
overrides (prompt_suffix), falls back gracefully when the registry
module is unavailable or the step is unregistered, and propagates
PromptConfigError without swallowing it.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.dsl.context import WorkflowContext
from maverick.dsl.executor.result import ExecutorResult
from maverick.dsl.serialization.executor.handlers.agent_step import (
    execute_agent_step,
)
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import AgentStepRecord
from maverick.prompts.defaults import _clear_registry_cache
from maverick.prompts.models import (
    GENERIC_PROVIDER,
    OverridePolicy,
    PromptConfigError,
    PromptEntry,
)
from maverick.prompts.registry import PromptRegistry

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_agent_step(
    name: str = "test_step",
    agent: str = "test-agent",
) -> AgentStepRecord:
    """Create a minimal AgentStepRecord for testing."""
    return AgentStepRecord(name=name, type="agent", agent=agent)


class _MockAgentClass:
    """Minimal agent class for registry registration."""

    name = "test-agent"

    def __init__(self, **kwargs: Any) -> None:
        pass

    async def execute(self, context: Any) -> dict[str, str]:
        return {"status": "done"}


def _make_registry(agent_name: str = "test-agent") -> ComponentRegistry:
    """Create a ComponentRegistry with a single registered agent."""
    registry = ComponentRegistry()
    registry.agents.register(agent_name, _MockAgentClass, validate=False)
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
    maverick_config: Any = None,
) -> WorkflowContext:
    """Create a WorkflowContext with optional overrides."""
    return WorkflowContext(
        inputs=inputs or {},
        step_executor=step_executor,
        maverick_config=maverick_config,
    )


def _make_prompt_registry(
    step_name: str,
    text: str = "Default prompt text.",
    policy: OverridePolicy = OverridePolicy.AUGMENT_ONLY,
) -> PromptRegistry:
    """Create a PromptRegistry with a single entry for the given step name."""
    entries = {
        (step_name, GENERIC_PROVIDER): PromptEntry(
            text=text,
            policy=policy,
        ),
    }
    return PromptRegistry(entries)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_prompt_cache() -> None:
    """Clear the prompt registry cache before each test."""
    _clear_registry_cache()


# ---------------------------------------------------------------------------
# T056-agent: resolve_prompt() integration hook in agent step
# ---------------------------------------------------------------------------


class TestAgentStepPromptResolutionHook:
    """Prompt resolution integration tests for execute_agent_step."""

    @pytest.mark.asyncio
    async def test_registered_step_uses_resolved_default_prompt(self) -> None:
        """When registry has an entry for step.name, resolved text is used
        as the 'instructions' argument to executor.execute()."""
        mock_executor = _make_mock_executor(output="resolved_output")
        registry = _make_registry()
        step = _make_agent_step(name="implement")
        context = _make_context(step_executor=mock_executor)

        prompt_reg = _make_prompt_registry(
            step_name="implement",
            text="You are the implementer agent.",
        )

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.agent_step"
                ".resolve_context_builder",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "maverick.prompts.defaults.build_default_registry",
                return_value=prompt_reg,
            ),
        ):
            result = await execute_agent_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

        # Verify executor was called with the resolved instructions
        mock_executor.execute.assert_awaited_once()
        call_kwargs = mock_executor.execute.call_args.kwargs
        instructions = call_kwargs["instructions"]
        assert instructions == "You are the implementer agent."
        assert result.result == "resolved_output"

    @pytest.mark.asyncio
    async def test_prompt_suffix_override_appended_to_default(self) -> None:
        """When user configures prompt_suffix via maverick_config.prompts,
        it should be appended to the default prompt from the registry."""
        from maverick.config import ModelConfig

        mock_executor = _make_mock_executor(output="suffix_output")
        registry = _make_registry()
        step = _make_agent_step(name="commit_message")
        # Set up maverick_config with a prompt override
        mock_config = MagicMock()

        # PromptOverrideConfig-like object
        mock_override = MagicMock()
        mock_override.prompt_suffix = "Always reference JIRA ticket."
        mock_override.prompt_file = None
        mock_config.prompts = {"commit_message": mock_override}
        mock_config.steps = {}
        mock_config.agents = {}
        mock_config.model = ModelConfig()

        context = _make_context(
            step_executor=mock_executor,
            maverick_config=mock_config,
        )

        prompt_reg = _make_prompt_registry(
            step_name="commit_message",
            text="Generate a commit message.",
            policy=OverridePolicy.REPLACE,
        )

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.agent_step"
                ".resolve_context_builder",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "maverick.prompts.defaults.build_default_registry",
                return_value=prompt_reg,
            ),
        ):
            result = await execute_agent_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

        mock_executor.execute.assert_awaited_once()
        call_kwargs = mock_executor.execute.call_args.kwargs
        instructions = call_kwargs["instructions"]
        # Suffix should appear in the resolved text
        assert "Always reference JIRA ticket." in instructions
        # Original base text should also appear
        assert "Generate a commit message." in instructions
        assert result.result == "suffix_output"

    @pytest.mark.asyncio
    async def test_unregistered_step_uses_no_instructions(self) -> None:
        """When step.name is NOT in the prompt registry, instructions
        should be None (no override from registry)."""
        mock_executor = _make_mock_executor(output="no_registry_output")
        registry = _make_registry()
        # "unknown_step" is NOT in the prompt registry
        step = _make_agent_step(name="unknown_step")
        context = _make_context(step_executor=mock_executor)

        # Registry with a different step name
        prompt_reg = _make_prompt_registry(
            step_name="implement",
            text="You are the implementer.",
        )

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.agent_step"
                ".resolve_context_builder",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "maverick.prompts.defaults.build_default_registry",
                return_value=prompt_reg,
            ),
        ):
            result = await execute_agent_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

        mock_executor.execute.assert_awaited_once()
        call_kwargs = mock_executor.execute.call_args.kwargs
        # No registry entry for "unknown_step", so instructions should be None
        assert call_kwargs["instructions"] is None
        assert result.result == "no_registry_output"

    @pytest.mark.asyncio
    async def test_resolution_failure_falls_back_gracefully(self) -> None:
        """If build_default_registry raises, execute_agent_step continues
        without error and passes instructions=None to the executor."""
        mock_executor = _make_mock_executor(output="graceful_output")
        registry = _make_registry()
        step = _make_agent_step(name="implement")
        context = _make_context(step_executor=mock_executor)

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.agent_step"
                ".resolve_context_builder",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "maverick.prompts.defaults.build_default_registry",
                side_effect=RuntimeError("registry construction failed"),
            ),
        ):
            result = await execute_agent_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

        # Should succeed despite registry failure
        mock_executor.execute.assert_awaited_once()
        call_kwargs = mock_executor.execute.call_args.kwargs
        assert call_kwargs["instructions"] is None
        assert result.result == "graceful_output"

    @pytest.mark.asyncio
    async def test_prompt_config_error_propagates(self) -> None:
        """PromptConfigError from resolve_prompt is NOT swallowed — it
        propagates to the caller so the user sees the configuration mistake."""
        mock_executor = _make_mock_executor(output="never_reached")
        registry = _make_registry()
        step = _make_agent_step(name="implement")
        context = _make_context(step_executor=mock_executor)

        prompt_reg = _make_prompt_registry(
            step_name="implement",
            text="You are the implementer.",
            policy=OverridePolicy.AUGMENT_ONLY,
        )

        def _resolve_prompt_raises(**kwargs: Any) -> None:
            raise PromptConfigError("Invalid prompt configuration")

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.agent_step"
                ".resolve_context_builder",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "maverick.prompts.defaults.build_default_registry",
                return_value=prompt_reg,
            ),
            patch(
                "maverick.prompts.resolver.resolve_prompt",
                side_effect=PromptConfigError("Invalid prompt configuration"),
            ),
            pytest.raises(PromptConfigError, match="Invalid prompt configuration"),
        ):
            await execute_agent_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

        # Executor should NOT have been called — error occurred before execution
        mock_executor.execute.assert_not_awaited()
