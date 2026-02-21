"""Unit tests for AgentRegistry.

This module tests the AgentRegistry class which manages registration,
retrieval, and instantiation of MaverickAgent subclasses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from maverick.agents.base import MaverickAgent
from maverick.agents.registry import AgentRegistry, register, registry
from maverick.exceptions import AgentNotFoundError, DuplicateAgentError

if TYPE_CHECKING:
    from maverick.agents.context import AgentContext
    from maverick.agents.result import AgentResult


# =============================================================================
# Mock Agent Classes for Testing
# =============================================================================


class MockAgent(MaverickAgent):
    """Mock agent for testing registry functionality."""

    def __init__(
        self,
        name: str = "mock",
        custom_param: str | None = None,
        **kwargs: object,
    ) -> None:
        """Initialize the mock agent.

        Args:
            name: Agent name (default: "mock").
            custom_param: Optional custom parameter for testing kwargs.
            **kwargs: Additional keyword arguments.
        """
        super().__init__(
            name=name,
            instructions="Mock system prompt",
            allowed_tools=["Read", "Write"],
        )
        self.custom_param = custom_param
        self.extra_kwargs = kwargs

    async def execute(self, context: AgentContext) -> AgentResult:
        """Mock execute method.

        Args:
            context: Agent context.

        Returns:
            Mock agent result.
        """
        from maverick.agents.result import AgentResult, AgentUsage

        return AgentResult.success_result(
            output="Mock output",
            usage=AgentUsage(
                input_tokens=0,
                output_tokens=0,
                total_cost_usd=None,
                duration_ms=0,
            ),
        )


class AnotherMockAgent(MaverickAgent):
    """Another mock agent for testing multiple registrations."""

    def __init__(self, name: str = "another") -> None:
        """Initialize the second mock agent.

        Args:
            name: Agent name (default: "another").
        """
        super().__init__(
            name=name,
            instructions="Another mock prompt",
            allowed_tools=[],
        )

    async def execute(self, context: AgentContext) -> AgentResult:
        """Mock execute method.

        Args:
            context: Agent context.

        Returns:
            Mock agent result.
        """
        from maverick.agents.result import AgentResult, AgentUsage

        return AgentResult.success_result(
            output="Another mock output",
            usage=AgentUsage(
                input_tokens=0,
                output_tokens=0,
                total_cost_usd=None,
                duration_ms=0,
            ),
        )


# =============================================================================
# AgentRegistry Tests
# =============================================================================


def test_registry_singleton_exists() -> None:
    """Test that the global registry singleton instance exists."""
    assert registry is not None
    assert isinstance(registry, AgentRegistry)


def test_register_valid_agent_class() -> None:
    """Test register() with a valid agent class."""
    test_registry = AgentRegistry()

    # Register the mock agent
    test_registry.register("test_agent", MockAgent)

    # Verify it was registered
    assert "test_agent" in test_registry.list_agents()


def test_register_raises_duplicate_agent_error() -> None:
    """Test register() raises DuplicateAgentError when registering same name twice."""
    test_registry = AgentRegistry()

    # Register the agent first time
    test_registry.register("duplicate_test", MockAgent)

    # Try to register with the same name again
    with pytest.raises(DuplicateAgentError) as exc_info:
        test_registry.register("duplicate_test", AnotherMockAgent)

    assert "duplicate_test" in str(exc_info.value.message)
    assert exc_info.value.agent_name == "duplicate_test"


def test_get_returns_registered_class() -> None:
    """Test get() returns the registered agent class."""
    test_registry = AgentRegistry()

    # Register the agent
    test_registry.register("get_test", MockAgent)

    # Retrieve it
    agent_class = test_registry.get("get_test")

    # Verify it's the correct class
    assert agent_class is MockAgent


def test_get_raises_agent_not_found_error() -> None:
    """Test get() raises AgentNotFoundError for unknown name."""
    test_registry = AgentRegistry()

    # Try to get a non-existent agent
    with pytest.raises(AgentNotFoundError) as exc_info:
        test_registry.get("nonexistent_agent")

    assert "nonexistent_agent" in str(exc_info.value.message)
    assert exc_info.value.agent_name == "nonexistent_agent"


def test_list_agents_returns_empty_list_when_nothing_registered() -> None:
    """Test list_agents() returns empty list when nothing is registered."""
    test_registry = AgentRegistry()

    agents = test_registry.list_agents()

    assert agents == []
    assert isinstance(agents, list)


def test_list_agents_returns_list_of_registered_names() -> None:
    """Test list_agents() returns list of registered agent names."""
    test_registry = AgentRegistry()

    # Register multiple agents
    test_registry.register("agent_one", MockAgent)
    test_registry.register("agent_two", AnotherMockAgent)
    test_registry.register("agent_three", MockAgent)

    agents = test_registry.list_agents()

    # Verify all registered names are in the list
    assert set(agents) == {"agent_one", "agent_two", "agent_three"}
    assert len(agents) == 3


def test_create_instantiates_agent_with_kwargs() -> None:
    """Test create() instantiates an agent with keyword arguments."""
    test_registry = AgentRegistry()

    # Register the agent
    test_registry.register("create_test", MockAgent)

    # Create an instance with custom parameters
    # Note: 'name' argument for create() is the registry lookup key
    # MockAgent's __init__ accepts name as a parameter with default "mock"
    agent = test_registry.create(
        "create_test",
        custom_param="test_value",
        extra_key="extra_value",
    )

    # Verify it's an instance of the correct class
    assert isinstance(agent, MockAgent)
    assert agent.name == "mock"  # default from MockAgent
    assert agent.custom_param == "test_value"
    assert agent.extra_kwargs["extra_key"] == "extra_value"


def test_create_raises_agent_not_found_error() -> None:
    """Test create() raises AgentNotFoundError for unknown name."""
    test_registry = AgentRegistry()

    # Try to create a non-existent agent
    with pytest.raises(AgentNotFoundError) as exc_info:
        test_registry.create("nonexistent_create")

    assert "nonexistent_create" in str(exc_info.value.message)
    assert exc_info.value.agent_name == "nonexistent_create"


def test_register_decorator_works_for_class_level_registration() -> None:
    """Test @register decorator works for class-level registration."""
    test_registry = AgentRegistry()

    # Define a class with the decorator
    @register("decorated_agent", registry=test_registry)
    class DecoratedAgent(MaverickAgent):
        """Agent registered via decorator."""

        def __init__(self) -> None:
            """Initialize the decorated agent."""
            super().__init__(
                name="decorated",
                instructions="Decorated prompt",
                allowed_tools=[],
            )

        async def execute(self, context: AgentContext) -> AgentResult:
            """Mock execute method.

            Args:
                context: Agent context.

            Returns:
                Mock agent result.
            """
            from maverick.agents.result import AgentResult, AgentUsage

            return AgentResult.success_result(
                output="Decorated output",
                usage=AgentUsage(
                    input_tokens=0,
                    output_tokens=0,
                    total_cost_usd=None,
                    duration_ms=0,
                ),
            )

    # Verify the decorator registered the class
    assert "decorated_agent" in test_registry.list_agents()
    agent_class = test_registry.get("decorated_agent")
    assert agent_class is DecoratedAgent

    # Verify we can instantiate it
    agent = test_registry.create("decorated_agent")
    assert isinstance(agent, DecoratedAgent)


def test_create_without_kwargs() -> None:
    """Test create() can instantiate an agent without additional kwargs."""
    test_registry = AgentRegistry()

    # Register the agent
    test_registry.register("simple_create", AnotherMockAgent)

    # Create instance without kwargs
    agent = test_registry.create("simple_create")

    # Verify it's an instance of the correct class with defaults
    assert isinstance(agent, AnotherMockAgent)
    assert agent.name == "another"  # Default name from AnotherMockAgent


def test_register_multiple_agents_independently() -> None:
    """Test registering multiple different agents works independently."""
    test_registry = AgentRegistry()

    # Register multiple different agents
    test_registry.register("first", MockAgent)
    test_registry.register("second", AnotherMockAgent)

    # Verify both are registered and retrievable
    first_class = test_registry.get("first")
    second_class = test_registry.get("second")

    assert first_class is MockAgent
    assert second_class is AnotherMockAgent

    # Verify both can be instantiated
    first_instance = test_registry.create("first")
    second_instance = test_registry.create("second")

    assert isinstance(first_instance, MockAgent)
    assert isinstance(second_instance, AnotherMockAgent)
    # Use default names from each agent class
    assert first_instance.name == "mock"  # MockAgent default
    assert second_instance.name == "another"  # AnotherMockAgent default


def test_list_agents_returns_sorted_names() -> None:
    """Test list_agents() returns names in sorted order."""
    test_registry = AgentRegistry()

    # Register agents in non-alphabetical order
    test_registry.register("zebra", MockAgent)
    test_registry.register("alpha", AnotherMockAgent)
    test_registry.register("beta", MockAgent)

    agents = test_registry.list_agents()

    # List should be sorted alphabetically
    assert agents == ["alpha", "beta", "zebra"]


def test_register_with_same_class_different_names() -> None:
    """Test registering the same class with different names."""
    test_registry = AgentRegistry()

    # Register the same class with different names
    test_registry.register("instance_one", MockAgent)
    test_registry.register("instance_two", MockAgent)

    # Verify both are registered
    assert "instance_one" in test_registry.list_agents()
    assert "instance_two" in test_registry.list_agents()

    # Verify both retrieve the same class
    class_one = test_registry.get("instance_one")
    class_two = test_registry.get("instance_two")
    assert class_one is class_two is MockAgent

    # Verify both can create independent instances with custom_param to distinguish
    agent_one = test_registry.create("instance_one", custom_param="one")
    agent_two = test_registry.create("instance_two", custom_param="two")

    # Both have default name from MockAgent, but different custom_param
    assert agent_one.custom_param == "one"
    assert agent_two.custom_param == "two"
    assert agent_one is not agent_two


def test_global_registry_can_be_used() -> None:
    """Test that the global registry instance can be used for registration."""
    # Just verify the global registry exists and is the right type
    from maverick.agents.registry import registry as global_registry

    assert global_registry is not None
    assert isinstance(global_registry, AgentRegistry)
    assert hasattr(global_registry, "register")
    assert hasattr(global_registry, "get")
    assert hasattr(global_registry, "create")
    assert hasattr(global_registry, "list_agents")


def test_decorator_defaults_to_global_registry() -> None:
    """Test @register decorator uses global registry when registry param is omitted."""
    # Import fresh to test default behavior
    from maverick.agents.registry import register as register_decorator
    from maverick.agents.registry import registry as global_registry

    # Create unique name to avoid conflicts
    unique_name = "test_decorator_global_registry_unique"

    # Clean up if it already exists (in case of test reruns)
    if unique_name in global_registry.list_agents():
        # Skip this test if we can't clean up (registry implementation dependent)
        pytest.skip("Global registry cannot be cleaned for this test")

    # Use decorator without explicit registry parameter
    @register_decorator(unique_name)
    class GlobalDecoratedAgent(MaverickAgent):
        """Agent registered to global registry via decorator."""

        def __init__(self) -> None:
            """Initialize the globally decorated agent."""
            super().__init__(
                name="global_decorated",
                instructions="Global decorated prompt",
                allowed_tools=[],
            )

        async def execute(self, context: AgentContext) -> AgentResult:
            """Mock execute method.

            Args:
                context: Agent context.

            Returns:
                Mock agent result.
            """
            from maverick.agents.result import AgentResult, AgentUsage

            return AgentResult.success_result(
                output="Global decorated output",
                usage=AgentUsage(
                    input_tokens=0,
                    output_tokens=0,
                    total_cost_usd=None,
                    duration_ms=0,
                ),
            )

    # Verify it was registered in the global registry
    assert unique_name in global_registry.list_agents()
    agent_class = global_registry.get(unique_name)
    assert agent_class is GlobalDecoratedAgent
