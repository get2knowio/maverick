"""Agent registry for MaverickAgent classes (T025-T031).

This module provides the AgentRegistry for managing MaverickAgent classes
that can be referenced by name in workflow definitions.
"""

from __future__ import annotations

from collections.abc import Callable

from maverick.dsl.errors import (
    DuplicateComponentError,
    ReferenceResolutionError,
)
from maverick.dsl.serialization.registry.protocol import AgentType
from maverick.dsl.serialization.registry.validation import validate_agent_class


class AgentRegistry:
    """Registry for MaverickAgent classes.

    Agents are MaverickAgent subclasses that perform complex tasks (code review,
    implementation, issue fixing, etc.). They are used in AgentStep definitions.

    Attributes:
        _agents: Internal dictionary mapping agent names to classes.

    Example:
        ```python
        # Using decorator registration
        @agent_registry.register("code_reviewer")
        class CodeReviewerAgent(MaverickAgent):
            ...

        # Using explicit registration
        agent_registry.register("implementer", ImplementerAgent)

        # Looking up an agent
        agent_class = agent_registry.get("code_reviewer")

        # Listing all registered agents
        names = agent_registry.list_names()
        ```
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._agents: dict[str, AgentType] = {}

    def register(
        self,
        name: str,
        component: AgentType | None = None,
        *,
        validate: bool = True,
    ) -> AgentType | Callable[[AgentType], AgentType]:
        """Register an agent class.

        Can be used as a decorator or called directly.

        Args:
            name: Unique name for the agent.
            component: Agent class to register (None when used as decorator).
            validate: Whether to validate that component inherits from
                MaverickAgent. Set to False for testing with mock objects.

        Returns:
            The registered class when called directly, or a decorator function
            when used as a decorator.

        Raises:
            ReferenceResolutionError: If an agent with this name is already
                registered.

        Example:
            ```python
            # As a decorator
            @registry.register("my_agent")
            class MyAgent(MaverickAgent):
                ...

            # Direct registration
            registry.register("my_agent", MyAgentClass)

            # For testing with mocks
            registry.register("mock_agent", MockAgent, validate=False)
            ```
        """
        if component is None:
            # Used as a decorator: @registry.register("name")
            def decorator(agent_class: AgentType) -> AgentType:
                self._register_impl(name, agent_class, validate=validate)
                return agent_class

            return decorator
        else:
            # Direct call: registry.register("name", AgentClass)
            self._register_impl(name, component, validate=validate)
            return component

    def _register_impl(
        self, name: str, component: AgentType, *, validate: bool = True
    ) -> None:
        """Internal implementation of registration logic.

        Args:
            name: Unique name for the agent.
            component: Agent class to register.
            validate: Whether to validate inheritance.

        Raises:
            DuplicateComponentError: If an agent with this name is already
                registered.
            TypeError: If component is not a valid MaverickAgent subclass.
        """
        # Validate that agent is a MaverickAgent subclass
        if validate:
            validate_agent_class(component, name)

        if name in self._agents:
            raise DuplicateComponentError(
                component_type="agent",
                component_name=name,
            )
        self._agents[name] = component

    def get(self, name: str) -> AgentType:
        """Look up an agent class by name.

        Args:
            name: Name of the agent to look up.

        Returns:
            The agent class associated with the name.

        Raises:
            ReferenceResolutionError: If no agent is registered with this name.

        Example:
            ```python
            agent_class = registry.get("code_reviewer")
            agent = agent_class(mcp_servers={...})
            ```
        """
        if name not in self._agents:
            raise ReferenceResolutionError(
                reference_type="agent",
                reference_name=name,
                available_names=list(self._agents.keys()),
            )
        return self._agents[name]

    def list_names(self) -> list[str]:
        """List all registered agent names.

        Returns:
            Sorted list of registered agent names.

        Example:
            ```python
            names = registry.list_names()
            # ['code_reviewer', 'implementer', 'issue_fixer', ...]
            ```
        """
        return sorted(self._agents.keys())

    def has(self, name: str) -> bool:
        """Check if an agent is registered.

        Args:
            name: Name of the agent to check.

        Returns:
            True if the agent is registered, False otherwise.

        Example:
            ```python
            if registry.has("code_reviewer"):
                agent_class = registry.get("code_reviewer")
            ```
        """
        return name in self._agents
