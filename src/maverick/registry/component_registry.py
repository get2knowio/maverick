"""Component registry facade (T025-T031).

This module provides the ComponentRegistry facade that aggregates all
component registries into a single entry point.
"""

from __future__ import annotations

from maverick.registry.agents import AgentRegistry


class ComponentRegistry:
    """Facade aggregating all component registries.

    Provides a single entry point for accessing the agent registry.
    Supports both strict and lenient modes for reference resolution.

    Attributes:
        agents: Registry for MaverickAgent classes.
        strict: If False, defer resolution errors (lenient mode).

    Example:
        ```python
        # Create with default registries
        registry = ComponentRegistry()

        # Create with custom registries
        registry = ComponentRegistry(
            agents=custom_agents,
            strict=False,  # Lenient mode
        )

        # Access agent registry
        registry.agents.register("my_agent", MyAgentClass)
        ```
    """

    def __init__(
        self,
        agents: AgentRegistry | None = None,
        strict: bool = True,
    ) -> None:
        """Initialize the ComponentRegistry facade.

        Args:
            agents: Optional AgentRegistry to use (creates new if None).
            strict: If False, defer resolution errors (lenient mode).
        """
        self.agents = agents if agents is not None else AgentRegistry()
        self.strict = strict
