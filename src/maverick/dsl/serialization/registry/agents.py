"""Agent registry for MaverickAgent classes (T025-T031).

This module provides the AgentRegistry for managing MaverickAgent classes
that can be referenced by name in workflow definitions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from maverick.dsl.errors import (
    DuplicateComponentError,
    ReferenceResolutionError,
)
from maverick.dsl.serialization.registry.protocol import AgentType
from maverick.dsl.serialization.registry.validation import validate_agent_class


@dataclass(frozen=True, slots=True)
class AgentMetadata:
    """Metadata for a registered agent.

    Attributes:
        requires: Tuple of prerequisite names this agent needs.
    """

    requires: tuple[str, ...] = field(default_factory=tuple)


class AgentRegistry:
    """Registry for MaverickAgent classes.

    Agents are MaverickAgent subclasses that perform complex tasks (code review,
    implementation, issue fixing, etc.). They are used in AgentStep definitions.

    Attributes:
        _agents: Internal dictionary mapping agent names to classes.
        _metadata: Internal dictionary mapping agent names to metadata.

    Example:
        ```python
        # Using decorator registration with prerequisites
        @agent_registry.register("code_reviewer", requires=("anthropic_key",))
        class CodeReviewerAgent(MaverickAgent):
            ...

        # Using explicit registration
        agent_registry.register(
            "implementer", ImplementerAgent, requires=("anthropic_key",)
        )

        # Looking up an agent
        agent_class = agent_registry.get("code_reviewer")

        # Getting prerequisites for an agent
        prereqs = agent_registry.get_requires("code_reviewer")
        ```
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._agents: dict[str, AgentType] = {}
        self._metadata: dict[str, AgentMetadata] = {}

    def register(
        self,
        name: str,
        component: AgentType | None = None,
        *,
        validate: bool = True,
        requires: tuple[str, ...] | list[str] | None = None,
    ) -> AgentType | Callable[[AgentType], AgentType]:
        """Register an agent class.

        Can be used as a decorator or called directly.

        Args:
            name: Unique name for the agent.
            component: Agent class to register (None when used as decorator).
            validate: Whether to validate that component inherits from
                MaverickAgent. Set to False for testing with mock objects.
            requires: Tuple/list of prerequisite names this agent needs.
                These are automatically collected during preflight.

        Returns:
            The registered class when called directly, or a decorator function
            when used as a decorator.

        Raises:
            ReferenceResolutionError: If an agent with this name is already
                registered.

        Example:
            ```python
            # As a decorator with prerequisites
            @registry.register("my_agent", requires=("anthropic_key",))
            class MyAgent(MaverickAgent):
                ...

            # Direct registration with prerequisites
            registry.register("my_agent", MyAgentClass, requires=["anthropic_key"])

            # For testing with mocks
            registry.register("mock_agent", MockAgent, validate=False)
            ```
        """
        requires_tuple = tuple(requires) if requires else ()

        if component is None:
            # Used as a decorator: @registry.register("name")
            def decorator(agent_class: AgentType) -> AgentType:
                self._register_impl(
                    name, agent_class, validate=validate, requires=requires_tuple
                )
                return agent_class

            return decorator
        else:
            # Direct call: registry.register("name", AgentClass)
            self._register_impl(
                name, component, validate=validate, requires=requires_tuple
            )
            return component

    def _register_impl(
        self,
        name: str,
        component: AgentType,
        *,
        validate: bool = True,
        requires: tuple[str, ...] = (),
    ) -> None:
        """Internal implementation of registration logic.

        Args:
            name: Unique name for the agent.
            component: Agent class to register.
            validate: Whether to validate inheritance.
            requires: Tuple of prerequisite names.

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
        self._metadata[name] = AgentMetadata(requires=requires)

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

    def get_requires(self, name: str) -> tuple[str, ...]:
        """Get prerequisite names for an agent.

        Args:
            name: Name of the agent.

        Returns:
            Tuple of prerequisite names, or empty tuple if none.

        Raises:
            ReferenceResolutionError: If no agent is registered with this name.

        Example:
            ```python
            prereqs = registry.get_requires("code_reviewer")
            # ('anthropic_key',)
            ```
        """
        if name not in self._agents:
            raise ReferenceResolutionError(
                reference_type="agent",
                reference_name=name,
                available_names=list(self._agents.keys()),
            )
        metadata = self._metadata.get(name)
        return metadata.requires if metadata else ()
