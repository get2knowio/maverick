"""Type stub file for Fly Workflow Interface.

This contract defines the public API surface for the fly workflow module.
Implementation in src/maverick/workflows/fly.py must conform to these signatures.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from maverick.agents.result import AgentResult, AgentUsage
from maverick.models.validation import ValidationWorkflowResult

# =============================================================================
# Enums (FR-001, FR-002)
# =============================================================================

class WorkflowStage(str, Enum):
    """Eight workflow stages with string representation."""

    INIT: str
    IMPLEMENTATION: str
    VALIDATION: str
    CODE_REVIEW: str
    CONVENTION_UPDATE: str
    PR_CREATION: str
    COMPLETE: str
    FAILED: str

# =============================================================================
# Configuration Models (FR-003 to FR-005, FR-021 to FR-023)
# =============================================================================

class FlyInputs(BaseModel):
    """Validated inputs for fly workflow execution."""

    branch_name: str  # Required, min_length=1
    task_file: Path | None
    skip_review: bool
    skip_pr: bool
    draft_pr: bool
    base_branch: str

class FlyConfig(BaseModel):
    """Configuration for fly workflow execution."""

    parallel_reviews: bool
    max_validation_attempts: int  # 1-10
    coderabbit_enabled: bool
    auto_merge: bool
    notification_on_complete: bool

# =============================================================================
# State Models (FR-006 to FR-008)
# =============================================================================

class WorkflowState(BaseModel):
    """Mutable state tracking workflow progress."""

    stage: WorkflowStage
    branch: str
    task_file: Path | None
    implementation_result: AgentResult | None
    validation_result: ValidationWorkflowResult | None
    review_results: list[AgentResult]
    pr_url: str | None
    errors: list[str]
    started_at: datetime
    completed_at: datetime | None

# =============================================================================
# Result Models (FR-009 to FR-011)
# =============================================================================

class FlyResult(BaseModel):
    """Immutable workflow execution result."""

    success: bool
    state: WorkflowState
    summary: str
    token_usage: AgentUsage
    total_cost_usd: float  # >= 0.0

# =============================================================================
# Progress Events (FR-012 to FR-016)
# =============================================================================

@dataclass(frozen=True, slots=True)
class FlyWorkflowStarted:
    """Event emitted when fly workflow starts."""

    inputs: FlyInputs
    timestamp: float

@dataclass(frozen=True, slots=True)
class FlyStageStarted:
    """Event emitted when a stage starts."""

    stage: WorkflowStage
    timestamp: float

@dataclass(frozen=True, slots=True)
class FlyStageCompleted:
    """Event emitted when a stage completes."""

    stage: WorkflowStage
    result: Any
    timestamp: float

@dataclass(frozen=True, slots=True)
class FlyWorkflowCompleted:
    """Event emitted when workflow completes successfully."""

    result: FlyResult
    timestamp: float

@dataclass(frozen=True, slots=True)
class FlyWorkflowFailed:
    """Event emitted when workflow fails."""

    error: str
    state: WorkflowState
    timestamp: float

# Union type for event handling
FlyProgressEvent = (
    FlyWorkflowStarted
    | FlyStageStarted
    | FlyStageCompleted
    | FlyWorkflowCompleted
    | FlyWorkflowFailed
)

# =============================================================================
# Workflow Class (FR-017 to FR-020)
# =============================================================================

class FlyWorkflow:
    """Fly workflow orchestrator."""

    def __init__(self, config: FlyConfig | None = None) -> None:
        """Initialize the fly workflow."""
        ...

    async def execute(self, inputs: FlyInputs) -> FlyResult:
        """Execute the fly workflow.

        Raises:
            NotImplementedError: Always - implementation in Spec 26.
        """
        ...

# =============================================================================
# Public API
# =============================================================================

__all__: list[str] = [
    # Enums
    "WorkflowStage",
    # Configuration
    "FlyInputs",
    "FlyConfig",
    # State
    "WorkflowState",
    # Result
    "FlyResult",
    # Progress Events
    "FlyWorkflowStarted",
    "FlyStageStarted",
    "FlyStageCompleted",
    "FlyWorkflowCompleted",
    "FlyWorkflowFailed",
    "FlyProgressEvent",
    # Workflow
    "FlyWorkflow",
]
