# Research: Workflow Visualization Widgets

**Feature**: 012-workflow-widgets
**Date**: 2025-12-16
**Status**: Complete

## Research Questions

### 1. Reactive Properties Pattern

**Question**: How to properly use Textual's `reactive` for automatic widget re-rendering?

**Decision**: Use `reactive[T]` class attributes with `watch_` methods for state-driven re-rendering.

**Rationale**: This is the established pattern in the Maverick codebase (see `StageIndicator`, `LogPanel`). Textual's reactive system automatically triggers watch methods when values change, enabling CSS class updates and re-renders.

**Alternatives Considered**:
- Manual `refresh()` calls: More error-prone, requires explicit tracking
- Render-only approach: Doesn't support incremental updates efficiently

**Pattern**:
```python
from textual.reactive import reactive

class MyWidget(Widget):
    status: reactive[str] = reactive("pending")

    def watch_status(self, old_value: str, new_value: str) -> None:
        self.remove_class(old_value)
        self.add_class(new_value)
        # Optional: self.refresh() for content changes
```

---

### 2. Syntax Highlighting in Textual

**Question**: Best approach for syntax highlighting code blocks in AgentOutput?

**Decision**: Use `RichLog` with `highlight=True` and Rich's built-in `Syntax` renderable for code blocks.

**Rationale**: Textual integrates directly with Rich. The `RichLog` widget accepts Rich renderables including `Syntax` objects which provide automatic language detection and highlighting. This matches the existing `LogPanel` pattern using `RichLog`.

**Alternatives Considered**:
- Custom highlighting: Unnecessary complexity; Rich/Pygments handles this
- External libraries: Would add dependencies; Rich is already in the stack

**Pattern**:
```python
from rich.syntax import Syntax
from textual.widgets import RichLog

# In AgentOutput widget:
code_block = Syntax(code_content, language, theme="monokai", line_numbers=False)
rich_log.write(code_block)
```

---

### 3. Collapsible Sections

**Question**: How to implement collapsible/expandable sections for tool calls and stage details?

**Decision**: Use Textual's built-in `Collapsible` widget with context manager composition.

**Rationale**: Textual provides a native `Collapsible` widget that handles expand/collapse state, animations, and keyboard accessibility. It emits `Collapsed` and `Expanded` events for state tracking.

**Alternatives Considered**:
- Custom toggle implementation: Reinventing the wheel; maintenance burden
- CSS-only visibility: Loses keyboard accessibility and event handling

**Pattern**:
```python
from textual.widgets import Collapsible, Label

def compose(self) -> ComposeResult:
    with Collapsible(title="Tool Call: execute_command", collapsed=True):
        yield Label("Arguments: {...}")
        yield Label("Result: {...}")
```

**Key Properties**:
- `collapsed: bool` - Toggle state programmatically
- `collapsed_symbol: str` - Icon when collapsed (default: `'>'`)
- `expanded_symbol: str` - Icon when expanded (default: `'v'`)

---

### 4. Auto-Scroll with Manual Override

**Question**: Pattern for auto-scrolling that pauses when user scrolls up?

**Decision**: Use `RichLog.auto_scroll` property combined with scroll position detection via `scroll_y` and `max_scroll_y` properties.

**Rationale**: `RichLog` has built-in `auto_scroll` (default `True`). When user scrolls, we detect if they're not at the bottom and set `auto_scroll = False`. When they scroll back to bottom, re-enable auto-scroll.

**Alternatives Considered**:
- Event-based tracking: More complex; requires custom scroll event handlers
- Timer-based polling: Inefficient and introduces latency

**Pattern**:
```python
class AgentOutput(ScrollableContainer):
    auto_scroll: reactive[bool] = reactive(True)

    def on_scroll(self) -> None:
        """Detect manual scroll and pause auto-scroll."""
        is_at_bottom = self.scroll_y >= self.max_scroll_y - 1
        self.auto_scroll = is_at_bottom

    def add_message(self, message: AgentMessage) -> None:
        # ... render message ...
        if self.auto_scroll:
            self.scroll_end(animate=False)
```

---

### 5. Search/Filtering in Widgets

**Question**: How to implement search functionality within AgentOutput?

**Decision**: Use action binding for `Ctrl+F` to toggle search overlay, with `Input` widget for search query. Filter/highlight matches using reactive property updates.

