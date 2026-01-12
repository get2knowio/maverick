# Research: TUI Real-Time Execution Visibility

**Feature**: 030-tui-execution-visibility
**Date**: 2026-01-12
**Status**: Complete

## Research Questions

### 1. How does the current event system work?

**Decision**: Extend the existing `ProgressEvent` union type in `src/maverick/dsl/events.py` with new event types.

**Rationale**: The current event system uses frozen dataclasses with `@dataclass(frozen=True, slots=True)` that are yielded via async generators from the executor. The TUI consumes these events in `WorkflowExecutionScreen._execute_workflow()`. This pattern is mature and well-tested.

**Findings**:
- Existing events: `StepStarted`, `StepCompleted`, `WorkflowStarted`, `WorkflowCompleted`, `ValidationStarted`, `ValidationCompleted`, `ValidationFailed`, `RollbackStarted`, `RollbackCompleted`, `CheckpointSaved`, `RollbackError`
- All events follow the pattern: frozen dataclass with timestamp field defaulting to `time.time()`
- `ProgressEvent` is a type alias union of all event types
- Events are yielded by executor via `async for event in executor.execute()`

**Alternatives Considered**:
1. **Callback-based system**: Rejected because it would require modifying all executor/handler interfaces and breaks the async generator pattern
2. **Message queue (e.g., asyncio.Queue)**: Rejected because it adds complexity and the generator pattern already handles backpressure naturally

### 2. How do loop steps currently execute?

**Decision**: Modify the loop handler in `src/maverick/dsl/serialization/executor/handlers/loop_step.py` to emit iteration events.

**Rationale**: The loop handler has full access to iteration context (index, total count, item value) but currently doesn't emit any intermediate events. The handler uses two execution modes (`for_each` and `tasks`) but both can be instrumented similarly.

**Findings**:
- `_execute_loop_for_each()` iterates over items with `enumerate()` giving access to index
- `_execute_loop_tasks()` uses `anyio.TaskGroup` for concurrent execution with `max_concurrency`
- Loop handler supports resume via `resume_iteration_index` and `resume_after_nested_step_index`
- Items are available from workflow context expressions like `${{ steps.get_phases.output }}`

**Key Code Location**: `src/maverick/dsl/serialization/executor/handlers/loop_step.py:253`

**Implementation Approach**:
- Emit `LoopIterationStarted` before each iteration begins
- Emit `LoopIterationCompleted` after each iteration completes
- For parallel execution, events may arrive out of order (acceptable per spec edge case)
- Pass events via async generator yield from handler back to executor

### 3. How does Claude Agent SDK streaming work?

**Decision**: Wrap agent execution in handlers to emit streaming events from the existing async message iterator.

**Rationale**: The Claude Agent SDK already provides streaming via `async for message in client.receive_response()` in `MaverickAgent.query()`. The messages are collected but not surfaced to the TUI. We can intercept this stream to emit events.

**Findings**:
- `MaverickAgent.query()` (src/maverick/agents/base.py:321-365) yields `Message` objects
- `GeneratorAgent._query()` (src/maverick/agents/generators/base.py:206-271) also streams
- Message types identified by `type(msg).__name__`: `AssistantMessage`, `ToolCallMessage`, `ResultMessage`
- Text extracted via `extract_text(message)` utility function
- Existing `AgentOutput` widget (784 lines) can display agent messages but isn't connected to executor

**Implementation Approach**:
- In `agent_step.py` handler, wrap agent execution to emit `AgentStreamChunk` events
- Extract text from `AssistantMessage` content blocks
- Include step name and agent name in events for UI display

### 4. What Textual patterns exist for real-time updates?

**Decision**: Follow the `LogPanelState` pattern for streaming buffer management and use Textual's reactive system for UI updates.

**Rationale**: The existing `LogPanelState` implements a FIFO buffer with max entries, auto-scroll, and visibility toggle. This matches the streaming panel requirements exactly.

**Findings**:
- `LogPanelState` (src/maverick/tui/models/widget_state.py): mutable state with `max_entries=1000`, `auto_scroll=True`
- `AgentOutputState` (same file): mutable state with message buffer, 1000 message limit
- Textual `Collapsible` widget provides expand/collapse functionality
- CSS classes `.visible`/`.hidden` for panel visibility with `display: none/block`
- `scroll_to_bottom()` method for auto-scroll behavior

**Performance Considerations**:
- Batch UI updates to prevent flickering (50ms minimum between state changes per spec)
- Use `app.call_later()` or debouncing for rapid event sequences
- Keep widget state mutable for performance (frozen would require full rebuild on each update)

### 5. How should nested loops be handled?

