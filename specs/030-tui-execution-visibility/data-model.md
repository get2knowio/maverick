# Data Model: TUI Real-Time Execution Visibility

**Feature**: 030-tui-execution-visibility
**Date**: 2026-01-12
**Status**: Complete

## Entity Overview

This feature introduces 3 new event types and 3 new state models to enable real-time visibility into workflow execution.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EVENT LAYER                                     │
│                         (src/maverick/dsl/events.py)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  LoopIterationStarted    LoopIterationCompleted    AgentStreamChunk         │
│  ├─ step_name            ├─ step_name              ├─ step_name             │
│  ├─ iteration_index      ├─ iteration_index        ├─ agent_name            │
│  ├─ total_iterations     ├─ success                ├─ text                  │
│  ├─ item_label           ├─ duration_ms            ├─ chunk_type            │
│  ├─ parent_step_name     ├─ error                  └─ timestamp             │
│  └─ timestamp            └─ timestamp                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              STATE LAYER                                     │
│                    (src/maverick/tui/models/widget_state.py)                │
├─────────────────────────────────────────────────────────────────────────────┤
│  LoopIterationItem       LoopIterationState        StreamingPanelState      │
│  ├─ index                ├─ step_name              ├─ visible               │
│  ├─ total                ├─ iterations             ├─ auto_scroll           │
│  ├─ label                ├─ nesting_level          ├─ entries               │
│  ├─ status               └─ expanded               ├─ current_source        │
│  ├─ duration_ms                                    └─ max_size_bytes        │
│  └─ error                                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ENUM LAYER                                      │
│                      (src/maverick/tui/models/enums.py)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  IterationStatus                   StreamChunkType                          │
│  ├─ PENDING                        ├─ OUTPUT                                │
│  ├─ RUNNING                        ├─ THINKING                              │
│  ├─ COMPLETED                      └─ ERROR                                 │
│  ├─ FAILED                                                                  │
│  ├─ SKIPPED                                                                 │
│  └─ CANCELLED                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Event Types

### LoopIterationStarted

Emitted when a loop iteration begins execution.

**Location**: `src/maverick/dsl/events.py`

```python
@dataclass(frozen=True, slots=True)
class LoopIterationStarted:
    """Emitted when a loop iteration begins."""

    step_name: str          # Name of the loop step (e.g., "implement_by_phase")
    iteration_index: int    # 0-based index of current iteration
    total_iterations: int   # Total number of iterations in the loop
    item_label: str         # Display label for iteration (e.g., "Phase 1: Core Data")
    parent_step_name: str | None = None  # Parent loop step name for nested loops
    timestamp: float = field(default_factory=time.time)
```

**Validation Rules**:
- `iteration_index` must be >= 0 and < `total_iterations`
- `total_iterations` must be > 0
- `item_label` must be non-empty string
- `step_name` must be non-empty string

**Relationships**:
- Followed by `LoopIterationCompleted` with same `step_name` and `iteration_index`
- May be parent of nested `LoopIterationStarted` events (via `parent_step_name`)

---

### LoopIterationCompleted

Emitted when a loop iteration finishes execution.

**Location**: `src/maverick/dsl/events.py`

```python
@dataclass(frozen=True, slots=True)
class LoopIterationCompleted:
    """Emitted when a loop iteration completes (success or failure)."""

    step_name: str          # Name of the loop step
    iteration_index: int    # 0-based index of completed iteration
    success: bool           # Whether iteration completed successfully
    duration_ms: int        # Execution time in milliseconds
    error: str | None = None  # Error message if failed
    timestamp: float = field(default_factory=time.time)
```

**Validation Rules**:
- `iteration_index` must be >= 0
- `duration_ms` must be >= 0
- If `success` is False, `error` should be non-None

**State Transitions**:
- Triggers iteration status change: RUNNING → COMPLETED (if success) or FAILED (if not success)

---

### AgentStreamChunk

Emitted when agent produces output during execution.

**Location**: `src/maverick/dsl/events.py`

