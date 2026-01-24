# #!/usr/bin/env python3
“””
Maverick Monitor Prototype

A standalone Textual prototype demonstrating monitoring patterns for long-running
AI agent tasks. No external dependencies beyond Textual itself.

Run with: textual run –dev maverick_monitor_prototype.py

Key bindings:
j/k or ↑/↓  - Navigate task list
Enter       - Select task (show detail)
l           - Toggle full-screen log view
f           - Toggle focus mode (hide task list)
s           - Toggle auto-scroll in log
/           - Filter tasks (ESC to clear)
1-5         - Set log verbosity level
?           - Show help
q           - Quit

Design principles demonstrated:

- Three-tier information hierarchy (grid → detail → logs)
- Glanceability through color-coded status
- Streaming output with auto-scroll/pause detection
- Preattentive visual encoding (status pops out)
- Detail-on-demand without losing context
  “””

from **future** import annotations

import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import ClassVar

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import (
Button,
DataTable,
Footer,
Header,
Label,
ProgressBar,
RichLog,
Rule,
Sparkline,
Static,
)

# =============================================================================

# Domain Models

# =============================================================================

class TaskStatus(Enum):
“”“Task execution states with associated styling.”””

```
PENDING = ("pending", "○", "dim white", "Waiting to start")
RUNNING = ("running", "●", "dodger_blue1", "In progress")
SUCCESS = ("success", "✓", "green", "Completed successfully")
WARNING = ("warning", "⚠", "yellow", "Completed with warnings")
ERROR = ("error", "✗", "red", "Failed")
CANCELLED = ("cancelled", "◌", "dim white", "Cancelled by user")

def __init__(self, id_: str, icon: str, color: str, description: str):
    self.id_ = id_
    self.icon = icon
    self.color = color
    self.description = description

@property
def styled(self) -> str:
    """Return Rich-formatted status string."""
    return f"[{self.color}]{self.icon}[/]"

@property
def styled_full(self) -> str:
    """Return Rich-formatted status with label."""
    return f"[{self.color}]{self.icon} {self.id_.title()}[/]"
```

class TaskPhase(Enum):
“”“Phases within a task lifecycle.”””

```
INITIALIZING = "Initializing"
PLANNING = "Planning"
EXECUTING = "Executing"
VERIFYING = "Verifying"
FINALIZING = "Finalizing"
COMPLETE = "Complete"
```

@dataclass
class Task:
“”“Represents a long-running AI agent task.”””

```
id: str
name: str
description: str
status: TaskStatus = TaskStatus.PENDING
phase: TaskPhase = TaskPhase.INITIALIZING
progress: float = 0.0  # 0.0 to 1.0
started_at: datetime | None = None
completed_at: datetime | None = None
tokens_used: int = 0
estimated_cost: float = 0.0
log_lines: list[str] = field(default_factory=list)
activity_history: list[float] = field(default_factory=list)  # For sparkline

@property
def elapsed(self) -> timedelta | None:
    """Time elapsed since task started."""
    if self.started_at is None:
        return None
    end = self.completed_at or datetime.now()
    return end - self.started_at

@property
def elapsed_str(self) -> str:
    """Human-readable elapsed time."""
    if self.elapsed is None:
        return "--:--"
    total_seconds = int(self.elapsed.total_seconds())
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes:02d}:{seconds:02d}"

@property
def preview_lines(self) -> list[str]:
    """Last few lines of output for preview."""
    return self.log_lines[-5:] if self.log_lines else ["(no output yet)"]
```

# =============================================================================

# Mock Data Generator

# =============================================================================

class MockTaskEngine:
“””
Generates mock task data and simulates streaming output.
In production, this would be replaced with real agent integration.
“””