**Decision**: Track loop nesting via parent step reference in events; display up to 3 levels with indentation.

**Rationale**: The spec requires nested loop support (FR-004) with hierarchical indentation. The executor already tracks nested context via `_checkpoint_location.is_nested`. We can leverage this pattern.

**Findings**:
- Loop handler receives `execute_step_fn` callback that can execute nested loops
- `_checkpoint_location` structure tracks `step_name`, `iteration_index`, `nested_step_index`
- No existing parent tracking in events (events are flat)
- Textual Tree widget or nested Collapsible could display hierarchy

**Implementation Approach**:
- Add `parent_step_name: str | None` field to iteration events
- TUI tracks active parent stack to compute nesting level
- Indent iterations based on nesting depth (e.g., 2 spaces per level)
- Collapse deeper than 3 levels per spec edge case

### 6. What iteration states are needed?

**Decision**: Add `IterationStatus` enum with 6 states: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `SKIPPED`, `CANCELLED`.

**Rationale**: The spec FR-003 requires distinct visual indicators for these states. The existing `StageStatus` enum only has 4 states (PENDING, ACTIVE, COMPLETED, FAILED) and lacks SKIPPED/CANCELLED for loop-specific scenarios.

**Findings**:
- Current `StageStatus` (src/maverick/tui/models/enums.py): PENDING, ACTIVE, COMPLETED, FAILED
- SKIPPED needed for: resume from checkpoint (iterations before resume point)
- CANCELLED needed for: user cancellation during loop execution
- Existing status icons: ⊙ (pending), ● (running), ✓ (completed), ✗ (failed)
- Need new icons: ⊘ (skipped), ⊗ (cancelled)

### 7. How should streaming panel relate to existing log panel?

**Decision**: Create a separate collapsible panel for agent streaming, distinct from the existing log panel, allowing both to be visible simultaneously.

**Rationale**: Per spec clarification (Session 2026-01-12), the streaming panel should be separate from the log panel. This allows users to see both structured logs and real-time agent output.

**Findings**:
- Existing `LogPanel` widget displays structured log entries from Python logging
- `AgentOutput` widget exists but is used for post-hoc review, not real-time streaming
- Panel layout uses Textual's dock system (top, bottom, left, right)
- Can use `Horizontal`/`Vertical` containers for side-by-side or stacked panels

**Implementation Approach**:
- New `AgentStreamingPanel` widget in `src/maverick/tui/widgets/agent_streaming_panel.py`
- Position below step list, above log panel (or make position configurable)
- Toggle visibility with keyboard shortcut (e.g., `s` for streaming)
- Default: expanded when workflow starts per spec clarification

## Technology Decisions Summary

| Component | Technology | Justification |
|-----------|------------|---------------|
| Event types | Frozen dataclasses | Matches existing pattern; immutable; type-safe |
| Event flow | Async generators | Existing pattern; natural backpressure; no new infrastructure |
| Streaming buffer | Mutable state with FIFO | Matches LogPanelState; performant for high-frequency updates |
| UI hierarchy | Textual Collapsible + custom indentation | Native expand/collapse; CSS styling support |
| Status enums | StrEnum | Matches existing enums; serializable; human-readable |
| Widget state | Mutable dataclass with slots | Performance for frequent updates; matches existing patterns |

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Event emission overhead | Low | Low | Events are lightweight frozen dataclasses; minimal allocation |
| UI update backpressure | Medium | Medium | Batch updates with 50ms debounce; use `call_later()` |
| Large output history | Low | Medium | 100KB FIFO buffer with oldest truncation |
| Parallel loop event ordering | Medium | Low | Document that events may arrive out of order; display by iteration index |
| SDK streaming compatibility | Low | High | SDK streaming is established; fallback to post-completion display if needed |

## Dependencies Verified

- **Textual 0.40+**: Collapsible widget, reactive system, CSS styling - all available
- **Claude Agent SDK**: Async streaming via `receive_response()` - confirmed working
- **DSL Executor**: Event yielding via async generator - confirmed working
- **Existing widgets**: LogPanelState pattern, AgentOutputState pattern - available to follow

## Open Questions (Resolved)

All questions from Technical Context have been resolved through research:

1. ~~How to emit events from loop handler?~~ → Yield from handler, executor passes through
2. ~~How to capture SDK streaming?~~ → Wrap agent execution, emit events from message stream
3. ~~How to handle nested loops?~~ → Parent reference in events, UI tracks nesting stack
4. ~~What states for iterations?~~ → 6-state enum covering all scenarios
5. ~~Streaming vs log panel?~~ → Separate panels, both can be visible
