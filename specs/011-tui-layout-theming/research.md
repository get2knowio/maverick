# Research: Textual TUI Layout and Theming

**Feature**: 011-tui-layout-theming
**Date**: 2025-12-16
**Status**: Complete

## Research Tasks

This document consolidates findings from research into Textual framework patterns, theming best practices, and integration with Maverick's existing architecture.

---

## 1. Textual Application Structure

### Decision: Use Textual's Screen-based Navigation

**Rationale**: Textual's screen stack provides built-in navigation (push/pop) with proper cleanup, modal support, and clear separation between views.

**Alternatives Considered**:
- **Single screen with dynamic content**: Rejected - harder to test, no clear state boundaries
- **Custom view switching**: Rejected - reinvents what Textual provides out of the box

### Implementation Pattern

```python
from textual.app import App, ComposeResult
from textual.screen import Screen

class MaverickApp(App):
    CSS_PATH = "maverick.tcss"
    TITLE = "Maverick"
    ENABLE_COMMAND_PALETTE = True

    def on_mount(self) -> None:
        self.push_screen(HomeScreen())
```

**Key Findings**:
- `CSS_PATH` should be relative to the app.py file
- `ENABLE_COMMAND_PALETTE = True` provides Ctrl+P functionality out of the box
- Default screen (pushed in `on_mount`) establishes initial view
- Screens can define their own `BINDINGS` that override app-level bindings

---

## 2. Screen Management

### Decision: Push/Pop Pattern for Navigation

**Rationale**: Screen stack enables natural "back" navigation with Escape key, maintains state for parent screens, and supports modal dialogs.

**Alternatives Considered**:
- **switch_screen()**: Rejected for main navigation - loses history
- **Modes (MODES dict)**: Rejected - overkill for 4 screens, better for tabbed interfaces

### Navigation Patterns

| Action | Method | Use Case |
|--------|--------|----------|
| Go deeper | `app.push_screen(Screen())` | Home → Workflow |
| Go back | `app.pop_screen()` | Workflow → Home |
| Modal dialog | `app.push_screen(ModalScreen())` | Quit confirmation |
| Replace current | `app.switch_screen(Screen())` | Settings changes |

**Key Findings**:
- Screens have lifecycle methods: `on_mount()`, `on_unmount()`, `compose()`
- `ModalScreen[T]` returns typed results via `dismiss(value)`
- `Screen.BINDINGS` override app bindings when screen is active

---

## 3. Dark Mode Theming

### Decision: Dark Theme by Default with Semantic Colors

**Rationale**: Over 70% of developer tools users prefer dark mode. Semantic color naming enables future light mode support without code changes.

**Alternatives Considered**:
- **Light theme default**: Rejected - user preference data
- **System theme detection**: Rejected - terminals don't reliably report this
- **Hardcoded colors**: Rejected - harder to maintain and customize

### Color Palette

```tcss
/* Background colors - avoid pure black */
$background: #1a1a1a;
$surface: #242424;
$surface-elevated: #2d2d2d;
$border: #3a3a3a;

/* Text colors */
$text: #e0e0e0;
$text-muted: #808080;
$text-dim: #606060;

/* Status colors (WCAG AA contrast compliant) */
$success: #4caf50;
$warning: #ff9800;
$error: #f44336;
$info: #2196f3;

/* Accent for selection/focus */
$accent: #00aaff;
$accent-muted: #0077aa;
```