```python
@dataclass(frozen=True, slots=True)
class AgentStreamChunk:
    """Emitted when agent produces streaming output."""

    step_name: str          # Name of the step running the agent
    agent_name: str         # Name/type of the agent (e.g., "ImplementerAgent")
    text: str               # Text content of the chunk
    chunk_type: str         # Type: "output", "thinking", "error"
    timestamp: float = field(default_factory=time.time)
```

**Validation Rules**:
- `chunk_type` must be one of: "output", "thinking", "error"
- `text` may be empty (e.g., for thinking indicator start)
- `step_name` and `agent_name` must be non-empty

**Relationships**:
- Multiple chunks may share same `step_name`/`agent_name` (streaming sequence)
- Chunks are ordered by `timestamp`

---

## State Models

### IterationStatus (Enum)

Status of a single loop iteration.

**Location**: `src/maverick/tui/models/enums.py`

```python
class IterationStatus(str, Enum):
    """Status of a loop iteration."""

    PENDING = "pending"      # Not yet started
    RUNNING = "running"      # Currently executing
    COMPLETED = "completed"  # Finished successfully
    FAILED = "failed"        # Finished with error
    SKIPPED = "skipped"      # Skipped (e.g., resume from checkpoint)
    CANCELLED = "cancelled"  # Cancelled by user
```

**Visual Indicators**:
| Status | Icon | Color Class |
|--------|------|-------------|
| PENDING | ○ | `iteration-pending` |
| RUNNING | ● | `iteration-running` |
| COMPLETED | ✓ | `iteration-completed` |
| FAILED | ✗ | `iteration-failed` |
| SKIPPED | ⊘ | `iteration-skipped` |
| CANCELLED | ⊗ | `iteration-cancelled` |

---

### StreamChunkType (Enum)

Type of agent streaming output.

**Location**: `src/maverick/tui/models/enums.py`

```python
class StreamChunkType(str, Enum):
    """Type of agent streaming chunk."""

    OUTPUT = "output"      # Normal agent output text
    THINKING = "thinking"  # Agent processing indicator
    ERROR = "error"        # Error message from agent
```

---

### LoopIterationItem

Represents a single iteration's display state.

**Location**: `src/maverick/tui/models/widget_state.py`

```python
@dataclass(slots=True)
class LoopIterationItem:
    """Display state for a single loop iteration."""

    index: int                          # 0-based iteration index
    total: int                          # Total iterations in loop
    label: str                          # Display label (e.g., "Phase 1: Setup")
    status: IterationStatus             # Current status
    duration_ms: int | None = None      # Execution time (None if not started)
    error: str | None = None            # Error message if failed
    started_at: float | None = None     # Timestamp when started
    completed_at: float | None = None   # Timestamp when completed
```

**Display Format**: `"{index+1}/{total}: {label}"` (e.g., "Phase 1/3: Core Data Structures")

**State Transitions**:
```
PENDING → RUNNING → COMPLETED
                  → FAILED
        → SKIPPED (on resume)
        → CANCELLED (on cancel)
```

---

### LoopIterationState

Aggregate state for all iterations of a loop step.

**Location**: `src/maverick/tui/models/widget_state.py`

```python
@dataclass(slots=True)
class LoopIterationState:
    """Aggregate state for loop iteration progress display."""

    step_name: str                      # Name of the loop step
    iterations: list[LoopIterationItem] # All iterations
    nesting_level: int = 0              # Depth of nesting (0 = top-level)
    expanded: bool = True               # Whether iterations are visible

    def get_iteration(self, index: int) -> LoopIterationItem | None:
        """Get iteration by index."""
        if 0 <= index < len(self.iterations):
            return self.iterations[index]
        return None

    def update_iteration(self, index: int, **updates) -> None:
        """Update iteration fields."""
        if item := self.get_iteration(index):
            for key, value in updates.items():
                setattr(item, key, value)

    @property
    def current_iteration(self) -> LoopIterationItem | None:
        """Get the currently running iteration."""
        for item in self.iterations:
            if item.status == IterationStatus.RUNNING:
                return item
        return None

    @property
    def progress_fraction(self) -> float:
        """Progress as fraction 0.0-1.0."""
        if not self.iterations:
            return 0.0
        completed = sum(1 for i in self.iterations
                       if i.status in (IterationStatus.COMPLETED,
                                       IterationStatus.FAILED,
                                       IterationStatus.SKIPPED))
        return completed / len(self.iterations)
```