**Rationale**: Textual's `BINDINGS` system allows key binding at widget level. The `Input` widget handles text entry. For highlighting, we can re-render with Rich's text highlighting or use CSS classes on matched elements.

**Alternatives Considered**:
- App-level search: Loses widget-specific context
- Browser-style dialog: Not native to terminal UX

**Pattern**:
```python
class AgentOutput(Widget):
    BINDINGS = [
        ("ctrl+f", "toggle_search", "Search"),
    ]

    search_visible: reactive[bool] = reactive(False)
    search_query: reactive[str] = reactive("")

    def action_toggle_search(self) -> None:
        self.search_visible = not self.search_visible
        if self.search_visible:
            self.query_one("#search-input", Input).focus()

    def watch_search_query(self, query: str) -> None:
        self._highlight_matches(query)
```

---

### 6. Bulk Selection Pattern

**Question**: How to implement multi-select with bulk actions for ReviewFindings?

**Decision**: Use `SelectionList` widget for checkbox-style multi-select, or custom list with manual selection state tracking in data model.

**Rationale**: `SelectionList` provides built-in multi-select with checkboxes and the `selected` property returns all selected values. For custom styling, we can use a list of findings with a `selected: bool` field and render checkboxes manually.

**Alternatives Considered**:
- DataTable: Overkill for simple lists; selection API is row-based, not checkbox-based
- Single-select ListView: Requires custom checkbox handling

**Pattern (Custom)**:
```python
@dataclass(frozen=True, slots=True)
class ReviewFindingState:
    finding: ReviewFinding
    selected: bool = False

class ReviewFindings(Widget):
    findings: reactive[tuple[ReviewFindingState, ...]] = reactive(())

    def toggle_selection(self, index: int) -> None:
        updated = list(self.findings)
        old = updated[index]
        updated[index] = ReviewFindingState(old.finding, not old.selected)
        self.findings = tuple(updated)

    @property
    def selected_findings(self) -> list[ReviewFinding]:
        return [f.finding for f in self.findings if f.selected]
```

---

### 7. Browser Opening for PR Links

**Question**: How to open PR URL in default browser from PRSummary?

**Decision**: Use Python's `webbrowser.open()` standard library function.

**Rationale**: Cross-platform, no additional dependencies, works in terminal environments. This is the standard approach for opening URLs from CLI/TUI applications.

**Pattern**:
```python
import webbrowser

def action_open_pr(self) -> None:
    if self.pr_url:
        webbrowser.open(self.pr_url)
```

---

### 8. Existing Patterns in Maverick Codebase

**Findings from codebase exploration**:

| Component | Pattern | Location |
|-----------|---------|----------|
| StageIndicator | Reactive status with watch method | `tui/widgets/stage_indicator.py` |
| LogPanel | RichLog with auto-scroll, buffer limit | `tui/widgets/log_panel.py` |
| WorkflowList | Message-based parent communication | `tui/widgets/workflow_list.py` |
| Sidebar | Mode switching with content rebuild | `tui/widgets/sidebar.py` |
| State models | Frozen dataclasses with slots | `tui/models.py` |
| CSS theming | WCAG AA compliant color variables | `tui/maverick.tcss` |

**Key Patterns to Follow**:
1. Use `@dataclass(frozen=True, slots=True)` for state models
2. Use `reactive[T]` with `watch_` methods for UI state
3. Emit `Message` subclasses for parent widget communication
4. Follow existing CSS class naming conventions (`.--selected`, `.status-*`)
5. Handle loading/empty states explicitly in compose/render methods

---

## Technology Decisions Summary

| Decision | Choice | Confidence |
|----------|--------|------------|
| Reactive data binding | Textual `reactive` with watch methods | High |
| Syntax highlighting | Rich `Syntax` in `RichLog` | High |
| Collapsible sections | Textual `Collapsible` widget | High |
| Auto-scroll | `RichLog.auto_scroll` + scroll position detection | High |
| Search functionality | Action binding + `Input` widget + filtering | Medium |
| Multi-select | Custom selection state in data model | High |
| Browser opening | `webbrowser.open()` | High |
| Widget base | Extend `Widget` or compose `ScrollableContainer` | High |

---

## Dependencies Confirmed

- **textual>=0.40**: Required for Collapsible, RichLog, SelectionList
- **rich**: Included with Textual; used for Syntax highlighting
- **webbrowser**: Standard library; no additional dependency

## Open Questions Resolved

All technical questions have been researched and decisions documented. No NEEDS CLARIFICATION items remain.
