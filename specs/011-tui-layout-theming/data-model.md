# Data Model: Textual TUI Layout and Theming

**Feature**: 011-tui-layout-theming
**Date**: 2025-12-16
**Status**: Complete

## Overview

This document defines the data models and state structures for the Maverick TUI. The TUI is primarily a presentation layer that consumes state from workflows; these models define how that state is represented and displayed.

---

## 1. Screen State Models

### ScreenState (Base)

All screens share common state for navigation and status display.

```python
@dataclass(frozen=True, slots=True)
class ScreenState:
    """Base state shared by all screens."""

    title: str
    can_go_back: bool = True
    error_message: str | None = None
```

### HomeScreenState

State for the home/dashboard screen.

```python
@dataclass(frozen=True, slots=True)
class RecentWorkflowEntry:
    """Entry in the recent workflows list."""

    branch_name: str
    workflow_type: str  # "fly" | "refuel"
    status: str  # "completed" | "failed" | "in_progress"
    started_at: datetime
    completed_at: datetime | None
    pr_url: str | None


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
```

**Validation Rules**:
- `recent_workflows`: Maximum 10 entries (FR-007, clarification)
- `selected_index`: Must be within bounds of recent_workflows

### WorkflowScreenState

State for the active workflow progress screen.

```python
@dataclass(frozen=True, slots=True)
class StageState:
    """State of a single workflow stage."""

    name: str
    display_name: str
    status: StageStatus  # Enum: pending, active, completed, failed
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None


class StageStatus(str, Enum):
    """Status of a workflow stage."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class WorkflowScreenState(ScreenState):
    """State for the workflow progress screen."""

    workflow_name: str
    branch_name: str
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
```

**Validation Rules**:
- `workflow_name`: Non-empty string
- `branch_name`: Non-empty string matching git branch format
- `stages`: At least one stage for active workflow
- `elapsed_seconds`: Non-negative

### ReviewScreenState

State for the code review results screen.

```python
class IssueSeverity(str, Enum):
    """Severity level of a review issue."""

    ERROR = "error"      # Red
    WARNING = "warning"  # Yellow
    INFO = "info"        # Blue
    SUGGESTION = "suggestion"  # Cyan


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
    filter_severity: IssueSeverity | None = None  # None = show all

    @property
    def filtered_issues(self) -> tuple[ReviewIssue, ...]:
        """Get issues filtered by severity."""
        if self.filter_severity is None:
            return self.issues
        return tuple(i for i in self.issues if i.severity == self.filter_severity)

    @property
    def issue_counts(self) -> dict[IssueSeverity, int]:
        """Count issues by severity."""
        counts = {s: 0 for s in IssueSeverity}
        for issue in self.issues:
            counts[issue.severity] += 1
        return counts
```

**Validation Rules**:
- `issues`: Can be empty (no issues found)
- `selected_issue_index`: Must be within bounds of filtered_issues
- `file_path`: Valid file path (may be relative)

### ConfigScreenState

State for the settings/configuration screen.

```python
@dataclass(frozen=True, slots=True)
class ConfigOption:
    """A single configuration option."""

    key: str
    display_name: str
    value: str | bool | int
    description: str
    option_type: str  # "bool" | "string" | "int" | "choice"
    choices: tuple[str, ...] | None = None  # For choice type


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
```

**Validation Rules**:
- `options`: Derived from MaverickConfig
- `edit_value`: Validated against option_type before applying

---

## 2. Widget State Models

### LogPanelState

State for the collapsible log panel.

```python
@dataclass(frozen=True, slots=True)
class LogEntry:
    """A single log entry."""

    timestamp: datetime
    source: str  # Agent or component name
    level: str   # "info" | "success" | "warning" | "error"
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
            self.entries = self.entries[-self.max_entries:]
```

**Note**: `LogPanelState` is mutable for performance (frequent appends). Uses `@dataclass(slots=True)` without `frozen=True`.

**Validation Rules**:
- `max_entries`: Default 1,000 (clarification)
- `entries`: FIFO buffer, oldest dropped when limit exceeded

### SidebarState

State for the sidebar component.

