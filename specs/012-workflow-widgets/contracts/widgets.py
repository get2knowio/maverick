"""Widget contracts for workflow visualization widgets.

This module defines the public interfaces for the five workflow visualization
widgets. These are NOT the implementations - they define the expected API
that consumers can rely on.

Feature: 012-workflow-widgets
Date: 2025-12-16
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence



# =============================================================================
# Enums (from data-model.md)
# =============================================================================


class MessageType(str, Enum):
    """Type of agent message content."""

    TEXT = "text"
    CODE = "code"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


class FindingSeverity(str, Enum):
    """Severity level of a code review finding."""

    ERROR = "error"
    WARNING = "warning"
    SUGGESTION = "suggestion"


class ValidationStepStatus(str, Enum):
    """Status of a validation step."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"


class PRState(str, Enum):
    """State of a pull request."""

    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"


class CheckStatus(str, Enum):
    """Status of a CI/CD status check."""

    PENDING = "pending"
    PASSING = "passing"
    FAILING = "failing"


# =============================================================================
# Data Transfer Objects
# =============================================================================


@dataclass(frozen=True, slots=True)
class WorkflowStageData:
    """Data for a workflow stage (input to WorkflowProgress widget).

    Attributes:
        name: Unique stage identifier.
        display_name: Human-readable name.
        status: Current status ("pending", "active", "completed", "failed").
        started_at: When stage started.
        completed_at: When stage finished.
        detail_content: Expandable detail text.
        error_message: Error details if failed.
    """

    name: str
    display_name: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    detail_content: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class ToolCallData:
    """Tool call information within an agent message."""

    tool_name: str
    arguments: str
    result: str | None = None


@dataclass(frozen=True, slots=True)
class AgentMessageData:
    """Data for an agent message (input to AgentOutput widget).

    Attributes:
        id: Unique message identifier.
        timestamp: When message was created.
        agent_id: Source agent identifier.
        agent_name: Human-readable agent name.
        message_type: Type of content (text, code, tool_call, tool_result).
        content: Message text or code.
        language: Programming language for code blocks.
        tool_call: Tool call details if applicable.
    """

    id: str
    timestamp: datetime
    agent_id: str
    agent_name: str
    message_type: MessageType
    content: str
    language: str | None = None
    tool_call: ToolCallData | None = None


@dataclass(frozen=True, slots=True)
class CodeLocationData:
    """Source code location."""

    file_path: str
    line_number: int
    end_line: int | None = None


@dataclass(frozen=True, slots=True)
class ReviewFindingData:
    """Data for a code review finding (input to ReviewFindings widget).

    Attributes:
        id: Unique finding identifier.
        severity: Error, warning, or suggestion.
        location: File and line number.
        title: Short summary.
        description: Full description.
        suggested_fix: Optional fix suggestion.
        source: Review source identifier.
    """

    id: str
    severity: FindingSeverity
    location: CodeLocationData
    title: str
    description: str
    suggested_fix: str | None = None
    source: str = "review"


@dataclass(frozen=True, slots=True)
class ValidationStepData:
    """Data for a validation step (input to ValidationStatus widget).

    Attributes:
        name: Step identifier (format, lint, build, test).
        display_name: Human-readable name.
        status: Current status.
        error_output: Error details if failed.
        command: Command that was executed.
    """

    name: str
    display_name: str
    status: ValidationStepStatus
    error_output: str | None = None
    command: str | None = None


@dataclass(frozen=True, slots=True)
class StatusCheckData:
    """CI/CD status check data."""

    name: str
    status: CheckStatus
    url: str | None = None


@dataclass(frozen=True, slots=True)
class PRData:
    """Data for a pull request (input to PRSummary widget).

    Attributes:
        number: PR number.
        title: PR title.
        description: PR body/description.
        state: Open, merged, or closed.
        url: GitHub PR URL.
        checks: Status checks.
        branch: Source branch.
        base_branch: Target branch.
    """

    number: int
    title: str
    description: str
    state: PRState
    url: str
    checks: tuple[StatusCheckData, ...] = ()
    branch: str = ""
    base_branch: str = "main"


# =============================================================================
# Widget Protocols
# =============================================================================


