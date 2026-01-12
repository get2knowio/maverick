# Quickstart: TUI Real-Time Execution Visibility

**Feature**: 030-tui-execution-visibility
**Date**: 2026-01-12

## Overview

This guide provides implementation patterns for adding real-time execution visibility to the Maverick TUI. The feature adds loop iteration progress and agent output streaming to the workflow execution screen.

---

## Quick Reference

### New Event Types

```python
# In src/maverick/dsl/events.py

from dataclasses import dataclass, field
import time

@dataclass(frozen=True, slots=True)
class LoopIterationStarted:
    """Emitted when a loop iteration begins."""
    step_name: str
    iteration_index: int
    total_iterations: int
    item_label: str
    parent_step_name: str | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class LoopIterationCompleted:
    """Emitted when a loop iteration completes."""
    step_name: str
    iteration_index: int
    success: bool
    duration_ms: int
    error: str | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class AgentStreamChunk:
    """Emitted when agent produces streaming output."""
    step_name: str
    agent_name: str
    text: str
    chunk_type: str  # "output", "thinking", "error"
    timestamp: float = field(default_factory=time.time)


# Update ProgressEvent union
ProgressEvent = (
    ValidationStarted | ValidationCompleted | ValidationFailed |
    WorkflowStarted | WorkflowCompleted |
    StepStarted | StepCompleted |
    RollbackStarted | RollbackCompleted | RollbackError |
    CheckpointSaved |
    LoopIterationStarted | LoopIterationCompleted |  # NEW
    AgentStreamChunk  # NEW
)
```

### Emitting Loop Iteration Events

```python
# In src/maverick/dsl/serialization/executor/handlers/loop_step.py

async def _execute_loop_for_each(
    self,
    loop_step: LoopStep,
    items: list[Any],
    execute_step_fn: Callable,
    context: WorkflowContext,
    parent_step_name: str | None = None,
) -> AsyncIterator[ProgressEvent]:
    """Execute loop with iteration events."""
    total = len(items)

    for index, item in enumerate(items):
        # Extract label from item
        item_label = _extract_item_label(item, index)

        # Emit iteration started
        yield LoopIterationStarted(
            step_name=loop_step.name,
            iteration_index=index,
            total_iterations=total,
            item_label=item_label,
            parent_step_name=parent_step_name,
        )

        start_time = time.time()
        success = True
        error_msg = None

        try:
            # Execute iteration steps
            for step in loop_step.steps:
                async for event in execute_step_fn(step, item_context):
                    yield event
        except Exception as e:
            success = False
            error_msg = str(e)
            raise
        finally:
            duration_ms = int((time.time() - start_time) * 1000)
            yield LoopIterationCompleted(
                step_name=loop_step.name,
                iteration_index=index,
                success=success,
                duration_ms=duration_ms,
                error=error_msg,
            )


def _extract_item_label(item: Any, index: int) -> str:
    """Extract display label from loop item."""
    if isinstance(item, dict):
        # Try common label keys
        for key in ("label", "name", "title", "phase", "id"):
            if key in item:
                return str(item[key])
    if isinstance(item, str):
        return item
    return f"Item {index + 1}"
```

### Emitting Agent Streaming Events

```python
# In src/maverick/dsl/serialization/executor/handlers/agent_step.py

async def _execute_with_streaming(
    self,
    agent: MaverickAgent,
    prompt: str,
    step_name: str,
    agent_name: str,
) -> AsyncIterator[ProgressEvent | Any]:
    """Execute agent with streaming events."""

    # Emit thinking indicator
    yield AgentStreamChunk(
        step_name=step_name,
        agent_name=agent_name,
        text="",
        chunk_type="thinking",
    )

    try:
        async for message in agent.query(prompt):
            # Extract text from assistant messages
            if type(message).__name__ == "AssistantMessage":
                text = extract_text(message)
                if text:
                    yield AgentStreamChunk(
                        step_name=step_name,
                        agent_name=agent_name,
                        text=text,
                        chunk_type="output",
                    )
            yield message  # Pass through for result collection

    except Exception as e:
        yield AgentStreamChunk(
            step_name=step_name,
            agent_name=agent_name,
            text=str(e),
            chunk_type="error",
        )
        raise
```

### TUI State Models

```python
# In src/maverick/tui/models/enums.py

class IterationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class StreamChunkType(str, Enum):
    OUTPUT = "output"
    THINKING = "thinking"
    ERROR = "error"
```