```python
class SidebarMode(str, Enum):
    """Display mode for the sidebar."""

    NAVIGATION = "navigation"  # Shows menu items
    WORKFLOW = "workflow"      # Shows workflow stages


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
        NavigationItem("home", "Home", "🏠", "Ctrl+H"),
        NavigationItem("workflows", "Workflows", "⚡"),
        NavigationItem("settings", "Settings", "⚙️", "Ctrl+,"),
    )
    workflow_stages: tuple[StageState, ...] = ()
    selected_nav_index: int = 0
```

**Validation Rules**:
- `mode`: Determines which content is displayed
- `workflow_stages`: Populated from WorkflowScreenState when workflow active

---

## 3. Theme Models

### ThemeColors

Color definitions for the theme system.

```python
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

    # Status (FR-015)
    success: str = "#4caf50"
    warning: str = "#ff9800"
    error: str = "#f44336"
    info: str = "#2196f3"

    # Accent (FR-016)
    accent: str = "#00aaff"
    accent_muted: str = "#0077aa"


# Default dark theme instance
DARK_THEME = ThemeColors()

# Light theme (future)
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
```

---

## 4. State Transitions

### Workflow Stage Transitions

```
pending → active → completed
               ↘ failed
```

Valid transitions:
- `pending` → `active`: Stage starts
- `active` → `completed`: Stage succeeds
- `active` → `failed`: Stage fails

Invalid transitions (should raise error):
- `completed` → any
- `failed` → any (must restart workflow)
- `pending` → `completed` (must go through active)

### Screen Navigation Transitions

```
                    ┌─────────────┐
                    │ HomeScreen  │
                    └──────┬──────┘
                           │ push
              ┌────────────┼────────────┐
              ↓            ↓            ↓
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │WorkflowScreen│ │ConfigScreen │ │ ReviewScreen│
    └─────────────┘ └─────────────┘ └─────────────┘
              ↑            ↑            ↑
              └────────────┴────────────┘
                       pop (Escape)
```

---

## 5. Entity Relationships

```
MaverickApp
├── LogPanelState (1)
├── SidebarState (1)
└── Screens
    ├── HomeScreen → HomeScreenState
    │   └── RecentWorkflowEntry (0..10)
    ├── WorkflowScreen → WorkflowScreenState
    │   └── StageState (1..n)
    ├── ReviewScreen → ReviewScreenState
    │   └── ReviewIssue (0..n)
    └── ConfigScreen → ConfigScreenState
        └── ConfigOption (0..n)

ThemeColors → Applied via maverick.tcss
```

---

## 6. Mapping to Functional Requirements

| Requirement | Entity/Model | Field/Property |
|-------------|--------------|----------------|
| FR-001 | MaverickApp | Main app class |
| FR-002 | Header widget | workflow_name, elapsed_seconds |
| FR-003 | SidebarState | mode, navigation_items, workflow_stages |
| FR-004 | Screen classes | Main content area |
| FR-005 | LogPanelState | visible, entries |
| FR-006 | Footer widget | Derived from BINDINGS |
| FR-007 | HomeScreenState | recent_workflows |
| FR-008 | WorkflowScreenState | stages, progress_percent |
| FR-009 | ReviewScreenState | issues, filtered_issues |
| FR-010 | ConfigScreenState | options |
| FR-014 | ThemeColors | DARK_THEME default |
| FR-015 | ThemeColors | success, warning, error, info |
| FR-016 | ThemeColors | accent, accent_muted |
| FR-019 | StageStatus | COMPLETED + icon ✓ |
| FR-020 | StageStatus | ACTIVE + animation |
| FR-021 | StageStatus | PENDING |
| FR-022 | StageStatus | FAILED + icon ✗ |

---

## Summary

This data model provides:

1. **Immutable screen states** with frozen dataclasses for predictable updates
2. **Mutable log panel state** for performance with high-frequency appends
3. **Theme colors** as data for CSS variable generation
4. **Clear state transitions** for workflow stages and navigation
5. **Direct mapping** to functional requirements

All models use Python 3.10+ type hints with `from __future__ import annotations` for forward references.
