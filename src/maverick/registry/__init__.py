"""Component registries for workflow components (T025-T031).

This package provides registries for managing workflow components:
- AgentRegistry: MaverickAgent classes
- ComponentRegistry: Facade aggregating all registries

Each registry supports decorator-based registration and provides type-safe
lookups with clear error messages.
"""

from __future__ import annotations

from maverick.registry.agents import AgentRegistry
from maverick.registry.component_registry import ComponentRegistry
from maverick.registry.protocol import (
    AgentType,
    Registry,
)

# Module-level singleton instances
#: Global agent registry instance
agent_registry = AgentRegistry()

#: Global component registry facade (uses singleton registries)
component_registry = ComponentRegistry(
    agents=agent_registry,
    strict=True,
)

__all__ = [
    # Registry classes
    "AgentRegistry",
    "ComponentRegistry",
    # Protocol and type aliases
    "Registry",
    "AgentType",
    # Singleton instances
    "agent_registry",
    "component_registry",
]
