---
layout: section
class: text-center
---

# 4. Textual - Terminal User Interfaces

<div class="text-lg text-secondary mt-4">
Modern TUI framework for async-native terminal applications
</div>

<div class="mt-8 flex justify-center gap-6 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-teal"></span>
    <span class="text-muted">11 Slides</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-brass"></span>
    <span class="text-muted">CSS in Terminal</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-coral"></span>
    <span class="text-muted">Reactive UI</span>
  </div>
</div>

<!--
Section 4 covers Textual - the modern TUI framework that powers Maverick's terminal user interface.

We'll cover:
1. What is Textual and why we chose it
2. App architecture and lifecycle
3. Built-in widgets
4. Custom widgets
5. Layouts and containers
6. TCSS styling
7. Reactive attributes
8. Message system
9. Screens and navigation
10. Command palette
11. Maverick TUI tour
-->

---

## layout: two-cols

# 4.1 What is Textual?

<div class="pr-4">

**Textual** is a modern TUI framework for building rich terminal applications

<div v-click class="mt-4">

## Key Features

<div class="space-y-2 text-sm mt-3">

- **Async-Native**: Built on `asyncio` for responsive UIs
- **CSS Styling**: Real CSS syntax for terminal layouts
- **Rich Widgets**: Buttons, inputs, tables, trees, and more
- **Reactive**: Automatic UI updates when state changes
- **Cross-Platform**: Windows, macOS, Linux support

</div>

</div>

<div v-click class="mt-4">

## Why Textual for Maverick?

<div class="text-sm space-y-1 mt-2">

- Matches our async-first architecture
- CSS styling enables rapid UI iteration
- Rich widget ecosystem reduces code
- Built-in testing framework
- Active development and community

</div>

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

## Textual vs Alternatives

<div class="text-sm mt-3">

| Feature | Textual    | curses  | blessed |
| ------- | ---------- | ------- | ------- |
| Async   | ✓ Native   | ✗       | ✗       |
| CSS     | ✓ Full     | ✗       | Partial |
| Widgets | ✓ Rich     | Basic   | Basic   |
| Testing | ✓ Built-in | Manual  | Manual  |
| Typing  | ✓ Complete | Partial | Partial |

</div>

</div>

<div v-click class="mt-6">

## Installation

```bash
# In Maverick's dependencies
pip install textual

# Development mode
pip install textual-dev
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Fun Fact:</strong> Textual can render to web browsers too! Run <code>textual serve</code> to see your TUI in a browser.
</div>

</div>

<!--
Textual is a modern Python framework for building terminal user interfaces. It brings web development concepts like CSS styling and reactive state to the terminal.

**Why We Chose Textual**:
1. **Async-Native**: Textual uses asyncio at its core, matching Maverick's async-first architecture perfectly.
2. **CSS Styling**: We can use real CSS syntax (with some extensions) to style our terminal UI, making it easy to iterate on designs.
3. **Rich Widgets**: Built-in widgets like DataTable, Tree, and RichLog saved us from writing hundreds of lines of code.
4. **Testing**: The Pilot API lets us write automated tests for our TUI just like we test our other code.

Textual was created by Will McGugan, the creator of Rich, and is actively maintained with excellent documentation.
-->

---

## layout: default

# 4.2 App Architecture

<div class="text-secondary text-sm mb-4">
Understanding the core structure of a Textual application
</div>

<div class="grid grid-cols-2 gap-6">

<div>

### The App Class

```python {1-4|6-14|16-22|all}
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer

