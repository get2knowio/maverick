"""Tests for component registries (T025a, T025b).

This module tests the Registry protocol and all concrete registry implementations,
including the ComponentRegistry facade.
"""

from __future__ import annotations

from typing import Any

import pytest

from maverick.dsl.errors import (
    DuplicateComponentError,
    ReferenceResolutionError,
)
from maverick.dsl.serialization.registry import (
    ActionRegistry,
    ComponentRegistry,
    ContextBuilderRegistry,
    GeneratorRegistry,
    WorkflowRegistry,
    action_registry,
    component_registry,
    context_builder_registry,
    generator_registry,
    workflow_registry,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def action_reg() -> ActionRegistry:
    """Create a fresh ActionRegistry for testing."""
    return ActionRegistry()


@pytest.fixture
def generator_reg() -> GeneratorRegistry:
    """Create a fresh GeneratorRegistry for testing."""
    return GeneratorRegistry()


@pytest.fixture
def context_builder_reg() -> ContextBuilderRegistry:
    """Create a fresh ContextBuilderRegistry for testing."""
    return ContextBuilderRegistry()


@pytest.fixture
def workflow_reg() -> WorkflowRegistry:
    """Create a fresh WorkflowRegistry for testing."""
    return WorkflowRegistry()


@pytest.fixture
def component_reg() -> ComponentRegistry:
    """Create a fresh ComponentRegistry for testing."""
    return ComponentRegistry(strict=True)


# =============================================================================
# ActionRegistry Tests
# =============================================================================


def test_action_registry_register_and_get(action_reg: ActionRegistry) -> None:
    """Test basic registration and retrieval of actions."""

    def my_action(x: int) -> int:
        return x * 2

    action_reg.register("double", my_action)
    retrieved = action_reg.get("double")
    assert retrieved is my_action
    assert retrieved(5) == 10


def test_action_registry_decorator_registration(action_reg: ActionRegistry) -> None:
    """Test decorator-based registration."""

    @action_reg.register("triple")
    def my_action(x: int) -> int:
        return x * 3

    retrieved = action_reg.get("triple")
    assert retrieved(5) == 15


def test_action_registry_list_names(action_reg: ActionRegistry) -> None:
    """Test listing all registered action names."""

    def action_a() -> None:
        pass

    def action_b() -> None:
        pass

    action_reg.register("action_a", action_a)
    action_reg.register("action_b", action_b)

    names = action_reg.list_names()
    assert sorted(names) == ["action_a", "action_b"]


def test_action_registry_has(action_reg: ActionRegistry) -> None:
    """Test checking if an action exists."""

    def my_action() -> None:
        pass

    action_reg.register("my_action", my_action)
    assert action_reg.has("my_action") is True
    assert action_reg.has("nonexistent") is False


def test_action_registry_duplicate_error(action_reg: ActionRegistry) -> None:
    """Test that duplicate registration raises an error."""

    def action_one() -> None:
        pass

    def action_two() -> None:
        pass

    action_reg.register("duplicate", action_one)

    with pytest.raises(DuplicateComponentError) as exc_info:
        action_reg.register("duplicate", action_two)

    assert "duplicate" in str(exc_info.value).lower()


def test_action_registry_get_missing_error(action_reg: ActionRegistry) -> None:
    """Test that retrieving a missing action raises an error."""
    with pytest.raises(ReferenceResolutionError) as exc_info:
        action_reg.get("nonexistent")

    assert "nonexistent" in str(exc_info.value)


# =============================================================================
# GeneratorRegistry Tests
# =============================================================================


def test_generator_registry_register_and_get(generator_reg: GeneratorRegistry) -> None:
    """Test basic registration and retrieval of generator classes."""

    class DummyGenerator:
        name = "dummy"

    generator_reg.register("dummy", DummyGenerator, validate=False)
    retrieved = generator_reg.get("dummy")
    assert retrieved is DummyGenerator


def test_generator_registry_decorator_registration(
    generator_reg: GeneratorRegistry,
) -> None:
    """Test decorator-based registration."""

    @generator_reg.register("decorated", validate=False)
    class DecoratedGenerator:
        name = "decorated"

    retrieved = generator_reg.get("decorated")
    assert retrieved.name == "decorated"


def test_generator_registry_list_names(generator_reg: GeneratorRegistry) -> None:
    """Test listing all registered generator names."""

    class GenA:
        pass

    class GenB:
        pass

    generator_reg.register("gen_a", GenA, validate=False)
    generator_reg.register("gen_b", GenB, validate=False)

    names = generator_reg.list_names()
    assert sorted(names) == ["gen_a", "gen_b"]


def test_generator_registry_has(generator_reg: GeneratorRegistry) -> None:
    """Test checking if a generator exists."""

    class MyGen:
        pass

    generator_reg.register("my_gen", MyGen, validate=False)
    assert generator_reg.has("my_gen") is True
    assert generator_reg.has("nonexistent") is False


def test_generator_registry_duplicate_error(
    generator_reg: GeneratorRegistry,
) -> None:
    """Test that duplicate registration raises an error."""

    class GenOne:
        pass

    class GenTwo:
        pass

    generator_reg.register("duplicate", GenOne, validate=False)

    with pytest.raises(DuplicateComponentError) as exc_info:
        generator_reg.register("duplicate", GenTwo, validate=False)

    assert "duplicate" in str(exc_info.value).lower()


def test_generator_registry_get_missing_error(
    generator_reg: GeneratorRegistry,
) -> None:
    """Test that retrieving a missing generator raises an error."""
    with pytest.raises(ReferenceResolutionError) as exc_info:
        generator_reg.get("nonexistent")

    assert "nonexistent" in str(exc_info.value)


# =============================================================================
# ContextBuilderRegistry Tests
# =============================================================================


def test_context_builder_registry_register_and_get(
    context_builder_reg: ContextBuilderRegistry,
) -> None:
    """Test basic registration and retrieval of context builders."""

    def my_builder() -> dict[str, Any]:
        return {"key": "value"}

    context_builder_reg.register("my_builder", my_builder, validate=False)
    retrieved = context_builder_reg.get("my_builder")
    assert retrieved is my_builder
    assert retrieved() == {"key": "value"}


def test_context_builder_registry_decorator_registration(
    context_builder_reg: ContextBuilderRegistry,
) -> None:
    """Test decorator-based registration."""

    @context_builder_reg.register("decorated_builder", validate=False)
    def my_builder() -> dict[str, Any]:
        return {"decorated": True}

    retrieved = context_builder_reg.get("decorated_builder")
    assert retrieved()["decorated"] is True


def test_context_builder_registry_list_names(
    context_builder_reg: ContextBuilderRegistry,
) -> None:
    """Test listing all registered context builder names."""

    def builder_a() -> dict[str, Any]:
        return {}

    def builder_b() -> dict[str, Any]:
        return {}

    context_builder_reg.register("builder_a", builder_a, validate=False)
    context_builder_reg.register("builder_b", builder_b, validate=False)

    names = context_builder_reg.list_names()
    assert sorted(names) == ["builder_a", "builder_b"]


def test_context_builder_registry_has(
    context_builder_reg: ContextBuilderRegistry,
) -> None:
    """Test checking if a context builder exists."""

    def my_builder() -> dict[str, Any]:
        return {}

    context_builder_reg.register("my_builder", my_builder, validate=False)
    assert context_builder_reg.has("my_builder") is True
    assert context_builder_reg.has("nonexistent") is False


def test_context_builder_registry_duplicate_error(
    context_builder_reg: ContextBuilderRegistry,
) -> None:
    """Test that duplicate registration raises an error."""

    def builder_one() -> dict[str, Any]:
        return {}

    def builder_two() -> dict[str, Any]:
        return {}

    context_builder_reg.register("duplicate", builder_one, validate=False)

    with pytest.raises(DuplicateComponentError) as exc_info:
        context_builder_reg.register("duplicate", builder_two, validate=False)

    assert "duplicate" in str(exc_info.value).lower()


def test_context_builder_registry_get_missing_error(
    context_builder_reg: ContextBuilderRegistry,
) -> None:
    """Test that retrieving a missing context builder raises an error."""
    with pytest.raises(ReferenceResolutionError) as exc_info:
        context_builder_reg.get("nonexistent")

    assert "nonexistent" in str(exc_info.value)


# =============================================================================
# WorkflowRegistry Tests
# =============================================================================


def test_workflow_registry_register_and_get(workflow_reg: WorkflowRegistry) -> None:
    """Test basic registration and retrieval of workflow definitions."""

    class DummyWorkflow:
        name = "dummy"

    workflow_reg.register("dummy", DummyWorkflow)
    retrieved = workflow_reg.get("dummy")
    assert retrieved is DummyWorkflow


def test_workflow_registry_decorator_registration(
    workflow_reg: WorkflowRegistry,
) -> None:
    """Test decorator-based registration."""

    @workflow_reg.register("decorated_workflow")
    class DecoratedWorkflow:
        name = "decorated"

    retrieved = workflow_reg.get("decorated_workflow")
    assert retrieved.name == "decorated"


def test_workflow_registry_list_names(workflow_reg: WorkflowRegistry) -> None:
    """Test listing all registered workflow names."""

    class WorkflowA:
        pass

    class WorkflowB:
        pass

    workflow_reg.register("workflow_a", WorkflowA)
    workflow_reg.register("workflow_b", WorkflowB)

    names = workflow_reg.list_names()
    assert sorted(names) == ["workflow_a", "workflow_b"]


def test_workflow_registry_has(workflow_reg: WorkflowRegistry) -> None:
    """Test checking if a workflow exists."""

    class MyWorkflow:
        pass

    workflow_reg.register("my_workflow", MyWorkflow)
    assert workflow_reg.has("my_workflow") is True
    assert workflow_reg.has("nonexistent") is False


def test_workflow_registry_duplicate_error(workflow_reg: WorkflowRegistry) -> None:
    """Test that duplicate registration raises an error."""

    class WorkflowOne:
        pass

    class WorkflowTwo:
        pass

    workflow_reg.register("duplicate", WorkflowOne)

    with pytest.raises(DuplicateComponentError) as exc_info:
        workflow_reg.register("duplicate", WorkflowTwo)

    assert "duplicate" in str(exc_info.value).lower()


def test_workflow_registry_get_missing_error(workflow_reg: WorkflowRegistry) -> None:
    """Test that retrieving a missing workflow raises an error."""
    with pytest.raises(ReferenceResolutionError) as exc_info:
        workflow_reg.get("nonexistent")

    assert "nonexistent" in str(exc_info.value)


# =============================================================================
# ComponentRegistry Facade Tests
# =============================================================================


def test_component_registry_creates_default_registries() -> None:
    """Test that ComponentRegistry creates default registries if not provided."""
    registry = ComponentRegistry()
    assert registry.actions is not None
    assert registry.generators is not None
    assert registry.context_builders is not None
    assert registry.workflows is not None


def test_component_registry_uses_provided_registries() -> None:
    """Test that ComponentRegistry uses provided registries."""
    actions = ActionRegistry()
    generators = GeneratorRegistry()
    context_builders = ContextBuilderRegistry()
    workflows = WorkflowRegistry()

    registry = ComponentRegistry(
        actions=actions,
        generators=generators,
        context_builders=context_builders,
        workflows=workflows,
    )

    assert registry.actions is actions
    assert registry.generators is generators
    assert registry.context_builders is context_builders
    assert registry.workflows is workflows


def test_component_registry_strict_mode() -> None:
    """Test that strict mode raises errors immediately."""
    registry = ComponentRegistry(strict=True)

    # Missing action should raise immediately
    with pytest.raises(ReferenceResolutionError):
        registry.actions.get("nonexistent")


def test_component_registry_lenient_mode() -> None:
    """Test that lenient mode defers errors (for now, same as strict)."""
    # Note: Lenient mode behavior may be implemented later to defer resolution
    # For now, it behaves the same as strict mode
    registry = ComponentRegistry(strict=False)

    # Missing action should still raise (same as strict for MVP)
    with pytest.raises(ReferenceResolutionError):
        registry.actions.get("nonexistent")


def test_component_registry_integration() -> None:
    """Test integration of all registries through the facade."""
    registry = ComponentRegistry()

    # Register components in each registry
    def my_action() -> int:
        return 42

    class MyGenerator:
        pass

    def my_context_builder() -> dict[str, Any]:
        return {"test": True}

    class MyWorkflow:
        pass

    registry.actions.register("my_action", my_action)
    registry.generators.register("my_gen", MyGenerator, validate=False)
    registry.context_builders.register("my_builder", my_context_builder, validate=False)
    registry.workflows.register("my_workflow", MyWorkflow)

    # Verify retrieval
    assert registry.actions.get("my_action")() == 42
    assert registry.generators.get("my_gen") is MyGenerator
    assert registry.context_builders.get("my_builder")()["test"] is True
    assert registry.workflows.get("my_workflow") is MyWorkflow


# =============================================================================
# Module-Level Singleton Tests
# =============================================================================


def test_module_level_action_registry_exists() -> None:
    """Test that module-level action_registry singleton exists."""
    assert action_registry is not None
    assert isinstance(action_registry, ActionRegistry)


def test_module_level_generator_registry_exists() -> None:
    """Test that module-level generator_registry singleton exists."""
    assert generator_registry is not None
    assert isinstance(generator_registry, GeneratorRegistry)


def test_module_level_context_builder_registry_exists() -> None:
    """Test that module-level context_builder_registry singleton exists."""
    assert context_builder_registry is not None
    assert isinstance(context_builder_registry, ContextBuilderRegistry)


def test_module_level_workflow_registry_exists() -> None:
    """Test that module-level workflow_registry singleton exists."""
    assert workflow_registry is not None
    assert isinstance(workflow_registry, WorkflowRegistry)


def test_module_level_component_registry_exists() -> None:
    """Test that module-level component_registry singleton exists."""
    assert component_registry is not None
    assert isinstance(component_registry, ComponentRegistry)


def test_module_level_component_registry_uses_singletons() -> None:
    """Test that the module-level component_registry uses singleton registries."""
    assert component_registry.actions is action_registry
    assert component_registry.generators is generator_registry
    assert component_registry.context_builders is context_builder_registry
    assert component_registry.workflows is workflow_registry


# =============================================================================
# Edge Cases and Error Messages
# =============================================================================


def test_action_registry_get_error_message_includes_available(
    action_reg: ActionRegistry,
) -> None:
    """Test that error messages include available actions for helpful feedback."""

    def action_a() -> None:
        pass

    def action_b() -> None:
        pass

    action_reg.register("action_a", action_a)
    action_reg.register("action_b", action_b)

    with pytest.raises(ReferenceResolutionError) as exc_info:
        action_reg.get("action_c")

    error_msg = str(exc_info.value)
    assert "action_a" in error_msg
    assert "action_b" in error_msg


def test_generator_registry_get_error_message_includes_available(
    generator_reg: GeneratorRegistry,
) -> None:
    """Test that error messages include available generators."""

    class GenA:
        pass

    class GenB:
        pass

    generator_reg.register("gen_a", GenA, validate=False)
    generator_reg.register("gen_b", GenB, validate=False)

    with pytest.raises(ReferenceResolutionError) as exc_info:
        generator_reg.get("gen_c")

    error_msg = str(exc_info.value)
    assert "gen_a" in error_msg
    assert "gen_b" in error_msg


def test_context_builder_registry_get_error_message_includes_available(
    context_builder_reg: ContextBuilderRegistry,
) -> None:
    """Test that error messages include available context builders."""

    def builder_a() -> dict[str, Any]:
        return {}

    def builder_b() -> dict[str, Any]:
        return {}

    context_builder_reg.register("builder_a", builder_a, validate=False)
    context_builder_reg.register("builder_b", builder_b, validate=False)

    with pytest.raises(ReferenceResolutionError) as exc_info:
        context_builder_reg.get("builder_c")

    error_msg = str(exc_info.value)
    assert "builder_a" in error_msg
    assert "builder_b" in error_msg


def test_workflow_registry_get_error_message_includes_available(
    workflow_reg: WorkflowRegistry,
) -> None:
    """Test that error messages include available workflows."""

    class WorkflowA:
        pass

    class WorkflowB:
        pass

    workflow_reg.register("workflow_a", WorkflowA)
    workflow_reg.register("workflow_b", WorkflowB)

    with pytest.raises(ReferenceResolutionError) as exc_info:
        workflow_reg.get("workflow_c")

    error_msg = str(exc_info.value)
    assert "workflow_a" in error_msg
    assert "workflow_b" in error_msg


def test_action_registry_empty_list() -> None:
    """Test that an empty registry returns an empty list."""
    reg = ActionRegistry()
    assert reg.list_names() == []


def test_generator_registry_empty_list() -> None:
    """Test that an empty registry returns an empty list."""
    reg = GeneratorRegistry()
    assert reg.list_names() == []


def test_context_builder_registry_empty_list() -> None:
    """Test that an empty registry returns an empty list."""
    reg = ContextBuilderRegistry()
    assert reg.list_names() == []


def test_workflow_registry_empty_list() -> None:
    """Test that an empty registry returns an empty list."""
    reg = WorkflowRegistry()
    assert reg.list_names() == []
