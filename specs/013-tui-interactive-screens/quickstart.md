# Quickstart: TUI Interactive Screens

**Feature**: 013-tui-interactive-screens
**Date**: 2025-12-17

## Overview

This guide covers implementing the interactive screens for Maverick's TUI. The screens build upon the layout from spec 011 and widgets from spec 012 to provide a complete workflow execution experience.

## Prerequisites

- Spec 011 (TUI Layout & Theming) implemented
- Spec 012 (Workflow Widgets) implemented
- Python 3.10+ with `from __future__ import annotations`
- Textual 0.40+, Click, Pydantic

## Quick Reference

### Screen Hierarchy

```
MaverickApp
├── HomeScreen (default)
│   ├── FlyScreen → WorkflowScreen → ReviewScreen
│   ├── RefuelScreen → (results summary)
│   └── SettingsScreen
└── Modal Dialogs (overlay any screen)
    ├── ConfirmDialog
    ├── ErrorDialog
    └── InputDialog
```

### Key Files to Create/Modify

```
src/maverick/tui/
├── history.py          # NEW: Workflow history persistence
├── screens/
│   ├── base.py         # NEW: MaverickScreen base class
│   ├── fly.py          # NEW: FlyScreen
│   ├── refuel.py       # NEW: RefuelScreen
│   ├── settings.py     # NEW: SettingsScreen (replaces config.py)
│   ├── home.py         # MODIFY: Add history integration
│   └── review.py       # MODIFY: Add action handlers
└── widgets/
    ├── modal.py        # NEW: Dialog widgets
    ├── form.py         # NEW: Form field widgets
    └── issue_list.py   # NEW: GitHub issue list
```

## Implementation Guide

### Step 1: Create Base Screen Class

Create `src/maverick/tui/screens/base.py`:

```python
"""Base screen class for Maverick TUI."""
from __future__ import annotations

from textual.screen import Screen, ModalScreen
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, Button


class MaverickScreen(Screen):
    """Base class for all Maverick screens.

    Provides common functionality for navigation and modal dialogs.
    """

    async def confirm(self, title: str, message: str) -> bool:
        """Show confirmation dialog and return user choice."""
        from maverick.tui.widgets.modal import ConfirmDialog
        return await self.app.push_screen_wait(
            ConfirmDialog(title=title, message=message)
        )

    def show_error(self, message: str, details: str | None = None) -> None:
        """Show error dialog."""
        from maverick.tui.widgets.modal import ErrorDialog
        self.app.push_screen(ErrorDialog(message=message, details=details))

    def go_back(self) -> None:
        """Navigate to previous screen."""
        self.app.pop_screen()
```

### Step 2: Create Modal Dialogs

Create `src/maverick/tui/widgets/modal.py`:

```python
"""Modal dialog widgets for Maverick TUI."""
from __future__ import annotations

from textual.screen import ModalScreen
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, Button, Input
from textual.binding import Binding


class ConfirmDialog(ModalScreen[bool]):
    """Confirmation dialog with Yes/No buttons."""

    DEFAULT_CSS = """
    ConfirmDialog {
        align: center middle;
    }
    ConfirmDialog > Container {
        width: 60;
        height: auto;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        title: str = "Confirm",
        message: str = "",
        confirm_label: str = "Yes",
        cancel_label: str = "No",
    ) -> None:
        super().__init__()
        self.title_text = title
        self.message_text = message
        self.confirm_label = confirm_label
        self.cancel_label = cancel_label

    def compose(self) -> ComposeResult:
        with Container():
            yield Static(f"[bold]{self.title_text}[/bold]", id="title")
            yield Static(self.message_text, id="message")
            with Horizontal(id="buttons"):
                yield Button(self.confirm_label, id="yes", variant="primary")
                yield Button(self.cancel_label, id="no")

    def on_mount(self) -> None:
        self.query_one("#yes", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class ErrorDialog(ModalScreen[None]):
    """Error dialog with dismiss button."""

    DEFAULT_CSS = """
    ErrorDialog {
        align: center middle;
    }
    ErrorDialog > Container {
        width: 70;
        height: auto;
        border: solid $error;
        background: $surface;
        padding: 1 2;
    }
    ErrorDialog #message {
        color: $error;
        margin: 1 0;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("enter", "dismiss", "Close"),
    ]

    def __init__(self, message: str, details: str | None = None) -> None:
        super().__init__()
        self.error_message = message
        self.error_details = details

    def compose(self) -> ComposeResult:
        with Container():
            yield Static("[bold red]Error[/bold red]", id="title")
            yield Static(self.error_message, id="message")
            if self.error_details:
                yield Static(self.error_details, id="details")
            yield Button("Dismiss", id="dismiss")

    def on_mount(self) -> None:
        self.query_one("#dismiss", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()
```

