# Implementation Plan: Spec Kit Ingestion Mode for Refuel

**Branch**: `048-speckit-refuel-ingestion` | **Date**: 2026-07-23 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/048-speckit-refuel-ingestion/spec.md`

## Summary

Add a deterministic ingestion path to `maverick refuel` for Spec Kit-managed repositories: parse `specs/NNN-name/{spec.md,plan.md,tasks.md}` with a fixed grammar (no LLM decomposition), create one epic bead + one task bead per open task, preserve task IDs / phases / `[P]` markers / file scope, wire dependencies as a phase barrier plus explicit notes, chain the epic behind existing open epics, support delta re-runs under the existing epic, and offer `--dry-run` plus an opt-in single-call LLM enrichment pass for verification commands.

Technical approach: a new pure-parsing package `src/maverick/speckit/` (modeled on `src/maverick/flight/parser.py`) feeding a new lightweight `PythonWorkflow` (`src/maverick/workflows/refuel_speckit/`) that reuses the existing `library/actions/beads.py` actions (`create_beads`, `wire_dependencies` — both already `dry_run`-capable) and `BeadClient` directly, bypassing Burr, `RefuelSquadron`, and the actor stack entirely. CLI mode dispatch lives in `cli/commands/refuel/_group.py`.

## Technical Context

**Language/Version**: Python 3.11+ (`from __future__ import annotations`)
**Primary Dependencies**: Pydantic (frozen models), Click + Rich (CLI), existing `maverick.beads.BeadClient` (async `bd` CLI wrapper), `maverick.library.actions.beads` (create/wire actions with `dry_run`), `maverick.flight.parser` primitives as precedent, structlog, persona-agent pattern from `maverick.agents.personas` for optional enrichment
**Storage**: beads database via `bd` CLI (`.beads/`); run metadata JSON in `<cwd>/.maverick/runs/<run_id>/` (`maverick.runway.run_metadata`); no new storage
**Testing**: pytest + pytest-asyncio + xdist via `make test` / `make test-fast`; existing Spec Kit fixtures in `tests/unit/beads/conftest.py` (`SAMPLE_TASKS_MD`, `spec_dir_with_tasks`, `spec_dir_with_deps`, `mock_runner` BeadClient stubbing)
**Target Platform**: Linux/macOS developer checkouts (jj-colocated repos, per Guardrail 0)
**Project Type**: single project (existing `src/maverick/` package layout)
**Performance Goals**: ingestion of a typical feature (≤50 tasks) completes in < 30 s wall clock with zero LLM calls (SC-001); parsing itself is pure CPU (< 100 ms), the budget is `bd` subprocess calls (~2 per bead + deps)
**Constraints**: no model invocation on the default path (FR-010); no partial bead trees on validation failure — validate fully before first write (FR-015); no `Path.cwd()` below the CLI boundary (Guardrail 7); all VCS writes via jj, all bead writes via `BeadClient`
**Scale/Scope**: task lists of 10–100 tasks, 3–10 phases; one feature dir per run; supported template range = Spec Kit 0.14.x initially

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle / Guardrail | Compliance |
| --- | --- |
| I. Async-first | PASS — parser is pure sync functions on in-memory strings (no I/O); all file reads via async loaders; all `bd` calls via async `BeadClient`/`CommandRunner`; no `subprocess.run` anywhere |
| II. Separation of concerns | PASS — deterministic decomposition lives in workflow/actions (not agents); the only agent involvement is the opt-in enrichment persona, which supplies judgment (verification commands) and owns no side effects |
| III. Dependency injection | PASS — parser takes strings; workflow receives `cwd`, config, and inputs from the CLI boundary; `BeadClient` constructed per-workflow with explicit `cwd`; enrichment runtime via `runtime_for_agent()` |
| IV. Fail gracefully | PASS — enrichment failure degrades to warning (FR-011); parse/validation errors fail before any write with file:line context (FR-012/FR-015); partial-creation reporting on interrupt |
| V. Test-first | PASS — parser grammar, delta logic, and dep-graph builder are pure functions designed for table-driven tests; fixtures already exist in `tests/unit/beads/conftest.py` |
| VI. Simplicity | PASS — no Burr graph, no squadron, no actor pool on this path; a plain sequential `PythonWorkflow` |
| Guardrail 0/7 (cwd threading) | PASS — CLI resolves `cwd = Path.cwd().resolve()` once; every layer receives explicit `cwd` |
| Guardrail 2 (deterministic ops in workflows) | PASS — bead creation/wiring/chaining owned by the workflow via typed actions |
| Guardrail 3 (typed contracts) | PASS — new frozen Pydantic models for parsed artifacts and ingestion plan; reuse `BeadDefinition`/`BeadDependency` |
| Guardrail 5 (one canonical wrapper) | PASS — all `bd` interaction via `BeadClient`/`library/actions/beads.py`; no new subprocess wrappers |
| Debt prevention (module size, package-per-workflow) | PASS — new `speckit/` package split into `models/parser/detect/build`; new `workflows/refuel_speckit/` package with `constants.py`, `models.py`, `workflow.py` |

No violations → Complexity Tracking not needed.

**Post-design re-check (after Phase 1)**: PASS — design artifacts introduce no new projects, no global state, no agent-owned side effects; the enrichment agent is a one-shot persona following the existing `VerificationPropertiesAgent` pattern (`workflows/refuel_maverick/workflow.py:363`).

## Project Structure

### Documentation (this feature)

```text
specs/048-speckit-refuel-ingestion/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── cli-refuel-speckit.md    # CLI surface: flags, mode dispatch, exit codes, error text
│   ├── tasks-md-grammar.md      # Supported Spec Kit template grammar + version range
│   └── bead-encoding.md         # How beads encode Spec Kit provenance (titles, state keys, description sections, dep edges)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/maverick/
├── speckit/                         # NEW: deterministic Spec Kit artifact layer (pure, no bd/VCS side effects)
│   ├── __init__.py                  # re-exports public surface
│   ├── models.py                    # frozen Pydantic: SpeckitFeature, SpeckitTask, SpeckitPhase, ParsedSpec, TemplateCompatibility
│   ├── parser.py                    # pure grammar functions (modeled on flight/parser.py): tasks.md, spec.md success criteria + story scenarios
│   ├── detect.py                    # feature-dir resolution, shape detection, vendored-version compatibility check
│   ├── build.py                     # IngestionPlan builder: bead definitions, phase-barrier + explicit dep edges, delta filtering
│   └── errors.py                    # SpeckitError(MaverickError) hierarchy backing error catalog E01–E07
├── workflows/
│   └── refuel_speckit/              # NEW: package-per-workflow (no Burr, no squadron)
│       ├── __init__.py
│       ├── constants.py             # step names: RESOLVE_FEATURE, CHECK_TEMPLATE, PARSE_ARTIFACTS, PLAN_INGESTION, ENRICH, CREATE_BEADS, WIRE_DEPS, CHAIN_EPIC, RECORD_RUN, COMMIT_OUTPUT
│       ├── models.py                # SpeckitRefuelResult (mirrors RefuelMaverickResult.to_dict() shape)
│       └── workflow.py              # SpeckitRefuelWorkflow(PythonWorkflow): sequential driver incl. dry-run + delta
├── agents/
│   └── personas.py                  # MODIFIED: add SpeckitEnrichmentAgent (one-shot persona, provider_tier="generate")
├── cli/commands/refuel/
│   └── _group.py                    # MODIFIED: add --speckit / --dry-run / --enrich, mode auto-detection + dispatch
└── beads/                           # UNCHANGED: BeadClient reused as-is

tests/unit/
├── speckit/                         # NEW: parser/detect/build table tests (reuse SAMPLE_TASKS_MD fixtures)
├── workflows/refuel_speckit/        # NEW: workflow tests with stubbed BeadClient runner
└── cli/commands/refuel/             # MODIFIED: mode-dispatch + flag tests
```

**Structure Decision**: single-project layout following the repo's package-per-workflow convention (`workflows/refuel_speckit/` mirrors `workflows/refuel_maverick/`). Parsing is a standalone `speckit/` package (not inside the workflow) because detection is also needed at the CLI boundary for mode dispatch, and pure parsing deserves isolated table-driven tests.

## Complexity Tracking

No constitution violations — table intentionally empty.
