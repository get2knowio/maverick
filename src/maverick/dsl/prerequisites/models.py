"""Dataclass models for the prerequisite system.

This module defines the core data structures for prerequisite checks:
- Prerequisite: A single check definition with dependencies and metadata
- PrerequisiteResult: The result of running a single check
- PreflightPlan: The collected set of prerequisites to run for a workflow
- PreflightResult: The aggregated results of all prerequisite checks
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Prerequisite:
    """A single prerequisite check definition.

    Attributes:
        name: Unique identifier for this prerequisite (e.g., "git_identity").
        display_name: Human-readable name for UI display (e.g., "Git Identity").
        check_fn: Async function that performs the check and returns PrerequisiteResult.
        dependencies: Names of prerequisites that must pass before this one runs.
        cost: Relative cost indicator (1=cheap/local, 2=moderate, 3=expensive/network).
        remediation: User-facing instructions for fixing a failed check.

    Example:
        >>> async def check_git_identity() -> PrerequisiteResult:
        ...     # Check git user.name and user.email
        ...     ...
        >>> prereq = Prerequisite(
        ...     name="git_identity",
        ...     display_name="Git Identity",
        ...     check_fn=check_git_identity,
        ...     dependencies=("git",),
        ...     cost=1,
        ...     remediation="Run: git config --global user.name 'Your Name'",
        ... )
    """

    name: str
    display_name: str
    check_fn: Callable[[], Awaitable[PrerequisiteResult]]
    dependencies: tuple[str, ...] = ()
    cost: int = 1
    remediation: str = ""


@dataclass(frozen=True, slots=True)
class PrerequisiteResult:
    """Result of a single prerequisite check.

    Attributes:
        success: Whether the check passed.
        message: Human-readable status message (success or error description).
        duration_ms: How long the check took to run in milliseconds.
        details: Optional structured details for debugging.

    Example:
        >>> result = PrerequisiteResult(
        ...     success=True,
        ...     message="Git identity configured: John Doe <john@example.com>",
        ...     duration_ms=15,
        ... )
    """

    success: bool
    message: str
    duration_ms: int = 0
    details: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class PreflightCheckResult:
    """Result of a single prerequisite check with its metadata.

    Combines the check result with the prerequisite metadata for display
    and reporting purposes.

    Attributes:
        prerequisite: The prerequisite definition that was checked.
        result: The result of running the check.
        affected_steps: List of step names that require this prerequisite.
    """

    prerequisite: Prerequisite
    result: PrerequisiteResult
    affected_steps: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PreflightPlan:
    """Collection of prerequisites to run before workflow execution.

    Created by PrerequisiteCollector after scanning a workflow definition
    and resolving all step/component prerequisites.

    Attributes:
        prerequisites: Tuple of unique prerequisite names to check.
        step_requirements: Mapping of prerequisite name to step names that need it.
        execution_order: Prerequisites in topological order respecting dependencies.

    Example:
        >>> plan = PreflightPlan(
        ...     prerequisites=("git", "git_repo", "git_identity"),
        ...     step_requirements={
        ...         "git": ("init", "commit"),
        ...         "git_repo": ("init",),
        ...         "git_identity": ("commit",),
        ...     },
        ...     execution_order=("git", "git_repo", "git_identity"),
        ... )
    """

    prerequisites: tuple[str, ...]
    step_requirements: dict[str, tuple[str, ...]]
    execution_order: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PreflightResult:
    """Aggregated result of all prerequisite checks.

    Returned by PrerequisiteRunner after executing all prerequisite checks.

    Attributes:
        success: True if all checks passed, False otherwise.
        check_results: Results for each individual check.
        total_duration_ms: Total time to run all checks.
        timestamp: Unix timestamp when preflight completed.

    Example:
        >>> result = PreflightResult(
        ...     success=False,
        ...     check_results=(
        ...         PreflightCheckResult(git_prereq, git_result, ("init",)),
        ...         PreflightCheckResult(gh_prereq, gh_result, ("create_pr",)),
        ...     ),
        ...     total_duration_ms=250,
        ... )
    """

    success: bool
    check_results: tuple[PreflightCheckResult, ...]
    total_duration_ms: int
    timestamp: float = field(default_factory=time.time)

    def format_error(self) -> str:
        """Format a human-readable error message for failed checks.

        Returns:
            Multi-line error message listing all failed checks with
            remediation hints and affected steps.
        """
        if self.success:
            return ""

        lines = ["Preflight checks failed:"]
        for check_result in self.check_results:
            if not check_result.result.success:
                prereq = check_result.prerequisite
                lines.append(f"\n  {prereq.display_name}:")
                lines.append(f"    Error: {check_result.result.message}")

                if check_result.affected_steps:
                    steps_str = ", ".join(check_result.affected_steps)
                    lines.append(f"    Affects steps: {steps_str}")

                if prereq.remediation:
                    lines.append(f"    Fix: {prereq.remediation}")

        return "\n".join(lines)

    def get_failed_checks(self) -> tuple[PreflightCheckResult, ...]:
        """Get only the failed check results.

        Returns:
            Tuple of PreflightCheckResult for checks that failed.
        """
        return tuple(cr for cr in self.check_results if not cr.result.success)

    def get_passed_checks(self) -> tuple[PreflightCheckResult, ...]:
        """Get only the passed check results.

        Returns:
            Tuple of PreflightCheckResult for checks that passed.
        """
        return tuple(cr for cr in self.check_results if cr.result.success)