```python
# In src/maverick/tui/models/widget_state.py

@dataclass(slots=True)
class LoopIterationItem:
    index: int
    total: int
    label: str
    status: IterationStatus
    duration_ms: int | None = None
    error: str | None = None

    @property
    def display_text(self) -> str:
        return f"{self.index + 1}/{self.total}: {self.label}"


@dataclass(slots=True)
class LoopIterationState:
    step_name: str
    iterations: list[LoopIterationItem]
    nesting_level: int = 0
    expanded: bool = True


@dataclass(frozen=True, slots=True)
class AgentStreamEntry:
    timestamp: float
    step_name: str
    agent_name: str
    text: str
    chunk_type: StreamChunkType

    @property
    def size_bytes(self) -> int:
        return len(self.text.encode('utf-8'))


@dataclass(slots=True)
class StreamingPanelState:
    visible: bool = True
    auto_scroll: bool = True
    entries: list[AgentStreamEntry] = field(default_factory=list)
    current_source: str | None = None
    max_size_bytes: int = 100 * 1024
    _current_size_bytes: int = 0

    def add_entry(self, entry: AgentStreamEntry) -> None:
        entry_size = entry.size_bytes
        while (self._current_size_bytes + entry_size > self.max_size_bytes
               and self.entries):
            removed = self.entries.pop(0)
            self._current_size_bytes -= removed.size_bytes
        self.entries.append(entry)
        self._current_size_bytes += entry_size
        self.current_source = f"{entry.step_name} - {entry.agent_name}"
```

### TUI Event Handling

```python
# In src/maverick/tui/screens/workflow_execution.py

class WorkflowExecutionScreen(MaverickScreen):
    # New state tracking
    _loop_states: dict[str, LoopIterationState]
    _streaming_state: StreamingPanelState

    def __init__(self, ...):
        super().__init__(...)
        self._loop_states = {}
        self._streaming_state = StreamingPanelState()

    async def _execute_workflow(self) -> WorkflowResult:
        async for event in executor.execute(self._workflow, self._inputs):
            await self._handle_event(event)
        return result

    async def _handle_event(self, event: ProgressEvent) -> None:
        match event:
            case LoopIterationStarted():
                await self._handle_iteration_started(event)
            case LoopIterationCompleted():
                await self._handle_iteration_completed(event)
            case AgentStreamChunk():
                await self._handle_stream_chunk(event)
            case StepStarted():
                await self._handle_step_started(event)
            case StepCompleted():
                await self._handle_step_completed(event)
            # ... existing handlers

    async def _handle_iteration_started(
        self,
        event: LoopIterationStarted
    ) -> None:
        # Get or create loop state
        if event.step_name not in self._loop_states:
            self._loop_states[event.step_name] = LoopIterationState(
                step_name=event.step_name,
                iterations=[
                    LoopIterationItem(
                        index=i,
                        total=event.total_iterations,
                        label="",
                        status=IterationStatus.PENDING,
                    )
                    for i in range(event.total_iterations)
                ],
                nesting_level=self._compute_nesting(event.parent_step_name),
            )

        # Update iteration to running
        state = self._loop_states[event.step_name]
        item = state.iterations[event.iteration_index]
        item.label = event.item_label
        item.status = IterationStatus.RUNNING

        # Trigger UI update
        self._refresh_iteration_widget(event.step_name)

    async def _handle_iteration_completed(
        self,
        event: LoopIterationCompleted
    ) -> None:
        state = self._loop_states.get(event.step_name)
        if not state:
            return

        item = state.iterations[event.iteration_index]
        item.status = (
            IterationStatus.COMPLETED if event.success
            else IterationStatus.FAILED
        )
        item.duration_ms = event.duration_ms
        item.error = event.error

        self._refresh_iteration_widget(event.step_name)

    async def _handle_stream_chunk(self, event: AgentStreamChunk) -> None:
        entry = AgentStreamEntry(
            timestamp=event.timestamp,
            step_name=event.step_name,
            agent_name=event.agent_name,
            text=event.text,
            chunk_type=StreamChunkType(event.chunk_type),
        )
        self._streaming_state.add_entry(entry)
        self._refresh_streaming_panel()
```

### Iteration Progress Widget

```python
# In src/maverick/tui/widgets/iteration_progress.py

from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Vertical


STATUS_ICONS = {
    IterationStatus.PENDING: "○",
    IterationStatus.RUNNING: "●",
    IterationStatus.COMPLETED: "✓",
    IterationStatus.FAILED: "✗",
    IterationStatus.SKIPPED: "⊘",
    IterationStatus.CANCELLED: "⊗",
}


class IterationProgress(Widget):
    """Widget displaying loop iteration progress."""

    def __init__(self, state: LoopIterationState) -> None:
        super().__init__()
        self._state = state

    def compose(self) -> ComposeResult:
        with Vertical():
            for item in self._state.iterations:
                indent = "  " * self._state.nesting_level
                icon = STATUS_ICONS[item.status]
                duration = f" ({item.duration_ms}ms)" if item.duration_ms else ""
                yield Static(
                    f"{indent}{icon} {item.display_text}{duration}",
                    classes=f"iteration iteration-{item.status.value}",
                )

    def update_state(self, state: LoopIterationState) -> None:
        self._state = state
        self.refresh()
```

### Agent Streaming Panel Widget

