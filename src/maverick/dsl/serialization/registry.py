"""Component registries for workflow serialization (T025-T031).

This module provides registries for managing workflow components:
- ActionRegistry: Python callables (actions)
- GeneratorRegistry: GeneratorAgent classes
- ContextBuilderRegistry: Context builder functions
- WorkflowRegistry: Workflow definitions
- ComponentRegistry: Facade aggregating all registries

Each registry supports decorator-based registration and provides type-safe
lookups with clear error messages.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, TypeVar

from maverick.dsl.serialization.errors import (
    DuplicateComponentError,
    ReferenceResolutionError,
)

if TYPE_CHECKING:
    from maverick.agents.base import MaverickAgent

# Type aliases for registry components
T = TypeVar("T")
ActionType = Callable[..., Any]
GeneratorType = type["MaverickAgent[Any, Any]"]
ContextBuilderType = Callable[..., dict[str, Any]]
WorkflowType = Any  # Will be WorkflowDefinition once defined


# =============================================================================
# Registry Protocol
# =============================================================================


class Registry(Protocol[T]):
    """Protocol for component registries.

    Defines the standard interface that all registries must implement.
    Supports decorator-based registration and type-safe lookups.
    """

    def register(
        self, name: str, component: T | None = None
    ) -> T | Callable[[T], T]: ...

    def get(self, name: str) -> T: ...

    def list_names(self) -> list[str]: ...

    def has(self, name: str) -> bool: ...


# =============================================================================
# ActionRegistry
# =============================================================================


class ActionRegistry:
    """Registry for Python callables (actions).

    Actions are Python functions or callables that can be referenced by name
    in workflow definitions. They are used in PythonStep definitions.

    Attributes:
        _actions: Internal dictionary mapping action names to callables.

    Example:
        ```python
        # Using decorator registration
        @action_registry.register("validate_files")
        def validate_files(path: str) -> bool:
            return Path(path).exists()

        # Using explicit registration
        action_registry.register("cleanup", cleanup_function)

        # Looking up an action
        action = action_registry.get("validate_files")

        # Listing all registered actions
        names = action_registry.list_names()
        ```
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._actions: dict[str, ActionType] = {}

    def register(
        self,
        name: str,
        component: ActionType | None = None,
    ) -> ActionType | Callable[[ActionType], ActionType]:
        """Register an action callable.

        Can be used as a decorator or called directly. When used as a decorator,
        the name is passed and the callable is provided later. When called directly,
        both name and callable must be provided.

        Args:
            name: Unique name for the action.
            component: Action callable to register (None when used as decorator).

        Returns:
            The registered callable when called directly, or a decorator function
            when used as a decorator.

        Raises:
            ReferenceResolutionError: If an action with this name is already registered.

        Example:
            ```python
            # As a decorator
            @registry.register("my_action")
            def my_action(x: int) -> int:
                return x * 2

            # Direct registration
            registry.register("my_action", my_action_func)
            ```
        """
        if component is None:
            # Used as a decorator: @registry.register("name")
            def decorator(action: ActionType) -> ActionType:
                self._register_impl(name, action)
                return action

            return decorator
        else:
            # Direct call: registry.register("name", callable)
            self._register_impl(name, component)
            return component

    def _register_impl(self, name: str, component: ActionType) -> None:
        """Internal implementation of registration logic.

        Args:
            name: Unique name for the action.
            component: Action callable to register.

        Raises:
            DuplicateComponentError: If an action with this name is already registered.
        """
        if name in self._actions:
            raise DuplicateComponentError(
                component_type="action",
                component_name=name,
            )
        self._actions[name] = component

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


# =============================================================================
# GeneratorRegistry
# =============================================================================


