"""Registry protocol and type aliases for component registries (T025-T031).

This module defines the standard Registry protocol that all concrete registries
must implement, along with type aliases for the different component types.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, TypeAlias, TypeVar

if TYPE_CHECKING:
    from maverick.agents.base import MaverickAgent

# Type aliases for registry components
T = TypeVar("T")

# Actions are callable functions that accept keyword arguments and return Any
# They can be sync or async functions
ActionType: TypeAlias = Callable[..., Any]

# Agents are MaverickAgent subclasses
AgentType: TypeAlias = type["MaverickAgent[Any, Any]"]

# Generators are MaverickAgent subclasses (same as AgentType)
GeneratorType: TypeAlias = type["MaverickAgent[Any, Any]"]


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
