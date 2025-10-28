"""Data models for CLI prerequisite checks.

Defines the data structures for individual prerequisite check results
and the overall readiness summary per data-model.md specification.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class CheckStatus(str, Enum):
    """Status of an individual prerequisite check."""
    PASS = "pass"
    FAIL = "fail"


class OverallStatus(str, Enum):
    """Overall readiness status."""
    READY = "ready"
    NOT_READY = "not_ready"


@dataclass
class PrereqCheckResult:
    """Result of checking a single prerequisite tool.
    
    Attributes:
        tool: Name of the tool checked (e.g., "gh", "copilot")
        status: Whether the check passed or failed
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
        if not self.message:
            raise ValueError("message must be present for both pass and fail")


@dataclass
class ReadinessSummary:
    """Summary of all prerequisite checks.
    
    Attributes:
        results: List of individual prerequisite check results
        overall_status: Overall readiness status (ready if all checks pass)
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
        all_passed = all(r.status == CheckStatus.PASS for r in self.results)
        if all_passed and self.overall_status != OverallStatus.READY:
            raise ValueError("overall_status must be 'ready' if all checks pass")
        if not all_passed and self.overall_status == OverallStatus.READY:
            raise ValueError("overall_status must be 'not_ready' if any check fails")
        
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")
