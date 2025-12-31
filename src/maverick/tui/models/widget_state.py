from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from maverick.tui.models.enums import (
    FindingSeverity,
    MessageType,
    StageStatus,
    ValidationStepStatus,
)
from maverick.tui.models.findings import CodeContext, ReviewFinding, ReviewFindingItem
from maverick.tui.models.github import PRInfo
from maverick.tui.models.workflow import AgentMessage, ValidationStep, WorkflowStage


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
        match_positions: List of (message_index, char_offset) for each match.
        current_match_index: Index of currently highlighted match in match_positions.
        total_matches: Count of all matches.
        filter_agent: Filter to specific agent ID.
        filter_message_type: Filter to specific message type.
        truncated: Whether old messages were discarded.
    """

    messages: list[AgentMessage] = field(default_factory=list)
    max_messages: int = 1000
    auto_scroll: bool = True
    search_query: str | None = None
    search_matches: list[int] = field(default_factory=list)
    match_positions: list[tuple[int, int]] = field(default_factory=list)
    current_match_index: int = -1
    total_matches: int = 0
    filter_agent: str | None = None
    filter_message_type: MessageType | None = None
    truncated: bool = False

    def add_message(self, message: AgentMessage) -> None:
        """Add a message, maintaining buffer limit."""
        self.messages.append(message)
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages :]
            self.truncated = True

    @property
    def filtered_messages(self) -> list[AgentMessage]:
        """Get messages filtered by agent, message type, and search."""
        result = self.messages
        if self.filter_agent:
            result = [m for m in result if m.agent_id == self.filter_agent]
        if self.filter_message_type:
            result = [m for m in result if m.message_type == self.filter_message_type]
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
