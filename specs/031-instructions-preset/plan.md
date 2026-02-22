# Implementation Plan: Instructions Preset

**Branch**: `031-instructions-preset` | **Date**: 2026-02-22 | **Spec**: `specs/031-instructions-preset/spec.md`
**Input**: Feature specification from `/specs/031-instructions-preset/spec.md`

## Summary

Update Maverick's agent base class to use the Claude Agent SDK's `claude_code` system prompt preset instead of raw system prompt strings, with agent-specific guidance passed via an `instructions` parameter that is appended to the preset.

**Key finding from research**: The core implementation is already in place. `MaverickAgent` already uses `{"type": "preset", "preset": "claude_code", "append": instructions}` and `setting_sources: ["project", "user"]`. The `instructions` parameter already exists. `GeneratorAgent` correctly uses a direct `system_prompt` (no preset) per FR-005. The remaining work is **verification, test hardening, and documentation**.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Claude Agent SDK (`claude-agent-sdk>=0.1.0`), Click, Rich, Pydantic
**Storage**: N/A
**Testing**: pytest + pytest-asyncio (parallel via xdist)
**Target Platform**: Linux/macOS CLI
**Project Type**: Single project (Python CLI application)
**Performance Goals**: N/A (no performance-critical changes)
**Constraints**: Must maintain backward compatibility for all existing agent tests
**Scale/Scope**: ~10 agent implementations (5 interactive + 7 generators)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | PASS | No changes to async patterns; agents remain async |
| II. Separation of Concerns | PASS | Agents define WHO (instructions); workflows define WHAT/WHEN |
| III. Dependency Injection | PASS | Instructions injected at construction; no global state |
| IV. Fail Gracefully | PASS | No changes to error handling |
| V. Test-First | PASS | Existing tests verify preset pattern; plan adds coverage gaps |
| VI. Type Safety | PASS | `instructions: str` is typed; `SystemPromptPreset` is a TypedDict in SDK |
| VII. Simplicity & DRY | PASS | Preset pattern centralizes system prompt; no duplication |
| VIII. Relentless Progress | N/A | Not a runtime/workflow change |
| IX. Hardening by Default | N/A | No external calls affected |
| X. Architectural Guardrails | PASS | #3 (agents provide judgment, not side effects) — preserved |
| XI. Modularize Early | PASS | `base.py` is ~595 LOC (under soft limit) |
| XII. Ownership | PASS | All agents updated in single pass; no partial migration |

**Guardrail #8 (Canonical Libraries)**: PASS — uses Claude Agent SDK's native preset/instructions API.

**Gate result**: PASS — no violations. Proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/031-instructions-preset/
├── plan.md              # This file
├── research.md          # Phase 0 output — SDK API verification
├── data-model.md        # Phase 1 output — agent configuration model
├── quickstart.md        # Phase 1 output — creating agents with instructions
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/maverick/
├── agents/
│   ├── base.py              # MaverickAgent — preset + instructions (ALREADY DONE)
│   ├── implementer.py       # ImplementerAgent — uses instructions (ALREADY DONE)
│   ├── fixer.py             # FixerAgent — uses instructions (ALREADY DONE)
│   ├── issue_fixer.py       # IssueFixerAgent — uses instructions (ALREADY DONE)
│   ├── code_reviewer/
│   │   └── agent.py         # CodeReviewerAgent — uses instructions (ALREADY DONE)
│   └── generators/
│       └── base.py          # GeneratorAgent — uses system_prompt (correct per FR-005)
│
tests/unit/agents/
├── test_base.py             # Preset pattern test exists; may need edge case tests
├── test_implementer.py      # Verify instructions usage
├── test_curator.py          # Verify system_prompt for GeneratorAgent (correct)
└── generators/
    └── test_base.py         # Verify system_prompt for generators (correct)
```

**Structure Decision**: Existing single-project layout. No new files or directories needed. All changes are modifications to existing files.

## Complexity Tracking

> No Constitution Check violations — this section is empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none)    | —          | —                                   |