```
TASK_TEMPLATES = [
    ("refactor-auth", "Refactor authentication module", "Modernizing OAuth2 flow"),
    ("add-tests", "Add unit tests for API", "Increasing coverage to 80%"),
    ("fix-perf", "Fix performance regression", "Optimizing database queries"),
    ("update-deps", "Update dependencies", "Security patches for Q1"),
    ("impl-feature", "Implement search feature", "Full-text search with filters"),
    ("migrate-db", "Database migration", "PostgreSQL 15 upgrade"),
]

OUTPUT_SAMPLES = [
    "Analyzing codebase structure...",
    "Found 23 files matching pattern",
    "Generating abstract syntax tree",
    "Identifying refactoring opportunities",
    "Applying transformation: extract_method",
    "Running static analysis checks",
    "Validating type annotations",
    "Executing test suite (47 tests)",
    "All assertions passed",
    "Formatting code with black",
    "Committing changes to branch",
    "Creating pull request draft",
    "Waiting for CI pipeline...",
    "Build succeeded ✓",
    "Ready for review",
]

THINKING_SAMPLES = [
    "[dim]Considering alternative approaches...[/]",
    "[dim]Evaluating trade-offs between speed and memory...[/]",
    "[dim]This reminds me of the adapter pattern...[/]",
    "[dim]Let me verify this assumption...[/]",
    "[dim]Hmm, edge case detected...[/]",
]

TOOL_CALLS = [
    "[cyan]→ read_file[/] src/auth/handler.py",
    "[cyan]→ write_file[/] src/auth/oauth2.py",
    "[cyan]→ run_command[/] pytest tests/",
    "[cyan]→ search_codebase[/] 'def authenticate'",
    "[cyan]→ git_commit[/] 'refactor: extract OAuth logic'",
]

@classmethod
def create_mock_tasks(cls) -> list[Task]:
    """Generate initial set of mock tasks in various states."""
    tasks = []

    # Running task - most activity
    t1 = Task(
        id="task-001",
        name="refactor-auth",
        description="Refactoring authentication module for OAuth2",
        status=TaskStatus.RUNNING,
        phase=TaskPhase.EXECUTING,
        progress=0.45,
        started_at=datetime.now() - timedelta(minutes=3, seconds=27),
        tokens_used=12847,
        estimated_cost=0.0385,
        activity_history=[0.2, 0.4, 0.3, 0.6, 0.8, 0.5, 0.7, 0.9, 0.6, 0.8],
    )
    t1.log_lines = [
        "Starting authentication module refactor...",
        "[cyan]→ read_file[/] src/auth/handler.py",
        "Analyzing current OAuth1 implementation",
        "[dim]This appears to use deprecated flow...[/]",
        "[cyan]→ search_codebase[/] 'token_refresh'",
        "Found 7 references to legacy token handling",
    ]
    tasks.append(t1)

    # Another running task - earlier phase
    t2 = Task(
        id="task-002",
        name="add-tests",
        description="Adding comprehensive unit tests for API endpoints",
        status=TaskStatus.RUNNING,
        phase=TaskPhase.PLANNING,
        progress=0.15,
        started_at=datetime.now() - timedelta(minutes=1, seconds=12),
        tokens_used=4521,
        estimated_cost=0.0136,
        activity_history=[0.1, 0.2, 0.3, 0.2, 0.4, 0.3],
    )
    t2.log_lines = [
        "Analyzing test coverage gaps...",
        "[cyan]→ run_command[/] pytest --cov --cov-report=json",
        "Current coverage: 47%",
        "Identifying critical paths without coverage",
    ]
    tasks.append(t2)

    # Completed successfully
    t3 = Task(
        id="task-003",
        name="fix-perf",
        description="Fixed N+1 query in user listing endpoint",
        status=TaskStatus.SUCCESS,
        phase=TaskPhase.COMPLETE,
        progress=1.0,
        started_at=datetime.now() - timedelta(minutes=8, seconds=45),
        completed_at=datetime.now() - timedelta(minutes=2, seconds=10),
        tokens_used=28934,
        estimated_cost=0.0868,
        activity_history=[0.3, 0.5, 0.7, 0.9, 0.8, 0.6, 0.4, 0.2, 0.1, 0.0],
    )
    t3.log_lines = [
        "Profiling database queries...",
        "[yellow]⚠ Detected N+1 pattern in get_users()[/]",
        "[cyan]→ read_file[/] src/api/users.py",
        "Applying eager loading with select_related()",
        "[cyan]→ write_file[/] src/api/users.py",
        "Running performance benchmark...",
        "[green]✓ Query time reduced from 340ms to 12ms[/]",
        "[cyan]→ git_commit[/] 'perf: fix N+1 in user listing'",
        "[green]✓ Task completed successfully[/]",
    ]
    tasks.append(t3)

    # Warning state
    t4 = Task(
        id="task-004",
        name="update-deps",
        description="Dependency updates with some deprecation warnings",
        status=TaskStatus.WARNING,
        phase=TaskPhase.COMPLETE,
        progress=1.0,
        started_at=datetime.now() - timedelta(minutes=12),
        completed_at=datetime.now() - timedelta(minutes=5),
        tokens_used=15672,
        estimated_cost=0.0470,
        activity_history=[0.4, 0.6, 0.5, 0.7, 0.5, 0.3, 0.2, 0.1],
    )
    t4.log_lines = [
        "Checking for outdated packages...",
        "[cyan]→ run_command[/] pip list --outdated",
        "Found 12 packages with updates available",
        "[yellow]⚠ requests 2.28→2.31 has breaking changes[/]",
        "[yellow]⚠ Deprecation: ssl.PROTOCOL_TLS[/]",
        "Updates applied, some warnings remain",
        "[yellow]⚠ Completed with 2 deprecation warnings[/]",
    ]
    tasks.append(t4)

    # Error state
    t5 = Task(
        id="task-005",
        name="impl-feature",
        description="Search feature implementation failed on index creation",
        status=TaskStatus.ERROR,
        phase=TaskPhase.EXECUTING,
        progress=0.67,
        started_at=datetime.now() - timedelta(minutes=6, seconds=30),
        completed_at=datetime.now() - timedelta(minutes=1),
        tokens_used=21456,
        estimated_cost=0.0644,
        activity_history=[0.2, 0.4, 0.6, 0.7, 0.8, 0.9, 0.0],
    )
    t5.log_lines = [
        "Implementing full-text search...",
        "[cyan]→ write_file[/] src/search/indexer.py",
        "Creating Elasticsearch index mapping",
        "[cyan]→ run_command[/] curl -X PUT localhost:9200/docs",
        "[red]✗ Connection refused: Elasticsearch not running[/]",
        "[red]✗ ERROR: Failed to create search index[/]",
        "[dim]Hint: Ensure Elasticsearch is running on port 9200[/]",
    ]
    tasks.append(t5)

    # Pending task
    t6 = Task(
        id="task-006",
        name="migrate-db",
        description="PostgreSQL 15 migration (queued)",
        status=TaskStatus.PENDING,
        phase=TaskPhase.INITIALIZING,
        progress=0.0,
    )
    t6.log_lines = ["Waiting in queue..."]
    tasks.append(t6)

    return tasks

@classmethod
def generate_output_line(cls) -> str:
    """Generate a random output line for streaming simulation."""
    roll = random.random()
    if roll < 0.15:
        return random.choice(cls.TOOL_CALLS)
    elif roll < 0.25:
        return random.choice(cls.THINKING_SAMPLES)
    else:
        return random.choice(cls.OUTPUT_SAMPLES)
```

