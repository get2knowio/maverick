"""Unit tests for prerequisite models."""

from __future__ import annotations

import pytest

from maverick.dsl.prerequisites.models import (
    PreflightCheckResult,
    PreflightPlan,
    PreflightResult,
    Prerequisite,
    PrerequisiteResult,
)


class TestPrerequisite:
    """Tests for Prerequisite dataclass."""

    def test_creation_minimal(self) -> None:
        """Test creating a prerequisite with minimal fields."""

        async def check() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        prereq = Prerequisite(
            name="test",
            display_name="Test Check",
            check_fn=check,
        )

        assert prereq.name == "test"
        assert prereq.display_name == "Test Check"
        assert prereq.dependencies == ()
        assert prereq.cost == 1
        assert prereq.remediation == ""

    def test_creation_full(self) -> None:
        """Test creating a prerequisite with all fields."""

        async def check() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        prereq = Prerequisite(
            name="git_identity",
            display_name="Git Identity",
            check_fn=check,
            dependencies=("git",),
            cost=2,
            remediation="Configure git user.name and user.email",
        )

        assert prereq.name == "git_identity"
        assert prereq.dependencies == ("git",)
        assert prereq.cost == 2
        assert prereq.remediation == "Configure git user.name and user.email"

    def test_immutability(self) -> None:
        """Test that prerequisite is immutable (frozen)."""

        async def check() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        prereq = Prerequisite(name="test", display_name="Test", check_fn=check)

        with pytest.raises(AttributeError):
            prereq.name = "changed"  # type: ignore[misc]


class TestPrerequisiteResult:
    """Tests for PrerequisiteResult dataclass."""

    def test_success_result(self) -> None:
        """Test creating a success result."""
        result = PrerequisiteResult(
            success=True,
            message="Git identity configured: John Doe <john@example.com>",
            duration_ms=15,
        )

        assert result.success is True
        assert "John Doe" in result.message
        assert result.duration_ms == 15
        assert result.details is None

    def test_failure_result(self) -> None:
        """Test creating a failure result."""
        result = PrerequisiteResult(
            success=False,
            message="Git is not installed",
            duration_ms=5,
            details={"checked_path": "/usr/bin/git"},
        )

        assert result.success is False
        assert "Git" in result.message
        assert result.details == {"checked_path": "/usr/bin/git"}


class TestPreflightPlan:
    """Tests for PreflightPlan dataclass."""

    def test_empty_plan(self) -> None:
        """Test creating an empty plan."""
        plan = PreflightPlan(
            prerequisites=(),
            step_requirements={},
            execution_order=(),
        )

        assert plan.prerequisites == ()
        assert plan.execution_order == ()

    def test_plan_with_prerequisites(self) -> None:
        """Test creating a plan with prerequisites."""
        plan = PreflightPlan(
            prerequisites=("git", "git_repo", "git_identity"),
            step_requirements={
                "git": ("init", "commit"),
                "git_repo": ("init",),
                "git_identity": ("commit",),
            },
            execution_order=("git", "git_repo", "git_identity"),
        )

        assert len(plan.prerequisites) == 3
        assert plan.step_requirements["git"] == ("init", "commit")
        assert plan.execution_order == ("git", "git_repo", "git_identity")


class TestPreflightResult:
    """Tests for PreflightResult dataclass."""

    def test_success_result(self) -> None:
        """Test creating a successful preflight result."""

        async def check() -> PrerequisiteResult:
            return PrerequisiteResult(success=True, message="OK")

        prereq = Prerequisite(name="git", display_name="Git", check_fn=check)
        check_result = PreflightCheckResult(
            prerequisite=prereq,
            result=PrerequisiteResult(
                success=True, message="Git found", duration_ms=10
            ),
            affected_steps=("commit",),
        )

        result = PreflightResult(
            success=True,
            check_results=(check_result,),
            total_duration_ms=10,
        )

        assert result.success is True
        assert len(result.check_results) == 1
        assert result.format_error() == ""
        assert len(result.get_passed_checks()) == 1
        assert len(result.get_failed_checks()) == 0

    def test_failure_result(self) -> None:
        """Test creating a failed preflight result."""

        async def check() -> PrerequisiteResult:
            return PrerequisiteResult(success=False, message="Not found")

        prereq = Prerequisite(
            name="git",
            display_name="Git CLI",
            check_fn=check,
            remediation="Install Git from https://git-scm.com/",
        )
        check_result = PreflightCheckResult(
            prerequisite=prereq,
            result=PrerequisiteResult(
                success=False, message="Git not found on PATH", duration_ms=5
            ),
            affected_steps=("init", "commit"),
        )

        result = PreflightResult(
            success=False,
            check_results=(check_result,),
            total_duration_ms=5,
        )

        assert result.success is False
        assert len(result.get_failed_checks()) == 1
        assert len(result.get_passed_checks()) == 0

        error_msg = result.format_error()
        assert "Preflight checks failed" in error_msg
        assert "Git CLI" in error_msg
        assert "Git not found" in error_msg
        assert "init, commit" in error_msg
        assert "https://git-scm.com" in error_msg
