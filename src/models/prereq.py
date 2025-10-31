"""Data models for CLI prerequisite checks.

Defines the data structures for individual prerequisite check results
and the overall readiness summary per data-model.md specification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.models.verification_result import VerificationResult


# Type aliases for status values (simpler than Enums for Temporal)
CheckStatus = Literal["pass", "fail"]
OverallStatus = Literal["ready", "not_ready"]


@dataclass
class PrereqCheckResult:
    """Result of checking a single prerequisite tool.

    Attributes:
        tool: Name of the tool checked (e.g., "gh", "copilot")
        status: Whether the check passed or failed ("pass" or "fail")
        message: Human-readable detail about the check result
        remediation: Optional human-readable guidance for fixing failures
    """
    tool: str
    status: CheckStatus
    message: str
    remediation: str | None = None

    def __post_init__(self):
        """Validate the result after initialization."""
        if not self.tool:
            raise ValueError("tool must not be empty")
        if self.status not in ("pass", "fail"):
            raise ValueError("status must be 'pass' or 'fail'")
        if not self.message:
            raise ValueError("message must be present for both pass and fail")


@dataclass
class ReadinessSummary:
    """Summary of all prerequisite checks and repository verification.

    Attributes:
        results: List of individual prerequisite check results
        repo_verification: Repository verification result
        overall_status: Overall readiness status ("ready" or "not_ready")
        duration_ms: Execution time in milliseconds
        compose_error: Compose startup error details (if compose failed)
        cleanup_instructions: Manual cleanup instructions (if environment preserved)
        target_service: Resolved target service name (if compose was used)
    """
    results: list[PrereqCheckResult]
    repo_verification: VerificationResult | None
    overall_status: OverallStatus
    duration_ms: int
    compose_error: str | None = None
    cleanup_instructions: str | None = None
    target_service: str | None = None

    def __post_init__(self):
        """Validate the summary after initialization."""
        # Allow empty results if compose startup failed before checks could run
        if not self.results and self.compose_error is None:
            raise ValueError("results must contain at least one check (unless compose_error is set)")

        # Validate unique tools (if results exist)
        if self.results:
            tools = [r.tool for r in self.results]
            if len(tools) != len(set(tools)):
                raise ValueError("Each tool must be unique within results")

        # Validate overall_status consistency
        # All CLI checks and repo verification (if present) must pass for "ready" status
        cli_checks_passed = all(r.status == "pass" for r in self.results) if self.results else False
        repo_check_passed = (
            self.repo_verification is None or
            self.repo_verification.status == "pass"
        )
        all_passed = cli_checks_passed and repo_check_passed and self.compose_error is None

        if all_passed and self.overall_status != "ready":
            raise ValueError("overall_status must be 'ready' if all checks pass")
        if not all_passed and self.overall_status == "ready":
            raise ValueError("overall_status must be 'not_ready' if any check fails")

        if self.overall_status not in ("ready", "not_ready"):
            raise ValueError("overall_status must be 'ready' or 'not_ready'")

        if self.duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")
