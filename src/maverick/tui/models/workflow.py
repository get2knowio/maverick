from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from maverick.tui.models.enums import (
    BranchValidationStatus,
    MessageType,
    StageStatus,
    ValidationStepStatus,
)


@dataclass(frozen=True, slots=True)
class ToolCallInfo:
    """Information about a tool call within an agent message.

    Attributes:
        tool_name: Name of the tool being called.
        arguments: Tool arguments as formatted string.
        result: Tool result (may be truncated for display).
    """

    tool_name: str
    arguments: str
    result: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowStage:
    """Represents a single stage in a workflow.

    Attributes:
        name: Unique identifier for the stage (e.g., "setup", "implementation").
        display_name: Human-readable name shown in UI.
        status: Current status of the stage.
        started_at: When the stage began execution.
        completed_at: When the stage finished (success or error).
        detail_content: Optional expandable content for the stage.
        error_message: Error details if status is ERROR.
    """

    name: str
    display_name: str
    status: StageStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    detail_content: str | None = None
    error_message: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        """Calculate duration if stage has started and completed."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def duration_display(self) -> str:
        """Format duration for display (e.g., '12s', '1m 30s')."""
        duration = self.duration_seconds
        if duration is None:
            return ""
        if duration < 60:
            return f"{int(duration)}s"
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        return f"{minutes}m {seconds}s"


@dataclass(frozen=True, slots=True)
class ValidationStep:
    """A single validation step (format, lint, build, test).

    Attributes:
        name: Unique identifier (e.g., "format", "lint").
        display_name: Human-readable name.
        status: Current status of the step.
        error_output: Error details if failed.
        command: The command that was run.
    """

    name: str
    display_name: str
    status: ValidationStepStatus
    error_output: str | None = None
    command: str | None = None


@dataclass(frozen=True, slots=True)
class AgentMessage:
    """A message from an agent in the workflow.

    Attributes:
        id: Unique identifier for the message.
        timestamp: When the message was created.
        agent_id: Identifier of the source agent.
        agent_name: Human-readable agent name.
        message_type: Type of message content.
        content: The message text or code content.
        language: Programming language for code blocks.
        tool_call: Tool call details if message_type is TOOL_CALL.
    """

    id: str
    timestamp: datetime
    agent_id: str
    agent_name: str
    message_type: MessageType
    content: str
    language: str | None = None
    tool_call: ToolCallInfo | None = None


@dataclass(frozen=True, slots=True)
class BranchValidation:
    """Result of branch name validation.

    Attributes:
        status: Validation status.
        message: User-facing message.
        is_valid: Whether the branch name can be used.
    """

    status: BranchValidationStatus
    message: str
    is_valid: bool

    @classmethod
    def empty(cls) -> BranchValidation:
        """Create validation result for empty branch name."""
        return cls(
            status=BranchValidationStatus.EMPTY,
            message="Branch name cannot be empty",
            is_valid=False,
        )

    @classmethod
    def invalid_chars(cls, chars: str) -> BranchValidation:
        """Create validation result for invalid characters."""
        return cls(
            status=BranchValidationStatus.INVALID_CHARS,
            message=f"Invalid characters: {chars}",
            is_valid=False,
        )

    @classmethod
    def valid_new(cls) -> BranchValidation:
        """Create validation result for valid new branch."""
        return cls(
            status=BranchValidationStatus.VALID_NEW,
            message="Valid - new branch",
            is_valid=True,
        )

    @classmethod
    def valid_existing(cls) -> BranchValidation:
        """Create validation result for existing branch."""
        return cls(
            status=BranchValidationStatus.VALID_EXISTING,
            message="Branch exists - will continue existing work",
            is_valid=True,
        )


@dataclass(frozen=True, slots=True)
class RefuelResultItem:
    """Result of processing a single issue.

    Attributes:
        issue_number: The issue number.
        success: Whether processing succeeded.
        pr_url: URL to created PR (if successful).
        error_message: Error message (if failed).
    """

    issue_number: int
    success: bool
    pr_url: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class RecentWorkflowEntry:
    """Entry in the recent workflows list."""

    branch_name: str
    workflow_type: str  # "fly" | "refuel"
    status: str  # "completed" | "failed" | "in_progress"
    started_at: datetime
    completed_at: datetime | None = None
    pr_url: str | None = None


@dataclass(frozen=True, slots=True)
class StageState:
    """State of a single workflow stage."""

    name: str
    display_name: str
    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
