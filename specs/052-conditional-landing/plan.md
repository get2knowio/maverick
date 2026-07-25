# Implementation Plan: Conditional Landing on the Assumption Frontier

**Branch**: `052-conditional-landing` | **Date**: 2026-07-24 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/052-conditional-landing/spec.md`

## Summary

Extend `maverick land` so the assumption gate evaluates the full **frontier**
(every open entry of any severity, plus answered entries whose changed answer
is still pending reconciliation), classify every successful land as
**verified** or **conditionally verified on unresolved assumptions**, and emit
a persisted provenance report (terminal + JSON + PR-ready markdown) that
enumerates resolved / waived / open entries. Add a spec-scoped,
severity-filtered **bulk waive** to `maverick review`. Make a running
`maverick fly` detect newly arrived answers at every bead boundary and invoke
the reconcile workflow in-process — the drain loop keeps going — by splicing a
new Burr action onto the `record_outcome → select_next_bead` edge and teaching
`ReconcileWorkflow` to exclude the calling fly run from its
concurrent-fly guard.

## Technical Context

**Language/Version**: Python 3.11+ (`from __future__ import annotations`)
**Primary Dependencies**: Click + Rich (CLI), Burr (fly drain-loop state
machine), bd via `maverick.beads.client.BeadClient`, jj via
`maverick.jj.client.JjClient` + `library/actions/jj.py`, airframe agent
runtimes via `ReconcileSquadron`, structlog, Pydantic (config)
**Storage**: bd bead state keys (assumption ledger, `assumptions/models.py`);
JSON artifacts under `.maverick/runs/<run-id>/` (atomic writes via
`utils/atomic.py`)
**Testing**: pytest + pytest-asyncio + xdist (`make test`); CliRunner for CLI;
Burr graph driven offline with `StubFlySquadron` (`test_burr_graph.py`
pattern); reconcile workflow with monkeypatched module-level collaborators
(`test_workflow.py` pattern); integration with real bd + jj
(`tests/integration/test_assumption_ledger_flow.py` pattern)
**Target Platform**: Linux/macOS dev machines (CLI tool)
**Project Type**: Single project (`src/maverick/` + `tests/`)
**Performance Goals**: Frontier evaluation and mid-flight detection are bd
queries (~ms) — negligible vs. multi-minute bead implementation; a mid-flight
reconcile pass runs only when detection is non-empty (zero cost otherwise)
**Constraints**: No-bypass gate (no force flag — asserted by existing test);
reconcile may touch the jj working copy only at bead boundaries (clean-tree
guard); reconcile refuses to run concurrently with a *different* fly run;
mid-flight processing must never stop the drain loop (Fail Gracefully)
**Scale/Scope**: Ledgers of ~10–100 entries per repo; runs of ≤30 beads
(`--max-beads` default)

## Constitution Check

*GATE: evaluated pre-Phase-0 and re-checked post-Phase-1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Async-First | PASS | All new paths are `async def`; bd/jj access via existing async `BeadClient`/`JjClient`/actions; no `subprocess.run`, no threading. Mid-flight reconcile runs inside fly's existing event loop as an awaited Burr action. |
| II. Separation of Concerns | PASS | Frontier/report/classification logic lives in `assumptions/` (pure, bd-backed); the CLI only renders and exits; fly's Burr action owns WHEN, `ReconcileWorkflow` owns HOW. No agent gains deterministic side effects. |
| III. Dependency Injection | PASS | New functions take an explicit `BeadClient` / `cwd`; `ReconcileWorkflow` invoked with explicit `config` + inputs; no globals (graceful-stop singleton is pre-existing). |
| IV. Fail Gracefully | PASS | Mid-flight reconcile failure → warning event + drain continues (FR-013); bd-unavailable keeps the existing degrade-not-crash gate behavior; report persistence failure degrades to a warning, never blocks landing. |
| V. Test-First | PASS | Every new public function/action gets unit tests before implementation; integration test extends `test_assumption_ledger_flow.py`. |
| VI. Typed Contracts | PASS | New frozen dataclasses (`AssumptionReportEntry`, `LandFrontier`, `LandReport`, `MidFlightOutcome`) with `to_dict()`; `LandVerification` StrEnum; no `dict[str, Any]` blobs. |
| VII. Simplicity & DRY | PASS | Reuses `answered_unreconciled_entries` (051) for both the land pending-reconcile check and mid-flight detection — one detection predicate repo-wide (per clarification). Bulk waive loops the existing `ledger.waive` (no parallel write path). |
| VIII. Relentless Progress | PASS | Mid-flight pass processes what it can, escalates the rest, and the loop proceeds; unprocessed answers remain detectable by later runs (deterministic detection). |
| IX. Hardening | PASS | Reconcile invocation wrapped with timeout semantics inherited from `ReconcileWorkflow`; bd/jj calls go through hardened clients; no bare `except Exception` (narrow to `MaverickError`/`WorkflowError` where degradation is intended). |
| X. Guardrails | PASS | Single-repo cwd threading (explicit `cwd` everywhere, no `Path.cwd()` below the CLI boundary); jj writes via existing actions only; no new git/gh wrappers (`create_github_pr` reused if/when needed). |
| XI. Modularize Early | PASS (with plan) | `land.py` is 498 LOC — report building/persistence goes to a new `assumptions/land_report.py`, rendering helpers to `cli/commands/land_helpers.py` if the command file would cross ~800 LOC. `actions.py` (fly) is already large — the mid-flight logic lives in a new `fly_beads/mid_flight.py`, with only a thin Burr action added to `actions.py`. |
| XII. Ownership | PASS | Existing stale docstrings encountered (e.g., xoscar-era `FlySupervisor` references in `graceful_stop.py`) are corrected in passing where touched. |

**Initial gate: PASS** — no violations to justify. **Post-design re-check: PASS**
(design keeps all logic in `assumptions/` + workflow modules; no new external
wrappers; no new global state; complexity table empty).

## Project Structure

### Documentation (this feature)

```text
specs/052-conditional-landing/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── cli-land.md
│   ├── cli-review-bulk-waive.md
│   ├── land-report-schema.md
│   └── mid-flight-reconcile.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by plan)
```

### Source Code (repository root)

```text
src/maverick/
├── assumptions/
│   ├── models.py            # + LandVerification enum, AssumptionReportEntry,
│   │                        #   LandFrontier, report-entry status vocabulary
│   ├── ledger.py            # + report_entries(), frontier gate helpers,
│   │                        #   bulk_waive() (loops existing waive())
│   ├── land_report.py       # NEW: classify(), build_report(), persist
│   │                        #   (JSON + markdown), pure of CLI concerns
│   └── __init__.py          # re-export new public surface
├── cli/commands/
│   ├── land.py              # gate swap → frontier, classification, report
│   │                        #   render + persist, mode hints reference
│   │                        #   the generated PR body file
│   └── review.py            # bulk-waive options (--spec/--severity/--waive
│   │                        #   without BEAD_ID)
├── workflows/
│   ├── fly_beads/
│   │   ├── mid_flight.py    # NEW: detection + in-process ReconcileWorkflow
│   │   │                    #   invocation + outcome typing
│   │   ├── actions.py       # + thin reconcile_answers Burr action
│   │   └── burr_graph.py    # splice action on record_outcome→select_next_bead
│   │                        #   edge + final pass before done
│   └── reconcile/
│       └── workflow.py      # + active_fly_run_id input; _find_flying_run
│                            #   exclusion; (guards otherwise unchanged)
└── config.py                # ReconcileConfig.mid_flight: bool = True

tests/
├── unit/
│   ├── assumptions/
│   │   ├── test_ledger_frontier.py     # NEW: report_entries, frontier, bulk_waive
│   │   └── test_land_report.py         # NEW: classification + persistence
│   ├── cli/
│   │   ├── test_land_command.py        # extend: frontier gate, states, report
│   │   └── test_review_command.py      # extend: bulk waive
│   └── workflows/
│       ├── fly_beads/
│       │   ├── test_mid_flight.py      # NEW: detection/invocation/failure
│       │   └── test_burr_graph.py      # extend: boundary action wiring
│       └── reconcile/
│           └── test_workflow.py        # extend: active_fly_run_id exclusion
└── integration/
    └── test_assumption_ledger_flow.py  # extend: frontier gate + bulk waive E2E
```

**Structure Decision**: Single-project layout (existing). All ledger-adjacent
logic stays in `src/maverick/assumptions/` (which must not import workflow/CLI
modules — enforced by that package's charter); fly-side orchestration in
`src/maverick/workflows/fly_beads/`; CLI files stay thin renderers.

## Complexity Tracking

No constitution violations — table intentionally empty.