```python
# In src/maverick/tui/widgets/agent_streaming_panel.py

from textual.widgets import Static, Collapsible
from textual.containers import ScrollableContainer


class AgentStreamingPanel(Widget):
    """Collapsible panel for real-time agent output."""

    DEFAULT_CSS = """
    AgentStreamingPanel {
        height: auto;
        max-height: 50%;
        border: solid $accent;
    }

    AgentStreamingPanel .header {
        background: $surface;
        padding: 0 1;
    }

    AgentStreamingPanel .content {
        padding: 1;
    }

    AgentStreamingPanel.collapsed .content {
        display: none;
    }
    """

    def __init__(self, state: StreamingPanelState) -> None:
        super().__init__()
        self._state = state

    def compose(self) -> ComposeResult:
        header_text = "Agent Output"
        if self._state.current_source:
            header_text = f"Agent Output: {self._state.current_source}"

        yield Static(header_text, classes="header")
        with ScrollableContainer(classes="content"):
            for entry in self._state.entries:
                yield Static(
                    entry.text,
                    classes=f"chunk chunk-{entry.chunk_type.value}",
                )

    def append_chunk(self, entry: AgentStreamEntry) -> None:
        """Add new chunk and scroll if auto-scroll enabled."""
        self._state.add_entry(entry)

        # Add to content container
        content = self.query_one(".content")
        content.mount(Static(
            entry.text,
            classes=f"chunk chunk-{entry.chunk_type.value}",
        ))

        # Auto-scroll
        if self._state.auto_scroll:
            content.scroll_end()

    def toggle_visibility(self) -> None:
        """Toggle panel expand/collapse."""
        self._state.visible = not self._state.visible
        self.toggle_class("collapsed")
```

---

## CSS Styles

```css
/* In src/maverick/tui/maverick.tcss */

/* Iteration status colors */
.iteration-pending {
    color: $text-muted;
}

.iteration-running {
    color: $accent;
}

.iteration-completed {
    color: $success;
}

.iteration-failed {
    color: $error;
}

.iteration-skipped {
    color: $warning;
}

.iteration-cancelled {
    color: $text-disabled;
}

/* Streaming panel */
AgentStreamingPanel {
    height: auto;
    max-height: 15;
    border: solid $primary;
    margin: 1 0;
}

AgentStreamingPanel .header {
    background: $surface;
    padding: 0 1;
    text-style: bold;
}

AgentStreamingPanel.collapsed {
    height: 3;
}

AgentStreamingPanel.collapsed .content {
    display: none;
}

.chunk-output {
    color: $text;
}

.chunk-thinking {
    color: $text-muted;
    text-style: italic;
}

.chunk-error {
    color: $error;
}
```

---

## Testing Patterns

### Event Tests

```python
# tests/unit/dsl/test_events.py

def test_loop_iteration_started_creation():
    event = LoopIterationStarted(
        step_name="implement_by_phase",
        iteration_index=0,
        total_iterations=3,
        item_label="Phase 1: Setup",
    )
    assert event.iteration_index == 0
    assert event.total_iterations == 3
    assert event.item_label == "Phase 1: Setup"
    assert event.parent_step_name is None
    assert event.timestamp > 0


def test_loop_iteration_completed_with_error():
    event = LoopIterationCompleted(
        step_name="implement_by_phase",
        iteration_index=1,
        success=False,
        duration_ms=5000,
        error="Validation failed",
    )
    assert not event.success
    assert event.error == "Validation failed"
```

### Widget Tests

```python
# tests/unit/tui/test_iteration_progress.py

async def test_iteration_progress_displays_all_iterations():
    state = LoopIterationState(
        step_name="test_loop",
        iterations=[
            LoopIterationItem(0, 3, "Item 1", IterationStatus.COMPLETED),
            LoopIterationItem(1, 3, "Item 2", IterationStatus.RUNNING),
            LoopIterationItem(2, 3, "Item 3", IterationStatus.PENDING),
        ],
    )
    widget = IterationProgress(state)

    async with widget.run_test() as pilot:
        assert "✓ 1/3: Item 1" in widget.query_one(".iteration-completed").renderable
        assert "● 2/3: Item 2" in widget.query_one(".iteration-running").renderable
        assert "○ 3/3: Item 3" in widget.query_one(".iteration-pending").renderable
```

### Streaming Buffer Tests

```python
# tests/unit/tui/test_streaming_panel.py

def test_streaming_panel_fifo_eviction():
    state = StreamingPanelState(max_size_bytes=100)

    # Add entries until over limit
    for i in range(20):
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="TestAgent",
            text="X" * 10,  # 10 bytes each
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry)

    # Should have evicted oldest to stay under 100 bytes
    assert state.total_size_bytes <= 100
    assert len(state.entries) <= 10
```

---

## Performance Considerations

1. **Debounce UI updates**: For rapid iteration completion, batch updates with 50ms minimum interval
2. **Lazy widget rendering**: Only render visible iterations (virtualize if > 50 iterations)
3. **Buffer size tracking**: Track size incrementally, don't recalculate on each add
4. **Frozen events**: Events are immutable, safe to pass between tasks without copying

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `s` | Toggle streaming panel visibility |
| `l` | Toggle log panel visibility |
| `↑`/`↓` | Navigate steps/iterations |
| `Enter` | Expand/collapse step iterations |
| `Esc` | Cancel workflow execution |
