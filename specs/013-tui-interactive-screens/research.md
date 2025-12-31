# Research: TUI Interactive Screens

**Feature**: 013-tui-interactive-screens
**Date**: 2025-12-17

## Decision Summary

| Topic | Decision | Rationale | Alternatives Considered |
|-------|----------|-----------|------------------------|
| Screen navigation | Stack-based with `push_screen`/`pop_screen` | Textual's native pattern; supports back navigation via Escape | Replace-style navigation (loses history) |
| Modal dialogs | `ModalScreen[T]` subclass | Built-in focus trapping and background dimming; typed return values | Custom overlay containers (manual focus management) |
| Form validation | Real-time with `reactive` + `watch_` methods | Instant feedback <200ms; patterns from 012-workflow-widgets | On-submit validation only (poor UX) |
| State management | Frozen dataclasses + reactive attributes | Immutability for screens; reactivity for widgets per constitution | Mutable state objects (violates constitution) |
| Keyboard navigation | `BINDINGS` class attribute + vim-style keys | Power user support; 100% keyboard accessibility requirement | Mouse-only (fails SC-012) |
| Workflow history | JSON file at `~/.config/maverick/history.json` | Simple persistence; spec-mandated location; FIFO eviction at 50 entries | SQLite (over-engineered for 50 entries) |

## Research Findings

### 1. Screen Navigation Patterns

#### Stack-Based Model

Textual uses a screen stack where only one screen is active at a time:

```python
from textual.screen import Screen
from textual.app import App

# Push screen onto stack (new screen becomes active)
self.app.push_screen(FlyScreen())

# Pop screen from stack (previous screen becomes active)
self.app.pop_screen()

# Return to home (pop all except base)
while len(self.screen_stack) > 1:
    self.pop_screen()
```

**Key Lifecycle Methods:**
- `on_mount()`: Screen entered stack, widgets rendered - load data, set focus
- `on_unmount()`: Screen popped from stack - cleanup, save state
- `on_screen_pause()`: Another screen pushed on top - pause operations
- `on_screen_resume()`: Screen returned to top - resume operations

#### Passing Data Between Screens

**Pattern 1: Constructor Parameters (input)**
```python
class WorkflowScreen(Screen):
    def __init__(self, workflow_name: str, branch_name: str, **kwargs):
        super().__init__(**kwargs)
        self._workflow_name = workflow_name
        self._branch_name = branch_name

# Usage
self.app.push_screen(WorkflowScreen(
    workflow_name="Fly",
    branch_name="feature/new-api"
))
```

**Pattern 2: Modal Return Values (output)**
```python
class ConfirmDialog(ModalScreen[bool]):
    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

# Usage with await
result = await self.app.push_screen_wait(ConfirmDialog())
if result:
    # User confirmed
```

### 2. Modal Dialog Implementation

#### ModalScreen for Focus Trapping

`ModalScreen` provides automatic:
- Focus trapping within modal
- Background dimming
- Escape key dismissal
- Return value typing

```python
from textual.screen import ModalScreen
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, Button

class ErrorDialog(ModalScreen[None]):
    """Error modal with dismiss action."""

    DEFAULT_CSS = """
    ErrorDialog {
        align: center middle;
    }

    ErrorDialog > Container {
        width: 60;
        height: auto;
        border: solid $error;
        background: $surface;
    }
    """

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("enter", "dismiss", "Close"),
    ]

    def __init__(self, message: str) -> None:
        super().__init__()
        self.error_message = message

    def compose(self) -> ComposeResult:
        with Container():
            yield Static("[red]Error[/red]", id="title")
            yield Static(self.error_message, id="message")
            yield Button("Dismiss", id="dismiss-btn")

    def on_mount(self) -> None:
        self.query_one("#dismiss-btn", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()
```

#### Confirmation Dialog Pattern

```python
class ConfirmationDialog(ModalScreen[bool]):
    """Yes/No confirmation dialog."""

    BINDINGS = [
        ("y", "confirm", "Yes"),
        ("n", "cancel", "No"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, title: str, message: str) -> None:
        super().__init__()
        self.title_text = title
        self.message_text = message

    def compose(self) -> ComposeResult:
        with Container():
            yield Static(f"[bold]{self.title_text}[/bold]")
            yield Static(self.message_text)
            with Horizontal():
                yield Button("Yes", id="yes-btn", variant="primary")
                yield Button("No", id="no-btn")

    def on_mount(self) -> None:
        self.query_one("#yes-btn", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes-btn")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
```