# =============================================================================

# Custom Widgets

# =============================================================================

class AggregateStats(Static):
“”“Header widget showing aggregate task statistics.”””

```
tasks: reactive[list[Task]] = reactive(list, recompose=True)

def render(self) -> str:
    if not self.tasks:
        return "No tasks"

    by_status = {}
    for task in self.tasks:
        by_status.setdefault(task.status, []).append(task)

    parts = []
    for status in [
        TaskStatus.RUNNING,
        TaskStatus.SUCCESS,
        TaskStatus.WARNING,
        TaskStatus.ERROR,
        TaskStatus.PENDING,
    ]:
        if status in by_status:
            count = len(by_status[status])
            parts.append(f"[{status.color}]{status.icon} {count}[/]")

    total_tokens = sum(t.tokens_used for t in self.tasks)
    total_cost = sum(t.estimated_cost for t in self.tasks)

    return (
        f"  {' │ '.join(parts)}  │  "
        f"[dim]Tokens:[/] {total_tokens:,}  │  "
        f"[dim]Cost:[/] ${total_cost:.4f}"
    )
```

class TaskRow(Static):
“”“A single row in the task list with status indicator.”””

```
task: reactive[Task | None] = reactive(None)
selected: reactive[bool] = reactive(False)

def __init__(self, task: Task, **kwargs):
    super().__init__(**kwargs)
    self.task = task

def render(self) -> str:
    if self.task is None:
        return ""

    t = self.task
    status = t.status.styled

    # Progress indicator for running tasks
    if t.status == TaskStatus.RUNNING:
        pct = int(t.progress * 100)
        progress = f"[dim]{pct:3d}%[/]"
    elif t.status == TaskStatus.SUCCESS:
        progress = "[green]done[/]"
    elif t.status == TaskStatus.ERROR:
        progress = "[red]fail[/]"
    else:
        progress = "    "

    elapsed = t.elapsed_str

    # Highlight if selected
    name = t.name
    if self.selected:
        name = f"[bold reverse] {name} [/]"
    else:
        name = f" {name}"

    return f" {status} {name:<20} {progress} {elapsed:>8}"
```