class GeneratorRegistry:
    """Registry for GeneratorAgent classes.

    Generators are MaverickAgent subclasses that generate text (commit messages,
    PR descriptions, etc.). They are used in GenerateStep definitions.

    Attributes:
        _generators: Internal dictionary mapping generator names to classes.

    Example:
        ```python
        # Using decorator registration
        @generator_registry.register("commit_msg")
        class CommitMessageGenerator(MaverickAgent):
            ...

        # Using explicit registration
        generator_registry.register("pr_body", PRBodyGenerator)

        # Looking up a generator
        gen_class = generator_registry.get("commit_msg")

        # Listing all registered generators
        names = generator_registry.list_names()
        ```
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._generators: dict[str, GeneratorType] = {}

    def register(
        self,
        name: str,
        component: GeneratorType | None = None,
    ) -> GeneratorType | Callable[[GeneratorType], GeneratorType]:
        """Register a generator class.

        Can be used as a decorator or called directly.

        Args:
            name: Unique name for the generator.
            component: Generator class to register (None when used as decorator).

        Returns:
            The registered class when called directly, or a decorator function
            when used as a decorator.

        Raises:
            ReferenceResolutionError: If a generator with this name is already
                registered.

        Example:
            ```python
            # As a decorator
            @registry.register("my_gen")
            class MyGenerator(MaverickAgent):
                ...

            # Direct registration
            registry.register("my_gen", MyGeneratorClass)
            ```
        """
        if component is None:
            # Used as a decorator: @registry.register("name")
            def decorator(gen_class: GeneratorType) -> GeneratorType:
                self._register_impl(name, gen_class)
                return gen_class

            return decorator
        else:
            # Direct call: registry.register("name", GeneratorClass)
            self._register_impl(name, component)
            return component

    def _register_impl(self, name: str, component: GeneratorType) -> None:
        """Internal implementation of registration logic.

        Args:
            name: Unique name for the generator.
            component: Generator class to register.

        Raises:
            DuplicateComponentError: If a generator with this name is already
                registered.
        """
        if name in self._generators:
            raise DuplicateComponentError(
                component_type="generator",
                component_name=name,
            )
        self._generators[name] = component

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


# =============================================================================
# ContextBuilderRegistry
# =============================================================================


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
    ) -> ContextBuilderType | Callable[[ContextBuilderType], ContextBuilderType]:
        """Register a context builder function.

        Can be used as a decorator or called directly.

        Args:
            name: Unique name for the context builder.
            component: Context builder function to register (None when used as
                decorator).

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
            ```
        """
        if component is None:
            # Used as a decorator: @registry.register("name")
            def decorator(builder: ContextBuilderType) -> ContextBuilderType:
                self._register_impl(name, builder)
                return builder

            return decorator
        else:
            # Direct call: registry.register("name", builder_func)
            self._register_impl(name, component)
            return component

    def _register_impl(self, name: str, component: ContextBuilderType) -> None:
        """Internal implementation of registration logic.

        Args:
            name: Unique name for the context builder.
            component: Context builder function to register.

        Raises:
            DuplicateComponentError: If a context builder with this name is
                already registered.
        """
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


# =============================================================================
# WorkflowRegistry
# =============================================================================


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


# =============================================================================
# ComponentRegistry Facade
# =============================================================================


class ComponentRegistry:
    """Facade aggregating all component registries.

    Provides a single entry point for accessing all component registries
    (actions, generators, context builders, workflows). Supports both strict
    and lenient modes for reference resolution.

    Attributes:
        actions: Registry for Python callables.
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
            generators=custom_generators,
            strict=False,  # Lenient mode
        )

        # Access individual registries
        registry.actions.register("my_action", my_func)
        registry.generators.register("my_gen", MyGenClass)
        ```
    """

    def __init__(
        self,
        actions: ActionRegistry | None = None,
        generators: GeneratorRegistry | None = None,
        context_builders: ContextBuilderRegistry | None = None,
        workflows: WorkflowRegistry | None = None,
        strict: bool = True,
    ) -> None:
        """Initialize the ComponentRegistry facade.

        Args:
            actions: Optional ActionRegistry to use (creates new if None).
            generators: Optional GeneratorRegistry to use (creates new if None).
            context_builders: Optional ContextBuilderRegistry to use (creates
                new if None).
            workflows: Optional WorkflowRegistry to use (creates new if None).
            strict: If False, defer resolution errors (lenient mode).
        """
        self.actions = actions if actions is not None else ActionRegistry()
        self.generators = generators if generators is not None else GeneratorRegistry()
        self.context_builders = (
            context_builders
            if context_builders is not None
            else ContextBuilderRegistry()
        )
        self.workflows = workflows if workflows is not None else WorkflowRegistry()
        self.strict = strict


# =============================================================================
# Module-level singleton instances
# =============================================================================

#: Global action registry instance
action_registry = ActionRegistry()

#: Global generator registry instance
generator_registry = GeneratorRegistry()

#: Global context builder registry instance
context_builder_registry = ContextBuilderRegistry()

#: Global workflow registry instance
workflow_registry = WorkflowRegistry()

#: Global component registry facade (uses singleton registries)
component_registry = ComponentRegistry(
    actions=action_registry,
    generators=generator_registry,
    context_builders=context_builder_registry,
    workflows=workflow_registry,
    strict=True,
)
