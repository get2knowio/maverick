"""Registry protocol and type aliases for component registries (T025-T031).

This module defines the standard Registry protocol that all concrete registries
must implement, along with type aliases for the different component types.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, Protocol, TypeAlias, TypeVar

if TYPE_CHECKING:
    from maverick.agents.base import MaverickAgent
    from maverick.dsl.serialization.schema import WorkflowFile

# Type aliases for registry components
T = TypeVar("T")

# Actions are callable functions that accept keyword arguments and return Any
# They can be sync or async functions
ActionType: TypeAlias = Callable[..., Any]

# Agents are MaverickAgent subclasses
AgentType: TypeAlias = type["MaverickAgent[Any, Any]"]

# Generators are MaverickAgent subclasses (same as AgentType)
GeneratorType: TypeAlias = type["MaverickAgent[Any, Any]"]

# Context builders are functions that accept exactly 2 positional parameters:
# - inputs: dict[str, Any] - Workflow input parameters
# - step_results: dict[str, Any] - Results from previously executed steps
# They can be sync or async and return any value (typically dict or Pydantic model)
ContextBuilderType: TypeAlias = (
    Callable[[dict[str, Any], dict[str, Any]], Any]
    | Callable[[dict[str, Any], dict[str, Any]], Coroutine[Any, Any, Any]]
)

# Workflows are WorkflowFile instances (YAML-based serialization DSL only)
WorkflowType: TypeAlias = "WorkflowFile"


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
