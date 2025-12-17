"""Data models for Maverick TUI.

This module defines the data models and state structures for the Maverick TUI.
The TUI is primarily a presentation layer that consumes state from workflows;
these models define how that state is represented and displayed.
"""

from __future__ import annotations

__all__ = [
    # Enums
    "CheckStatus",
    "FindingSeverity",
    "IssueSeverity",
    "MessageType",
    "PRState",
    "SidebarMode",
    "StageStatus",
    "ValidationStepStatus",
    # Helper dataclasses
    "AgentMessage",
    "CodeContext",
    "CodeLocation",
    "PRInfo",
    "ReviewFinding",
    "ReviewFindingItem",
    "StatusCheck",
    "ToolCallInfo",
    "ValidationStep",
    "WorkflowStage",
    # Widget state models
    "AgentOutputState",
    "PRSummaryState",
    "ReviewFindingsState",
    "ValidationStatusState",
    "WorkflowProgressState",
    # Screen state models
    "ConfigOption",
    "ConfigScreenState",
    "HomeScreenState",
    "LogEntry",
    "LogPanelState",
    "NavigationItem",
    "RecentWorkflowEntry",
    "ReviewIssue",
    "ReviewScreenState",
    "ScreenState",
    "SidebarState",
    "StageState",
    "WorkflowScreenState",
    # Theme models
    "DARK_THEME",
    "LIGHT_THEME",
    "ThemeColors",
]

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class StageStatus(str, Enum):
    """Status of a workflow stage."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class IssueSeverity(str, Enum):
    """Severity level of a review issue."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    SUGGESTION = "suggestion"


class SidebarMode(str, Enum):
    """Display mode for the sidebar."""

    NAVIGATION = "navigation"
    WORKFLOW = "workflow"


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
# Widget Helper Models (012-workflow-widgets)
# =============================================================================


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
class StatusCheck:
    """A CI/CD status check on a PR.

    Attributes:
        name: Name of the check (e.g., "CI / build").
        status: Current status.
        url: Link to the check details.
    """

    name: str
    status: CheckStatus
    url: str | None = None


@dataclass(frozen=True, slots=True)
class CodeLocation:
    """Location in source code.

    Attributes:
        file_path: Path to the file relative to repo root.
        line_number: Line number (1-indexed).
        end_line: End line for multi-line ranges.
    """

    file_path: str
    line_number: int
    end_line: int | None = None


@dataclass(frozen=True, slots=True)
class CodeContext:
    """Code context for a finding.

    Attributes:
        file_path: Path to the file.
        start_line: First line of context.
        end_line: Last line of context.
        content: The code content.
        highlight_line: Line to highlight (the finding line).
    """

    file_path: str
    start_line: int
    end_line: int
    content: str
    highlight_line: int


@dataclass(frozen=True, slots=True)
class ReviewFinding:
    """A single finding from code review.

    Attributes:
        id: Unique identifier for the finding.
        severity: Error, warning, or suggestion.
        location: File path and line number.
        title: Short summary of the finding.
        description: Full description with context.
        suggested_fix: Optional suggested code change.
        source: Review source (e.g., "coderabbit", "architecture").
    """

    id: str
    severity: FindingSeverity
    location: CodeLocation
    title: str
    description: str
    suggested_fix: str | None = None
    source: str = "review"


@dataclass(frozen=True, slots=True)
class ReviewFindingItem:
    """A finding with selection state for the UI.

    Attributes:
        finding: The review finding data.
        selected: Whether this item is selected for bulk action.
    """

    finding: ReviewFinding
    selected: bool = False


@dataclass(frozen=True, slots=True)
class PRInfo:
    """Pull request metadata.

    Attributes:
        number: PR number.
        title: PR title.
        description: Full PR description/body.
        state: Open, merged, or closed.
        url: URL to the PR on GitHub.
        checks: Status checks on the PR.
        branch: Source branch name.
        base_branch: Target branch name.
    """

    number: int
    title: str
    description: str
    state: PRState
    url: str
    checks: tuple[StatusCheck, ...] = ()
    branch: str = ""
    base_branch: str = "main"

    @property
    def description_preview(self) -> str:
        """Get truncated description for preview."""
        max_length = 200
        if len(self.description) <= max_length:
            return self.description
        return self.description[:max_length].rsplit(" ", 1)[0] + "..."


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


# =============================================================================
# Screen State Models
# =============================================================================


@dataclass(frozen=True, slots=True)
class ScreenState:
    """Base state shared by all screens."""

    title: str
    can_go_back: bool = True
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
class HomeScreenState(ScreenState):
    """State for the home screen."""

    recent_workflows: tuple[RecentWorkflowEntry, ...] = ()
    selected_index: int = 0

    @property
    def selected_workflow(self) -> RecentWorkflowEntry | None:
        """Get the currently selected workflow entry."""
        if 0 <= self.selected_index < len(self.recent_workflows):
            return self.recent_workflows[self.selected_index]
        return None


