from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from maverick.tui.models.enums import (
    FindingSeverity,
    IterationStatus,
    MessageType,
    StageStatus,
    StreamChunkType,
    StreamEntryType,
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


@dataclass(slots=True)
class LoopIterationItem:
    """Display state for a single loop iteration.

    Attributes:
        index: 0-based iteration index.
        total: Total iterations in loop.
        label: Display label (e.g., "Phase 1: Setup").
        status: Current status.
        duration_ms: Execution time (None if not started).
        error: Error message if failed.
        started_at: Timestamp when started.
        completed_at: Timestamp when completed.
    """

    index: int
    total: int
    label: str
    status: IterationStatus
    duration_ms: int | None = None
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None

    @property
    def display_text(self) -> str:
        """Display format: '{index+1}/{total}: {label}'.

        Example: '1/3: Phase 1: Setup'
        """
        return f"{self.index + 1}/{self.total}: {self.label}"


@dataclass(slots=True)
class LoopIterationState:
    """Aggregate state for loop iteration progress display.

    Attributes:
        step_name: Name of the loop step.
        iterations: All iterations.
        nesting_level: Depth of nesting (0 = top-level).
        expanded: Whether iterations are visible.
    """

    step_name: str
    iterations: list[LoopIterationItem] = field(default_factory=list)
    nesting_level: int = 0
    expanded: bool = True

    def get_iteration(self, index: int) -> LoopIterationItem | None:
        """Get iteration by index.

        Args:
            index: Zero-based index of the iteration.

        Returns:
            The iteration item if found, None otherwise.
        """
        if 0 <= index < len(self.iterations):
            return self.iterations[index]
        return None

    def update_iteration(self, index: int, **updates: object) -> None:
        """Update iteration fields.

        Args:
            index: Zero-based index of the iteration to update.
            **updates: Field names and values to update.
        """
        if item := self.get_iteration(index):
            for key, value in updates.items():
                setattr(item, key, value)

    @property
    def current_iteration(self) -> LoopIterationItem | None:
        """Get the currently running iteration.

        Returns:
            The iteration with RUNNING status, or None if no iteration is running.
        """
        for item in self.iterations:
            if item.status == IterationStatus.RUNNING:
                return item
        return None

    @property
    def progress_fraction(self) -> float:
        """Progress as fraction 0.0-1.0.

        Returns:
            Fraction of completed iterations (including failed/skipped).
        """
        if not self.iterations:
            return 0.0
        terminal_statuses = (
            IterationStatus.COMPLETED,
            IterationStatus.FAILED,
            IterationStatus.SKIPPED,
        )
        completed = sum(1 for i in self.iterations if i.status in terminal_statuses)
        return completed / len(self.iterations)


@dataclass(frozen=True, slots=True)
class AgentStreamEntry:
    """A single streaming output entry.

    Attributes:
        timestamp: When the chunk was received.
        step_name: Source step name.
        agent_name: Source agent name.
        text: Text content.
        chunk_type: Type of chunk.
    """

    timestamp: float
    step_name: str
    agent_name: str
    text: str
    chunk_type: StreamChunkType

    @property
    def size_bytes(self) -> int:
        """Approximate size in bytes for buffer management."""
        return len(self.text.encode("utf-8"))


@dataclass(slots=True)
class StreamingPanelState:
    """State for the agent streaming panel.

    Attributes:
        visible: Panel expanded/collapsed.
        auto_scroll: Auto-scroll to latest.
        entries: List of streaming output entries.
        current_source: Current source identifier ("{step_name} - {agent_name}").
        max_size_bytes: Maximum buffer size in bytes (default: 100KB).
        _current_size_bytes: Tracked current size in bytes.
    """

    visible: bool = True
    auto_scroll: bool = True
    entries: list[AgentStreamEntry] = field(default_factory=list)
    current_source: str | None = None
    max_size_bytes: int = 100 * 1024  # 100KB limit
    _current_size_bytes: int = 0

    def __post_init__(self) -> None:
        """Initialize size tracking from any pre-existing entries."""
        if self.entries and self._current_size_bytes == 0:
            self._current_size_bytes = sum(e.size_bytes for e in self.entries)

    def add_entry(self, entry: AgentStreamEntry) -> None:
        """Add entry, enforcing size limit with FIFO eviction.

        Args:
            entry: The streaming entry to add.
        """
        entry_size = entry.size_bytes

        # Evict oldest entries if needed
        while (
            self._current_size_bytes + entry_size > self.max_size_bytes and self.entries
        ):
            removed = self.entries.pop(0)
            self._current_size_bytes -= removed.size_bytes

        self.entries.append(entry)
        self._current_size_bytes += entry_size
        self.current_source = f"{entry.step_name} - {entry.agent_name}"

    def clear(self) -> None:
        """Clear all entries."""
        self.entries.clear()
        self._current_size_bytes = 0
        self.current_source = None

    @property
    def total_size_bytes(self) -> int:
        """Current buffer size in bytes."""
        return self._current_size_bytes


@dataclass(frozen=True, slots=True)
class UnifiedStreamEntry:
    """A single entry in the unified event stream.

    Used by UnifiedStreamWidget to display all workflow events in a
    single chronological stream with type-specific styling.

    Attributes:
        timestamp: When the event occurred.
        entry_type: Type of entry for styling.
        source: Step name or agent name.
        content: Primary text content.
        level: Severity level for coloring (info, success, warning, error).
        duration_ms: Duration in milliseconds (for completed steps).
        metadata: Additional data for the entry (e.g., tool parameters).
    """

    timestamp: float
    entry_type: StreamEntryType
    source: str
    content: str
    level: str = "info"
    duration_ms: int | None = None
    metadata: dict[str, object] | None = None
    step_name: str | None = None
    step_path: str | None = None

    @property
    def formatted_time(self) -> str:
        """Format timestamp as HH:MM:SS."""
        dt = datetime.fromtimestamp(self.timestamp)
        return dt.strftime("%H:%M:%S")

    @property
    def size_bytes(self) -> int:
        """Approximate size in bytes for buffer management."""
        return len(self.content.encode("utf-8"))

    @property
    def badge(self) -> str:
        """Get the display badge for this entry type."""
        badges = {
            StreamEntryType.STEP_START: "[STEP]",
            StreamEntryType.STEP_COMPLETE: "[OK]",
            StreamEntryType.STEP_FAILED: "[FAIL]",
            StreamEntryType.STEP_OUTPUT: f"[{self.source}]" if self.source else "[OUT]",
            StreamEntryType.AGENT_OUTPUT: f"[{self.source}]",
            StreamEntryType.AGENT_THINKING: "[thinking]",
            StreamEntryType.TOOL_CALL: "[TOOL]",
            StreamEntryType.TOOL_RESULT: "[RESULT]",
            StreamEntryType.LOOP_START: "[LOOP]",
            StreamEntryType.LOOP_COMPLETE: "[LOOP]",
            StreamEntryType.ERROR: "[ERROR]",
            StreamEntryType.INFO: "[INFO]",
        }
        return badges.get(self.entry_type, f"[{self.entry_type.value}]")


@dataclass(slots=True)
class UnifiedStreamState:
    """State for the unified stream widget.

    Attributes:
        entries: List of stream entries.
        auto_scroll: Whether to auto-scroll to latest.
        max_size_bytes: Maximum buffer size in bytes (default: 100KB).
        _current_size_bytes: Tracked current size in bytes.
        current_step: Name of the currently running step.
        current_step_number: 1-based index of current step.
        total_steps: Total number of steps.
        workflow_name: Name of the running workflow.
        start_time: When the workflow started.
        current_step_type: Type of the currently running step.
        current_step_started_at: Timestamp when current step started.
        current_step_tokens: Running total tokens for current step.
        current_step_cost: Running cost for current step.
        total_tokens: Aggregate token count across all steps.
        total_cost: Aggregate cost across all steps.
        completed_steps: Count of successfully completed steps.
        failed_steps: Count of failed steps.
    """

    entries: list[UnifiedStreamEntry] = field(default_factory=list)
    auto_scroll: bool = True
    max_size_bytes: int = 100 * 1024  # 100KB limit
    _current_size_bytes: int = 0
    current_step: str | None = None
    current_step_number: int = 0
    total_steps: int = 0
    workflow_name: str = ""
    start_time: float | None = None
    # Detail panel state (for step detail tracking)
    current_step_type: str | None = None
    current_step_started_at: float | None = None
    current_step_tokens: int = 0
    current_step_cost: float = 0.0
    # Aggregate tracking
    total_tokens: int = 0
    total_cost: float = 0.0
    completed_steps: int = 0
    failed_steps: int = 0

    def __post_init__(self) -> None:
        """Initialize size tracking from any pre-existing entries."""
        if self.entries and self._current_size_bytes == 0:
            self._current_size_bytes = sum(e.size_bytes for e in self.entries)

    def add_entry(self, entry: UnifiedStreamEntry) -> None:
        """Add entry, enforcing size limit with FIFO eviction.

        Args:
            entry: The stream entry to add.
        """
        entry_size = entry.size_bytes

        # Evict oldest entries if needed
        while (
            self._current_size_bytes + entry_size > self.max_size_bytes and self.entries
        ):
            removed = self.entries.pop(0)
            self._current_size_bytes -= removed.size_bytes

        self.entries.append(entry)
        self._current_size_bytes += entry_size

    def clear(self) -> None:
        """Clear all entries."""
        self.entries.clear()
        self._current_size_bytes = 0

    @property
    def elapsed_seconds(self) -> int:
        """Get elapsed time since workflow started."""
        if self.start_time is None:
            return 0
        import time

        return int(time.time() - self.start_time)

    @property
    def elapsed_formatted(self) -> str:
        """Get elapsed time formatted as MM:SS."""
        total = self.elapsed_seconds
        minutes = total // 60
        seconds = total % 60
        return f"{minutes:02d}:{seconds:02d}"

    def start_step(self, step_name: str, step_type: str) -> None:
        """Record that a step has started.

        Args:
            step_name: Name of the step.
            step_type: Type of the step (e.g., "agent", "python").
        """
        import time

        self.current_step = step_name
        self.current_step_type = step_type
        self.current_step_started_at = time.time()
        self.current_step_tokens = 0
        self.current_step_cost = 0.0
        self.current_step_number += 1

    def complete_step(
        self,
        success: bool,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_usd: float | None = None,
    ) -> None:
        """Record that a step has completed.

        Args:
            success: Whether the step completed successfully.
            input_tokens: Input tokens consumed (agent steps only).
            output_tokens: Output tokens generated (agent steps only).
            cost_usd: Cost in USD (agent steps only).
        """
        if success:
            self.completed_steps += 1
        else:
            self.failed_steps += 1

        # Accumulate tokens and cost from this step
        tokens = 0
        if input_tokens is not None:
            tokens += input_tokens
        if output_tokens is not None:
            tokens += output_tokens

        if tokens > 0:
            self.current_step_tokens = tokens
            self.total_tokens += tokens

        if cost_usd is not None:
            self.current_step_cost = cost_usd
            self.total_cost += cost_usd

    @property
    def current_step_elapsed_formatted(self) -> str:
        """Get elapsed time for current step formatted as MM:SS."""
        if self.current_step_started_at is None:
            return "--:--"
        import time

        elapsed = int(time.time() - self.current_step_started_at)
        minutes, seconds = divmod(elapsed, 60)
        return f"{minutes:02d}:{seconds:02d}"
