"""Component registries for workflow components (T025-T031).

This package provides registries for managing workflow components:
- ActionRegistry: Python callables (actions)
- AgentRegistry: MaverickAgent classes
- GeneratorRegistry: GeneratorAgent classes
- ComponentRegistry: Facade aggregating all registries

Each registry supports decorator-based registration and provides type-safe
lookups with clear error messages.
"""

from __future__ import annotations

from maverick.registry.actions import ActionRegistry
from maverick.registry.agents import AgentRegistry
from maverick.registry.component_registry import ComponentRegistry
from maverick.registry.generators import GeneratorRegistry
from maverick.registry.protocol import (
    ActionType,
    AgentType,
    GeneratorType,
    Registry,
)

# Module-level singleton instances
#: Global action registry instance
action_registry = ActionRegistry()

#: Global agent registry instance
agent_registry = AgentRegistry()

#: Global generator registry instance
generator_registry = GeneratorRegistry()

#: Global component registry facade (uses singleton registries)
component_registry = ComponentRegistry(
    actions=action_registry,
    agents=agent_registry,
    generators=generator_registry,
    strict=True,
)

__all__ = [
    # Registry classes
    "ActionRegistry",
    "AgentRegistry",
    "GeneratorRegistry",
    "ComponentRegistry",
    # Protocol and type aliases
    "Registry",
    "ActionType",
    "AgentType",
    "GeneratorType",
    # Singleton instances
    "action_registry",
    "agent_registry",
    "generator_registry",
    "component_registry",
]
