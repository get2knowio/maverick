# Implementation Plan: Workflow Visualization Widgets

**Branch**: `012-workflow-widgets` | **Date**: 2025-12-16 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/012-workflow-widgets/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Implement five specialized Textual widgets for workflow visualization in Maverick: WorkflowProgress (stage tracking), AgentOutput (streaming message display), ReviewFindings (code review findings), ValidationStatus (compact validation step display), and PRSummary (pull request metadata). Widgets use immutable data snapshots with Textual's reactive properties for automatic re-rendering.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Textual 0.40+, Rich (syntax highlighting via Textual's built-in support)
**Storage**: N/A (in-memory state; widgets receive immutable snapshots)
**Testing**: pytest + pytest-asyncio with Textual's `pilot` fixture
**Target Platform**: Cross-platform terminal (Linux, macOS, Windows with compatible terminal)
**Project Type**: Single project (extends existing TUI in `src/maverick/tui/widgets/`)
**Performance Goals**: <100ms message render, 60fps scroll, <200ms loading state display
**Constraints**: 1000 message buffer limit (AgentOutput), 200 finding limit (ReviewFindings), WCAG AA contrast compliance
**Scale/Scope**: 5 widgets, ~7 user stories, 39 functional requirements

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Design Check (Phase 0)

| Principle | Compliance | Notes |
|-----------|------------|-------|
| I. Async-First | ✅ PASS | Widgets use Textual's reactive system; no blocking I/O in widgets |
| II. Separation of Concerns | ✅ PASS | Widgets are presentation-only; receive immutable snapshots from workflows |
| III. Dependency Injection | ✅ PASS | Widgets receive data via constructor/reactive properties; no global state |
| IV. Fail Gracefully | ✅ PASS | Widgets handle empty/loading states; missing data doesn't crash |
| V. Test-First | ✅ PASS | TDD with pytest + Textual pilot fixture required |
| VI. Type Safety | ✅ PASS | All public APIs with complete type hints; frozen dataclasses for state |
| VII. Simplicity | ✅ PASS | 5 focused widgets with clear responsibilities; no premature abstractions |
| VIII. Relentless Progress | ⬜ N/A | Widgets are passive display; progress resilience is workflow concern |

**Pre-Design Gate Status**: ✅ PASSED

### Post-Design Verification (Phase 1)

| Principle | Verification | Evidence |
|-----------|-------------|----------|
| I. Async-First | ✅ VERIFIED | data-model.md: No blocking operations in state models; widgets use reactive properties |
| II. Separation of Concerns | ✅ VERIFIED | contracts/widgets.py: Widget protocols define presentation-only interfaces; data flows in via DTOs |
| III. Dependency Injection | ✅ VERIFIED | contracts/widgets.py: All data passed via method parameters; no global imports in protocols |
| IV. Fail Gracefully | ✅ VERIFIED | data-model.md: `is_empty` properties on all state classes; loading states defined |
| V. Test-First | ✅ VERIFIED | quickstart.md: Testing patterns documented with pytest/pilot examples |
| VI. Type Safety | ✅ VERIFIED | data-model.md: All models use `@dataclass(frozen=True, slots=True)`; complete type hints |
| VII. Simplicity | ✅ VERIFIED | Each widget has focused responsibility; uses existing Textual primitives (Collapsible, RichLog) |
| VIII. Relentless Progress | ⬜ N/A | Passive display widgets; progress resilience handled by workflows |

**Post-Design Gate Status**: ✅ PASSED - Design artifacts comply with all applicable constitution principles

## Project Structure

### Documentation (this feature)

```text
specs/012-workflow-widgets/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/maverick/tui/
├── models.py                    # Extend with new widget state models
├── maverick.tcss                # Extend with widget-specific styles
└── widgets/
    ├── __init__.py              # Export new widgets
    ├── workflow_progress.py     # NEW: WorkflowProgress widget (FR-001 to FR-007)
    ├── agent_output.py          # NEW: AgentOutput widget (FR-008 to FR-016)
    ├── review_findings.py       # NEW: ReviewFindings widget (FR-017 to FR-024)
    ├── validation_status.py     # NEW: ValidationStatus widget (FR-025 to FR-029)
    └── pr_summary.py            # NEW: PRSummary widget (FR-030 to FR-034)

tests/unit/tui/
├── widgets/
│   ├── test_workflow_progress.py
│   ├── test_agent_output.py
│   ├── test_review_findings.py
│   ├── test_validation_status.py
│   └── test_pr_summary.py
└── test_models.py               # Extend with new model tests
```

**Structure Decision**: Extends existing single-project TUI structure. Widgets go in `src/maverick/tui/widgets/`, following established patterns from `stage_indicator.py` and `log_panel.py`. State models extend `src/maverick/tui/models.py`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations to justify. Design adheres to all constitution principles.
