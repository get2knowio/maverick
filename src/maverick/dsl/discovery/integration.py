"""Integration between workflow discovery and component registry.

This module provides the bridge between the workflow discovery system
(which finds workflows and fragments from multiple locations) and the
component registry (which is used by WorkflowFileExecutor for runtime lookup).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maverick.dsl.serialization.registry import ComponentRegistry

from maverick.dsl.discovery.registry import create_discovery

__all__ = [
    "load_workflows_into_registry",
]


def load_workflows_into_registry(registry: ComponentRegistry) -> None:
    """Discover and register all workflows and fragments.

    This function runs workflow discovery to find workflows and fragments
    from all configured locations (builtin, user, project) and registers
    them in the provided ComponentRegistry. This makes them available for
    runtime lookup by WorkflowFileExecutor when executing subworkflow steps.

    The discovery system already handles precedence (PROJECT > USER > BUILTIN),
    so only the "winning" workflow for each name is included in the result.
    Fragments follow the same precedence rules.

    Args:
        registry: ComponentRegistry to populate with discovered workflows
            and fragments.

    Example:
        ```python
        from maverick.dsl.serialization.registry import ComponentRegistry
        from maverick.dsl.discovery.integration import load_workflows_into_registry

        # Create a registry
        registry = ComponentRegistry()

        # Load all discovered workflows and fragments
        load_workflows_into_registry(registry)

        # Now workflows can be looked up by name
        workflow = registry.workflows.get("fly")
        ```

    Note:
        - Workflows and fragments are registered in the same namespace
          (registry.workflows)
        - The discovery result only contains the highest-precedence workflow
          for each name (precedence already applied)
        - No duplicate checking is needed since discovery ensures uniqueness
    """
    # Create discovery service
    discovery = create_discovery()

    # Run discovery to find all workflows and fragments
    result = discovery.discover()

    # Register workflows
    # The discovery system has already applied precedence rules,
    # so we can directly register each workflow
    for discovered_workflow in result.workflows:
        # discovered_workflow.workflow is the WorkflowFile object
        # discovered_workflow.source indicates origin (builtin/user/project)
        registry.workflows.register(
            discovered_workflow.workflow.name,
            discovered_workflow.workflow,
        )

    # Register fragments
    # Fragments are reusable sub-workflows that can be invoked by other workflows.
    # They follow the same precedence rules as workflows and are registered
    # in the same namespace.
    for discovered_fragment in result.fragments:
        registry.workflows.register(
            discovered_fragment.workflow.name,
            discovered_fragment.workflow,
        )
