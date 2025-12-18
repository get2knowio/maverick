# Implementation Plan: Textual TUI Layout and Theming

**Branch**: `011-tui-layout-theming` | **Date**: 2025-12-16 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/011-tui-layout-theming/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Implement the core Textual TUI layout and theming infrastructure for Maverick. This includes the main MaverickApp class, four primary screens (Home, Workflow, Review, Config), a collapsible log panel, dark mode theming with status colors, workflow progress indicators, and keyboard navigation with command palette support.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Textual 0.40+, Click (CLI entry point), Pydantic (for configuration models)
**Storage**: N/A (in-memory state; workflows provide state via async generators)
**Testing**: pytest + pytest-asyncio + Textual's pilot fixture
**Target Platform**: Cross-platform terminal emulators supporting 256 colors or true color
**Project Type**: Single project (extends existing `src/maverick/tui/` module)
**Performance Goals**: <200ms log panel toggle response, <1s stage status update reflection
**Constraints**: Minimum terminal size 80×24, log buffer limit 1,000 lines
**Scale/Scope**: 4 screens, ~10 widgets, 1 stylesheet

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | ✅ PASS | TUI event loop is inherently async; workflows yield progress as async generators |
| II. Separation of Concerns | ✅ PASS | TUI presents state only; no business logic in screens/widgets |
| III. Dependency Injection | ✅ PASS | Workflow state passed to screens via reactive attributes/data binding |
| IV. Fail Gracefully | ✅ PASS | Stage failure displays error indicator; workflow continues if possible |
| V. Test-First | ✅ PASS | Textual pilot fixture enables comprehensive async tests |
| VI. Type Safety | ✅ PASS | Complete type hints; Pydantic models for structured data |
| VII. Simplicity | ✅ PASS | Standard Textual patterns; no premature abstractions |
| VIII. Relentless Progress | ✅ PASS | TUI displays progress; recovery logic in workflows not TUI |

**Gate Status**: PASS - All constitution principles satisfied.

## Project Structure

### Documentation (this feature)

```text
specs/011-tui-layout-theming/
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
├── tui/
│   ├── __init__.py          # Public exports (MaverickApp, screens)
│   ├── app.py               # MaverickApp main application class
│   ├── maverick.tcss        # Stylesheet with theme definitions
│   ├── screens/
│   │   ├── __init__.py      # Screen exports
│   │   ├── home.py          # HomeScreen - workflow selection, recent runs
│   │   ├── workflow.py      # WorkflowScreen - active workflow progress
│   │   ├── review.py        # ReviewScreen - code review results
│   │   └── config.py        # ConfigScreen - settings
│   └── widgets/
│       ├── __init__.py      # Widget exports
│       ├── sidebar.py       # WorkflowSidebar - navigation/stages
│       ├── log_panel.py     # LogPanel - collapsible agent output
│       ├── stage_indicator.py # StageIndicator - status icons
│       └── workflow_list.py # WorkflowList - recent workflows

tests/
├── unit/
│   └── tui/
│       ├── __init__.py
│       ├── test_app.py      # MaverickApp tests
│       ├── test_screens.py  # Screen navigation tests
│       └── test_widgets.py  # Widget behavior tests
└── integration/
    └── tui/
        └── test_workflow_display.py  # End-to-end TUI tests
```

**Structure Decision**: Extends existing `src/maverick/tui/` module with screens and widgets subdirectories following Textual's recommended compound widget pattern.

## Constitution Check (Post-Design Re-evaluation)

After Phase 1 design completion, all constitution principles remain satisfied:

| Principle | Status | Design Evidence |
|-----------|--------|-----------------|
| I. Async-First | ✅ PASS | All screens use async `on_mount()`; workflow events consumed via async generators; Textual's event loop is async |
| II. Separation of Concerns | ✅ PASS | Screens/widgets only display state (see contracts/); no business logic in TUI; workflows handle orchestration |
| III. Dependency Injection | ✅ PASS | Screen states are immutable dataclasses passed via reactive attributes; no global state; workflows injected |
| IV. Fail Gracefully | ✅ PASS | StageStatus.FAILED shows error indicator (✗); error messages stored in state; TUI doesn't crash on workflow failure |
| V. Test-First | ✅ PASS | Testing patterns documented in quickstart.md; pilot fixture for all screen/widget tests |
| VI. Type Safety | ✅ PASS | All models use frozen dataclasses with slots; Protocol interfaces in contracts/; complete type hints |
| VII. Simplicity | ✅ PASS | Standard Textual patterns (Screen, Widget, reactive); CSS-based theming; no custom event systems |
| VIII. Relentless Progress | ✅ PASS | Log panel shows ongoing activity; stage indicators show progress; TUI updates in real-time from event streams |

**Post-Design Gate Status**: ✅ PASS - All principles satisfied with design evidence.

## Complexity Tracking

> No violations - design follows all constitution principles.
