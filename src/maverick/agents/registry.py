"""AgentRegistry for discovering and instantiating agents.

This module provides the AgentRegistry class that manages agent registration,
lookup, and instantiation. It supports both explicit registration and decorator-based
registration patterns.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from maverick.exceptions import AgentNotFoundError, DuplicateAgentError

if TYPE_CHECKING:
    from maverick.agents.base import MaverickAgent

# Type alias for any MaverickAgent instance (with any context/result types)
MaverickAgentType = type["MaverickAgent[Any, Any]"]


class AgentRegistry:
    """Registry for discovering and instantiating agents (FR-010).

    The registry maintains a mapping of agent names to their implementation classes.
    It provides methods for registration, lookup, and instantiation of agents.

    Attributes:
        _agents: Internal dictionary mapping agent names to their classes.

    Example:
        ```python
        # Using decorator registration
        @registry.register("code_reviewer")
        class CodeReviewerAgent(MaverickAgent):
            ...

        # Using explicit registration
        registry.register("task_executor", TaskExecutorAgent)

        # Looking up an agent class
        agent_class = registry.get("code_reviewer")

        # Instantiating an agent
        agent = registry.create("code_reviewer", mcp_servers={...})

        # Listing all registered agents
        names = registry.list_agents()
        ```
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._agents: dict[str, MaverickAgentType] = {}

    def register(
        self,
        name: str,
        cls: MaverickAgentType | None = None,
    ) -> MaverickAgentType | Callable[[MaverickAgentType], MaverickAgentType]:
        """Register an agent class (FR-011).

        Can be used as a decorator or called directly. When used as a decorator,
        the name is passed and the class is provided later. When called directly,
        both name and class must be provided.

        Args:
            name: Unique name for the agent.
            cls: Agent class to register (None when used as decorator).

        Returns:
            The registered class when called directly, or a decorator function
            when used as a decorator.

        Raises:
            DuplicateAgentError: If an agent with this name is already registered.

        Example:
            ```python
            # As a decorator
            @registry.register("greeter")
            class GreeterAgent(MaverickAgent):
                ...

            # Direct registration
            registry.register("greeter", GreeterAgent)
            ```
        """
        if cls is None:
            # Used as a decorator: @registry.register("name")
            def decorator(agent_cls: MaverickAgentType) -> MaverickAgentType:
                self._register_impl(name, agent_cls)
                return agent_cls

            return decorator
        else:
            # Direct call: registry.register("name", AgentClass)
            self._register_impl(name, cls)
            return cls

    def _register_impl(self, name: str, cls: MaverickAgentType) -> None:
        """Internal implementation of registration logic.

        Args:
            name: Unique name for the agent.
            cls: Agent class to register.

        Raises:
            DuplicateAgentError: If an agent with this name is already registered.
        """
        if name in self._agents:
            raise DuplicateAgentError(name)
        self._agents[name] = cls

    def get(self, name: str) -> MaverickAgentType:
        """Look up an agent class by name (FR-012).

        Args:
            name: Name of the agent to look up.

        Returns:
            The agent class associated with the name.

        Raises:
            AgentNotFoundError: If no agent is registered with this name.

        Example:
            ```python
            agent_class = registry.get("code_reviewer")
            agent = agent_class(mcp_servers={...})
            ```
        """
        if name not in self._agents:
            raise AgentNotFoundError(name)
        return self._agents[name]

    def list_agents(self) -> list[str]:
        """List all registered agent names.

        Returns:
            Sorted list of registered agent names.

        Example:
            ```python
            names = registry.list_agents()
            # ['code_reviewer', 'task_executor', ...]
            ```
        """
        return sorted(self._agents.keys())

    def create(self, name: str, **kwargs: Any) -> MaverickAgent[Any, Any]:
        """Instantiate an agent by name.

        Args:
            name: Name of the agent to instantiate.
            **kwargs: Arguments to pass to the agent constructor.

        Returns:
            Instantiated agent instance.

        Raises:
            AgentNotFoundError: If no agent is registered with this name.

        Example:
            ```python
            agent = registry.create(
                "code_reviewer",
                mcp_servers={"github": {...}},
            )
            ```
        """
        agent_class = self.get(name)
        return agent_class(**kwargs)


# =============================================================================
# Module-level singleton instance (FR-026)
# =============================================================================

#: Global registry instance for agent registration and lookup
registry = AgentRegistry()


def register(
    name: str,
    registry: AgentRegistry | None = None,  # noqa: A002  # intentionally shadows global
) -> Callable[[MaverickAgentType], MaverickAgentType]:
    """Decorator for registering agent classes.

    Args:
        name: Unique name for the agent.
        registry: Optional registry to use (defaults to global registry).

    Returns:
        Decorator function that registers the class.

    Example:
        ```python
        @register("greeter")
        class GreeterAgent(MaverickAgent):
            ...
        ```
    """
    # Use module-level registry if not provided (via globals to avoid shadowing)
    reg = registry if registry is not None else globals()["registry"]

    def decorator(cls: MaverickAgentType) -> MaverickAgentType:
        reg._register_impl(name, cls)
        return cls

    return decorator
