"""Tests for component registry validation (type checking and signature validation).

This module tests the validation logic that ensures components meet the expected
contracts before being registered in the DSL registries.
"""

from __future__ import annotations

from typing import Any

import pytest

from maverick.agents.base import MaverickAgent
from maverick.agents.generators.base import GeneratorAgent
from maverick.dsl.serialization.registry import (
    ActionRegistry,
    AgentRegistry,
    ContextBuilderRegistry,
    GeneratorRegistry,
)
from maverick.dsl.serialization.registry.validation import (
    is_async_callable,
    validate_agent_class,
    validate_callable,
    validate_context_builder,
    validate_signature,
)

# =============================================================================
# Test Fixtures - Valid Components
# =============================================================================


class ValidAgent(MaverickAgent[dict[str, Any], str]):
    """A valid agent for testing."""

    def __init__(self) -> None:
        super().__init__(
            name="test_agent",
            instructions="Test agent",
            allowed_tools=[],
        )

    async def execute(self, context: dict[str, Any]) -> str:
        return "test result"


class ValidGenerator(GeneratorAgent):
    """A valid generator for testing."""

    def __init__(self) -> None:
        super().__init__(
            name="test_generator",
            system_prompt="Test generator",
        )

    async def generate(
        self, context: dict[str, Any], return_usage: bool = False
    ) -> str:
        return "generated text"


def valid_action(x: int, y: int = 0) -> int:
    """A valid action."""
    return x + y


async def valid_async_action(x: int) -> int:
    """A valid async action."""
    return x * 2


def valid_context_builder(
    inputs: dict[str, Any], step_results: dict[str, Any]
) -> dict[str, Any]:
    """A valid context builder."""
    return {**inputs, **step_results}


async def valid_async_context_builder(
    inputs: dict[str, Any], step_results: dict[str, Any]
) -> dict[str, Any]:
    """A valid async context builder."""
    return {**inputs, **step_results}


# =============================================================================
# Test Fixtures - Invalid Components
# =============================================================================


class NotAnAgent:
    """A class that doesn't inherit from MaverickAgent."""

    def execute(self, context: dict[str, Any]) -> str:
        return "not an agent"


class AgentWithoutExecute(MaverickAgent[dict[str, Any], str]):
    """An agent without an execute method."""

    def __init__(self) -> None:
        super().__init__(
            name="incomplete_agent",
            instructions="Incomplete agent",
            allowed_tools=[],
        )


def context_builder_wrong_params(inputs: dict[str, Any]) -> dict[str, Any]:
    """Context builder with wrong number of parameters."""
    return inputs


def context_builder_too_many_params(
    inputs: dict[str, Any],
    step_results: dict[str, Any],
    extra: str,
) -> dict[str, Any]:
    """Context builder with too many parameters."""
    return inputs


# =============================================================================
# Validation Helper Tests
# =============================================================================


def test_validate_callable_accepts_function() -> None:
    """Test that validate_callable accepts a function."""
    validate_callable(valid_action, "test_action")


def test_validate_callable_accepts_lambda() -> None:
    """Test that validate_callable accepts a lambda."""
    validate_callable(lambda x: x * 2, "test_lambda")


def test_validate_callable_accepts_class() -> None:
    """Test that validate_callable accepts a class (it's callable)."""
    validate_callable(ValidAgent, "test_class")


def test_validate_callable_rejects_non_callable() -> None:
    """Test that validate_callable rejects non-callable objects."""
    with pytest.raises(TypeError, match="must be callable"):
        validate_callable("not a function", "test_string")

    with pytest.raises(TypeError, match="must be callable"):
        validate_callable(42, "test_number")

    with pytest.raises(TypeError, match="must be callable"):
        validate_callable([], "test_list")


def test_validate_signature_exact_params() -> None:
    """Test signature validation with exact parameter count."""

    def two_params(a: int, b: int) -> int:
        return a + b

    # Should succeed
    validate_signature(two_params, "test", expected_params=2)

    # Should fail
    with pytest.raises(TypeError, match="must accept exactly 3"):
        validate_signature(two_params, "test", expected_params=3)


def test_validate_signature_min_max_params() -> None:
    """Test signature validation with min/max parameter counts."""

    def one_param(a: int) -> int:
        return a

    def two_params(a: int, b: int) -> int:
        return a + b

    def three_params(a: int, b: int, c: int) -> int:
        return a + b + c

    # Test minimum
    validate_signature(two_params, "test", min_params=1)
    validate_signature(two_params, "test", min_params=2)
    with pytest.raises(TypeError, match="must accept at least 3"):
        validate_signature(two_params, "test", min_params=3)

    # Test maximum
    validate_signature(two_params, "test", max_params=3)
    validate_signature(two_params, "test", max_params=2)
    with pytest.raises(TypeError, match="must accept at most 1"):
        validate_signature(two_params, "test", max_params=1)

    # Test range
    validate_signature(one_param, "test", min_params=1, max_params=3)
    validate_signature(two_params, "test", min_params=1, max_params=3)
    validate_signature(three_params, "test", min_params=1, max_params=3)


