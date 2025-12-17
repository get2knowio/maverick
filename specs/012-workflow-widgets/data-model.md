# Data Model: Workflow Visualization Widgets

**Feature**: 012-workflow-widgets
**Date**: 2025-12-16
**Status**: Complete

## Overview

This document defines the data models for the five workflow visualization widgets. All models follow Maverick conventions:
- Use `@dataclass(frozen=True, slots=True)` for immutable state
- Use `tuple` instead of `list` for immutable collections
- Extend existing models in `src/maverick/tui/models.py`

## Entity Relationship Diagram

```
WorkflowProgressState
├── stages: tuple[WorkflowStage, ...]
└── loading: bool

AgentOutputState
├── messages: tuple[AgentMessage, ...]
│   └── AgentMessage
│       ├── content: str
│       ├── message_type: MessageType
│       └── tool_call: ToolCallInfo | None
├── auto_scroll: bool
├── search_query: str | None
└── filter_agent: str | None

ReviewFindingsState
├── findings: tuple[ReviewFindingItem, ...]
│   └── ReviewFindingItem
│       ├── finding: ReviewFinding
│       └── selected: bool
├── expanded_index: int | None
└── code_context: CodeContext | None

ValidationStatusState
├── steps: tuple[ValidationStep, ...]
└── expanded_step: str | None

PRSummaryState
├── pr: PRInfo | None
├── description_expanded: bool
└── loading: bool
```

## Enums

### MessageType

```python
class MessageType(str, Enum):
    """Type of agent message content."""
    TEXT = "text"
    CODE = "code"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
```

**Usage**: Discriminator for rendering logic in AgentOutput widget.

### FindingSeverity

```python
class FindingSeverity(str, Enum):
    """Severity level of a code review finding."""
    ERROR = "error"
    WARNING = "warning"
    SUGGESTION = "suggestion"
```

**Note**: Extends existing `IssueSeverity` enum. Removes `INFO` as spec only mentions error/warning/suggestion.

### ValidationStepStatus

```python
class ValidationStepStatus(str, Enum):
    """Status of a validation step."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
```

**Usage**: Four-state status for validation steps (FR-025 to FR-029).

### PRState

```python
class PRState(str, Enum):
    """State of a pull request."""
    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"
```

**Usage**: Visual indicator for PR status (FR-034).

### CheckStatus

```python
class CheckStatus(str, Enum):
    """Status of a CI/CD status check."""
    PENDING = "pending"
    PASSING = "passing"
    FAILING = "failing"
```

**Usage**: Status check indicators in PRSummary (FR-032).

---

## Core Entities

### WorkflowStage

```python
@dataclass(frozen=True, slots=True)
class WorkflowStage:
    """Represents a single stage in a workflow.

    Attributes:
        name: Unique identifier for the stage (e.g., "setup", "implementation").
        display_name: Human-readable name shown in UI.
        status: Current status of the stage.
        started_at: When the stage began execution.
        completed_at: When the stage finished (success or error).
        duration_seconds: Elapsed time (computed if completed_at set).
        detail_content: Optional expandable content for the stage.
        error_message: Error details if status is ERROR.
    """
    name: str
    display_name: str
    status: StageStatus  # Reuse existing enum from models.py
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
```

**FR Coverage**: FR-001 to FR-007

---

### AgentMessage

```python
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
    language: str | None = None  # For code blocks
    tool_call: ToolCallInfo | None = None
```

**FR Coverage**: FR-008 to FR-011

---

### ReviewFinding

```python
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
class ReviewFindingItem:
    """A finding with selection state for the UI.

    Attributes:
        finding: The review finding data.
        selected: Whether this item is selected for bulk action.
    """
    finding: ReviewFinding
    selected: bool = False
```

**FR Coverage**: FR-017 to FR-024

---

### ValidationStep

```python
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
```

**FR Coverage**: FR-025 to FR-029

---

### PRInfo

```python
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
```

**FR Coverage**: FR-030 to FR-034

---

## Widget State Models

### WorkflowProgressState

```python
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
```

---

### AgentOutputState

```python
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
            self.messages = self.messages[-self.max_messages:]
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
```

---

### ReviewFindingsState

```python
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
```

---

### ValidationStatusState

```python
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
```

---

### PRSummaryState

```python
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
```

---

## Validation Rules

### WorkflowStage
- `name` must be non-empty, lowercase alphanumeric with hyphens
- `display_name` must be non-empty
- `status` must be valid `StageStatus` enum value
- `completed_at` must be >= `started_at` if both set
- `error_message` should only be set when `status == FAILED`

### AgentMessage
- `id` must be unique within the message buffer
- `timestamp` must be valid datetime
- `content` can be empty for tool calls
- `language` should be set when `message_type == CODE`
- `tool_call` should be set when `message_type == TOOL_CALL`

### ReviewFinding
- `id` must be unique within the findings list
- `location.line_number` must be >= 1
- `location.file_path` must be a valid relative path
- `title` must be non-empty (max 100 chars for display)
- `description` can be multi-line markdown

### ValidationStep
- `name` must be one of: "format", "lint", "type_check", "build", "test"
- `display_name` maps: format->Format, lint->Lint, type_check->Type Check, build->Build, test->Test
- `error_output` should only be set when `status == FAILED`

### PRInfo
- `number` must be > 0
- `title` must be non-empty
- `url` must be valid GitHub PR URL format
- `checks` items must have unique names

---

## State Transitions

### WorkflowStage Status Flow
```
PENDING -> ACTIVE -> COMPLETED
                  -> FAILED
```

### ValidationStep Status Flow
```
PENDING -> RUNNING -> PASSED
                   -> FAILED -> RUNNING (re-run)
```

### AgentOutputState Auto-Scroll
```
auto_scroll=True + user_at_bottom -> auto_scroll=True
auto_scroll=True + user_scrolls_up -> auto_scroll=False
auto_scroll=False + user_scrolls_to_bottom -> auto_scroll=True
```

---

## Integration Points

### Workflow Events -> Widget State

| Workflow Event | Widget State Update |
|---------------|---------------------|
| `FlyStageStarted` | `WorkflowStage.status = ACTIVE` |
| `FlyStageCompleted` | `WorkflowStage.status = COMPLETED` |
| `ProgressUpdate` | `ValidationStep.status` update |
| Agent message stream | `AgentOutputState.add_message()` |

### Widget Actions -> External Systems

| Widget Action | External Call |
|--------------|---------------|
| "Create Issue" button | GitHub CLI `gh issue create` |
| "Open PR" link | `webbrowser.open(pr.url)` |
| "Re-run" button | Validation workflow re-execution |
