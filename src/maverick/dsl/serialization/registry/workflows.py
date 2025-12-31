"""Workflow registry for workflow definitions (T025-T031).

This module provides the WorkflowRegistry for managing workflow definitions
that can be referenced by name in workflow definitions.
"""

from __future__ import annotations

from collections.abc import Callable

from maverick.dsl.errors import (
    DuplicateComponentError,
    ReferenceResolutionError,
)
from maverick.dsl.serialization.registry.protocol import WorkflowType


class WorkflowRegistry:
    """Registry for workflow definitions.

    Workflows are WorkflowDefinition objects that can be referenced by name
    for sub-workflow execution or reuse.

    Attributes:
        _workflows: Internal dictionary mapping workflow names to definitions.

    Example:
        ```python
        # Using decorator registration
        @workflow_registry.register("validation")
        class ValidationWorkflow:
            ...

        # Using explicit registration
        workflow_registry.register("deployment", deployment_workflow)

        # Looking up a workflow
        workflow = workflow_registry.get("validation")

        # Listing all registered workflows
        names = workflow_registry.list_names()
        ```
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._workflows: dict[str, WorkflowType] = {}

    def register(
        self,
        name: str,
        component: WorkflowType | None = None,
    ) -> WorkflowType | Callable[[WorkflowType], WorkflowType]:
        """Register a workflow definition.

        Can be used as a decorator or called directly.

        Args:
            name: Unique name for the workflow.
            component: Workflow definition to register (None when used as decorator).

        Returns:
            The registered workflow when called directly, or a decorator function
            when used as a decorator.

        Raises:
            ReferenceResolutionError: If a workflow with this name is already
                registered.

        Example:
            ```python
            # As a decorator
            @registry.register("my_workflow")
            class MyWorkflow:
                ...

            # Direct registration
            registry.register("my_workflow", my_workflow_def)
            ```
        """
        if component is None:
            # Used as a decorator: @registry.register("name")
            def decorator(workflow: WorkflowType) -> WorkflowType:
                self._register_impl(name, workflow)
                return workflow

            return decorator
        else:
            # Direct call: registry.register("name", workflow_def)
            self._register_impl(name, component)
            return component

    def _register_impl(self, name: str, component: WorkflowType) -> None:
        """Internal implementation of registration logic.

        Args:
            name: Unique name for the workflow.
            component: Workflow definition to register.

        Raises:
            DuplicateComponentError: If a workflow with this name is already
                registered.
        """
        if name in self._workflows:
            raise DuplicateComponentError(
                component_type="workflow",
                component_name=name,
            )
        self._workflows[name] = component

    def get(self, name: str) -> WorkflowType:
        """Look up a workflow by name.

        Args:
            name: Name of the workflow to look up.

        Returns:
            The workflow definition associated with the name.

        Raises:
            ReferenceResolutionError: If no workflow is registered with this name.

        Example:
            ```python
            workflow = registry.get("validation")
            result = await workflow.execute(...)
            ```
        """
        if name not in self._workflows:
            raise ReferenceResolutionError(
                reference_type="workflow",
                reference_name=name,
                available_names=list(self._workflows.keys()),
            )
        return self._workflows[name]

    def list_names(self) -> list[str]:
        """List all registered workflow names.

        Returns:
            Sorted list of registered workflow names.

        Example:
            ```python
            names = registry.list_names()
            # ['deployment', 'validation', ...]
            ```
        """
        return sorted(self._workflows.keys())

    def has(self, name: str) -> bool:
        """Check if a workflow is registered.

        Args:
            name: Name of the workflow to check.

        Returns:
            True if the workflow is registered, False otherwise.

        Example:
            ```python
            if registry.has("validation"):
                workflow = registry.get("validation")
            ```
        """
        return name in self._workflows