### 3. Form Handling & Input Validation

#### Real-Time Validation with Reactive Attributes

```python
from textual.widgets import Input, Static
from textual.reactive import reactive
import re

class BranchInput(Static):
    """Branch name input with real-time validation."""

    is_valid: reactive[bool] = reactive(False)
    error_message: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        yield Input(id="branch-input", placeholder="feature/my-feature")
        yield Static("", id="error-display")

    def on_input_changed(self, event: Input.Changed) -> None:
        self._validate(event.value)

    def _validate(self, value: str) -> None:
        if not value.strip():
            self.is_valid = False
            self.error_message = "Branch name cannot be empty"
        elif not re.match(r"^[a-zA-Z0-9._/-]+$", value):
            self.is_valid = False
            self.error_message = "Invalid characters"
        else:
            self.is_valid = True
            self.error_message = ""

    def watch_error_message(self, message: str) -> None:
        self.query_one("#error-display", Static).update(
            f"[red]{message}[/red]" if message else "[green]✓[/green]"
        )
```

#### Form Focus Management

```python
class FormScreen(Screen):
    def on_mount(self) -> None:
        # Focus first field
        self.query_one("#first-input", Input).focus()

        # Set tab order
        self.set_focus_cycle([
            "#branch-input",
            "#file-input",
            "#start-btn",
            "#cancel-btn",
        ])
```

#### Input Widget Features

```python
from textual.widgets import Input
from textual.validation import Validator

class BranchValidator(Validator):
    def validate(self, value: str) -> None:
        if " " in value:
            self.failure_description = "No spaces allowed"
            raise ValidationError(self.failure_description)

input = Input(
    id="branch-input",
    placeholder="Enter branch name",
    restrict=r"^[a-zA-Z0-9/_-]*$",  # Allowed characters
    max_length=255,
    validate_on=["change"],  # Validate on every keystroke
    validators=[BranchValidator()],
)
```

### 4. Reactive State Management

#### Reactive Attributes with Watch Methods

```python
from textual.reactive import reactive
from textual.widget import Widget

class StageIndicator(Widget):
    """Widget with reactive state."""

    status: reactive[str] = reactive("pending")

    ICONS = {
        "pending": "○",
        "active": "◉",
        "completed": "✓",
        "failed": "✗",
    }

    def render(self) -> str:
        """Called automatically when reactive attributes change."""
        return f"{self.ICONS[self.status]} {self.name}"

    def watch_status(self, old: str, new: str) -> None:
        """Called when status changes - side effects here."""
        self.remove_class(old)
        self.add_class(new)
```

#### Computed Properties

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class WorkflowConfig:
    branch_name: str
    parallel: bool = False
    max_agents: int = 3

class ConfigWidget(Static):
    config: reactive[WorkflowConfig] = reactive(WorkflowConfig(branch_name=""))

    @property
    def is_valid(self) -> bool:
        """Computed from reactive state."""
        return bool(self.config.branch_name.strip())

    def validate_config(self, config: WorkflowConfig) -> WorkflowConfig:
        """Validate before setting - raise on error."""
        if not config.branch_name.strip():
            raise ValueError("Branch name required")
        return config
```

### 5. Keyboard Navigation

#### Defining Keybindings

```python
from textual.binding import Binding

class ReviewScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
        Binding("n", "next_issue", "Next", show=True),
        Binding("p", "prev_issue", "Previous", show=True),
        Binding("space", "toggle_selection", "Toggle", show=True),
        Binding("a", "approve", "Approve", show=True),
        Binding("ctrl+f", "search", "Search", priority=True),
    ]

    def action_next_issue(self) -> None:
        self._select_next()

    def action_approve(self) -> None:
        self._approve_review()
```

#### Vim-Style Navigation

```python
class IssueList(Static):
    BINDINGS = [
        ("j", "move_down", "Down"),
        ("k", "move_up", "Up"),
        ("g g", "home", "Start"),  # Double key
        ("shift+g", "end", "End"),
        ("enter", "select", "Select"),
    ]

    selected_index: reactive[int] = reactive(0)

    def action_move_down(self) -> None:
        if self._items:
            self.selected_index = min(
                self.selected_index + 1,
                len(self._items) - 1
            )

    def action_move_up(self) -> None:
        self.selected_index = max(self.selected_index - 1, 0)
