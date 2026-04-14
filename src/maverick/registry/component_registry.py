"""Component registry facade (T025-T031).

This module provides the ComponentRegistry facade that aggregates all
component registries into a single entry point.
"""

from __future__ import annotations

from maverick.registry.actions import ActionRegistry
from maverick.registry.agents import AgentRegistry


class ComponentRegistry:
    """Facade aggregating all component registries.

    Provides a single entry point for accessing all component registries
    (actions, agents). Supports both strict and lenient modes
    for reference resolution.

    Attributes:
        actions: Registry for Python callables.
        agents: Registry for MaverickAgent classes.
        strict: If False, defer resolution errors (lenient mode).

    Example:
        ```python
        # Create with default registries
        registry = ComponentRegistry()

        # Create with custom registries
        registry = ComponentRegistry(
            actions=custom_actions,
            agents=custom_agents,
            strict=False,  # Lenient mode
        )

        # Access individual registries
        registry.actions.register("my_action", my_func)
        registry.agents.register("my_agent", MyAgentClass)
        ```
    """

    def __init__(
        self,
        actions: ActionRegistry | None = None,
        agents: AgentRegistry | None = None,
        strict: bool = True,
    ) -> None:
        """Initialize the ComponentRegistry facade.

        Args:
            actions: Optional ActionRegistry to use (creates new if None).
            agents: Optional AgentRegistry to use (creates new if None).
            strict: If False, defer resolution errors (lenient mode).
        """
        self.actions = actions if actions is not None else ActionRegistry()
        self.agents = agents if agents is not None else AgentRegistry()
        self.strict = strict