### Step 3: Create FlyScreen

Create `src/maverick/tui/screens/fly.py`:

```python
"""Fly workflow screen for Maverick TUI."""
from __future__ import annotations

import re
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive
from textual.widgets import Static, Input, Button

from maverick.tui.screens.base import MaverickScreen


class FlyScreen(MaverickScreen):
    """Screen for configuring and starting a Fly workflow."""

    TITLE = "Start Fly Workflow"

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("ctrl+enter", "start", "Start", show=False),
    ]

    # Reactive state
    branch_name: reactive[str] = reactive("")
    branch_error: reactive[str] = reactive("")
    is_valid: reactive[bool] = reactive(False)
    is_starting: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        yield Static("[bold]Start Fly Workflow[/bold]", id="title")
        with Vertical(id="form"):
            yield Static("Branch Name:", classes="label")
            yield Input(id="branch-input", placeholder="feature/my-feature")
            yield Static("", id="branch-error")
            yield Static("Task File (optional):", classes="label")
            yield Input(id="file-input", placeholder="tasks.md")
            with Horizontal(id="buttons"):
                yield Button("Start", id="start-btn", variant="primary")
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#branch-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "branch-input":
            self.branch_name = event.value
            self._validate_branch()

    def _validate_branch(self) -> None:
        name = self.branch_name.strip()
        if not name:
            self.branch_error = "Branch name cannot be empty"
            self.is_valid = False
        elif not re.match(r"^[a-zA-Z0-9._/-]+$", name):
            self.branch_error = "Invalid characters in branch name"
            self.is_valid = False
        else:
            self.branch_error = ""
            self.is_valid = True

    def watch_branch_error(self, error: str) -> None:
        widget = self.query_one("#branch-error", Static)
        if error:
            widget.update(f"[red]{error}[/red]")
        else:
            widget.update("[green]✓ Valid[/green]")

    def watch_is_valid(self, valid: bool) -> None:
        self.query_one("#start-btn", Button).disabled = not valid

    def watch_is_starting(self, starting: bool) -> None:
        btn = self.query_one("#start-btn", Button)
        btn.disabled = starting
        btn.label = "Starting..." if starting else "Start"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start-btn":
            self.action_start()
        elif event.button.id == "cancel-btn":
            self.go_back()

    def action_start(self) -> None:
        if not self.is_valid or self.is_starting:
            return
        self.is_starting = True
        # Transition to WorkflowScreen
        from maverick.tui.screens.workflow import WorkflowScreen
        self.app.push_screen(
            WorkflowScreen(
                workflow_name="Fly",
                branch_name=self.branch_name
            )
        )

    def action_go_back(self) -> None:
        self.go_back()
```

### Step 4: Create History Persistence

Create `src/maverick/tui/history.py`:

```python
"""Workflow history persistence for Maverick TUI."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

HISTORY_PATH = Path.home() / ".config" / "maverick" / "history.json"
MAX_ENTRIES = 50


@dataclass(frozen=True, slots=True)
class WorkflowHistoryEntry:
    """Persisted record of a completed workflow."""
    id: str
    workflow_type: str
    branch_name: str
    timestamp: str
    final_status: str
    stages_completed: tuple[str, ...]
    finding_counts: dict[str, int]
    pr_link: str | None = None

    @classmethod
    def create(
        cls,
        workflow_type: str,
        branch_name: str,
        final_status: str,
        stages_completed: list[str],
        finding_counts: dict[str, int],
        pr_link: str | None = None,
    ) -> "WorkflowHistoryEntry":
        return cls(
            id=str(uuid.uuid4()),
            workflow_type=workflow_type,
            branch_name=branch_name,
            timestamp=datetime.now().isoformat(),
            final_status=final_status,
            stages_completed=tuple(stages_completed),
            finding_counts=finding_counts,
            pr_link=pr_link,
        )


class WorkflowHistoryStore:
    """Persistent storage for workflow history."""

    def __init__(
        self,
        path: Path = HISTORY_PATH,
        max_entries: int = MAX_ENTRIES,
    ) -> None:
        self.path = path
        self.max_entries = max_entries

    def load(self) -> list[WorkflowHistoryEntry]:
        if not self.path.exists():
            return []
        with open(self.path) as f:
            data = json.load(f)
        return [
            WorkflowHistoryEntry(
                id=e["id"],
                workflow_type=e["workflow_type"],
                branch_name=e["branch_name"],
                timestamp=e["timestamp"],
                final_status=e["final_status"],
                stages_completed=tuple(e["stages_completed"]),
                finding_counts=e["finding_counts"],
                pr_link=e.get("pr_link"),
            )
            for e in data
        ]

    def save(self, entries: list[WorkflowHistoryEntry]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        trimmed = entries[-self.max_entries:]
        data = [
            {
                "id": e.id,
                "workflow_type": e.workflow_type,
                "branch_name": e.branch_name,
                "timestamp": e.timestamp,
                "final_status": e.final_status,
                "stages_completed": list(e.stages_completed),
                "finding_counts": e.finding_counts,
                "pr_link": e.pr_link,
            }
            for e in trimmed
        ]
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def add(self, entry: WorkflowHistoryEntry) -> None:
        entries = self.load()
        entries.append(entry)
        self.save(entries)

    def get_recent(self, count: int = 10) -> list[WorkflowHistoryEntry]:
        entries = self.load()
        return list(reversed(entries[-count:]))
```