def test_validate_signature_with_default_params() -> None:
    """Test that default parameters are counted in the signature."""

    def func_with_defaults(a: int, b: int = 0, c: int = 0) -> int:
        return a + b + c

    # All 3 parameters are positional (even with defaults)
    validate_signature(func_with_defaults, "test", expected_params=3)


def test_validate_signature_ignores_varargs() -> None:
    """Test that *args and **kwargs are not counted as positional params."""

    def func_with_varargs(a: int, *args: Any, **kwargs: Any) -> int:
        return a

    # Only 'a' is positional
    validate_signature(func_with_varargs, "test", expected_params=1)


def test_validate_agent_class_accepts_valid_agent() -> None:
    """Test that validate_agent_class accepts a valid MaverickAgent subclass."""
    validate_agent_class(ValidAgent, "valid_agent")


def test_validate_agent_class_rejects_non_class() -> None:
    """Test that validate_agent_class rejects non-class objects."""
    with pytest.raises(TypeError, match="must be a class"):
        validate_agent_class(valid_action, "not_a_class")

    with pytest.raises(TypeError, match="must be a class"):
        validate_agent_class("not a class", "test_string")


def test_validate_agent_class_rejects_non_maverick_agent() -> None:
    """Test validate_agent_class rejects classes not inheriting from MaverickAgent."""
    with pytest.raises(TypeError, match="must inherit from MaverickAgent"):
        validate_agent_class(NotAnAgent, "not_an_agent")


def test_validate_agent_class_rejects_agent_without_execute() -> None:
    """Test that validate_agent_class rejects agents without execute method."""
    with pytest.raises(TypeError, match="must implement the abstract 'execute' method"):
        validate_agent_class(AgentWithoutExecute, "incomplete_agent")


def test_validate_context_builder_accepts_valid_builder() -> None:
    """Test that validate_context_builder accepts a valid context builder."""
    validate_context_builder(valid_context_builder, "valid_builder")
    validate_context_builder(valid_async_context_builder, "valid_async_builder")


def test_validate_context_builder_rejects_non_callable() -> None:
    """Test that validate_context_builder rejects non-callable objects."""
    with pytest.raises(TypeError, match="must be callable"):
        validate_context_builder("not a function", "test_string")


def test_validate_context_builder_rejects_wrong_param_count() -> None:
    """Test validate_context_builder rejects functions with wrong param count."""
    # Too few parameters
    with pytest.raises(TypeError, match="must accept exactly 2"):
        validate_context_builder(context_builder_wrong_params, "wrong_params")

    # Too many parameters
    with pytest.raises(TypeError, match="must accept exactly 2"):
        validate_context_builder(context_builder_too_many_params, "too_many_params")


def test_is_async_callable_detects_async_functions() -> None:
    """Test that is_async_callable correctly identifies async functions."""
    assert is_async_callable(valid_async_action) is True
    assert is_async_callable(valid_async_context_builder) is True
    assert is_async_callable(valid_action) is False
    assert is_async_callable(valid_context_builder) is False


# =============================================================================
# ActionRegistry Validation Tests
# =============================================================================


def test_action_registry_accepts_valid_actions() -> None:
    """Test that ActionRegistry accepts valid actions."""
    registry = ActionRegistry()

    # Sync action
    registry.register("sync_action", valid_action)
    assert registry.has("sync_action")

    # Async action
    registry.register("async_action", valid_async_action)
    assert registry.has("async_action")

    # Lambda
    registry.register("lambda_action", lambda x: x * 2)
    assert registry.has("lambda_action")


def test_action_registry_rejects_non_callable() -> None:
    """Test that ActionRegistry rejects non-callable objects."""
    registry = ActionRegistry()

    with pytest.raises(TypeError, match="must be callable"):
        registry.register("invalid", "not a function")

    with pytest.raises(TypeError, match="must be callable"):
        registry.register("invalid", 42)

    with pytest.raises(TypeError, match="must be callable"):
        registry.register("invalid", [1, 2, 3])


# =============================================================================
# AgentRegistry Validation Tests
# =============================================================================


def test_agent_registry_accepts_valid_agents() -> None:
    """Test that AgentRegistry accepts valid agent classes."""
    registry = AgentRegistry()

    registry.register("valid_agent", ValidAgent)
    assert registry.has("valid_agent")


def test_agent_registry_rejects_non_class() -> None:
    """Test that AgentRegistry rejects non-class objects."""
    registry = AgentRegistry()

    with pytest.raises(TypeError, match="must be a class"):
        registry.register("invalid", valid_action)

    with pytest.raises(TypeError, match="must be a class"):
        registry.register("invalid", "not a class")


