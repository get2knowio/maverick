"""Generator registry for GeneratorAgent classes (T025-T031).

This module provides the GeneratorRegistry for managing GeneratorAgent classes
that can be referenced by name in workflow definitions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from maverick.dsl.errors import (
    DuplicateComponentError,
    ReferenceResolutionError,
)
from maverick.dsl.serialization.registry.protocol import GeneratorType
from maverick.dsl.serialization.registry.validation import validate_generator_class


@dataclass(frozen=True, slots=True)
class GeneratorMetadata:
    """Metadata for a registered generator.

    Attributes:
        requires: Tuple of prerequisite names this generator needs.
    """

    requires: tuple[str, ...] = field(default_factory=tuple)


class GeneratorRegistry:
    """Registry for GeneratorAgent classes.

    Generators are MaverickAgent subclasses that generate text (commit messages,
    PR descriptions, etc.). They are used in GenerateStep definitions.

    Attributes:
        _generators: Internal dictionary mapping generator names to classes.
        _metadata: Internal dictionary mapping generator names to metadata.

    Example:
        ```python
        # Using decorator registration with prerequisites
        @generator_registry.register("commit_msg", requires=("anthropic_key",))
        class CommitMessageGenerator(MaverickAgent):
            ...

        # Using explicit registration
        generator_registry.register(
            "pr_body", PRBodyGenerator, requires=("anthropic_key",)
        )

        # Looking up a generator
        gen_class = generator_registry.get("commit_msg")

        # Getting prerequisites for a generator
        prereqs = generator_registry.get_requires("commit_msg")
        ```
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._generators: dict[str, GeneratorType] = {}
        self._metadata: dict[str, GeneratorMetadata] = {}

    def register(
        self,
        name: str,
        component: GeneratorType | None = None,
        *,
        validate: bool = True,
        requires: tuple[str, ...] | list[str] | None = None,
    ) -> GeneratorType | Callable[[GeneratorType], GeneratorType]:
        """Register a generator class.

        Can be used as a decorator or called directly.

        Args:
            name: Unique name for the generator.
            component: Generator class to register (None when used as decorator).
            validate: Whether to validate that component inherits from
                GeneratorAgent. Set to False for testing with mock objects.
            requires: Tuple/list of prerequisite names this generator needs.
                These are automatically collected during preflight.

        Returns:
            The registered class when called directly, or a decorator function
            when used as a decorator.

        Raises:
            ReferenceResolutionError: If a generator with this name is already
                registered.

        Example:
            ```python
            # As a decorator with prerequisites
            @registry.register("my_gen", requires=("anthropic_key",))
            class MyGenerator(MaverickAgent):
                ...

            # Direct registration with prerequisites
            registry.register("my_gen", MyGeneratorClass, requires=["anthropic_key"])

            # For testing with mocks
            registry.register("mock_gen", MockGenerator, validate=False)
            ```
        """
        requires_tuple = tuple(requires) if requires else ()

        if component is None:
            # Used as a decorator: @registry.register("name")
            def decorator(gen_class: GeneratorType) -> GeneratorType:
                self._register_impl(
                    name, gen_class, validate=validate, requires=requires_tuple
                )
                return gen_class

            return decorator
        else:
            # Direct call: registry.register("name", GeneratorClass)
            self._register_impl(
                name, component, validate=validate, requires=requires_tuple
            )
            return component

    def _register_impl(
        self,
        name: str,
        component: GeneratorType,
        *,
        validate: bool = True,
        requires: tuple[str, ...] = (),
    ) -> None:
        """Internal implementation of registration logic.

        Args:
            name: Unique name for the generator.
            component: Generator class to register.
            validate: Whether to validate inheritance.
            requires: Tuple of prerequisite names.

        Raises:
            DuplicateComponentError: If a generator with this name is already
                registered.
            TypeError: If component is not a valid GeneratorAgent subclass.
        """
        # Validate that generator is a GeneratorAgent subclass
        # (generators are agent classes that provide text generation)
        if validate:
            validate_generator_class(component, name)

        if name in self._generators:
            raise DuplicateComponentError(
                component_type="generator",
                component_name=name,
            )
        self._generators[name] = component
        self._metadata[name] = GeneratorMetadata(requires=requires)

    def get(self, name: str) -> GeneratorType:
        """Look up a generator class by name.

        Args:
            name: Name of the generator to look up.

        Returns:
            The generator class associated with the name.

        Raises:
            ReferenceResolutionError: If no generator is registered with this name.

        Example:
            ```python
            gen_class = registry.get("commit_msg")
            generator = gen_class(mcp_servers={...})
            ```
        """
        if name not in self._generators:
            raise ReferenceResolutionError(
                reference_type="generator",
                reference_name=name,
                available_names=list(self._generators.keys()),
            )
        return self._generators[name]

    def list_names(self) -> list[str]:
        """List all registered generator names.

        Returns:
            Sorted list of registered generator names.

        Example:
            ```python
            names = registry.list_names()
            # ['commit_msg', 'pr_body', ...]
            ```
        """
        return sorted(self._generators.keys())

    def has(self, name: str) -> bool:
        """Check if a generator is registered.

        Args:
            name: Name of the generator to check.

        Returns:
            True if the generator is registered, False otherwise.

        Example:
            ```python
            if registry.has("commit_msg"):
                gen_class = registry.get("commit_msg")
            ```
        """
        return name in self._generators

    def get_requires(self, name: str) -> tuple[str, ...]:
        """Get prerequisite names for a generator.

        Args:
            name: Name of the generator.

        Returns:
            Tuple of prerequisite names, or empty tuple if none.

        Raises:
            ReferenceResolutionError: If no generator is registered with this name.

        Example:
            ```python
            prereqs = registry.get_requires("commit_msg")
            # ('anthropic_key',)
            ```
        """
        if name not in self._generators:
            raise ReferenceResolutionError(
                reference_type="generator",
                reference_name=name,
                available_names=list(self._generators.keys()),
            )
        metadata = self._metadata.get(name)
        return metadata.requires if metadata else ()