### Step 5: Testing Pattern

Example test for FlyScreen:

```python
"""Tests for FlyScreen."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maverick.tui.screens.fly import FlyScreen


class TestFlyScreenValidation:
    """Tests for branch name validation."""

    def test_empty_branch_is_invalid(self) -> None:
        screen = FlyScreen()
        screen.branch_name = ""
        screen._validate_branch()
        assert not screen.is_valid
        assert "empty" in screen.branch_error.lower()

    def test_valid_branch_name(self) -> None:
        screen = FlyScreen()
        screen.branch_name = "feature/my-feature"
        screen._validate_branch()
        assert screen.is_valid
        assert screen.branch_error == ""

    def test_branch_with_spaces_is_invalid(self) -> None:
        screen = FlyScreen()
        screen.branch_name = "feature my feature"
        screen._validate_branch()
        assert not screen.is_valid
        assert "invalid" in screen.branch_error.lower()


class TestFlyScreenActions:
    """Tests for FlyScreen actions."""

    def test_start_disabled_when_invalid(self) -> None:
        screen = FlyScreen()
        screen.is_valid = False
        screen.action_start()
        assert not screen.is_starting

    def test_start_transitions_to_workflow_screen(self) -> None:
        screen = FlyScreen()
        screen.branch_name = "feature/test"
        screen.is_valid = True
        mock_app = MagicMock()

        with patch.object(type(screen), "app", new_callable=lambda: property(lambda s: mock_app)):
            screen.action_start()

        mock_app.push_screen.assert_called_once()
```

## Key Patterns

### 1. Reactive State

Use reactive attributes for UI state that auto-updates:

```python
class MyScreen(Screen):
    is_loading: reactive[bool] = reactive(False)

    def watch_is_loading(self, loading: bool) -> None:
        """Called when is_loading changes."""
        self.query_one("#spinner").visible = loading
```

### 2. Modal Dialogs

Always use `ModalScreen[T]` for dialogs:

```python
# Show and wait for result
result = await self.app.push_screen_wait(ConfirmDialog(...))

# Fire and forget
self.app.push_screen(ErrorDialog(...))
```

### 3. Form Validation

Validate on every keystroke for instant feedback:

```python
def on_input_changed(self, event: Input.Changed) -> None:
    self._validate()  # Updates reactive error state
```

### 4. Screen Transitions

Always use stack-based navigation:

```python
# Push new screen
self.app.push_screen(NewScreen())

# Pop current screen
self.app.pop_screen()

# Return to home
while len(self.app.screen_stack) > 1:
    self.app.pop_screen()
```

## Acceptance Criteria Checklist

- [ ] HomeScreen displays workflow history from JSON file
- [ ] FlyScreen validates branch name in real-time (<200ms)
- [ ] FlyScreen transitions to WorkflowScreen on start
- [ ] RefuelScreen fetches and displays GitHub issues
- [ ] RefuelScreen supports issue selection with checkboxes
- [ ] ReviewScreen shows findings grouped by severity
- [ ] ReviewScreen supports Approve, Request Changes, Fix All actions
- [ ] SettingsScreen tracks unsaved changes
- [ ] SettingsScreen prompts before navigation with unsaved changes
- [ ] All screens navigable via keyboard only
- [ ] Modal dialogs trap focus
- [ ] Screen transitions complete <300ms
- [ ] 100% of acceptance scenarios from spec pass
