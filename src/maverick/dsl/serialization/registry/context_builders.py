"""Context builder registry for context builder functions (T025-T031).

This module provides the ContextBuilderRegistry for managing context builder
functions that can be referenced by name in workflow definitions.
"""

from __future__ import annotations

from collections.abc import Callable

from maverick.dsl.errors import (
    DuplicateComponentError,
    ReferenceResolutionError,
)
from maverick.dsl.serialization.registry.protocol import ContextBuilderType
from maverick.dsl.serialization.registry.validation import validate_context_builder


class ContextBuilderRegistry:
    """Registry for context builder functions.

    Context builders are functions that build context dictionaries for agent
    and generator steps. They are used to provide dynamic context at runtime.

    Attributes:
        _builders: Internal dictionary mapping builder names to functions.

    Example:
        ```python
        # Using decorator registration
        @context_builder_registry.register("git_context")
        def build_git_context() -> dict[str, Any]:
            return {"branch": get_current_branch(), ...}

        # Using explicit registration
        context_builder_registry.register("file_context", build_file_context)

        # Looking up a context builder
        builder = context_builder_registry.get("git_context")

        # Listing all registered context builders
        names = context_builder_registry.list_names()
        ```
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._builders: dict[str, ContextBuilderType] = {}

    def register(
        self,
        name: str,
        component: ContextBuilderType | None = None,
        *,
        validate: bool = True,
    ) -> ContextBuilderType | Callable[[ContextBuilderType], ContextBuilderType]:
        """Register a context builder function.

        Can be used as a decorator or called directly.

        Args:
            name: Unique name for the context builder.
            component: Context builder function to register (None when used as
                decorator).
            validate: Whether to validate that component has correct signature.
                Set to False for testing with mock objects.

        Returns:
            The registered function when called directly, or a decorator function
            when used as a decorator.

        Raises:
            ReferenceResolutionError: If a context builder with this name is
                already registered.

        Example:
            ```python
            # As a decorator
            @registry.register("my_context")
            def my_context_builder() -> dict[str, Any]:
                return {"key": "value"}

            # Direct registration
            registry.register("my_context", my_context_func)

            # For testing with mocks
            registry.register("mock_context", mock_func, validate=False)
            ```
        """
        if component is None:
            # Used as a decorator: @registry.register("name")
            def decorator(builder: ContextBuilderType) -> ContextBuilderType:
                self._register_impl(name, builder, validate=validate)
                return builder

            return decorator
        else:
            # Direct call: registry.register("name", builder_func)
            self._register_impl(name, component, validate=validate)
            return component

    def _register_impl(
        self, name: str, component: ContextBuilderType, *, validate: bool = True
    ) -> None:
        """Internal implementation of registration logic.

        Args:
            name: Unique name for the context builder.
            component: Context builder function to register.
            validate: Whether to validate signature.

        Raises:
            DuplicateComponentError: If a context builder with this name is
                already registered.
            TypeError: If component is not callable or has incorrect signature.
        """
        # Validate that context builder has correct signature
        # (must accept exactly 2 parameters: inputs and step_results)
        if validate:
            validate_context_builder(component, name)

        if name in self._builders:
            raise DuplicateComponentError(
                component_type="context_builder",
                component_name=name,
            )
        self._builders[name] = component

    def get(self, name: str) -> ContextBuilderType:
        """Look up a context builder by name.

        Args:
            name: Name of the context builder to look up.

        Returns:
            The context builder function associated with the name.

        Raises:
            ReferenceResolutionError: If no context builder is registered with
                this name.

        Example:
            ```python
            builder = registry.get("git_context")
            context = builder()
            ```
        """
        if name not in self._builders:
            raise ReferenceResolutionError(
                reference_type="context_builder",
                reference_name=name,
                available_names=list(self._builders.keys()),
            )
        return self._builders[name]

    def list_names(self) -> list[str]:
        """List all registered context builder names.

        Returns:
            Sorted list of registered context builder names.

        Example:
            ```python
            names = registry.list_names()
            # ['file_context', 'git_context', ...]
            ```
        """
        return sorted(self._builders.keys())

    def has(self, name: str) -> bool:
        """Check if a context builder is registered.

        Args:
            name: Name of the context builder to check.

        Returns:
            True if the context builder is registered, False otherwise.

        Example:
            ```python
            if registry.has("git_context"):
                builder = registry.get("git_context")
            ```
        """
        return name in self._builders