@dataclass(frozen=True, slots=True)
class StageState:
    """State of a single workflow stage."""

    name: str
    display_name: str
    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowScreenState(ScreenState):
    """State for the workflow progress screen."""

    workflow_name: str = ""
    branch_name: str = ""
    stages: tuple[StageState, ...] = ()
    elapsed_seconds: float = 0.0
    current_stage_index: int = 0

    @property
    def current_stage(self) -> StageState | None:
        """Get the currently active stage."""
        for stage in self.stages:
            if stage.status == StageStatus.ACTIVE:
                return stage
        return None

    @property
    def progress_percent(self) -> float:
        """Calculate overall progress percentage."""
        if not self.stages:
            return 0.0
        completed = sum(1 for s in self.stages if s.status == StageStatus.COMPLETED)
        return (completed / len(self.stages)) * 100


@dataclass(frozen=True, slots=True)
class ReviewIssue:
    """A single issue from code review."""

    file_path: str
    line_number: int | None
    severity: IssueSeverity
    message: str
    source: str  # "architecture" | "coderabbit" | "validation"


@dataclass(frozen=True, slots=True)
class ReviewScreenState(ScreenState):
    """State for the review results screen."""

    issues: tuple[ReviewIssue, ...] = ()
    selected_issue_index: int = 0
    filter_severity: IssueSeverity | None = None

    @property
    def filtered_issues(self) -> tuple[ReviewIssue, ...]:
        """Get issues filtered by severity."""
        if self.filter_severity is None:
            return self.issues
        return tuple(i for i in self.issues if i.severity == self.filter_severity)

    @property
    def issue_counts(self) -> dict[IssueSeverity, int]:
        """Count issues by severity."""
        counts = dict.fromkeys(IssueSeverity, 0)
        for issue in self.issues:
            counts[issue.severity] += 1
        return counts


@dataclass(frozen=True, slots=True)
class ConfigOption:
    """A single configuration option."""

    key: str
    display_name: str
    value: str | bool | int
    description: str
    option_type: str  # "bool" | "string" | "int" | "choice"
    choices: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class ConfigScreenState(ScreenState):
    """State for the config screen."""

    options: tuple[ConfigOption, ...] = ()
    selected_option_index: int = 0
    editing: bool = False
    edit_value: str = ""

    @property
    def selected_option(self) -> ConfigOption | None:
        """Get the currently selected option."""
        if 0 <= self.selected_option_index < len(self.options):
            return self.options[self.selected_option_index]
        return None


# =============================================================================
# Widget State Models
# =============================================================================


@dataclass(frozen=True, slots=True)
class LogEntry:
    """A single log entry."""

    timestamp: datetime
    source: str
    level: str  # "info" | "success" | "warning" | "error"
    message: str


@dataclass(slots=True)
class LogPanelState:
    """Mutable state for the log panel (performance optimization)."""

    visible: bool = False
    entries: list[LogEntry] = field(default_factory=list)
    max_entries: int = 1000
    auto_scroll: bool = True

    def add_entry(self, entry: LogEntry) -> None:
        """Add entry, maintaining buffer limit."""
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries :]


@dataclass(slots=True)
class AgentOutputState:
    """Mutable state for AgentOutput widget (performance optimization).

    Using mutable state for message buffer to avoid creating new tuples
    on every message. Buffer is capped at max_messages.

    Attributes:
        messages: Buffer of agent messages.
        max_messages: Maximum messages to retain (default: 1000).
        auto_scroll: Whether to auto-scroll on new messages.
        search_query: Current search filter text.
        search_matches: Indices of messages matching search.
        filter_agent: Filter to specific agent ID.
        truncated: Whether old messages were discarded.
    """

    messages: list[AgentMessage] = field(default_factory=list)
    max_messages: int = 1000
    auto_scroll: bool = True
    search_query: str | None = None
    search_matches: list[int] = field(default_factory=list)
    filter_agent: str | None = None
    truncated: bool = False

    def add_message(self, message: AgentMessage) -> None:
        """Add a message, maintaining buffer limit."""
        self.messages.append(message)
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages :]
            self.truncated = True

    @property
    def filtered_messages(self) -> list[AgentMessage]:
        """Get messages filtered by agent and search."""
        result = self.messages
        if self.filter_agent:
            result = [m for m in result if m.agent_id == self.filter_agent]
        # Search filtering handled in widget for highlighting
        return result

    @property
    def is_empty(self) -> bool:
        """Check if there are no messages."""
        return len(self.messages) == 0


