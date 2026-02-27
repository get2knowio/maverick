"""Tests for prompt resolution hooks in execute_generate_step (036-prompt-config).

Verifies that execute_generate_step integrates with the prompt registry
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
from maverick.dsl.serialization.executor.handlers.generate_step import (
    execute_generate_step,
)
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import GenerateStepRecord
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


def _make_generate_step(
    name: str = "test_step",
    generator: str = "test-generator",
) -> GenerateStepRecord:
    """Create a minimal GenerateStepRecord for testing."""
    return GenerateStepRecord(name=name, type="generate", generator=generator)


class _MockGenerator:
    """Minimal generator class with a generate method and system_prompt attr."""

    def __init__(self) -> None:
        self.system_prompt: str = "original system prompt"
        self._last_context: Any = None

    def generate(self, context: Any) -> str:
        self._last_context = context
        return f"generated with prompt: {self.system_prompt}"


class _MockGeneratorNoSystemPrompt:
    """Generator without a system_prompt attribute."""

    def generate(self, context: Any) -> str:
        return "generated without system_prompt"


def _make_registry(
    generator_name: str = "test-generator",
    generator_class: type | None = None,
) -> ComponentRegistry:
    """Create a ComponentRegistry with a single registered generator."""
    registry = ComponentRegistry()
    cls = generator_class or _MockGenerator
    registry.generators.register(generator_name, cls, validate=False)
    return registry


def _make_context(
    inputs: dict[str, Any] | None = None,
    maverick_config: Any = None,
) -> WorkflowContext:
    """Create a WorkflowContext with optional overrides."""
    return WorkflowContext(
        inputs=inputs or {},
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
# T056-generate: resolve_prompt() integration hook in generate step
# ---------------------------------------------------------------------------


class TestGenerateStepPromptResolutionHook:
    """Prompt resolution integration tests for execute_generate_step."""

    @pytest.mark.asyncio
    async def test_registered_step_uses_resolved_default_prompt(self) -> None:
        """When registry has an entry for step.name, resolved text is used
        as the system_prompt on the generator instance."""
        registry = _make_registry()
        step = _make_generate_step(name="commit_message")
        context = _make_context()

        prompt_reg = _make_prompt_registry(
            step_name="commit_message",
            text="You are a commit message generator.",
            policy=OverridePolicy.REPLACE,
        )

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.generate_step"
                ".resolve_context_builder",
                new_callable=AsyncMock,
                return_value={"diff": "some diff"},
            ),
            patch(
                "maverick.prompts.defaults.build_default_registry",
                return_value=prompt_reg,
            ),
        ):
            result = await execute_generate_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

        # The resolved prompt should appear in the output because
        # _MockGenerator.generate() embeds self.system_prompt in its return
        assert "You are a commit message generator." in result

    @pytest.mark.asyncio
    async def test_prompt_suffix_override_appended_to_default(self) -> None:
        """When user configures prompt_suffix via maverick_config.prompts,
        it should be appended to the default prompt and set on
        generator.system_prompt."""
        registry = _make_registry()
        step = _make_generate_step(name="pr_title")

        # Set up maverick_config with a prompt override
        mock_config = MagicMock()
        mock_override = MagicMock()
        mock_override.prompt_suffix = "Keep titles under 50 chars."
        mock_override.prompt_file = None
        mock_config.prompts = {"pr_title": mock_override}

        context = _make_context(maverick_config=mock_config)

        prompt_reg = _make_prompt_registry(
            step_name="pr_title",
            text="Generate a PR title.",
            policy=OverridePolicy.REPLACE,
        )

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.generate_step"
                ".resolve_context_builder",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "maverick.prompts.defaults.build_default_registry",
                return_value=prompt_reg,
            ),
        ):
            result = await execute_generate_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

        # Both base text and suffix should appear in the result
        # because _MockGenerator embeds system_prompt in output
        assert "Generate a PR title." in result
        assert "Keep titles under 50 chars." in result

    @pytest.mark.asyncio
    async def test_unregistered_step_preserves_original_system_prompt(self) -> None:
        """When step.name is NOT in the prompt registry,
        the generator's original system_prompt should remain unchanged."""
        registry = _make_registry()
        # "unknown_step" is NOT registered in the prompt registry
        step = _make_generate_step(name="unknown_step")
        context = _make_context()

        prompt_reg = _make_prompt_registry(
            step_name="commit_message",
            text="You are a commit message generator.",
        )

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.generate_step"
                ".resolve_context_builder",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "maverick.prompts.defaults.build_default_registry",
                return_value=prompt_reg,
            ),
        ):
            result = await execute_generate_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

        # Original system_prompt should be preserved (not overwritten)
        assert "original system prompt" in result

    @pytest.mark.asyncio
    async def test_resolution_failure_falls_back_gracefully(self) -> None:
        """If build_default_registry raises, execute_generate_step continues
        without error and the original system_prompt is preserved."""
        registry = _make_registry()
        step = _make_generate_step(name="commit_message")
        context = _make_context()

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.generate_step"
                ".resolve_context_builder",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "maverick.prompts.defaults.build_default_registry",
                side_effect=RuntimeError("registry construction failed"),
            ),
        ):
            result = await execute_generate_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

        # Should succeed despite registry failure; original prompt untouched
        assert "original system prompt" in result

    @pytest.mark.asyncio
    async def test_prompt_config_error_propagates(self) -> None:
        """PromptConfigError from resolve_prompt is NOT swallowed — it
        propagates to the caller so the user sees the configuration mistake."""
        registry = _make_registry()
        step = _make_generate_step(name="commit_message")
        context = _make_context()

        prompt_reg = _make_prompt_registry(
            step_name="commit_message",
            text="You are a commit message generator.",
            policy=OverridePolicy.AUGMENT_ONLY,
        )

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.generate_step"
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
                side_effect=PromptConfigError("Bad prompt config"),
            ),
            pytest.raises(PromptConfigError, match="Bad prompt config"),
        ):
            await execute_generate_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

    @pytest.mark.asyncio
    async def test_generator_without_system_prompt_attr_no_error(self) -> None:
        """When generator instance lacks system_prompt attr, prompt resolution
        skips assignment without error."""
        registry = _make_registry(
            generator_class=_MockGeneratorNoSystemPrompt,
        )
        step = _make_generate_step(name="commit_message")
        context = _make_context()

        prompt_reg = _make_prompt_registry(
            step_name="commit_message",
            text="You are a commit message generator.",
            policy=OverridePolicy.REPLACE,
        )

        with (
            patch(
                "maverick.dsl.serialization.executor.handlers.generate_step"
                ".resolve_context_builder",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "maverick.prompts.defaults.build_default_registry",
                return_value=prompt_reg,
            ),
        ):
            result = await execute_generate_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

        # Generator without system_prompt should still work
        assert result == "generated without system_prompt"
