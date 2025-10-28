"""Data models for CLI prerequisite checks.

Defines the data structures for individual prerequisite check results
and the overall readiness summary per data-model.md specification.
"""

from dataclasses import dataclass
from typing import List, Optional, Literal


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
    remediation: Optional[str] = None

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
    """Summary of all prerequisite checks.
    
    Attributes:
        results: List of individual prerequisite check results
        overall_status: Overall readiness status ("ready" or "not_ready")
        duration_ms: Execution time in milliseconds
    """
    results: List[PrereqCheckResult]
    overall_status: OverallStatus
    duration_ms: int

    def __post_init__(self):
        """Validate the summary after initialization."""
        if not self.results:
            raise ValueError("results must contain at least one check")
        
        # Validate unique tools
        tools = [r.tool for r in self.results]
        if len(tools) != len(set(tools)):
            raise ValueError("Each tool must be unique within results")
        
        # Validate overall_status consistency
        all_passed = all(r.status == "pass" for r in self.results)
        if all_passed and self.overall_status != "ready":
            raise ValueError("overall_status must be 'ready' if all checks pass")
        if not all_passed and self.overall_status == "ready":
            raise ValueError("overall_status must be 'not_ready' if any check fails")
        
        if self.overall_status not in ("ready", "not_ready"):
            raise ValueError("overall_status must be 'ready' or 'not_ready'")
        
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")
