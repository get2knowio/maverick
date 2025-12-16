"""Fly Workflow interface module.

This module defines the interface and data models for the Fly Workflow, which
orchestrates the complete spec-based development workflow including setup,
implementation, code review, validation, convention updates, and PR management.

Note: Full implementation is deferred to Spec 26 (026-fly-workflow-implementation).
This module provides the interface contracts and data structures.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

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


class WorkflowState(BaseModel):
    """Mutable state tracking workflow progress."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

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

    # Timestamps
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
    token_usage: AgentUsage = Field(description="Aggregated token usage")
    total_cost_usd: float = Field(ge=0.0, description="Total execution cost")


@dataclass(frozen=True, slots=True)
class FlyWorkflowStarted:
    """Event emitted when fly workflow starts."""

    inputs: FlyInputs
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class FlyStageStarted:
    """Event emitted when a stage starts."""

    stage: WorkflowStage
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class FlyStageCompleted:
    """Event emitted when a stage completes."""

    stage: WorkflowStage
    result: Any  # Stage-specific result type
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class FlyWorkflowCompleted:
    """Event emitted when workflow completes successfully."""

    result: FlyResult
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class FlyWorkflowFailed:
    """Event emitted when workflow fails."""

    error: str
    state: WorkflowState
    timestamp: float = field(default_factory=time.time)


# Union type for event handling
FlyProgressEvent = (
    FlyWorkflowStarted
    | FlyStageStarted
    | FlyStageCompleted
    | FlyWorkflowCompleted
    | FlyWorkflowFailed
)


class FlyWorkflow:
    """Fly workflow orchestrator.

    Orchestrates the complete spec-based development workflow across 8 stages:

    1. INIT Stage: Parse arguments, validate inputs, checkout branch,
       sync with origin/main
    2. IMPLEMENTATION Stage: Execute ImplementerAgent on tasks,
       parallel for "P:" marked tasks
    3. VALIDATION Stage: Run ValidationWorkflow with auto-fix,
       retry up to max_validation_attempts
    4. CODE_REVIEW Stage: Run parallel reviews, optionally integrate
       CodeRabbit CLI
    5. CONVENTION_UPDATE Stage: Analyze findings, suggest CLAUDE.md updates
    6. PR_CREATION Stage: Generate PR body, create/update via gh CLI
    7. COMPLETE Stage: Terminal success state
    8. FAILED Stage: Terminal failure state

    The workflow maintains immutable state transitions and supports
    graceful failure handling.
    """

    def __init__(self, config: FlyConfig | None = None) -> None:
        """Initialize the fly workflow.

        Args:
            config: Optional workflow configuration. Uses defaults if None.
        """
        self._config = config or FlyConfig()

    async def execute(self, inputs: FlyInputs) -> FlyResult:
        """Execute the fly workflow.

        Args:
            inputs: Validated workflow inputs including branch name and options.

        Returns:
            FlyResult containing success status, final state, and summary.

        Raises:
            NotImplementedError: Always raised - implementation in Spec 26.
        """
        raise NotImplementedError(
            "FlyWorkflow.execute() is not implemented. "
            "Full implementation will be provided in Spec 26 using the workflow DSL."
        )


__all__ = [
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
