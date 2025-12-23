"""Component registries for workflow serialization (T025-T031).

This package provides registries for managing workflow components:
- ActionRegistry: Python callables (actions)
- AgentRegistry: MaverickAgent classes
- GeneratorRegistry: GeneratorAgent classes
- ContextBuilderRegistry: Context builder functions
- WorkflowRegistry: Workflow definitions
- ComponentRegistry: Facade aggregating all registries

Each registry supports decorator-based registration and provides type-safe
lookups with clear error messages.
"""

from __future__ import annotations

from maverick.dsl.serialization.registry.actions import ActionRegistry
from maverick.dsl.serialization.registry.agents import AgentRegistry
from maverick.dsl.serialization.registry.component_registry import ComponentRegistry
from maverick.dsl.serialization.registry.context_builders import ContextBuilderRegistry
from maverick.dsl.serialization.registry.generators import GeneratorRegistry
from maverick.dsl.serialization.registry.protocol import (
    ActionType,
    AgentType,
    ContextBuilderType,
    GeneratorType,
    Registry,
    WorkflowType,
)
from maverick.dsl.serialization.registry.workflows import WorkflowRegistry

# Module-level singleton instances
#: Global action registry instance
action_registry = ActionRegistry()

#: Global agent registry instance
agent_registry = AgentRegistry()

#: Global generator registry instance
generator_registry = GeneratorRegistry()

#: Global context builder registry instance
context_builder_registry = ContextBuilderRegistry()

#: Global workflow registry instance
workflow_registry = WorkflowRegistry()

#: Global component registry facade (uses singleton registries)
component_registry = ComponentRegistry(
    actions=action_registry,
    agents=agent_registry,
    generators=generator_registry,
    context_builders=context_builder_registry,
    workflows=workflow_registry,
    strict=True,
)

__all__ = [
    # Registry classes
    "ActionRegistry",
    "AgentRegistry",
    "GeneratorRegistry",
    "ContextBuilderRegistry",
    "WorkflowRegistry",
    "ComponentRegistry",
    # Protocol and type aliases
    "Registry",
    "ActionType",
    "AgentType",
    "GeneratorType",
    "ContextBuilderType",
    "WorkflowType",
    # Singleton instances
    "action_registry",
    "agent_registry",
    "generator_registry",
    "context_builder_registry",
    "workflow_registry",
    "component_registry",
]
