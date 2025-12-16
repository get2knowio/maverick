# Quickstart: Textual TUI Layout and Theming

**Feature**: 011-tui-layout-theming
**Date**: 2025-12-16
**Estimated Implementation**: 4 screens, ~10 widgets, 1 stylesheet

## Overview

This quickstart guide provides implementers with the essential patterns, code snippets, and conventions for building the Maverick TUI.

---

## 1. Getting Started

### File Structure

Create the following files under `src/maverick/tui/`:

```
tui/
├── __init__.py          # Export MaverickApp
├── app.py               # Main application
├── maverick.tcss        # Stylesheet
├── screens/
│   ├── __init__.py
│   ├── home.py
│   ├── workflow.py
│   ├── review.py
│   └── config.py
└── widgets/
    ├── __init__.py
    ├── sidebar.py
    ├── log_panel.py
    ├── stage_indicator.py
    └── workflow_list.py
```

### Base Imports

Every TUI module should start with:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import ComposeResult
```

---

## 2. Application Shell

### MaverickApp (app.py)

```python
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header

from maverick.tui.screens.home import HomeScreen
from maverick.tui.widgets.log_panel import LogPanel
from maverick.tui.widgets.sidebar import Sidebar


class MaverickApp(App[None]):
    """Maverick TUI application."""

    CSS_PATH = "maverick.tcss"
    TITLE = "Maverick"
    ENABLE_COMMAND_PALETTE = True

    BINDINGS = [
        Binding("ctrl+l", "toggle_log", "Toggle Log", show=True),
        Binding("escape", "pop_screen", "Back", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("?", "show_help", "Help"),
    ]

    def compose(self) -> ComposeResult:
        """Create the app layout."""
        yield Header()
        with Horizontal(id="main-container"):
            yield Sidebar(id="sidebar")
            yield Vertical(id="content-area")
        yield LogPanel(id="log-panel")
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize the app with HomeScreen."""
        await self.push_screen(HomeScreen())

    def action_toggle_log(self) -> None:
        """Toggle log panel visibility."""
        log_panel = self.query_one(LogPanel)
        log_panel.toggle()

    def action_pop_screen(self) -> None:
        """Go back to previous screen."""
        if len(self.screen_stack) > 1:
            self.pop_screen()

    def add_log(self, message: str, level: str = "info", source: str = "") -> None:
        """Add a log entry (convenience method)."""
        log_panel = self.query_one(LogPanel)
        log_panel.add_log(message, level, source)
```

---

## 3. Stylesheet (maverick.tcss)

```tcss
/* === Color Variables === */
$background: #1a1a1a;
$surface: #242424;
$surface-elevated: #2d2d2d;
$border: #3a3a3a;

$text: #e0e0e0;
$text-muted: #808080;
$text-dim: #606060;

$success: #4caf50;
$warning: #ff9800;
$error: #f44336;
$info: #2196f3;

$accent: #00aaff;
$accent-muted: #0077aa;

/* === Base Layout === */
Screen {
    background: $background;
}

Header {
    dock: top;
    height: 3;
    background: $surface;
}

Footer {
    dock: bottom;
    height: 1;
    background: $surface;
}

#sidebar {
    dock: left;
    width: 30;
    border-right: solid $border;
    background: $surface;
}

#content-area {
    width: 1fr;
    height: 100%;
    padding: 1;
}

#main-container {
    height: 100%;
}

/* === Log Panel === */
#log-panel {
    dock: bottom;
    height: 15;
    display: none;
    border-top: solid $border;
    background: $surface-elevated;
}

#log-panel.visible {
    display: block;
}

/* === Status Colors === */
.status-success {
    color: $success;
}

.status-warning {
    color: $warning;
}

.status-error {
    color: $error;
}

.status-info {
    color: $info;
}

/* === Stage Indicators === */
StageIndicator {
    height: 1;
    padding: 0 1;
}

StageIndicator.pending {
    color: $text-muted;
}

StageIndicator.active {
    color: $accent;
    text-style: bold;
}

StageIndicator.completed {
    color: $success;
}

StageIndicator.failed {
    color: $error;
}

/* === Workflow List === */
WorkflowList {
    height: auto;
    max-height: 100%;
}

WorkflowList > .workflow-item {
    height: 2;
    padding: 0 1;
}

WorkflowList > .workflow-item:hover {
    background: $surface-elevated;
}

WorkflowList > .workflow-item.--selected {
    background: $accent-muted;
}

/* === Minimum Size Warning === */
#min-size-warning {
    dock: top;
    height: 100%;
    width: 100%;
    background: $error 50%;
    content-align: center middle;
    display: none;
}

#min-size-warning.visible {
    display: block;
}
```

---

## 4. Screen Patterns

### Base Screen Pattern

```python
from __future__ import annotations

from textual.screen import Screen
from textual.app import ComposeResult
from textual.binding import Binding


class BaseScreen(Screen):
    """Base class for all Maverick screens."""

    # Override in subclasses
    TITLE: str = "Screen"

    def compose(self) -> ComposeResult:
        """Implement in subclasses."""
        raise NotImplementedError


class HomeScreen(BaseScreen):
    """Home screen with workflow selection."""

    TITLE = "Home"

    BINDINGS = [
        Binding("enter", "select_workflow", "Select"),
        Binding("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        from textual.widgets import Static
        from maverick.tui.widgets.workflow_list import WorkflowList

        yield Static("Welcome to Maverick", id="welcome")
        yield Static("Recent Workflows:", id="recent-label")
        yield WorkflowList(id="workflow-list")

    def action_select_workflow(self) -> None:
        """Handle workflow selection."""
        workflow_list = self.query_one(WorkflowList)
        # Navigate to workflow details
        ...
```

---

## 5. Widget Patterns

### StageIndicator Widget

```python
from __future__ import annotations

from textual.widget import Widget
from textual.reactive import reactive


class StageIndicator(Widget):
    """Displays a workflow stage with status icon."""

    DEFAULT_CSS = """
    StageIndicator {
        height: 1;
    }
    """

    ICONS = {
        "pending": "○",
        "active": "◉",
        "completed": "✓",
        "failed": "✗",
    }

    name: reactive[str] = reactive("")
    status: reactive[str] = reactive("pending")

    def __init__(
        self,
        name: str,
        status: str = "pending",
        *,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self.name = name
        self.status = status

    def render(self) -> str:
        """Render the stage indicator."""
        icon = self.ICONS.get(self.status, "○")
        return f"{icon} {self.name}"

    def watch_status(self, old_status: str, new_status: str) -> None:
        """Update CSS class when status changes."""
        self.remove_class(old_status)
        self.add_class(new_status)
```

### LogPanel Widget

```python
from __future__ import annotations

from datetime import datetime
from textual.widget import Widget
from textual.widgets import RichLog
from textual.reactive import reactive
from textual.app import ComposeResult


class LogPanel(Widget):
    """Collapsible log panel for agent output."""

    DEFAULT_CSS = """
    LogPanel {
        height: 15;
    }
    """

    MAX_LINES = 1000

    visible: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        """Create the log panel."""
        yield RichLog(
            highlight=True,
            markup=True,
            max_lines=self.MAX_LINES,
            id="log-content",
        )

    def toggle(self) -> None:
        """Toggle visibility."""
        self.visible = not self.visible

    def watch_visible(self, visible: bool) -> None:
        """Update CSS class on visibility change."""
        self.set_class(visible, "visible")

    def add_log(
        self,
        message: str,
        level: str = "info",
        source: str = "",
    ) -> None:
        """Add a log entry."""
        log = self.query_one(RichLog)
        color = {
            "info": "blue",
            "success": "green",
            "warning": "yellow",
            "error": "red",
        }.get(level, "white")

        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = f"[{source}] " if source else ""
        log.write(f"[dim]{timestamp}[/dim] [{color}]{prefix}{message}[/{color}]")

    def clear(self) -> None:
        """Clear all logs."""
        log = self.query_one(RichLog)
        log.clear()
```

---

## 6. Testing Patterns

### Basic App Test

```python
import pytest
from maverick.tui.app import MaverickApp


async def test_app_launches():
    """Test that the app launches successfully."""
    app = MaverickApp()
    async with app.run_test() as pilot:
        assert app.title == "Maverick"
        # Verify HomeScreen is displayed
        assert "HomeScreen" in str(type(app.screen))


async def test_toggle_log_panel():
    """Test log panel toggle with Ctrl+L."""
    app = MaverickApp()
    async with app.run_test() as pilot:
        log_panel = app.query_one("#log-panel")
        assert not log_panel.has_class("visible")

        await pilot.press("ctrl+l")
        await pilot.pause()
        assert log_panel.has_class("visible")

        await pilot.press("ctrl+l")
        await pilot.pause()
        assert not log_panel.has_class("visible")


async def test_minimum_terminal_size():
    """Test app at minimum terminal size."""
    app = MaverickApp()
    async with app.run_test(size=(80, 24)) as pilot:
        # App should render without errors
        assert app.screen is not None
```

### Widget Test

```python
from maverick.tui.widgets.stage_indicator import StageIndicator


async def test_stage_indicator_status_change():
    """Test stage indicator updates on status change."""
    indicator = StageIndicator("Setup", status="pending")

    assert indicator.status == "pending"
    assert "○" in indicator.render()

    indicator.status = "active"
    assert indicator.status == "active"
    assert "◉" in indicator.render()

    indicator.status = "completed"
    assert "✓" in indicator.render()
```

---

## 7. Integration with Workflows

### Consuming Workflow Events

```python
from maverick.workflows.fly import FlyWorkflow, FlyInputs, FlyProgressEvent
from maverick.workflows.fly import (
    FlyStageStarted,
    FlyStageCompleted,
    FlyWorkflowFailed,
)


class WorkflowScreen(Screen):
    """Workflow progress screen."""

    async def run_workflow(
        self,
        workflow: FlyWorkflow,
        inputs: FlyInputs,
    ) -> None:
        """Execute workflow and update display."""
        try:
            async for event in workflow.execute_stream(inputs):
                await self._handle_event(event)
        except Exception as e:
            self.app.add_log(str(e), level="error", source="workflow")

    async def _handle_event(self, event: FlyProgressEvent) -> None:
        """Handle a workflow progress event."""
        match event:
            case FlyStageStarted(stage=stage):
                self._update_stage(stage.value, "active")
                self.app.add_log(
                    f"Stage started: {stage.value}",
                    level="info",
                    source="workflow",
                )

            case FlyStageCompleted(stage=stage):
                self._update_stage(stage.value, "completed")
                self.app.add_log(
                    f"Stage completed: {stage.value}",
                    level="success",
                    source="workflow",
                )

            case FlyWorkflowFailed(error=error):
                self.app.add_log(
                    f"Workflow failed: {error}",
                    level="error",
                    source="workflow",
                )

    def _update_stage(self, stage_name: str, status: str) -> None:
        """Update a stage indicator."""
        indicators = self.query(StageIndicator)
        for indicator in indicators:
            if indicator.name == stage_name:
                indicator.status = status
                break
```

---

## 8. Key Reminders

### Do

- Use `from __future__ import annotations` in all modules
- Keep business logic out of TUI components
- Use reactive attributes for state that affects display
- Test at 80×24 minimum terminal size
- Use CSS classes for visibility toggling (faster than recompose)

### Don't

- Put workflow logic in screens or widgets
- Use threading (Textual is async-first)
- Use print() for debugging (use logging or app.add_log)
- Create global mutable state
- Hardcode colors (use TCSS variables)

---

## 9. Running the TUI

### Development

```bash
# Run with Textual's dev mode (live CSS reload)
textual run --dev -c python -m maverick.main tui

# Or directly
python -m maverick.main tui
```

### Testing

```bash
# Run all TUI tests
pytest tests/unit/tui/ tests/integration/tui/ -v

# Run with coverage
pytest tests/unit/tui/ --cov=maverick.tui --cov-report=html
```

---

## Summary

This quickstart covers the essential patterns for implementing the Maverick TUI:

1. **Application shell** with MaverickApp class
2. **Stylesheet** with theme colors and layout rules
3. **Screen patterns** for navigation
4. **Widget patterns** for reusable components
5. **Testing patterns** with pilot fixture
6. **Workflow integration** for consuming events

Follow TDD: write tests first, then implement to pass tests.
