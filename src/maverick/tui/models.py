"""Data models for Maverick TUI.

This module defines the data models and state structures for the Maverick TUI.
The TUI is primarily a presentation layer that consumes state from workflows;
these models define how that state is represented and displayed.
"""

from __future__ import annotations

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