**Key Findings**:
- Pure black (#000) causes eye strain; use dark gray (#1a1a1a)
- Textual supports `:dark` and `:light` pseudo-selectors for theme variants
- Colors can be defined in TCSS variables and reused
- Status colors should be distinguishable for colorblind users

---

## 4. Layout Architecture

### Decision: Fixed Sidebar + Flexible Main Content

**Rationale**: Workflow stages fit naturally in a fixed-width sidebar; main content needs to adapt to terminal size.

**Alternatives Considered**:
- **Tab-based layout**: Rejected - stages are sequential, not parallel
- **Full-width scrolling**: Rejected - loses stage visibility during workflow
- **Responsive sidebar**: Rejected - stages need consistent width for icons

### Layout Structure

```text
┌──────────────────────────────────────────────────┐
│ Header (dock: top)                                │
├──────────┬───────────────────────────────────────┤
│ Sidebar  │ Main Content Area                     │
│ (30 cols)│ (flexible width)                      │
│          │                                       │
│          │                                       │
├──────────┴───────────────────────────────────────┤
│ Log Panel (dock: bottom, collapsible)            │
├──────────────────────────────────────────────────┤
│ Footer (dock: bottom)                            │
└──────────────────────────────────────────────────┘
```

**Key Findings**:
- Use `dock` property for fixed elements (header, footer, sidebar)
- `1fr` (fractional unit) for flexible content areas
- Log panel uses `display: none/block` for toggle (faster than recompose)
- Minimum terminal size 80×24 allows ~50 cols for main content

---

## 5. Workflow Progress Indicators

### Decision: Unicode Icons with CSS-based Animation

**Rationale**: Unicode icons work across all terminals; CSS animation for spinner avoids complex timer logic in Python.

**Alternatives Considered**:
- **Rich Spinner widget**: Rejected - requires Python timer, more complex
- **ASCII icons**: Rejected - less visually clear
- **Progress bar**: Rejected - doesn't show individual stage status

### Stage Status Icons

| Status | Icon | Color Variable |
|--------|------|----------------|
| Pending | `○` | `$text-muted` |
| Active | `◉` | `$accent` (pulsing) |
| Completed | `✓` | `$success` |
| Failed | `✗` | `$error` |

**Key Findings**:
- Textual's `RichLog` supports Rich markup for colored output
- CSS `text-style: bold` for active stage emphasis
- Spinner animation via CSS `animation` property (if supported) or fallback to static icon
- Stage indicator widgets should be reusable across screens

---

## 6. Collapsible Log Panel

### Decision: RichLog Widget with 1,000 Line Buffer

**Rationale**: RichLog provides syntax highlighting, markup support, and efficient scrolling. Buffer limit prevents memory issues during long workflows.

**Alternatives Considered**:
- **Plain Static widget**: Rejected - no syntax highlighting, no scrolling
- **TextArea**: Rejected - designed for editing, not display
- **Custom widget**: Rejected - RichLog already optimized for this use case

### Implementation Pattern

```python
from textual.widgets import RichLog

class LogPanel(Widget):
    MAX_LINES = 1000
    visible = reactive(False)

    def compose(self) -> ComposeResult:
        yield RichLog(highlight=True, markup=True, max_lines=self.MAX_LINES)

    def add_log(self, message: str, level: str = "info") -> None:
        log = self.query_one(RichLog)
        color = {"info": "blue", "success": "green", "warning": "yellow", "error": "red"}
        log.write(f"[{color.get(level, 'white')}]{message}[/{color.get(level, 'white')}]")
```

**Key Findings**:
- `max_lines` parameter handles buffer automatically
- `highlight=True` enables syntax highlighting for code snippets
- Toggle visibility via CSS class, not widget removal (faster)
- Ctrl+L is common keybinding for log/terminal clear (repurposed for toggle)

---

## 7. Command Palette Integration

### Decision: Use Built-in Command Palette with Custom Providers

**Rationale**: Textual's command palette (Ctrl+P) provides fuzzy search, keyboard navigation, and consistent UX. Custom providers add Maverick-specific commands.

**Alternatives Considered**:
- **Custom search dialog**: Rejected - reinvents existing functionality
- **Menu-based navigation**: Rejected - slower than keyboard-driven palette
- **No command palette**: Rejected - reduces discoverability

### Custom Command Provider

```python
from textual.command import Provider, Hit, DiscoveryHit

class MaverickCommands(Provider):
    async def discover(self) -> Hits:
        yield DiscoveryHit("Start Fly Workflow", self._start_fly)
        yield DiscoveryHit("Start Refuel Workflow", self._start_refuel)
        yield DiscoveryHit("View Recent Workflows", self._show_recent)

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        commands = [("Fly Workflow", self._start_fly), ...]
        for name, action in commands:
            if (score := matcher.match(name)) > 0:
                yield Hit(score, matcher.highlight(name), action)
```

**Key Findings**:
- `discover()` returns commands shown when palette opens (empty query)
- `search()` returns fuzzy-matched commands as user types
- `Hit` score determines ordering; `matcher.highlight()` shows match
- Commands are callable functions or partial applications

---

## 8. Keybinding Strategy

### Decision: Hierarchical Bindings with Screen Override

**Rationale**: App-level bindings for global actions (quit, help, palette); screen-level bindings for context-specific actions.

**App-Level Bindings (MaverickApp)**:
| Key | Action | Description |
|-----|--------|-------------|
| `Ctrl+P` | command_palette | Open command palette |
| `Ctrl+L` | toggle_log | Toggle log panel |
| `Escape` | pop_screen | Go back / cancel |
| `q` | quit | Quit application |
| `?` | show_help | Show keybindings help |

**Screen-Level Bindings (examples)**:
| Screen | Key | Action |
|--------|-----|--------|
| HomeScreen | `Enter` | Select workflow |
| WorkflowScreen | `r` | Retry failed stage |
| ReviewScreen | `n` | Next issue |

**Key Findings**:
- Use `Binding(show=True/False)` to control footer visibility
- `check_action()` method can dynamically enable/disable bindings
- Screen bindings override app bindings for same key
- Tuple shorthand `("key", "action", "description")` for simple bindings

---

## 9. Testing Strategy

### Decision: Pytest + pytest-asyncio + Textual Pilot

**Rationale**: Textual's pilot fixture provides simulated user interaction, works with pytest's async test patterns, and enables snapshot testing.

**Test Categories**:
1. **Unit tests**: Individual widget behavior (stage indicator, log panel)
2. **Screen tests**: Navigation, compose output, keybindings
3. **Integration tests**: Full app scenarios with pilot

### Test Pattern

```python
async def test_toggle_log_panel():
    app = MaverickApp()
    async with app.run_test() as pilot:
        log_panel = app.query_one(LogPanel)
        assert not log_panel.visible

        await pilot.press("ctrl+l")
        await pilot.pause()
        assert log_panel.visible

        await pilot.press("ctrl+l")
        await pilot.pause()
        assert not log_panel.visible
```

**Key Findings**:
- `app.run_test()` context manager handles app lifecycle
- `pilot.press()` simulates keystrokes
- `pilot.pause()` waits for reactive updates
- `pilot.click()` simulates mouse clicks on widgets
- `size=(80, 24)` parameter tests minimum terminal size

---

## 10. Integration with Existing Maverick Code

### Workflow Events Consumption

Maverick workflows (FlyWorkflow, RefuelWorkflow) emit `FlyProgressEvent` events as async generators. The TUI must consume these events to update display.

**Integration Pattern**:
```python
class WorkflowScreen(Screen):
    async def run_workflow(self, workflow: FlyWorkflow, inputs: FlyInputs) -> None:
        async for event in workflow.execute_stream(inputs):
            match event:
                case FlyStageStarted(stage=stage):
                    self.update_stage(stage, "active")
                case FlyStageCompleted(stage=stage):
                    self.update_stage(stage, "completed")
                case FlyWorkflowFailed(error=error):
                    self.show_error(error)
```

**Key Findings**:
- Workflows provide typed event dataclasses
- TUI widgets use reactive attributes for state updates
- Async generator pattern enables real-time progress without polling
- Error events trigger visual feedback without crashing TUI

### Exception Handling

TUI should display errors from `MaverickError` hierarchy without crashing:
- `AgentError`: Show in log panel with context
- `WorkflowError`: Update stage status to failed
- `ConfigError`: Show in settings screen validation

---

## Summary

All research tasks completed. No blocking issues identified.

| Topic | Decision | Confidence |
|-------|----------|------------|
| App structure | Screen-based navigation | High |
| Navigation | Push/pop pattern | High |
| Theming | Dark default, semantic colors | High |
| Layout | Fixed sidebar + flexible main | High |
| Progress | Unicode icons + CSS animation | High |
| Log panel | RichLog with 1k buffer | High |
| Command palette | Built-in with custom providers | High |
| Keybindings | Hierarchical with screen override | High |
| Testing | Pilot fixture + async tests | High |
| Integration | Event stream consumption | High |

**Ready for Phase 1: Data Model and Contracts**