class TaskDetail(Static):
“”“Detail panel showing selected task information.”””

```
task: reactive[Task | None] = reactive(None, recompose=True)

def compose(self) -> ComposeResult:
    if self.task is None:
        yield Static("[dim]Select a task to view details[/]", id="no-selection")
        return

    t = self.task

    # Header with name and status
    yield Static(
        f"[bold]{t.name}[/] {t.status.styled_full}",
        id="detail-header",
    )
    yield Static(f"[dim]{t.description}[/]", id="detail-desc")
    yield Rule(style="dim")

    # Metrics row
    yield Static(
        f"[dim]Phase:[/] {t.phase.value}  │  "
        f"[dim]Elapsed:[/] {t.elapsed_str}  │  "
        f"[dim]Tokens:[/] {t.tokens_used:,}  │  "
        f"[dim]Cost:[/] ${t.estimated_cost:.4f}",
        id="detail-metrics",
    )

    # Progress bar for running tasks
    if t.status == TaskStatus.RUNNING:
        yield ProgressBar(total=100, show_eta=False, id="detail-progress")

    # Activity sparkline
    if t.activity_history:
        yield Static("[dim]Activity:[/]", id="spark-label")
        yield Sparkline(t.activity_history, summary_function=max, id="detail-spark")

    yield Rule(style="dim")

    # Preview of recent output
    yield Static("[dim]Recent output:[/]", id="preview-label")
    preview_text = "\n".join(t.preview_lines)
    yield Static(preview_text, id="detail-preview", markup=True)

def on_mount(self) -> None:
    """Update progress bar if present."""
    self._update_progress()

def watch_task(self, task: Task | None) -> None:
    """React to task changes."""
    self._update_progress()

def _update_progress(self) -> None:
    """Update progress bar value."""
    try:
        if self.task and self.task.status == TaskStatus.RUNNING:
            bar = self.query_one("#detail-progress", ProgressBar)
            bar.update(progress=self.task.progress * 100)
    except Exception:
        pass
```

class LogPanel(RichLog):
“”“Extended RichLog with scroll state tracking.”””

```
auto_scroll: reactive[bool] = reactive(True)
_user_scrolled: bool = False

def on_mount(self) -> None:
    self.border_title = "Output Log"

def write_line(self, content: str) -> None:
    """Write a line and auto-scroll if enabled."""
    self.write(content, expand=True)
    if self.auto_scroll:
        self.scroll_end(animate=False)

def watch_auto_scroll(self, value: bool) -> None:
    """Update border subtitle to show scroll state."""
    if value:
        self.border_subtitle = "[green]LIVE ●[/]"
    else:
        self.border_subtitle = "[yellow]PAUSED ‖[/]"
```

class HelpScreen(ModalScreen):
“”“Modal help screen showing keybindings.”””

```
BINDINGS = [
    Binding("escape", "dismiss", "Close"),
    Binding("?", "dismiss", "Close"),
]

def compose(self) -> ComposeResult:
    yield Container(
        Static("[bold]Maverick Monitor - Keyboard Shortcuts[/]\n", id="help-title"),
        Static(
            """
```

[bold]Navigation[/]
[cyan]j/k[/] or [cyan]↑/↓[/]   Navigate task list
[cyan]Enter[/]        Select task / show detail
[cyan]g[/]            Go to first task
[cyan]G[/]            Go to last task

[bold]Views[/]
[cyan]l[/]            Toggle full-screen log view
[cyan]f[/]            Toggle focus mode (hide task list)
[cyan]s[/]            Toggle auto-scroll in log

[bold]Filtering[/]
[cyan]/[/]            Filter tasks by name
[cyan]Escape[/]       Clear filter

[bold]Log Control[/]
[cyan]1-5[/]          Set verbosity (1=errors only, 5=all)

[bold]General[/]
[cyan]?[/]            Show this help
[cyan]q[/]            Quit
“””,
id=“help-content”,
),
Button(“Close”, variant=“primary”, id=“help-close”),
id=“help-container”,
)

```
@on(Button.Pressed, "#help-close")
def close_help(self) -> None:
    self.dismiss()
```

# =============================================================================

# Main Application

# =============================================================================

class MaverickMonitor(App):
“””
Maverick Monitor Prototype

