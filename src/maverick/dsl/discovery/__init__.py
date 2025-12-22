"""Workflow discovery module.

This module provides multi-location workflow discovery with override precedence.
Workflows are discovered from three locations:
1. Built-in: Packaged with Maverick
2. User: ~/.config/maverick/workflows/
3. Project: .maverick/workflows/

Project workflows override user workflows which override built-in workflows.
"""

from __future__ import annotations

from maverick.dsl.discovery.exceptions import (
    WorkflowConflictError,
    WorkflowDiscoveryError,
)
from maverick.dsl.discovery.integration import load_workflows_into_registry
from maverick.dsl.discovery.models import (
    DiscoveredWorkflow,
    DiscoveryResult,
    SkippedWorkflow,
    WorkflowConflict,
    WorkflowMetadata,
    WorkflowSource,
)
from maverick.dsl.discovery.registry import (
    DefaultWorkflowDiscovery,
    WorkflowLoader,
    WorkflowLocator,
    create_discovery,
)

__all__ = [
    # Enums
    "WorkflowSource",
    # Models
    "WorkflowMetadata",
    "DiscoveredWorkflow",
    "SkippedWorkflow",
    "WorkflowConflict",
    "DiscoveryResult",
    # Exceptions
    "WorkflowDiscoveryError",
    "WorkflowConflictError",
    # Services
    "WorkflowLocator",
    "WorkflowLoader",
    "DefaultWorkflowDiscovery",
    # Factory
    "create_discovery",
    # Integration
    "load_workflows_into_registry",
]