```

#### Widget Focus States

```python
class SelectableItem(Static):
    can_focus = True  # Make widget focusable

    def on_focus(self) -> None:
        self.add_class("focused")

    def on_blur(self) -> None:
        self.remove_class("focused")

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            self.post_message(self.Selected(self))
```

### 6. Message Passing

#### Custom Messages

```python
from textual.message import Message

class ReviewFinding(Widget):
    class Approved(Message):
        def __init__(self, finding_id: str) -> None:
            self.finding_id = finding_id
            super().__init__()

    class Dismissed(Message):
        def __init__(self, finding_id: str) -> None:
            self.finding_id = finding_id
            super().__init__()

    def action_approve(self) -> None:
        self.post_message(self.Approved(self.finding_id))


class ReviewScreen(Screen):
    def on_review_finding_approved(self, msg: ReviewFinding.Approved) -> None:
        """Handler follows naming: on_<widget>_<message>"""
        self._handle_approval(msg.finding_id)
```

### 7. Async Operations

#### Workers for Background Tasks

```python
from textual.worker import Worker, work

class RefuelScreen(Screen):
    @work(exclusive=True)
    async def fetch_issues(self, label: str) -> list[dict]:
        """Async GitHub fetch."""
        result = await asyncio.create_subprocess_exec(
            "gh", "issue", "list", "-l", label,
            stdout=asyncio.subprocess.PIPE
        )
        stdout, _ = await result.communicate()
        return self._parse_issues(stdout.decode())

    def action_search(self) -> None:
        self.fetch_issues(self._label)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.is_finished:
            self._display_issues(event.worker.result)
```

### 8. Workflow History Persistence

Per spec clarification, history stored at `~/.config/maverick/history.json`:

```python
from pathlib import Path
import json
from dataclasses import dataclass, asdict
from datetime import datetime

HISTORY_PATH = Path.home() / ".config" / "maverick" / "history.json"
MAX_ENTRIES = 50

@dataclass(frozen=True)
class WorkflowHistoryEntry:
    workflow_type: str  # "fly" | "refuel"
    branch_name: str
    timestamp: str  # ISO format
    final_status: str  # "completed" | "failed"
    stages_completed: list[str]
    finding_counts: dict[str, int]  # {"error": 0, "warning": 0, "suggestion": 0}
    pr_link: str | None = None

def load_history() -> list[WorkflowHistoryEntry]:
    """Load history with FIFO eviction."""
    if not HISTORY_PATH.exists():
        return []
    with open(HISTORY_PATH) as f:
        data = json.load(f)
    return [WorkflowHistoryEntry(**entry) for entry in data[-MAX_ENTRIES:]]

def save_history(entries: list[WorkflowHistoryEntry]) -> None:
    """Save history, enforcing max entries."""
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = [asdict(e) for e in entries[-MAX_ENTRIES:]]
    with open(HISTORY_PATH, "w") as f:
        json.dump(data, f, indent=2)

def add_history_entry(entry: WorkflowHistoryEntry) -> None:
    """Add entry with FIFO eviction."""
    entries = load_history()
    entries.append(entry)
    save_history(entries)
```

## Implementation Recommendations

### Screen Base Class

Create `MaverickScreen` base class for common functionality:

```python
class MaverickScreen(Screen):
    """Base class for all Maverick screens."""

    async def confirm(self, title: str, message: str) -> bool:
        """Show confirmation dialog."""
        return await self.app.push_screen_wait(
            ConfirmationDialog(title, message)
        )

    def show_error(self, message: str) -> None:
        """Show error dialog."""
        self.app.push_screen(ErrorDialog(message))

    def go_back(self) -> None:
        """Navigate back."""
        self.app.pop_screen()
```

### Screen-Specific Patterns

| Screen | Key Pattern | Notes |
|--------|-------------|-------|
| FlyScreen | Form validation + transition | Validate branch, transition to WorkflowScreen |
| RefuelScreen | Async fetch + checkboxes | Worker for GitHub API, SelectableItem for issues |
| ReviewScreen | Message passing | ReviewFinding widgets post Approved/Dismissed messages |
| SettingsScreen | Unsaved changes tracking | Track dirty state, confirm before navigation |
| HomeScreen | History display | Load from JSON, WorkflowList widget |

### Performance Considerations

- Screen transitions: Use `push_screen()` (not `switch_screen()`) to preserve state
- Large lists: Existing widgets handle 200 findings per spec 012
- Input validation: Real-time via `watch_` methods (<200ms per spec)
- Modal display: Native `ModalScreen` (<100ms per spec)