@runtime_checkable
class WorkflowProgressProtocol(Protocol):
    """Protocol for WorkflowProgress widget.

    The WorkflowProgress widget displays workflow stages as a vertical list
    with status icons and optional expandable details.

    Messages emitted:
        - StageExpanded: When a stage is expanded by user
        - StageCollapsed: When a stage is collapsed

    Example usage:
        progress = WorkflowProgress()
        progress.update_stages(stages_data)
        progress.update_stage_status("setup", "completed")
    """

    def update_stages(self, stages: Sequence[WorkflowStageData]) -> None:
        """Update all stages with new data.

        Args:
            stages: Sequence of stage data in display order.
        """
        ...

    def update_stage_status(
        self,
        stage_name: str,
        status: str,
        *,
        error_message: str | None = None,
    ) -> None:
        """Update a single stage's status.

        Args:
            stage_name: The stage identifier.
            status: New status value.
            error_message: Error details if status is "failed".
        """
        ...

    def expand_stage(self, stage_name: str) -> None:
        """Expand a stage to show details.

        Args:
            stage_name: The stage to expand.
        """
        ...

    def collapse_stage(self, stage_name: str) -> None:
        """Collapse an expanded stage.

        Args:
            stage_name: The stage to collapse.
        """
        ...


@runtime_checkable
class AgentOutputProtocol(Protocol):
    """Protocol for AgentOutput widget.

    The AgentOutput widget displays streaming agent messages with syntax
    highlighting, collapsible tool calls, and search functionality.

    Messages emitted:
        - SearchActivated: When Ctrl+F is pressed
        - ToolCallExpanded: When a tool call section is expanded
        - ToolCallCollapsed: When a tool call section is collapsed

    Example usage:
        output = AgentOutput()
        output.add_message(message_data)
        output.set_search_query("error")
    """

    def add_message(self, message: AgentMessageData) -> None:
        """Add a new agent message.

        Messages are appended to the buffer. If buffer exceeds max_messages,
        oldest messages are discarded.

        Args:
            message: The message data to add.
        """
        ...

    def clear_messages(self) -> None:
        """Clear all messages from the output."""
        ...

    def set_auto_scroll(self, enabled: bool) -> None:
        """Enable or disable auto-scrolling.

        Args:
            enabled: Whether to auto-scroll on new messages.
        """
        ...

    def scroll_to_bottom(self) -> None:
        """Scroll to the bottom of the output."""
        ...

    def set_search_query(self, query: str | None) -> None:
        """Set the search filter query.

        Args:
            query: Search string to filter/highlight, or None to clear.
        """
        ...

    def set_agent_filter(self, agent_id: str | None) -> None:
        """Filter messages to a specific agent.

        Args:
            agent_id: Agent ID to filter by, or None to show all.
        """
        ...


@runtime_checkable
class ReviewFindingsProtocol(Protocol):
    """Protocol for ReviewFindings widget.

    The ReviewFindings widget displays code review findings grouped by
    severity with selection, expansion, and bulk actions.

    Messages emitted:
        - FindingExpanded: When a finding is expanded
        - FindingCollapsed: When a finding is collapsed
        - FindingSelected: When a finding selection changes
        - BulkDismissRequested: When user triggers bulk dismiss
        - BulkCreateIssueRequested: When user triggers bulk issue creation
        - FileLocationClicked: When a file:line link is clicked

    Example usage:
        findings = ReviewFindings()
        findings.update_findings(findings_data)
        findings.select_finding(0, selected=True)
    """

    def update_findings(self, findings: Sequence[ReviewFindingData]) -> None:
        """Update all findings with new data.

        Findings are automatically grouped by severity.

        Args:
            findings: Sequence of finding data.
        """
        ...

    def select_finding(self, index: int, *, selected: bool) -> None:
        """Set selection state for a finding.

        Args:
            index: Finding index in the list.
            selected: Whether to select or deselect.
        """
        ...

    def select_all(self) -> None:
        """Select all findings."""
        ...

    def deselect_all(self) -> None:
        """Deselect all findings."""
        ...

    def expand_finding(self, index: int) -> None:
        """Expand a finding to show full details.

        Args:
            index: Finding index to expand.
        """
        ...

    def collapse_finding(self) -> None:
        """Collapse the currently expanded finding."""
        ...

    def show_code_context(self, finding_index: int) -> None:
        """Show code context for a finding.

        Args:
            finding_index: Index of finding to show context for.
        """
        ...

    @property
    def selected_findings(self) -> tuple[ReviewFindingData, ...]:
        """Get all currently selected findings."""
        ...


