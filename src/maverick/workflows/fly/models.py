"""Data models for the Fly Workflow.

This module defines Pydantic models and state tracking classes used
throughout the Fly workflow execution lifecycle.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from maverick.agents.result import AgentResult, AgentUsage
from maverick.exceptions import (
    AgentError,  # noqa: F401 - required for Pydantic type resolution
)
from maverick.models.validation import ValidationWorkflowResult


class WorkflowStage(str, Enum):
    """Eight workflow stages with string representation."""

    INIT = "init"
    IMPLEMENTATION = "implementation"
    VALIDATION = "validation"
    CODE_REVIEW = "code_review"
    CONVENTION_UPDATE = "convention_update"
    PR_CREATION = "pr_creation"
    COMPLETE = "complete"
    FAILED = "failed"

    def __str__(self) -> str:
        """Return the lowercase string value."""
        return self.value


class FlyConfig(BaseModel):
    """Configuration for fly workflow execution."""

    model_config = ConfigDict(frozen=True)

    parallel_reviews: bool = Field(default=True, description="Run reviews in parallel")
    max_validation_attempts: int = Field(
        default=3, ge=1, le=10, description="Max validation retries"
    )
    coderabbit_enabled: bool = Field(default=False, description="Enable CodeRabbit CLI")
    auto_merge: bool = Field(default=False, description="Auto-merge on success")
    notification_on_complete: bool = Field(
        default=True, description="Send notification on completion"
    )


class FlyInputs(BaseModel):
    """Validated inputs for fly workflow execution."""

    model_config = ConfigDict(frozen=True)

    # Required
    branch_name: str = Field(min_length=1, description="Feature branch name")

    # Optional with defaults
    task_file: Path | None = Field(default=None, description="Path to tasks.md")
    skip_review: bool = Field(default=False, description="Skip code review stage")
    skip_pr: bool = Field(default=False, description="Skip PR creation stage")
    draft_pr: bool = Field(default=False, description="Create PR as draft")
    base_branch: str = Field(default="main", description="Base branch for PR")
    dry_run: bool = Field(default=False, description="Preview mode (no changes)")


class WorkflowState(BaseModel):
    """Mutable state tracking workflow progress.

    Note on timestamps:
        WorkflowState uses datetime objects for started_at/completed_at for
        human-readable state inspection and serialization. Event dataclasses
        use float (Unix timestamps) for performance in high-frequency emission.
        Use datetime.fromtimestamp() to convert event timestamps if needed.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=False)

    # Stage tracking
    stage: WorkflowStage = Field(default=WorkflowStage.INIT)
    branch: str = Field(description="Current branch name")
    task_file: Path | None = Field(default=None)

    # Results (populated as stages complete)
    implementation_result: AgentResult | None = Field(default=None)
    validation_result: ValidationWorkflowResult | None = Field(default=None)
    review_results: list[AgentResult] = Field(default_factory=list)

    # Final outputs
    pr_url: str | None = Field(default=None)
    errors: list[str] = Field(default_factory=list)

    # Timestamps (datetime for human readability; events use float for performance)
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = Field(default=None)


# Rebuild the model to resolve forward references
WorkflowState.model_rebuild()


class FlyResult(BaseModel):
    """Immutable workflow execution result."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    success: bool = Field(description="Overall workflow success")
    state: WorkflowState = Field(description="Final workflow state")
    summary: str = Field(description="Human-readable outcome summary")
    token_usage: AgentUsage = Field(
        description="Aggregated token usage from all agent interactions in the workflow"
    )
    total_cost_usd: float = Field(ge=0.0, description="Total execution cost")


__all__ = [
    "WorkflowStage",
    "FlyConfig",
    "FlyInputs",
    "WorkflowState",
    "FlyResult",
]
