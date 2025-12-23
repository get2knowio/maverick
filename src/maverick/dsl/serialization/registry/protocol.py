"""Registry protocol and type aliases for component registries (T025-T031).

This module defines the standard Registry protocol that all concrete registries
must implement, along with type aliases for the different component types.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, Protocol, TypeAlias, TypeVar

if TYPE_CHECKING:
    from maverick.agents.base import MaverickAgent
    from maverick.dsl.decorator import WorkflowDefinition

# Type aliases for registry components
T = TypeVar("T")
ActionType: TypeAlias = Callable[..., Any]
AgentType: TypeAlias = type["MaverickAgent[Any, Any]"]
GeneratorType: TypeAlias = type["MaverickAgent[Any, Any]"]
# Context builders can be sync or async functions returning dict[str, Any]
# For async functions, the callable returns a Coroutine when invoked
ContextBuilderType: TypeAlias = (
    Callable[..., dict[str, Any]] | Callable[..., Coroutine[Any, Any, dict[str, Any]]]
)
WorkflowType: TypeAlias = "WorkflowDefinition"


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