@runtime_checkable
class ValidationStatusProtocol(Protocol):
    """Protocol for ValidationStatus widget.

    The ValidationStatus widget displays validation steps in a compact
    layout with pass/fail indicators and expandable error details.

    Messages emitted:
        - StepExpanded: When a failed step is expanded
        - StepCollapsed: When a step is collapsed
        - RerunRequested: When re-run button is clicked

    Example usage:
        validation = ValidationStatus()
        validation.update_steps(steps_data)
        validation.expand_step("lint")
    """

    def update_steps(self, steps: Sequence[ValidationStepData]) -> None:
        """Update all validation steps.

        Args:
            steps: Sequence of step data in execution order.
        """
        ...

    def update_step_status(
        self,
        step_name: str,
        status: ValidationStepStatus,
        *,
        error_output: str | None = None,
    ) -> None:
        """Update a single step's status.

        Args:
            step_name: The step identifier.
            status: New status value.
            error_output: Error details if status is FAILED.
        """
        ...

    def expand_step(self, step_name: str) -> None:
        """Expand a failed step to show error details.

        Args:
            step_name: The step to expand.
        """
        ...

    def collapse_step(self) -> None:
        """Collapse the currently expanded step."""
        ...

    def set_rerun_enabled(self, step_name: str, enabled: bool) -> None:
        """Enable or disable the re-run button for a step.

        Args:
            step_name: The step identifier.
            enabled: Whether re-run should be enabled.
        """
        ...


@runtime_checkable
class PRSummaryProtocol(Protocol):
    """Protocol for PRSummary widget.

    The PRSummary widget displays pull request metadata with title,
    description preview, status checks, and a link to open in browser.

    Messages emitted:
        - OpenPRRequested: When user activates the PR link
        - DescriptionExpanded: When description is expanded
        - DescriptionCollapsed: When description is collapsed

    Example usage:
        pr_summary = PRSummary()
        pr_summary.update_pr(pr_data)
    """

    def update_pr(self, pr: PRData | None) -> None:
        """Update the PR data.

        Args:
            pr: PR data to display, or None to show empty state.
        """
        ...

    def set_loading(self, loading: bool) -> None:
        """Set the loading state.

        Args:
            loading: Whether PR data is loading.
        """
        ...

    def expand_description(self) -> None:
        """Expand the full PR description."""
        ...

    def collapse_description(self) -> None:
        """Collapse to description preview."""
        ...

    def open_pr_in_browser(self) -> None:
        """Open the PR URL in the default browser."""
        ...


# =============================================================================
# Widget Messages (Events)
# =============================================================================


@dataclass(frozen=True)
class StageExpandedEvent:
    """Emitted when a workflow stage is expanded."""

    stage_name: str


@dataclass(frozen=True)
class StageCollapsedEvent:
    """Emitted when a workflow stage is collapsed."""

    stage_name: str


@dataclass(frozen=True)
class ToolCallExpandedEvent:
    """Emitted when a tool call section is expanded."""

    message_id: str
    tool_name: str


@dataclass(frozen=True)
class ToolCallCollapsedEvent:
    """Emitted when a tool call section is collapsed."""

    message_id: str
    tool_name: str


@dataclass(frozen=True)
class FindingExpandedEvent:
    """Emitted when a finding is expanded."""

    finding_id: str
    index: int


@dataclass(frozen=True)
class FindingSelectedEvent:
    """Emitted when finding selection changes."""

    finding_id: str
    index: int
    selected: bool


@dataclass(frozen=True)
class BulkDismissRequestedEvent:
    """Emitted when bulk dismiss is requested."""

    finding_ids: tuple[str, ...]


@dataclass(frozen=True)
class BulkCreateIssueRequestedEvent:
    """Emitted when bulk issue creation is requested."""

    finding_ids: tuple[str, ...]


@dataclass(frozen=True)
class FileLocationClickedEvent:
    """Emitted when a file:line link is clicked."""

    file_path: str
    line_number: int


@dataclass(frozen=True)
class RerunRequestedEvent:
    """Emitted when re-run is requested for a validation step."""

    step_name: str


@dataclass(frozen=True)
class OpenPRRequestedEvent:
    """Emitted when PR link is activated."""

    url: str


# =============================================================================
# Callback Types
# =============================================================================

OnStageExpanded = Callable[[StageExpandedEvent], None]
OnToolCallExpanded = Callable[[ToolCallExpandedEvent], None]
OnFindingSelected = Callable[[FindingSelectedEvent], None]
OnBulkDismiss = Callable[[BulkDismissRequestedEvent], None]
OnBulkCreateIssue = Callable[[BulkCreateIssueRequestedEvent], None]
OnFileLocationClicked = Callable[[FileLocationClickedEvent], None]
OnRerunRequested = Callable[[RerunRequestedEvent], None]
OnOpenPR = Callable[[OpenPRRequestedEvent], None]
