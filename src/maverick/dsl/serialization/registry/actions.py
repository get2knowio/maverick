"""Action registry for Python callables (T025-T031).

This module provides the ActionRegistry for managing Python callables (actions)
that can be referenced by name in workflow definitions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from maverick.dsl.errors import (
    DuplicateComponentError,
    ReferenceResolutionError,
)
from maverick.dsl.serialization.registry.protocol import ActionType
from maverick.dsl.serialization.registry.validation import validate_callable


@dataclass(frozen=True, slots=True)
class ComponentMetadata:
    """Metadata for a registered component.

    Attributes:
        requires: Tuple of prerequisite names this component needs.
    """

    requires: tuple[str, ...] = field(default_factory=tuple)


class ActionRegistry:
    """Registry for Python callables (actions).

    Actions are Python functions or callables that can be referenced by name
    in workflow definitions. They are used in PythonStep definitions.

    Attributes:
        _actions: Internal dictionary mapping action names to callables.
        _metadata: Internal dictionary mapping action names to metadata.

    Example:
        ```python
        # Using decorator registration with prerequisites
        @action_registry.register("git_commit", requires=("git", "git_identity"))
        async def git_commit(message: str) -> dict:
            ...

        # Using explicit registration
        action_registry.register("cleanup", cleanup_function)

        # Looking up an action
        action = action_registry.get("validate_files")

        # Getting prerequisites for an action
        prereqs = action_registry.get_requires("git_commit")
        # Returns: ("git", "git_identity")
        ```
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._actions: dict[str, ActionType] = {}
        self._metadata: dict[str, ComponentMetadata] = {}

    def register(
        self,
        name: str,
        component: ActionType | None = None,
        *,
        requires: tuple[str, ...] | list[str] | None = None,
    ) -> ActionType | Callable[[ActionType], ActionType]:
        """Register an action callable.

        Can be used as a decorator or called directly. When used as a decorator,
        the name is passed and the callable is provided later. When called directly,
        both name and callable must be provided.

        Args:
            name: Unique name for the action.
            component: Action callable to register (None when used as decorator).
            requires: Tuple/list of prerequisite names this action needs.
                These are automatically collected during preflight.

        Returns:
            The registered callable when called directly, or a decorator function
            when used as a decorator.

        Raises:
            ReferenceResolutionError: If an action with this name is already registered.

        Example:
            ```python
            # As a decorator with prerequisites
            @registry.register("git_commit", requires=("git", "git_identity"))
            async def git_commit(message: str) -> dict:
                ...

            # Direct registration with prerequisites
            registry.register("my_action", my_action_func, requires=["anthropic_key"])
            ```
        """
        requires_tuple = tuple(requires) if requires else ()

        if component is None:
            # Used as a decorator: @registry.register("name")
            def decorator(action: ActionType) -> ActionType:
                self._register_impl(name, action, requires=requires_tuple)
                return action

            return decorator
        else:
            # Direct call: registry.register("name", callable)
            self._register_impl(name, component, requires=requires_tuple)
            return component

    def _register_impl(
        self,
        name: str,
        component: ActionType,
        *,
        requires: tuple[str, ...] = (),
    ) -> None:
        """Internal implementation of registration logic.

        Args:
            name: Unique name for the action.
            component: Action callable to register.
            requires: Tuple of prerequisite names.

        Raises:
            DuplicateComponentError: If an action with this name is already registered.
            TypeError: If component is not callable.
        """
        # Validate that action is callable
        validate_callable(component, name)

        if name in self._actions:
            raise DuplicateComponentError(
                component_type="action",
                component_name=name,
            )
        self._actions[name] = component
        self._metadata[name] = ComponentMetadata(requires=requires)

    def get(self, name: str) -> ActionType:
        """Look up an action by name.

        Args:
            name: Name of the action to look up.

        Returns:
            The action callable associated with the name.

        Raises:
            ReferenceResolutionError: If no action is registered with this name.

        Example:
            ```python
            action = registry.get("validate_files")
            result = action("/path/to/file")
            ```
        """
        if name not in self._actions:
            raise ReferenceResolutionError(
                reference_type="action",
                reference_name=name,
                available_names=list(self._actions.keys()),
            )
        return self._actions[name]

    def list_names(self) -> list[str]:
        """List all registered action names.

        Returns:
            Sorted list of registered action names.

        Example:
            ```python
            names = registry.list_names()
            # ['cleanup', 'validate_files', ...]
            ```
        """
        return sorted(self._actions.keys())

    def has(self, name: str) -> bool:
        """Check if an action is registered.

        Args:
            name: Name of the action to check.

        Returns:
            True if the action is registered, False otherwise.

        Example:
            ```python
            if registry.has("validate_files"):
                action = registry.get("validate_files")
            ```
        """
        return name in self._actions

    def get_requires(self, name: str) -> tuple[str, ...]:
        """Get prerequisite names for an action.

        Args:
            name: Name of the action.

        Returns:
            Tuple of prerequisite names, or empty tuple if none.

        Raises:
            ReferenceResolutionError: If no action is registered with this name.

        Example:
            ```python
            prereqs = registry.get_requires("git_commit")
            # ('git', 'git_identity')
            ```
        """
        if name not in self._actions:
            raise ReferenceResolutionError(
                reference_type="action",
                reference_name=name,
                available_names=list(self._actions.keys()),
            )
        metadata = self._metadata.get(name)
        return metadata.requires if metadata else ()