class MaverickApp(App[None]):
    """Maverick TUI application."""

    CSS_PATH = "maverick.tcss"
    TITLE = "Maverick"
    ENABLE_COMMAND_PALETTE = True

    BINDINGS = [
        Binding("ctrl+l", "toggle_log", "Log"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        """Define the widget tree."""
        yield Header()
        yield Sidebar(id="sidebar")
        yield ContentArea(id="content")
        yield Footer()

    async def on_mount(self) -> None:
        """Called when app is ready."""
        self.push_screen(HomeScreen())
```

</div>

<div>

<div v-click>

### App Lifecycle

<div class="text-sm mt-3 space-y-3">

<div class="flex items-center gap-3">
  <span class="w-8 h-8 rounded-full bg-teal/20 text-teal flex items-center justify-center text-xs font-bold">1</span>
  <div>
    <strong>__init__</strong>
    <div class="text-muted">Initialize app state</div>
  </div>
</div>

<div class="flex items-center gap-3">
  <span class="w-8 h-8 rounded-full bg-teal/20 text-teal flex items-center justify-center text-xs font-bold">2</span>
  <div>
    <strong>compose()</strong>
    <div class="text-muted">Build the widget tree</div>
  </div>
</div>

<div class="flex items-center gap-3">
  <span class="w-8 h-8 rounded-full bg-teal/20 text-teal flex items-center justify-center text-xs font-bold">3</span>
  <div>
    <strong>on_mount()</strong>
    <div class="text-muted">App is rendered, push initial screen</div>
  </div>
</div>

<div class="flex items-center gap-3">
  <span class="w-8 h-8 rounded-full bg-brass/20 text-brass flex items-center justify-center text-xs font-bold">4</span>
  <div>
    <strong>Event Loop</strong>
    <div class="text-muted">Handle messages, keys, mouse events</div>
  </div>
</div>

<div class="flex items-center gap-3">
  <span class="w-8 h-8 rounded-full bg-coral/20 text-coral flex items-center justify-center text-xs font-bold">5</span>
  <div>
    <strong>on_unmount()</strong>
    <div class="text-muted">Cleanup when app exits</div>
  </div>
</div>

</div>

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Key Pattern:</strong> <code>compose()</code> is a generator that <code>yield</code>s widgets. This builds the DOM-like widget tree.
</div>

</div>

</div>

<!--
The App class is the entry point for every Textual application. Let's break down its key components:

**Class Attributes**:
- `CSS_PATH`: Path to the TCSS stylesheet
- `TITLE`: Window/terminal title
- `ENABLE_COMMAND_PALETTE`: Ctrl+P command palette
- `BINDINGS`: Global keyboard shortcuts

**Key Methods**:
1. `compose()`: Generator that yields widgets to build the UI tree. Think of it like React's render or Vue's template.
2. `on_mount()`: Called after the app is fully rendered. Perfect for pushing the initial screen.
3. `action_*`: Methods called by bindings (e.g., `action_quit` for "quit" binding)

**Lifecycle**:
The app initializes, composes widgets, mounts them, then enters the async event loop. When the user quits, unmount handlers run for cleanup.
-->

---

## layout: default

# 4.3 Built-in Widgets

<div class="text-secondary text-sm mb-4">
Textual provides a rich library of pre-built widgets
</div>

<div class="grid grid-cols-3 gap-4">

<div v-click>

### Display Widgets

```python
from textual.widgets import (
    Static,      # Text/markup
    Label,       # Simple text
    Markdown,    # Markdown render
    RichLog,     # Scrolling log
    Pretty,      # Pretty-print objects
    Digits,      # Large digits
)

# Static with Rich markup
yield Static(
    "[bold green]Success![/]"
)

# Auto-scrolling log
yield RichLog(
    highlight=True,
    max_lines=1000
)
```

</div>

<div v-click>

### Input Widgets

```python
from textual.widgets import (
    Button,     # Clickable button
    Input,      # Text input
    TextArea,   # Multi-line input
    Checkbox,   # Boolean toggle
    RadioSet,   # Radio buttons
    Select,     # Dropdown
    Switch,     # Toggle switch
)

# Button with callback
yield Button(
    "Start Workflow",
    variant="primary",
    id="start-btn"
)

# Text input with validation
yield Input(
    placeholder="Branch name",
    validators=[Length(min=1)]
)
```

</div>

<div v-click>

### Data Widgets

```python
from textual.widgets import (
    DataTable,   # Spreadsheet-like
    Tree,        # Hierarchical
    DirectoryTree,  # File browser
    ListView,    # Scrollable list
    OptionList,  # Selectable options
    TabbedContent,  # Tabs
)

# DataTable example
table = DataTable()
table.add_columns("Name", "Status")
table.add_row("lint", "✓ passed")
table.add_row("test", "running...")

# Tree for workflows
tree = Tree("Workflows")
node = tree.root.add("feature")
node.add_leaf("lint")
node.add_leaf("test")
```

</div>

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Maverick Uses:</strong> <code>Static</code> for labels, <code>RichLog</code> for log panel, <code>DataTable</code> for workflow lists, <code>Input</code> for branch names, <code>Button</code> for actions.
</div>

<!--
Textual comes with a comprehensive widget library. Here are the ones most relevant to Maverick:

**Display Widgets**:
- `Static`: Renders Rich markup (like our status messages)
- `RichLog`: Scrolling log with auto-scroll and line limits (our log panel)
- `Markdown`: Render markdown content

**Input Widgets**:
- `Button`: Clickable buttons with variants (primary, warning, error)
- `Input`: Text input with placeholder and validation
- `Select`: Dropdown selection (for workflow selection)

**Data Widgets**:
- `DataTable`: Excel-like table (workflow lists, issue lists)
- `Tree`: Hierarchical data (workflow stages)
- `TabbedContent`: Tabbed panels

The key is that these widgets are fully styled via CSS and emit messages for interaction. We don't need to build these from scratch!
-->

---

## layout: two-cols

# 4.4 Custom Widgets

<div class="pr-4">

Creating reusable widgets for your application

<div v-click class="mt-4">

### Basic Custom Widget

```python
from textual.widget import Widget
from textual.reactive import reactive

class StageIndicator(Widget):
    """Displays a workflow stage status."""

    ICONS = {
        "pending": "○",
        "active": "◉",
        "completed": "✓",
        "failed": "✗",
    }

    # Reactive attribute
    status: reactive[str] = reactive("pending")

    def __init__(self, name: str, **kwargs):
        super().__init__(**kwargs)
        self.name = name

    def render(self) -> str:
        """Return string to display."""
        icon = self.ICONS.get(self.status, "○")
        return f"{icon} {self.name}"
```

</div>

</div>

::right::

<div class="pl-4">

<div v-click class="mt-8">

### Compound Widget

```python
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

class Sidebar(Widget):
    """Sidebar with navigation items."""

    def compose(self) -> ComposeResult:
        """Build child widgets."""
        yield Static("Navigation", classes="title")
        with Vertical(classes="nav-items"):
            yield Static("[H] Home", classes="nav-item")
            yield Static("[W] Workflows")
            yield Static("[S] Settings")
```

</div>

<div v-click class="mt-4">

### When to Use Each

<div class="text-sm space-y-2 mt-2">

| Pattern     | Use When                        |
| ----------- | ------------------------------- |
| `render()`  | Single element, simple output   |
| `compose()` | Multiple children, layouts      |
| Both        | Complex widget with decorations |

</div>

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Pattern:</strong> Simple widgets use <code>render()</code>, compound widgets use <code>compose()</code>.
</div>

</div>

<!--
Custom widgets let you encapsulate reusable UI components. There are two patterns:

**render() Pattern** (StageIndicator):
- Return a string or Rich renderable
- Best for single-element widgets
- The widget IS the content

**compose() Pattern** (Sidebar):
- Yield child widgets
- Best for compound widgets with layout
- The widget CONTAINS other widgets

**Maverick's Custom Widgets**:
- `StageIndicator`: Uses render() - just shows icon + name
- `Sidebar`: Uses compose() - contains navigation items
- `LogPanel`: Uses compose() - wraps RichLog with controls

You can also combine both: compose() for structure, render() for each part.
-->

---

## layout: default

# 4.5 Layouts & Containers

<div class="text-secondary text-sm mb-4">
Arrange widgets with container classes
</div>

<div class="grid grid-cols-2 gap-6">

<div>

### Container Types

```python {1-6|8-17|19-27|all}
from textual.containers import (
    Container,    # Generic container
    Horizontal,   # Left-to-right
    Vertical,     # Top-to-bottom
    Grid,         # CSS Grid layout
)

# Horizontal layout
with Horizontal():
    yield Button("Cancel")
    yield Button("Save", variant="primary")

# Three buttons side-by-side:
# [Cancel] [Save]

# Vertical layout
with Vertical(id="sidebar"):
    yield Static("Navigation")
    yield Static("Home")
    yield Static("Workflows")
    yield Static("Settings")

# Stacked vertically:
# Navigation
# Home
# Workflows
# Settings
```

</div>

<div>

<div v-click>

### Maverick's Layout Structure

```
┌─────────────────────────────────────────┐
│                 Header                  │
├──────────┬──────────────────────────────┤
│          │                              │
│ Sidebar  │       Content Area           │
│  (30)    │         (1fr)                │
│          │                              │
├──────────┴──────────────────────────────┤
│              Log Panel (15)             │
├─────────────────────────────────────────┤
│                 Footer                  │
└─────────────────────────────────────────┘
```

</div>

<div v-click class="mt-4">

### In Code

```python
def compose(self) -> ComposeResult:
    yield Header()
    with Horizontal(id="main-container"):
        yield Sidebar(id="sidebar")
        yield Vertical(id="content-area")
    yield LogPanel(id="log-panel")
    yield Footer()
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Tip:</strong> Use <code>id</code> for CSS targeting and <code>classes</code> for shared styles.
</div>

</div>

</div>

<!--
Containers control how widgets are arranged:

**Horizontal**: Children flow left to right
**Vertical**: Children stack top to bottom
**Grid**: CSS Grid-style layout
**Container**: Generic wrapper for styling

**Maverick's Layout**:
- Header docked to top (height: 3)
- Main container fills middle with Horizontal
  - Sidebar docked left (width: 30)
  - Content area takes remaining space (1fr)
- Log panel docked to bottom (height: 15, toggleable)
- Footer at very bottom (height: 1)

The magic is in the TCSS file where we use `dock` and fractional units to create this responsive layout.
-->

---

## layout: two-cols

# 4.6 TCSS Styling

<div class="pr-4">

Textual CSS - CSS syntax adapted for terminals

<div v-click class="mt-4">

### Color Variables

```css
/* maverick.tcss */
$background: #1a1a1a;
$surface: #242424;
$text: #e0e0e0;
$text-muted: #808080;

$success: #4caf50;
$warning: #ff9800;
$error: #f44336;
$accent: #00aaff;
```

</div>

<div v-click class="mt-4">

### Layout Rules

```css
/* Dock sidebar to left */
#sidebar {
  dock: left;
  width: 30;
  border-right: solid $border;
  background: $surface;
}

/* Content fills remaining space */
#content-area {
  width: 1fr;
  height: 100%;
}
```

</div>

</div>

::right::

<div class="pl-4">

<div v-click class="mt-8">

### Status Classes

```css
/* Stage indicator states */
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
```

</div>

<div v-click class="mt-4">

### TCSS vs CSS Differences

<div class="text-sm mt-2">

| CSS               | TCSS                           |
| ----------------- | ------------------------------ |
| `px`, `em`, `rem` | Numbers (cells), `%`, `fr`     |
| `display: flex`   | `Horizontal`/`Vertical`        |
| `position: fixed` | `dock: top/bottom/left/right`  |
| `font-size`       | Not supported (terminal cells) |

</div>

</div>

<div v-click class="mt-4 p-3 bg-coral/10 border border-coral/30 rounded-lg text-sm">
  <strong class="text-coral">WCAG:</strong> Maverick's colors maintain AA contrast ratios for accessibility.
</div>

</div>

<!--
TCSS (Textual CSS) uses familiar CSS syntax but adapted for terminal constraints:

**What's the Same**:
- Selectors: `#id`, `.class`, `WidgetType`
- Variables: `$name: value`
- Properties: `background`, `color`, `border`, `padding`
- Pseudo-classes: `:hover`, `:focus`, `.--selected`

**What's Different**:
- Units are terminal cells, not pixels
- `dock` instead of `position: absolute`
- Fractional units (`1fr`) for flexible sizing
- No font styling (terminals use monospace)
- Colors support hex, RGB, and named colors

**Maverick's Theme**:
We define color variables at the top of `maverick.tcss` for consistency. Status colors (success, warning, error) are carefully chosen for:
1. Visual distinctiveness
2. WCAG AA contrast compliance
3. Colorblind accessibility
-->

---

## layout: default

# 4.7 Reactive Attributes

<div class="text-secondary text-sm mb-4">
Automatic UI updates when state changes
</div>

<div class="grid grid-cols-2 gap-6">

<div>

### Defining Reactive Attributes

```python {1-5|7-18|20-27|all}
from textual.reactive import reactive
from textual.widget import Widget

class StageIndicator(Widget):
    """Widget with reactive state."""

    # Declare reactive attributes
    status: reactive[str] = reactive("pending")
    progress: reactive[int] = reactive(0)

    ICONS = {
        "pending": "○",
        "active": "◉",
        "completed": "✓",
        "failed": "✗",
    }

    def render(self) -> str:
        """Auto-called when reactives change."""
        icon = self.ICONS[self.status]
        return f"{icon} {self.name}"

    def watch_status(
        self, old: str, new: str
    ) -> None:
        """Side effects on status change."""
        self.remove_class(old)
        self.add_class(new)
```

</div>

<div>

<div v-click>

### How It Works

<div class="space-y-4 mt-4">

<div class="flex items-start gap-3">
  <span class="text-teal text-lg">1</span>
  <div>
    <strong>Declare with <code>reactive()</code></strong>
    <div class="text-sm text-muted">Creates a descriptor that tracks changes</div>
  </div>
</div>

<div class="flex items-start gap-3">
  <span class="text-teal text-lg">2</span>
  <div>
    <strong>Update normally</strong>
    <div class="text-sm text-muted"><code>widget.status = "active"</code></div>
  </div>
</div>

<div class="flex items-start gap-3">
  <span class="text-teal text-lg">3</span>
  <div>
    <strong>Textual detects change</strong>
    <div class="text-sm text-muted">Schedules re-render automatically</div>
  </div>
</div>

<div class="flex items-start gap-3">
  <span class="text-teal text-lg">4</span>
  <div>
    <strong><code>watch_*</code> methods run</strong>
    <div class="text-sm text-muted">Handle side effects (CSS classes, etc.)</div>
  </div>
</div>

</div>

</div>

<div v-click class="mt-6">

### Usage in Maverick

```python
# Workflow updates stage status
indicator.status = "completed"
# → render() re-runs automatically
# → watch_status() updates CSS class
# → UI shows ✓ in green
```

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Pattern:</strong> Use <code>reactive()</code> for state that should trigger UI updates. Use regular attributes for static data.
</div>

</div>

</div>

<!--
Reactive attributes are Textual's answer to state management. When a reactive attribute changes, Textual automatically:

1. **Re-renders**: Calls `render()` or updates `compose()` output
2. **Runs Watchers**: Calls `watch_<name>(old, new)` for side effects

**In StageIndicator**:
- `status` is reactive - when it changes from "pending" to "completed":
  1. `render()` re-runs, returning "✓ {name}" instead of "○ {name}"
  2. `watch_status()` runs, updating CSS classes

**Best Practices**:
- Use reactive for UI-relevant state only
- Use watch methods for side effects (CSS classes, messages)
- Don't put heavy computation in render() - it runs frequently

This pattern keeps Maverick's TUI responsive - workflow events update reactive state, and the UI automatically reflects changes.
-->

---

## layout: two-cols

# 4.8 Message System

<div class="pr-4">

Communication between widgets via messages

<div v-click class="mt-4">

### Define Custom Messages

```python
from textual.message import Message
from textual.widget import Widget

class Sidebar(Widget):
    """Sidebar with navigation."""

    class NavigationSelected(Message):
        """User selected a nav item."""

        def __init__(
            self,
            item_id: str,
            sender: Widget
        ) -> None:
            self.item_id = item_id
            super().__init__()

    def on_click(self, event) -> None:
        """Handle click on nav item."""
        self.post_message(
            self.NavigationSelected(
                item_id="home",
                sender=self
            )
        )
```

</div>

</div>

::right::

<div class="pl-4">

<div v-click class="mt-8">

### Handle Messages

```python
class MaverickApp(App):
    """Main application."""

    def on_sidebar_navigation_selected(
        self,
        message: Sidebar.NavigationSelected
    ) -> None:
        """Handle navigation selection."""
        match message.item_id:
            case "home":
                self.push_screen(HomeScreen())
            case "workflows":
                self.push_screen(WorkflowScreen())
            case "settings":
                self.push_screen(ConfigScreen())
```

</div>

<div v-click class="mt-4">

### Message Flow

```
[Sidebar] ──post_message()──▶ [MaverickApp]
                                   │
                    on_sidebar_navigation_selected()
                                   │
                                   ▼
                          push_screen(HomeScreen)
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Naming:</strong> Handler is <code>on_&lt;widget&gt;_&lt;message_name&gt;</code> in snake_case.
</div>

</div>

<!--
Messages are how widgets communicate in Textual. It's an event-driven pattern similar to DOM events.

**Defining Messages**:
- Subclass `Message` inside your widget
- Add any data fields you need
- Call `super().__init__()` at the end

**Posting Messages**:
- `self.post_message(MyMessage(...))` sends it up the tree
- Messages bubble from child → parent → app

**Handling Messages**:
- Handler name: `on_<widget_class>_<message_class>` in snake_case
- Receives the message object with all its data
- Can call `message.stop()` to prevent further bubbling

**In Maverick**:
- Sidebar posts `NavigationSelected` when user clicks
- App receives it and pushes the appropriate screen
- LogPanel posts messages when log level changes
- Widgets stay decoupled - they just emit messages
-->

---

## layout: default

# 4.9 Screens & Navigation

<div class="text-secondary text-sm mb-4">
Managing multiple views with screens
</div>

<div class="grid grid-cols-2 gap-6">

<div>

### Defining Screens

```python {1-8|10-22|24-32}
from textual.screen import Screen
from textual.app import ComposeResult
from textual.binding import Binding

class HomeScreen(Screen[None]):
    """Home screen with workflow list."""

    TITLE = "Home"

    BINDINGS = [
        Binding("enter", "select", "Select"),
        Binding("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Static("Welcome to Maverick")
        yield WorkflowList(id="workflow-list")

    def action_select(self) -> None:
        """Handle enter key."""
        workflow = self.get_selected_workflow()
        self.app.push_screen(
            WorkflowScreen(workflow)
        )

class WorkflowScreen(Screen[None]):
    """Active workflow progress."""

    def __init__(self, workflow: str) -> None:
        super().__init__()
        self.workflow = workflow
```

</div>

<div>

<div v-click>

### Screen Navigation

```python
# Push a new screen (adds to stack)
self.app.push_screen(WorkflowScreen())

# Pop current screen (go back)
self.app.pop_screen()

# Switch screen (replace current)
self.app.switch_screen(HomeScreen())

# Install screen for later use
app.install_screen(HomeScreen(), name="home")
app.push_screen("home")
```

</div>

<div v-click class="mt-4">

### Maverick's Screen Stack

```
┌─────────────────────────────┐
│     ReviewScreen            │  ← top (current)
├─────────────────────────────┤
│     WorkflowScreen          │
├─────────────────────────────┤
│     HomeScreen              │
├─────────────────────────────┤
│     DashboardScreen         │  ← base
└─────────────────────────────┘
```

</div>

<div v-click class="mt-4">

### Modal Screens

```python
class ConfirmDialog(ModalScreen[bool]):
    """Modal for confirmation."""

    def compose(self) -> ComposeResult:
        yield Static("Are you sure?")
        yield Button("Yes", id="yes")
        yield Button("No", id="no")

    def on_button_pressed(self, event):
        self.dismiss(event.button.id == "yes")

# Usage: result = await app.push_screen_wait(ConfirmDialog())
```

</div>

</div>

</div>

<!--
Screens are full-page views that can be stacked and navigated:

**Screen Stack**:
- `push_screen()`: Add screen on top of stack
- `pop_screen()`: Remove current screen, reveal previous
- `switch_screen()`: Replace current screen (same stack depth)

**Maverick's Screens**:
1. `DashboardScreen`: Base screen with workflow list
2. `WorkflowScreen`: Shows active workflow progress
3. `ReviewScreen`: Code review results
4. `ConfigScreen`: Settings editor

**Screen Types**:
- `Screen[None]`: Regular screen with no return value
- `Screen[T]`: Screen that returns a value when dismissed
- `ModalScreen[T]`: Overlays current screen, returns value

**Navigation Pattern**:
- Escape key typically pops screen (configured in BINDINGS)
- Screens can have their own BINDINGS that override app bindings
- Use `push_screen_wait()` for modal dialogs that need a result
-->

---

## layout: two-cols

# 4.10 Command Palette

<div class="pr-4">

Keyboard-driven command discovery with Ctrl+P

<div v-click class="mt-4">

### Defining a Provider

```python
from textual.command import Provider, Hit, Hits

class MaverickCommands(Provider):
    """Command palette provider."""

    async def search(
        self, query: str
    ) -> Hits:
        """Search for commands."""
        commands = [
            ("Go to Home", "Navigate home",
             self.app.action_go_home),
            ("Toggle Log", "Show/hide log",
             self.app.action_toggle_log),
            ("Start Workflow", "Begin workflow",
             self.app.action_start_workflow),
            ("Show Help", "Display help",
             self.app.action_show_help),
        ]

        query_lower = query.lower()
        for name, desc, callback in commands:
            if query_lower in name.lower():
                yield Hit(
                    score=1,
                    match_display=name,
                    command=callback,
                    help=desc,
                )
```

</div>

</div>

::right::

<div class="pl-4">

<div v-click class="mt-8">

### Register Provider

```python
class MaverickApp(App):
    ENABLE_COMMAND_PALETTE = True
    COMMANDS = {MaverickCommands}

    # Commands call action_* methods
    def action_go_home(self) -> None:
        self.push_screen(HomeScreen())

    def action_toggle_log(self) -> None:
        log_panel = self.query_one(LogPanel)
        log_panel.toggle()

    def action_start_workflow(self) -> None:
        # Show workflow picker...
        pass
```

</div>

<div v-click class="mt-4">

### User Experience

```
┌─────────────────────────────────────┐
│ 🔍 start                            │
├─────────────────────────────────────┤
│ ▶ Start Workflow                    │
│   Begin workflow                    │
│                                     │
│   Toggle Log                        │
│   Show/hide log                     │
└─────────────────────────────────────┘
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Tip:</strong> The command palette is a core Textual feature. Just enable it and add providers for a VS Code-like experience.
</div>

</div>

<!--
The command palette provides VS Code-like command discovery:

**How It Works**:
1. User presses Ctrl+P (or configured key)
2. Textual shows the command palette
3. User types to filter commands
4. Providers' `search()` methods yield matching `Hit` objects
5. User selects a command
6. The callback runs

**Provider Pattern**:
- Subclass `Provider`
- Implement `async def search(self, query: str) -> Hits`
- Yield `Hit` objects with score, display text, and callback
- Access `self.app` for context

**In Maverick**:
We register `MaverickCommands` which searches our available actions:
- Navigation commands (Home, Workflows, Settings)
- Action commands (Start Workflow, Toggle Log)
- Help commands (Show Help, Keybindings)

This gives users a discoverable interface without memorizing all keybindings.
-->

---

## layout: default

# 4.11 Maverick TUI Tour

<div class="text-secondary text-sm mb-4">
How Textual concepts come together in Maverick
</div>

<div class="grid grid-cols-2 gap-6">

<div>

### Architecture Overview

```
MaverickApp
├── Header (Textual built-in)
├── Horizontal #main-container
│   ├── Sidebar (custom widget)
│   │   ├── Static "Navigation"
│   │   └── nav-items (StageIndicator[])
│   └── Vertical #content-area
│       └── [Current Screen Content]
├── LogPanel (custom widget)
│   └── RichLog (Textual built-in)
└── ShortcutFooter (custom widget)
```

<div v-click class="mt-4">

### Key Files

<div class="text-sm space-y-2">

| File                | Purpose                           |
| ------------------- | --------------------------------- |
| `tui/app.py`        | MaverickApp, command palette      |
| `tui/maverick.tcss` | All styles (~2000 lines)          |
| `tui/screens/`      | HomeScreen, WorkflowScreen, etc.  |
| `tui/widgets/`      | Sidebar, LogPanel, StageIndicator |
| `tui/models.py`     | Data models, enums, theme colors  |

</div>

</div>

</div>

<div>

<div v-click>

### Live Layout

```
┌───────────────────────────────────────────────┐
│ Maverick                                      │
├────────────┬──────────────────────────────────┤
│ Navigation │  Welcome to Maverick             │
│            │                                  │
│ [H] Home   │  Recent Workflows:               │
│ [W] Flows  │  ┌────────────────────────────┐  │
│ [S] Config │  │ feature-123    2min ago    │  │
│            │  │ bugfix-456     1hr ago     │  │
│ ─────────  │  │ refactor       yesterday   │  │
│ Stages:    │  └────────────────────────────┘  │
│ ○ lint     │                                  │
│ ○ test     │                                  │
│ ○ commit   │                                  │
├────────────┴──────────────────────────────────┤
│ [INFO] Ready to start workflow                │
├───────────────────────────────────────────────┤
│ [Ctrl+L] Log  [Escape] Back  [?] Help  [Q] Quit│
└───────────────────────────────────────────────┘
```

</div>

<div v-click class="mt-4">

### Running the TUI

<Terminal :commands="[
  { command: 'maverick tui', output: '# Opens the TUI' },
  { command: 'textual run --dev maverick.tui.app:MaverickApp', output: '# Dev mode with CSS hot-reload' }
]" />

</div>

</div>

</div>

<!--
Let's see how all the Textual concepts come together in Maverick:

**Widget Tree**:
- MaverickApp at the root
- Header and Footer from Textual
- Custom Sidebar with navigation and stage indicators
- Content area holds the current screen
- Collapsible LogPanel at bottom

**Key Design Decisions**:
1. **Streaming-first**: Log panel uses RichLog for continuous output
2. **Reactive state**: StageIndicator updates automatically from workflow events
3. **Message-driven**: Sidebar navigation uses messages, not callbacks
4. **CSS-based**: All styling in maverick.tcss, no inline styles

**Running Maverick TUI**:
- `maverick tui` - Production mode
- `textual run --dev` - Development mode with CSS hot-reload

The TUI is display-only per our architecture - it consumes workflow events and updates the UI, but doesn't execute business logic itself.
-->