def test_agent_registry_rejects_non_maverick_agent() -> None:
    """Test that AgentRegistry rejects classes that don't inherit from MaverickAgent."""
    registry = AgentRegistry()

    with pytest.raises(TypeError, match="must inherit from MaverickAgent"):
        registry.register("invalid", NotAnAgent)


def test_agent_registry_rejects_agent_without_execute() -> None:
    """Test that AgentRegistry rejects agents without execute method."""
    registry = AgentRegistry()

    with pytest.raises(TypeError, match="must implement the abstract 'execute' method"):
        registry.register("invalid", AgentWithoutExecute)


# =============================================================================
# GeneratorRegistry Validation Tests
# =============================================================================


def test_generator_registry_accepts_valid_generators() -> None:
    """Test that GeneratorRegistry accepts valid generator classes."""
    registry = GeneratorRegistry()

    # Generators must inherit from GeneratorAgent
    registry.register("valid_generator", ValidGenerator)
    assert registry.has("valid_generator")


def test_generator_registry_rejects_non_class() -> None:
    """Test that GeneratorRegistry rejects non-class objects."""
    registry = GeneratorRegistry()

    with pytest.raises(TypeError, match="must be a class"):
        registry.register("invalid", valid_action)


def test_generator_registry_rejects_non_generator_agent() -> None:
    """Test GeneratorRegistry rejects classes not inheriting from GeneratorAgent."""
    registry = GeneratorRegistry()

    with pytest.raises(TypeError, match="must inherit from GeneratorAgent"):
        registry.register("invalid", NotAnAgent)


# =============================================================================
# ContextBuilderRegistry Validation Tests
# =============================================================================


def test_context_builder_registry_accepts_valid_builders() -> None:
    """Test that ContextBuilderRegistry accepts valid context builders."""
    registry = ContextBuilderRegistry()

    # Sync builder
    registry.register("sync_builder", valid_context_builder)
    assert registry.has("sync_builder")

    # Async builder
    registry.register("async_builder", valid_async_context_builder)
    assert registry.has("async_builder")


def test_context_builder_registry_rejects_non_callable() -> None:
    """Test that ContextBuilderRegistry rejects non-callable objects."""
    registry = ContextBuilderRegistry()

    with pytest.raises(TypeError, match="must be callable"):
        registry.register("invalid", "not a function")


def test_context_builder_registry_rejects_wrong_signature() -> None:
    """Test that ContextBuilderRegistry rejects builders with wrong signature."""
    registry = ContextBuilderRegistry()

    # Too few parameters
    with pytest.raises(TypeError, match="must accept exactly 2"):
        registry.register("invalid", context_builder_wrong_params)

    # Too many parameters
    with pytest.raises(TypeError, match="must accept exactly 2"):
        registry.register("invalid", context_builder_too_many_params)


# =============================================================================
# Integration Tests - Error Messages
# =============================================================================


def test_validation_error_messages_are_helpful() -> None:
    """Test that validation errors provide helpful, actionable messages."""
    registry = ActionRegistry()

    # Non-callable should mention what type was provided
    try:
        registry.register("bad_action", 42)
        pytest.fail("Expected TypeError")
    except TypeError as e:
        assert "must be callable" in str(e)
        assert "int" in str(e)

    # Agent validation should mention what's wrong
    agent_registry = AgentRegistry()
    try:
        agent_registry.register("bad_agent", NotAnAgent)
        pytest.fail("Expected TypeError")
    except TypeError as e:
        assert "must inherit from MaverickAgent" in str(e)

    # Context builder validation should mention signature
    builder_registry = ContextBuilderRegistry()
    try:
        builder_registry.register("bad_builder", context_builder_wrong_params)
        pytest.fail("Expected TypeError")
    except TypeError as e:
        assert "must accept exactly 2" in str(e)
        assert "accepts 1" in str(e)


def test_validation_preserves_backward_compatibility() -> None:
    """Test that validation doesn't break existing valid registrations."""
    # This test ensures that all previously valid registrations still work

    # Actions - any callable should work
    action_registry = ActionRegistry()
    action_registry.register("func", lambda x: x)
    action_registry.register("class", ValidAgent)  # Classes are callable

    # Agents - MaverickAgent subclasses with execute method
    agent_registry = AgentRegistry()
    agent_registry.register("agent", ValidAgent)

    # Generators - GeneratorAgent subclasses
    generator_registry = GeneratorRegistry()
    generator_registry.register("gen", ValidGenerator)

    # Context builders - functions with 2 parameters
    builder_registry = ContextBuilderRegistry()
    builder_registry.register("builder", valid_context_builder)
    builder_registry.register("async_builder", valid_async_context_builder)

    # All should be retrievable
    assert action_registry.get("func") is not None
    assert agent_registry.get("agent") is ValidAgent
    assert generator_registry.get("gen") is ValidGenerator
    assert builder_registry.get("builder") is valid_context_builder
