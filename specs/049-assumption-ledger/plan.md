# Implementation Plan: Assumption Ledger

**Branch**: `049-assumption-ledger` | **Date**: 2026-07-23 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/049-assumption-ledger/spec.md`

## Summary

Extend Maverick's assumption beads into a structured assumption ledger. Agents
surface adopted assumptions (question, adopted answer, alternatives, severity)
as new fields in their existing structured result payloads; a new deterministic
fly action creates one ledger bead per assumption under the owning epic —
owner spec derived from epic state (`speckit_feature` / `flight_plan_name`),
discovered-from edge to the spawning bead — and the commit action (fixed to
stop discarding `jj_commit_bead`'s return) stamps entries with the jj change
ID(s) embodying them. Severity drives enforcement with zero new pause
machinery: low entries are `bd defer`red (advisory), medium/high entries block
`maverick land` via a no-bypass pre-curation gate, and high entries
additionally gain a `blocks` edge onto the next spec's epic (wired at
recording time and at refuel `_chain_epic` time) so downstream work never
becomes `bd ready` until answered or waived through `maverick review`.
`maverick brief` gains a per-spec assumption-counts section as a spec-quality
signal. All ledger operations live in a new `maverick.assumptions` package.

## Technical Context

**Language/Version**: Python 3.11+ (`from __future__ import annotations`)
**Primary Dependencies**: bd CLI via `maverick.beads.BeadClient` (CommandRunner
subprocess), Jujutsu via `maverick.jj.client.JjClient` /
`library/actions/jj.py`, Pydantic (payloads + validation), Click + Rich (CLI),
burr graph in `workflows/fly_beads/`, structlog, tenacity
**Storage**: bd bead store (beads + state key/values + labels + dependency
edges) — no new persistence layer (research R1)
**Testing**: pytest + pytest-asyncio + xdist via `make test` / `make test-fast`;
CI gate `make ci`
**Target Platform**: Linux/macOS developer machines (CLI, single-repo
jj-colocated checkout per Guardrail 0)
**Project Type**: single project (existing `src/maverick/` layout)
**Performance Goals**: interactive CLI latency — land gate and brief section
add O(assumption beads) `bd` calls (tens of beads, each subprocess ≤30s
`BD_TIMEOUT`); no hot paths
**Constraints**: bd state values are `dict[str, str]` (multi-values
comma-joined); recording/stamping must be non-fatal to fly (FR-012, existing
`create_human_bead` pattern); payload changes must be additive/backward
compatible; no `Path.cwd()` below the CLI boundary (Guardrail 7)
**Scale/Scope**: tens of assumptions per run, a handful of specs per repo;
~6 source areas touched + 1 new package (~10 modules incl. tests)

## Constitution Check

*GATE: evaluated against constitution v1.10.0 before Phase 0; re-evaluated
after Phase 1 design.*

| Principle / Guardrail | Verdict | Notes |
|---|---|---|
| I. Async-first | PASS | All new ops go through async `BeadClient`/`JjClient`/CommandRunner; no `subprocess.run` in async paths |
| II. Separation of concerns | PASS | Agents only *report* assumptions in payloads (judgment); the workflow's `record_assumptions` action and CLI own all side effects (clarification #4 codifies this) |
| III. Dependency injection | PASS | Ledger functions take `client`/`cwd` explicitly; no globals |
| IV/VIII. Fail gracefully, relentless progress | PASS | Recording and stamping are non-fatal to fly (warn + continue, mirrors `create_human_bead`); land gate failure is an intentional hard stop, not a crash |
| V. Test-first | PASS (plan) | Test areas enumerated in quickstart; tasks phase orders tests before implementation |
| VI. Typed contracts | PASS | Frozen dataclasses (`AssumptionRecord`, `PerSpecAssumptionCounts`), StrEnum severity, state-key constants exported — no ad-hoc dict blobs, no magic strings |
| VII. Simplicity/DRY | PASS | Reuses bd ready/defer/close, existing labels, existing epic chaining; no new pause machinery (clarification #2) |
| IX. Hardening | PASS | bd calls inherit BeadClient timeouts; typed `AssumptionLedgerError`; no bare except |
| X.5 One canonical wrapper | PASS (improves) | Adds `DependencyType.DISCOVERED_FROM`; migrates the two raw `bd dep add` call sites in `_commit.py` to `BeadClient` (research R11) |
| X.7 / Guardrail 7 explicit cwd | PASS | Every ledger function takes explicit `cwd`; CLI resolves once |
| XI. Modularize early | PASS | New `maverick.assumptions` package instead of growing `fly_beads/actions.py` (1200+ LOC) further |
| XII. Ownership | PASS | Fixes two found issues in passing: discarded commit change_id; nondeterministic `_chain_epic` tail ordering |

**Post-Phase-1 re-check**: no new violations introduced by the design; the
Complexity Tracking table remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/049-assumption-ledger/
├── plan.md              # This file
├── spec.md              # Feature specification (clarified 2026-07-23)
├── research.md          # Phase 0 — decisions R1–R13
├── data-model.md        # Phase 1 — bead shape, state keys, transitions
├── quickstart.md        # Phase 1 — validation scenarios
├── contracts/
│   ├── README.md
│   ├── payloads.md      # AssumptionPayload + submit-payload additions
│   ├── ledger-api.md    # maverick.assumptions public API
│   └── cli.md           # land gate, review answer/waive, brief section
└── tasks.md             # Phase 2 (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
src/maverick/
├── assumptions/                    # NEW package (research R13)
│   ├── __init__.py                 # public re-exports
│   ├── models.py                   # Severity, AssumptionRecord,
│   │                               # PerSpecAssumptionCounts, state-key consts
│   ├── ledger.py                   # record/stamp/answer/waive/query ops
│   ├── report.py                   # per_spec_counts aggregation
│   └── errors.py                   # AssumptionLedgerError(MaverickError)
├── payloads.py                     # + AssumptionPayload; + assumptions field on
│                                   #   SubmitImplementation/Review/FixResult
├── beads/models.py                 # + DependencyType.DISCOVERED_FROM
├── agents/                         # implementer/reviewer/fixer prompt builders:
│                                   #   assumption-reporting instructions
├── workflows/
│   ├── fly_beads/
│   │   ├── actions.py              # collect payload assumptions →
│   │   │                           #   pending_assumptions; commit captures
│   │   │                           #   change_id + stamps entries
│   │   ├── burr_graph.py           # wire record_assumptions before commit
│   │   └── _commit.py              # raw `bd dep add` → BeadClient (cleanup)
│   └── refuel_speckit/workflow.py  # _chain_epic: deterministic NNN ordering +
│                                   #   wire open high-severity entries → new epic
└── cli/commands/
    ├── land.py                     # pre-curation assumption gate (no bypass)
    ├── review.py                   # answer / waive flows for ledger entries
    └── brief.py                    # per-spec assumption counts section

tests/
├── unit/
│   ├── assumptions/                # NEW: ledger, report, severity coercion,
│   │                               #   dedup, owner-spec derivation
│   ├── test_payloads_assumptions.py  # AssumptionPayload validation/back-compat
│   ├── beads/                      # DependencyType.DISCOVERED_FROM
│   ├── workflows/fly_beads/        # record_assumptions action, commit stamping
│   ├── workflows/refuel_speckit/   # _chain_epic high-severity wiring, ordering
│   ├── library/actions/            # select_next_bead skip regression
│   └── cli/                        # land gate, review flows, brief section
└── integration/
    └── test_assumption_ledger_flow.py  # quickstart scenarios + legacy compat
```

**Structure Decision**: Single-project layout, existing tree. One new focused
package (`src/maverick/assumptions/`) holds all ledger domain logic so its
five consumers (fly, refuel_speckit, land, review, brief) share one
implementation; all other changes are edits inside existing modules,
mirrored by tests in the existing `tests/` hierarchy.

## Complexity Tracking

No constitution violations to justify — table intentionally empty.
