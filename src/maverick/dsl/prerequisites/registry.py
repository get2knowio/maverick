"""Prerequisite registry for managing available checks.

This module provides the PrerequisiteRegistry class that acts as a catalog
of all available prerequisite checks. It supports registration, lookup,
and dependency resolution.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from maverick.dsl.prerequisites.models import Prerequisite, PrerequisiteResult
from maverick.logging import get_logger

logger = get_logger(__name__)


class PrerequisiteRegistry:
    """Registry of available prerequisite checks.

    Acts as a catalog of all prerequisite checks that can be declared
    by workflow steps or registered components. Supports dependency
    resolution and provides lookup by name.

    Attributes:
        _prerequisites: Internal dict mapping names to Prerequisite objects.

    Example:
        ```python
        registry = PrerequisiteRegistry()

        # Register a prerequisite
        @registry.register(
            name="git_identity",
            display_name="Git Identity",
            dependencies=("git",),
            remediation="Run: git config --global user.name 'Your Name'",
        )
        async def check_git_identity() -> PrerequisiteResult:
            # Check implementation
            ...

        # Look up a prerequisite
        prereq = registry.get("git_identity")

        # Get all dependencies for a set of prerequisites
        all_deps = registry.get_all_dependencies(["git_identity"])
        # Returns: ["git", "git_identity"]
        ```
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._prerequisites: dict[str, Prerequisite] = {}

    def register(
        self,
        name: str,
        display_name: str,
        *,
        dependencies: tuple[str, ...] = (),
        cost: int = 1,
        remediation: str = "",
    ) -> Callable[
        [Callable[[], Awaitable[PrerequisiteResult]]],
        Callable[[], Awaitable[PrerequisiteResult]],
    ]:
        """Register a prerequisite check function.

        Use as a decorator on an async function that performs the check.

        Args:
            name: Unique identifier for the prerequisite.
            display_name: Human-readable name for UI display.
            dependencies: Names of prerequisites that must pass first.
            cost: Relative cost (1=cheap, 2=moderate, 3=expensive/network).
            remediation: User-facing fix instructions.

        Returns:
            Decorator function that registers the check.

        Raises:
            ValueError: If a prerequisite with this name already exists.

        Example:
            ```python
            @registry.register(
                name="git",
                display_name="Git CLI",
                remediation="Install Git from https://git-scm.com/",
            )
            async def check_git() -> PrerequisiteResult:
                import shutil
                if shutil.which("git"):
                    return PrerequisiteResult(success=True, message="Git found")
                return PrerequisiteResult(success=False, message="Git not found")
            ```
        """

        def decorator(
            fn: Callable[[], Awaitable[PrerequisiteResult]],
        ) -> Callable[[], Awaitable[PrerequisiteResult]]:
            if name in self._prerequisites:
                raise ValueError(f"Prerequisite '{name}' is already registered")

            prereq = Prerequisite(
                name=name,
                display_name=display_name,
                check_fn=fn,
                dependencies=dependencies,
                cost=cost,
                remediation=remediation,
            )
            self._prerequisites[name] = prereq
            logger.debug(f"Registered prerequisite: {name}")
            return fn

        return decorator

    def register_prerequisite(self, prereq: Prerequisite) -> None:
        """Register a Prerequisite object directly.

        Args:
            prereq: The Prerequisite to register.

        Raises:
            ValueError: If a prerequisite with this name already exists.
        """
        if prereq.name in self._prerequisites:
            raise ValueError(f"Prerequisite '{prereq.name}' is already registered")

        self._prerequisites[prereq.name] = prereq
        logger.debug(f"Registered prerequisite: {prereq.name}")

    def get(self, name: str) -> Prerequisite:
        """Look up a prerequisite by name.

        Args:
            name: The prerequisite name.

        Returns:
            The Prerequisite object.

        Raises:
            KeyError: If no prerequisite with this name exists.
        """
        if name not in self._prerequisites:
            available = ", ".join(sorted(self._prerequisites.keys()))
            raise KeyError(
                f"Unknown prerequisite '{name}'. Available: {available or '(none)'}"
            )
        return self._prerequisites[name]

    def has(self, name: str) -> bool:
        """Check if a prerequisite is registered.

        Args:
            name: The prerequisite name.

        Returns:
            True if registered, False otherwise.
        """
        return name in self._prerequisites

    def list_names(self) -> list[str]:
        """List all registered prerequisite names.

        Returns:
            Sorted list of prerequisite names.
        """
        return sorted(self._prerequisites.keys())

    def list_all(self) -> list[Prerequisite]:
        """List all registered prerequisites.

        Returns:
            List of Prerequisite objects sorted by name.
        """
        return [
            self._prerequisites[name] for name in sorted(self._prerequisites.keys())
        ]

    def get_dependencies(self, name: str) -> tuple[str, ...]:
        """Get direct dependencies for a prerequisite.

        Args:
            name: The prerequisite name.

        Returns:
            Tuple of dependency prerequisite names.

        Raises:
            KeyError: If no prerequisite with this name exists.
        """
        return self.get(name).dependencies

    def get_all_dependencies(self, names: list[str]) -> list[str]:
        """Get all transitive dependencies for a set of prerequisites.

        Performs a depth-first traversal to collect all dependencies,
        returning them in topological order (dependencies before dependents).

        Args:
            names: List of prerequisite names.

        Returns:
            List of all prerequisite names in dependency order.

        Raises:
            KeyError: If any prerequisite name is unknown.
            ValueError: If a circular dependency is detected.
        """
        visited: set[str] = set()
        in_stack: set[str] = set()  # For cycle detection
        result: list[str] = []

        def visit(name: str) -> None:
            if name in in_stack:
                raise ValueError(f"Circular dependency detected involving '{name}'")

            if name in visited:
                return

            in_stack.add(name)

            prereq = self.get(name)
            for dep in prereq.dependencies:
                visit(dep)

            in_stack.remove(name)
            visited.add(name)
            result.append(name)

        for name in names:
            visit(name)

        return result

    def clear(self) -> None:
        """Clear all registered prerequisites.

        Primarily useful for testing.
        """
        self._prerequisites.clear()


# Global prerequisite registry instance
prerequisite_registry = PrerequisiteRegistry()