```
A demonstration of monitoring patterns for long-running AI agent tasks.
"""

CSS = """
/* Layout structure */
#main-container {
    layout: horizontal;
}

#left-panel {
    width: 35;
    min-width: 30;
    border: solid $primary;
    border-title-color: $text;
}

#right-panel {
    width: 1fr;
    layout: vertical;
}

#task-detail {
    height: auto;
    max-height: 14;
    padding: 1;
    border: solid $surface-lighten-1;
    border-title-color: $text;
}

#log-panel {
    height: 1fr;
    border: solid $surface-lighten-1;
    border-title-color: $text;
}

/* Task list styling */
.task-row {
    height: 1;
    padding: 0 1;
}

.task-row:hover {
    background: $surface-lighten-1;
}

.task-row.selected {
    background: $primary 30%;
}

/* Detail panel */
#detail-header {
    text-style: bold;
}

#detail-desc {
    color: $text-muted;
}

#detail-metrics {
    margin-top: 1;
}

#detail-progress {
    margin: 1 0;
}

#detail-spark {
    height: 2;
    margin: 0 0 1 0;
}

#detail-preview {
    padding: 1;
    background: $surface;
    border: round $surface-lighten-2;
}

/* Aggregate stats header */
#stats-bar {
    height: 1;
    background: $surface;
    text-align: center;
    padding: 0 2;
}

/* Help modal */
#help-container {
    width: 60;
    height: auto;
    padding: 2;
    background: $surface;
    border: double $primary;
}

#help-title {
    text-align: center;
    margin-bottom: 1;
}

#help-content {
    margin-bottom: 2;
}

#help-close {
    width: 100%;
}

/* Full-screen log mode */
.fullscreen-log #left-panel {
    display: none;
}

.fullscreen-log #task-detail {
    display: none;
}

.fullscreen-log #log-panel {
    height: 100%;
}

/* Focus mode - hide task list */
.focus-mode #left-panel {
    display: none;
}

/* Status colors for task rows */
.status-running {
    color: $primary;
}

.status-success {
    color: $success;
}

.status-error {
    color: $error;
}

.status-warning {
    color: $warning;
}

/* No selection state */
#no-selection {
    padding: 2;
    text-align: center;
    color: $text-muted;
}
"""

BINDINGS = [
    Binding("q", "quit", "Quit"),
    Binding("?", "help", "Help"),
    Binding("j", "cursor_down", "Down", show=False),
    Binding("k", "cursor_up", "Up", show=False),
    Binding("down", "cursor_down", "Down", show=False),
    Binding("up", "cursor_up", "Up", show=False),
    Binding("enter", "select_task", "Select", show=False),
    Binding("l", "toggle_fullscreen_log", "Full Log"),
    Binding("f", "toggle_focus", "Focus"),
    Binding("s", "toggle_scroll", "Auto-scroll"),
    Binding("g", "goto_first", "First", show=False),
    Binding("G", "goto_last", "Last", show=False),
]

# Reactive state
tasks: reactive[list[Task]] = reactive(list)
selected_index: reactive[int] = reactive(0)
fullscreen_log: reactive[bool] = reactive(False)
focus_mode: reactive[bool] = reactive(False)

def __init__(self):
    super().__init__()
    self.tasks = MockTaskEngine.create_mock_tasks()
    self._streaming_active = True

def compose(self) -> ComposeResult:
    yield Header(show_clock=True)
    yield AggregateStats(id="stats-bar")

    with Container(id="main-container"):
        # Left panel: task list
        with VerticalScroll(id="left-panel"):
            for i, task in enumerate(self.tasks):
                row = TaskRow(task, classes="task-row")
                row.id = f"task-row-{i}"
                if i == 0:
                    row.selected = True
                yield row

        # Right panel: detail + logs
        with Vertical(id="right-panel"):
            yield TaskDetail(id="task-detail")
            yield LogPanel(id="log-panel", highlight=True, markup=True)

    yield Footer()

def on_mount(self) -> None:
    """Initialize the app state."""
    self.query_one("#left-panel").border_title = "Tasks"
    self.query_one("#task-detail").border_title = "Detail"
    self.query_one("#log-panel", LogPanel).border_title = "Output Log"

    # Set initial selection
    self._update_selection()
    self._load_task_log()

    # Update stats
    self.query_one("#stats-bar", AggregateStats).tasks = self.tasks

    # Start streaming simulation
    self._simulate_streaming()

def _update_selection(self) -> None:
    """Update visual selection state."""
    for i, row in enumerate(self.query(".task-row")):
        row.selected = i == self.selected_index

def _load_task_log(self) -> None:
    """Load selected task's log into the log panel."""
    if 0 <= self.selected_index < len(self.tasks):
        task = self.tasks[self.selected_index]
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.clear()
        for line in task.log_lines:
            log_panel.write_line(line)

        # Update detail panel
        detail = self.query_one("#task-detail", TaskDetail)
        detail.task = task

@property
def selected_task(self) -> Task | None:
    """Currently selected task."""
    if 0 <= self.selected_index < len(self.tasks):
        return self.tasks[self.selected_index]
    return None

# -------------------------------------------------------------------------
# Actions
# -------------------------------------------------------------------------

def action_cursor_down(self) -> None:
    """Move selection down."""
    if self.selected_index < len(self.tasks) - 1:
        self.selected_index += 1
        self._update_selection()
        self._load_task_log()

def action_cursor_up(self) -> None:
    """Move selection up."""
    if self.selected_index > 0:
        self.selected_index -= 1
        self._update_selection()
        self._load_task_log()

def action_goto_first(self) -> None:
    """Jump to first task."""
    self.selected_index = 0
    self._update_selection()
    self._load_task_log()

def action_goto_last(self) -> None:
    """Jump to last task."""
    self.selected_index = len(self.tasks) - 1
    self._update_selection()
    self._load_task_log()

def action_select_task(self) -> None:
    """Select current task (refresh detail view)."""
    self._load_task_log()
    # Scroll task into view
    if 0 <= self.selected_index < len(self.tasks):
        row = self.query_one(f"#task-row-{self.selected_index}")
        row.scroll_visible()

def action_toggle_fullscreen_log(self) -> None:
    """Toggle full-screen log view."""
    self.fullscreen_log = not self.fullscreen_log
    container = self.query_one("#main-container")
    container.set_class(self.fullscreen_log, "fullscreen-log")
    mode = "ON" if self.fullscreen_log else "OFF"
    self.notify(f"Full-screen log: {mode}", timeout=1)

def action_toggle_focus(self) -> None:
    """Toggle focus mode (hide task list)."""
    self.focus_mode = not self.focus_mode
    container = self.query_one("#main-container")
    container.set_class(self.focus_mode, "focus-mode")
    mode = "ON" if self.focus_mode else "OFF"
    self.notify(f"Focus mode: {mode}", timeout=1)

def action_toggle_scroll(self) -> None:
    """Toggle auto-scroll in log panel."""
    log_panel = self.query_one("#log-panel", LogPanel)
    log_panel.auto_scroll = not log_panel.auto_scroll
    mode = "ON" if log_panel.auto_scroll else "OFF"
    self.notify(f"Auto-scroll: {mode}", timeout=1)

def action_help(self) -> None:
    """Show help screen."""
    self.push_screen(HelpScreen())

# -------------------------------------------------------------------------
# Streaming Simulation
# -------------------------------------------------------------------------

@work(exclusive=True)
async def _simulate_streaming(self) -> None:
    """
    Simulate streaming output from running tasks.
    In production, this would receive real agent output.
    """
    while self._streaming_active:
        # Find running tasks
        running = [t for t in self.tasks if t.status == TaskStatus.RUNNING]

        for task in running:
            # Randomly generate output
            if random.random() < 0.3:  # 30% chance per tick
                line = MockTaskEngine.generate_output_line()
                task.log_lines.append(line)
                task.tokens_used += random.randint(50, 200)
                task.estimated_cost = task.tokens_used * 0.000003

                # Update activity sparkline
                activity = random.uniform(0.3, 1.0)
                task.activity_history.append(activity)
                if len(task.activity_history) > 20:
                    task.activity_history.pop(0)

                # Progress
                task.progress = min(1.0, task.progress + random.uniform(0.01, 0.03))

                # Phase transitions
                if task.progress > 0.8 and task.phase == TaskPhase.EXECUTING:
                    task.phase = TaskPhase.VERIFYING

                # If this is the selected task, update the log panel
                if task == self.selected_task:
                    log_panel = self.query_one("#log-panel", LogPanel)
                    log_panel.write_line(line)

                    # Update detail panel
                    detail = self.query_one("#task-detail", TaskDetail)
                    detail.task = task

                # Update the task row
                for i, t in enumerate(self.tasks):
                    if t.id == task.id:
                        row = self.query_one(f"#task-row-{i}", TaskRow)
                        row.task = task

        # Update stats
        self.query_one("#stats-bar", AggregateStats).tasks = list(self.tasks)

        await asyncio.sleep(0.5)  # Update every 500ms
```

# =============================================================================

# Entry Point

# =============================================================================

if **name** == “**main**”:
app = MaverickMonitor()
app.run()
