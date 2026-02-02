"""Unit tests for the prerequisite registry."""

from __future__ import annotations

import pytest

from maverick.dsl.prerequisites.models import Prerequisite, PrerequisiteResult
from maverick.dsl.prerequisites.registry import PrerequisiteRegistry


class TestPrerequisiteRegistry:
    """Tests for PrerequisiteRegistry."""

    @pytest.fixture
    def registry(self) -> PrerequisiteRegistry:
        """Create a fresh registry for each test."""
        return PrerequisiteRegistry()

    def test_register_with_decorator(self, registry: PrerequisiteRegistry) -> None:
        """Test registering a prerequisite using the decorator."""

        @registry.register(
            name="test_check",
            display_name="Test Check",
            cost=1,
        )
        async def check_test() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        assert registry.has("test_check")
        prereq = registry.get("test_check")
        assert prereq.name == "test_check"
        assert prereq.display_name == "Test Check"
        assert prereq.cost == 1

    def test_register_with_dependencies(self, registry: PrerequisiteRegistry) -> None:
        """Test registering a prerequisite with dependencies."""

        @registry.register(
            name="base",
            display_name="Base",
        )
        async def check_base() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        @registry.register(
            name="dependent",
            display_name="Dependent",
            dependencies=("base",),
        )
        async def check_dependent() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        prereq = registry.get("dependent")
        assert prereq.dependencies == ("base",)

    def test_register_prerequisite_directly(
        self, registry: PrerequisiteRegistry
    ) -> None:
        """Test registering a Prerequisite object directly."""

        async def check() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        prereq = Prerequisite(
            name="direct",
            display_name="Direct Registration",
            check_fn=check,
        )
        registry.register_prerequisite(prereq)

        assert registry.has("direct")
        assert registry.get("direct") is prereq

    def test_duplicate_registration_raises(
        self, registry: PrerequisiteRegistry
    ) -> None:
        """Test that duplicate registration raises an error."""

        @registry.register(name="dup", display_name="Duplicate")
        async def check1() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        with pytest.raises(ValueError, match="already registered"):

            @registry.register(name="dup", display_name="Duplicate Again")
            async def check2() -> PrerequisiteResult:
                return PrerequisiteResult(success=True, message="OK")

    def test_get_unknown_raises(self, registry: PrerequisiteRegistry) -> None:
        """Test that getting an unknown prerequisite raises KeyError."""
        with pytest.raises(KeyError, match="Unknown prerequisite"):
            registry.get("nonexistent")

    def test_has_returns_false_for_unknown(
        self, registry: PrerequisiteRegistry
    ) -> None:
        """Test that has() returns False for unknown prerequisites."""
        assert registry.has("nonexistent") is False

    def test_list_names(self, registry: PrerequisiteRegistry) -> None:
        """Test listing all registered prerequisite names."""

        @registry.register(name="beta", display_name="Beta")
        async def check_beta() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        @registry.register(name="alpha", display_name="Alpha")
        async def check_alpha() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        names = registry.list_names()
        assert names == ["alpha", "beta"]  # Sorted

    def test_list_all(self, registry: PrerequisiteRegistry) -> None:
        """Test listing all registered prerequisites."""

        @registry.register(name="first", display_name="First")
        async def check1() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        @registry.register(name="second", display_name="Second")
        async def check2() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        prereqs = registry.list_all()
        assert len(prereqs) == 2
        assert prereqs[0].name == "first"
        assert prereqs[1].name == "second"

    def test_get_dependencies(self, registry: PrerequisiteRegistry) -> None:
        """Test getting direct dependencies for a prerequisite."""

        @registry.register(name="git", display_name="Git")
        async def check_git() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        @registry.register(
            name="git_identity", display_name="Git ID", dependencies=("git",)
        )
        async def check_id() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        deps = registry.get_dependencies("git_identity")
        assert deps == ("git",)

    def test_get_all_dependencies(self, registry: PrerequisiteRegistry) -> None:
        """Test getting all transitive dependencies."""

        @registry.register(name="a", display_name="A")
        async def check_a() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        @registry.register(name="b", display_name="B", dependencies=("a",))
        async def check_b() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        @registry.register(name="c", display_name="C", dependencies=("b",))
        async def check_c() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        all_deps = registry.get_all_dependencies(["c"])
        # Should be in topological order: a, b, c
        assert all_deps == ["a", "b", "c"]

    def test_get_all_dependencies_multiple(
        self, registry: PrerequisiteRegistry
    ) -> None:
        """Test getting all dependencies for multiple starting points."""

        @registry.register(name="git", display_name="Git")
        async def check_git() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        @registry.register(
            name="git_repo", display_name="Git Repo", dependencies=("git",)
        )
        async def check_repo() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        @registry.register(
            name="git_identity", display_name="Git ID", dependencies=("git",)
        )
        async def check_id() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        all_deps = registry.get_all_dependencies(["git_repo", "git_identity"])
        # Should include git (common dependency) plus both requested
        assert "git" in all_deps
        assert "git_repo" in all_deps
        assert "git_identity" in all_deps
        # git should come before its dependents
        git_idx = all_deps.index("git")
        assert git_idx < all_deps.index("git_repo")
        assert git_idx < all_deps.index("git_identity")

    def test_get_all_dependencies_circular_raises(
        self, registry: PrerequisiteRegistry
    ) -> None:
        """Test that circular dependencies are detected."""

        async def check() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        # Create circular dependency manually
        registry.register_prerequisite(
            Prerequisite(
                name="a", display_name="A", check_fn=check, dependencies=("b",)
            )
        )
        registry.register_prerequisite(
            Prerequisite(
                name="b", display_name="B", check_fn=check, dependencies=("a",)
            )
        )

        with pytest.raises(ValueError, match="Circular dependency"):
            registry.get_all_dependencies(["a"])

    def test_clear(self, registry: PrerequisiteRegistry) -> None:
        """Test clearing the registry."""

        @registry.register(name="test", display_name="Test")
        async def check() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        assert registry.has("test")

        registry.clear()

        assert not registry.has("test")
        assert registry.list_names() == []
