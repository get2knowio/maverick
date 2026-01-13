# Implementation Plan: TUI Real-Time Execution Visibility

**Branch**: `030-tui-execution-visibility` | **Date**: 2026-01-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/030-tui-execution-visibility/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Add real-time visibility into workflow execution by:
1. **Loop iteration progress** (P1): Expand loop steps in the UI to show each iteration with progress indicator "Phase 1/3: Core Data Structures" and distinct status icons
2. **Agent output streaming** (P2): Add a collapsible streaming panel that displays agent output in real-time as it's generated during workflow execution
3. **Debug history** (P3): Preserve agent output history for the session to enable post-failure debugging

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Textual 0.40+, Claude Agent SDK (`claude-agent-sdk`), Click, Pydantic, PyYAML
**Storage**: N/A (in-memory state during workflow execution; streaming buffer with 100KB FIFO limit)
**Testing**: pytest + pytest-asyncio (all tests async-compatible)
**Target Platform**: Linux/macOS CLI (any terminal supporting ANSI escape codes)
**Project Type**: Single Python package (src/maverick/)
**Performance Goals**:
- UI update latency: <100ms from event emission to visual update (SC-001, SC-002)
- No UI freezes while streaming at 100 chars/sec (SC-003)
- Responsive scrolling for 100KB of agent output history (SC-007)
**Constraints**:
- Minimum 50ms between visual state changes to prevent flickering
- Maximum 3 levels of nested loop indentation displayed
- 100KB agent output history buffer (FIFO truncation)
**Scale/Scope**:
- Support workflows with up to 100 iterations per loop
- Handle agent output at 100 chars/second
- Display up to 3 levels of nested loop hierarchy

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Requirement | Status | Notes |
|-----------|-------------|--------|-------|
| **I. Async-First** | All event handling must be async; no blocking on event loop | ✅ PASS | TUI uses workers; events flow via async generators |
| **II. Separation of Concerns** | TUI is display-only; no subprocess/network calls | ✅ PASS | TUI receives events, updates state, renders; executor emits events |
| **III. Dependency Injection** | Events/state injected, not global | ✅ PASS | WorkflowExecutionScreen receives executor; state passed via events |
| **IV. Fail Gracefully** | Partial streaming should display even on errors | ✅ PASS | Design includes interrupted/cancelled iteration states |
| **V. Test-First** | All new events, widgets, handlers must have tests | ⏳ REQUIRED | Tests will cover event types, widget states, screen handlers |
| **VI. Type Safety** | New events must be frozen dataclasses with typed fields | ✅ PASS | LoopIterationProgress, AgentStreamEntry are typed dataclasses |
| **VII. Simplicity/DRY** | Reuse existing LogPanelState pattern for streaming buffer | ✅ PASS | StreamingPanelState follows same pattern |
| **X. Architectural Guardrails** | TUI display-only; deterministic ops in executor | ✅ PASS | Events emitted by executor handlers; TUI only consumes |
| **XI. Modularize Early** | New widgets should be separate modules | ✅ PASS | iteration_widget.py, agent_streaming_panel.py as new files |

**Gate Status**: ✅ PASS - No violations. Ready for Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/030-tui-execution-visibility/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/maverick/
├── dsl/
│   ├── events.py                           # Extend: LoopIterationStarted, LoopIterationCompleted, AgentStreamChunk
│   └── serialization/executor/
│       └── handlers/
│           ├── loop_step.py                # Modify: emit iteration events
│           └── agent_step.py               # Modify: emit streaming events
├── tui/
│   ├── models/
│   │   ├── enums.py                        # Extend: IterationStatus enum
│   │   └── widget_state.py                 # Extend: LoopIterationState, StreamingPanelState
│   ├── screens/
│   │   └── workflow_execution.py           # Modify: handle new events, manage streaming panel
│   ├── widgets/
│   │   ├── iteration_progress.py           # New: widget for loop iteration display
│   │   └── agent_streaming_panel.py        # New: collapsible streaming output panel
│   └── maverick.tcss                       # Extend: styles for iteration states, streaming panel

tests/
├── unit/
│   ├── dsl/
│   │   └── test_events.py                  # New: test new event types
│   ├── tui/
│   │   ├── test_iteration_progress.py      # New: test iteration widget
│   │   └── test_streaming_panel.py         # New: test streaming panel widget
│   └── test_workflow_execution_events.py   # New: test screen event handlers
└── integration/
    └── dsl/
        └── test_loop_events.py             # New: test loop event emission end-to-end
```

**Structure Decision**: Extension of existing single-package structure. No new packages required. New widgets follow established pattern in `src/maverick/tui/widgets/`. Event types extend existing `src/maverick/dsl/events.py`.

## Complexity Tracking

> **No violations identified. Table left empty.**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