@dataclass(frozen=True, slots=True)
class ValidationStatusState:
    """State for ValidationStatus widget.

    Attributes:
        steps: All validation steps.
        expanded_step: Name of expanded failed step.
        loading: Whether validation is starting.
        running_step: Name of currently running step.
    """

    steps: tuple[ValidationStep, ...] = ()
    expanded_step: str | None = None
    loading: bool = False
    running_step: str | None = None

    @property
    def all_passed(self) -> bool:
        """Check if all steps passed."""
        return all(s.status == ValidationStepStatus.PASSED for s in self.steps)

    @property
    def has_failures(self) -> bool:
        """Check if any step failed."""
        return any(s.status == ValidationStepStatus.FAILED for s in self.steps)

    @property
    def is_running(self) -> bool:
        """Check if any step is currently running."""
        return any(s.status == ValidationStepStatus.RUNNING for s in self.steps)

    @property
    def is_empty(self) -> bool:
        """Check if there are no steps."""
        return len(self.steps) == 0 and not self.loading


@dataclass(frozen=True, slots=True)
class PRSummaryState:
    """State for PRSummary widget.

    Attributes:
        pr: Pull request information.
        description_expanded: Whether description is expanded.
        loading: Whether PR data is loading.
    """

    pr: PRInfo | None = None
    description_expanded: bool = False
    loading: bool = False

    @property
    def is_empty(self) -> bool:
        """Check if no PR data is available."""
        return self.pr is None and not self.loading


@dataclass(frozen=True, slots=True)
class NavigationItem:
    """A navigation menu item."""

    id: str
    label: str
    icon: str
    shortcut: str | None = None


@dataclass(frozen=True, slots=True)
class SidebarState:
    """State for the sidebar widget."""

    mode: SidebarMode = SidebarMode.NAVIGATION
    navigation_items: tuple[NavigationItem, ...] = (
        NavigationItem("home", "Home", "H", "Ctrl+H"),
        NavigationItem("workflows", "Workflows", "W"),
        NavigationItem("settings", "Settings", "S", "Ctrl+,"),
    )
    workflow_stages: tuple[StageState, ...] = ()
    selected_nav_index: int = 0


@dataclass(frozen=True, slots=True)
class WorkflowProgressState:
    """State for WorkflowProgress widget.

    Attributes:
        stages: All workflow stages in order.
        loading: Whether initial data is loading.
        expanded_stage: Name of currently expanded stage.
    """

    stages: tuple[WorkflowStage, ...] = ()
    loading: bool = False
    expanded_stage: str | None = None

    @property
    def current_stage(self) -> WorkflowStage | None:
        """Get the currently active stage."""
        for stage in self.stages:
            if stage.status == StageStatus.ACTIVE:
                return stage
        return None

    @property
    def is_empty(self) -> bool:
        """Check if there are no stages."""
        return len(self.stages) == 0 and not self.loading


@dataclass(frozen=True, slots=True)
class ReviewFindingsState:
    """State for ReviewFindings widget.

    Attributes:
        findings: All findings with selection state.
        expanded_index: Index of expanded finding.
        code_context: Code context for expanded finding.
        focused_index: Currently focused finding index.
    """

    findings: tuple[ReviewFindingItem, ...] = ()
    expanded_index: int | None = None
    code_context: CodeContext | None = None
    focused_index: int = 0

    @property
    def selected_findings(self) -> tuple[ReviewFinding, ...]:
        """Get all selected findings."""
        return tuple(item.finding for item in self.findings if item.selected)

    @property
    def selected_count(self) -> int:
        """Count of selected findings."""
        return sum(1 for item in self.findings if item.selected)

    @property
    def findings_by_severity(self) -> dict[FindingSeverity, list[ReviewFindingItem]]:
        """Group findings by severity."""
        result: dict[FindingSeverity, list[ReviewFindingItem]] = {
            FindingSeverity.ERROR: [],
            FindingSeverity.WARNING: [],
            FindingSeverity.SUGGESTION: [],
        }
        for item in self.findings:
            result[item.finding.severity].append(item)
        return result

    @property
    def is_empty(self) -> bool:
        """Check if there are no findings."""
        return len(self.findings) == 0


# =============================================================================
# Theme Models
# =============================================================================


@dataclass(frozen=True, slots=True)
class ThemeColors:
    """Color palette for a theme."""

    # Backgrounds
    background: str = "#1a1a1a"
    surface: str = "#242424"
    surface_elevated: str = "#2d2d2d"

    # Borders
    border: str = "#3a3a3a"
    border_focus: str = "#00aaff"

    # Text
    text: str = "#e0e0e0"
    text_muted: str = "#808080"
    text_dim: str = "#606060"

    # Status
    success: str = "#4caf50"
    warning: str = "#ff9800"
    error: str = "#f44336"
    info: str = "#2196f3"

    # Accent
    accent: str = "#00aaff"
    accent_muted: str = "#0077aa"


# Default theme instances
DARK_THEME = ThemeColors()

LIGHT_THEME = ThemeColors(
    background="#f5f5f5",
    surface="#ffffff",
    surface_elevated="#fafafa",
    border="#e0e0e0",
    border_focus="#0066cc",
    text="#1a1a1a",
    text_muted="#606060",
    text_dim="#909090",
    success="#388e3c",
    warning="#f57c00",
    error="#d32f2f",
    info="#1976d2",
    accent="#0066cc",
    accent_muted="#004499",
)