---

### AgentStreamEntry

A single entry in the streaming output buffer.

**Location**: `src/maverick/tui/models/widget_state.py`

```python
@dataclass(frozen=True, slots=True)
class AgentStreamEntry:
    """A single streaming output entry."""

    timestamp: float          # When the chunk was received
    step_name: str            # Source step name
    agent_name: str           # Source agent name
    text: str                 # Text content
    chunk_type: StreamChunkType  # Type of chunk

    @property
    def size_bytes(self) -> int:
        """Approximate size in bytes for buffer management."""
        return len(self.text.encode('utf-8'))
```

---

### StreamingPanelState

State for the agent streaming panel widget.

**Location**: `src/maverick/tui/models/widget_state.py`

```python
@dataclass(slots=True)
class StreamingPanelState:
    """State for the agent streaming panel."""

    visible: bool = True                    # Panel expanded/collapsed
    auto_scroll: bool = True                # Auto-scroll to latest
    entries: list[AgentStreamEntry] = field(default_factory=list)
    current_source: str | None = None       # "{step_name} - {agent_name}"
    max_size_bytes: int = 100 * 1024        # 100KB limit
    _current_size_bytes: int = 0            # Tracked size

    def add_entry(self, entry: AgentStreamEntry) -> None:
        """Add entry, enforcing size limit with FIFO eviction."""
        entry_size = entry.size_bytes

        # Evict oldest entries if needed
        while (self._current_size_bytes + entry_size > self.max_size_bytes
               and self.entries):
            removed = self.entries.pop(0)
            self._current_size_bytes -= removed.size_bytes

        self.entries.append(entry)
        self._current_size_bytes += entry_size
        self.current_source = f"{entry.step_name} - {entry.agent_name}"

    def clear(self) -> None:
        """Clear all entries."""
        self.entries.clear()
        self._current_size_bytes = 0
        self.current_source = None

    @property
    def total_size_bytes(self) -> int:
        """Current buffer size in bytes."""
        return self._current_size_bytes
```

---

## Entity Relationships

```
LoopIterationStarted  ──creates──►  LoopIterationItem (status=RUNNING)
         │                                    │
         │                                    │
         ▼                                    ▼
LoopIterationCompleted ──updates──►  LoopIterationItem (status=COMPLETED/FAILED)
         │
         │
         ▼
   LoopIterationState.iterations[]


AgentStreamChunk  ──creates──►  AgentStreamEntry
                                      │
                                      ▼
                        StreamingPanelState.entries[]
```

---

## Validation Summary

| Entity | Field | Rule |
|--------|-------|------|
| LoopIterationStarted | iteration_index | 0 <= value < total_iterations |
| LoopIterationStarted | total_iterations | > 0 |
| LoopIterationStarted | item_label | Non-empty string |
| LoopIterationCompleted | duration_ms | >= 0 |
| AgentStreamChunk | chunk_type | One of: output, thinking, error |
| StreamingPanelState | entries | Total size <= max_size_bytes |
| LoopIterationItem | status transitions | Must follow valid state machine |

---

## Integration Points

### Event Emission (Executor Layer)

1. **loop_step.py** emits `LoopIterationStarted`/`LoopIterationCompleted`
2. **agent_step.py** emits `AgentStreamChunk`
3. Events yielded through executor async generator

### Event Consumption (TUI Layer)

1. **workflow_execution.py** receives events in `_execute_workflow()`
2. Creates/updates `LoopIterationState` and `StreamingPanelState`
3. Widgets render state reactively

### State Ownership

| State | Owner | Mutability |
|-------|-------|------------|
| LoopIterationState | WorkflowExecutionScreen | Mutable (frequent updates) |
| StreamingPanelState | WorkflowExecutionScreen | Mutable (streaming buffer) |
| Event types | DSL Executor | Immutable (frozen dataclass) |
