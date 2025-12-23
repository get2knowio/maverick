"""Component registry facade (T025-T031).

This module provides the ComponentRegistry facade that aggregates all
component registries into a single entry point.
"""

from __future__ import annotations

from maverick.dsl.serialization.registry.actions import ActionRegistry
from maverick.dsl.serialization.registry.agents import AgentRegistry
from maverick.dsl.serialization.registry.context_builders import ContextBuilderRegistry
from maverick.dsl.serialization.registry.generators import GeneratorRegistry
from maverick.dsl.serialization.registry.workflows import WorkflowRegistry


class ComponentRegistry:
    """Facade aggregating all component registries.

    Provides a single entry point for accessing all component registries
    (actions, agents, generators, context builders, workflows). Supports both
    strict and lenient modes for reference resolution.

    Attributes:
        actions: Registry for Python callables.
        agents: Registry for MaverickAgent classes.
        generators: Registry for GeneratorAgent classes.
        context_builders: Registry for context builder functions.
        workflows: Registry for workflow definitions.
        strict: If False, defer resolution errors (lenient mode).

    Example:
        ```python
        # Create with default registries
        registry = ComponentRegistry()

        # Create with custom registries
        registry = ComponentRegistry(
            actions=custom_actions,
            agents=custom_agents,
            generators=custom_generators,
            strict=False,  # Lenient mode
        )

        # Access individual registries
        registry.actions.register("my_action", my_func)
        registry.agents.register("my_agent", MyAgentClass)
        registry.generators.register("my_gen", MyGenClass)
        ```
    """

    def __init__(
        self,
        actions: ActionRegistry | None = None,
        agents: AgentRegistry | None = None,
        generators: GeneratorRegistry | None = None,
        context_builders: ContextBuilderRegistry | None = None,
        workflows: WorkflowRegistry | None = None,
        strict: bool = True,
    ) -> None:
        """Initialize the ComponentRegistry facade.

        Args:
            actions: Optional ActionRegistry to use (creates new if None).
            agents: Optional AgentRegistry to use (creates new if None).
            generators: Optional GeneratorRegistry to use (creates new if None).
            context_builders: Optional ContextBuilderRegistry to use (creates
                new if None).
            workflows: Optional WorkflowRegistry to use (creates new if None).
            strict: If False, defer resolution errors (lenient mode).
        """
        self.actions = actions if actions is not None else ActionRegistry()
        self.agents = agents if agents is not None else AgentRegistry()
        self.generators = generators if generators is not None else GeneratorRegistry()
        self.context_builders = (
            context_builders
            if context_builders is not None
            else ContextBuilderRegistry()
        )
        self.workflows = workflows if workflows is not None else WorkflowRegistry()
        self.strict = strict
