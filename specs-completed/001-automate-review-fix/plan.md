# Implementation Plan: Automated Review & Fix Loop for AI-Generated Rust Changes

**Branch**: `001-automate-review-fix` | **Date**: 2025-11-08 | **Spec**: specs/001-automate-review-fix/spec.md
**Input**: Feature specification from `/specs/001-automate-review-fix/spec.md`

## Summary

Temporal activity that runs the CodeRabbit CLI against AI-authored Rust branches, normalizes findings, optionally invokes OpenCode to apply guided fixes, re-runs validation (default `cargo test`), and returns an auditable outcome (`clean`, `fixed`, or `failed`) with sanitized artifacts and retry fingerprints for idempotent automation.

## Technical Context

**Language/Version**: Python 3.11 (Temporal activity implementation), Rust toolchain for validation (cargo)  
**Primary Dependencies**: Temporal Python SDK, uv tooling, CodeRabbit CLI, OpenCode CLI, cargo  
**Storage**: N/A (rely on Temporal workflow state and downstream artifact persistence)  
**Testing**: pytest with Temporal activity fixtures; integration tests exercising CLI orchestration  
**Target Platform**: Linux Temporal worker environment with CodeRabbit/OpenCode binaries available  
**Project Type**: Temporal backend automation within existing `src/activities` module  
**Performance Goals**: Must surface `clean` verdicts within 2 minutes in 95% of no-finding runs; retries should avoid duplicate OpenCode invocations  
**Constraints**: Deterministic workflow behavior, sanitized prompts (length + secret filtering), CLI invocations routed via uv-managed environment, tolerant stderr decoding  
**Scale/Scope**: Single-branch automation executed per CI run; must support repeated retries per findings fingerprint

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Simplicity First: PASS – scope limited to one orchestrating activity leveraged by existing workflows; no new services introduced.
- Test-Driven Development: PASS – plan requires new unit/integration tests for activity orchestration, CLI parsing, and retry fingerprints before implementation.
- UV-Based Development: PASS – all CLI executions will be wrapped through `uv run` helpers; confirm best practices during research.
- Temporal-First Architecture: PASS – business logic remains in activity; workflow changes limited to orchestration hooks, respecting determinism rules.
- Observability & Monitoring: PASS – activity will emit structured JSON logs via `src/utils/logging` and capture sanitized artifacts for auditing.
- Documentation Standards: PASS – deliverables confined to `specs/001-automate-review-fix` without referencing specs from durable docs.

*Re-evaluated after Phase 1 design: PASS (no new constitutional risks identified).* 

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
```text
src/
├── activities/
│   ├── copilot_help.py
│   ├── phase_runner.py
│   ├── repo_verification.py
│   ├── review_fix.py          # new activity orchestrating CodeRabbit/OpenCode loop
│   └── __init__.py
├── utils/
│   ├── logging.py
│   ├── tasks_markdown.py
│   └── retry_fingerprint.py   # new helper for stable fingerprints (if needed)
├── workflows/
│   └── phase_automation.py    # integrates new activity into automation phases
└── workers/
    └── main.py

tests/
├── unit/
│   └── test_review_fix_activity.py          # new unit tests for parsing/sanitization
└── integration/
    └── test_review_fix_loop.py              # new integration test covering end-to-end orchestration
```

**Structure Decision**: Extend existing Temporal automation backend by adding a dedicated review/fix activity module plus targeted utilities and mirrored tests while reusing current worker/workflow scaffolding.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| *None* |  |  |
