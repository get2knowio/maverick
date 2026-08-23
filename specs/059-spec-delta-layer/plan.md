# Implementation Plan: Spec Delta Layer

**Branch**: `059-spec-delta-layer` | **Date**: 2026-08-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/059-spec-delta-layer/spec.md`

## Summary

Add `maverick delta validate|apply|list` — a deterministic, zero-model-call
layer for changing an already-shipped spec. A delta document states requirement
operations (ADDED / MODIFIED / REMOVED / RENAMED) and, where work changes, task
entries. Applying rewrites `spec.md` and `tasks.md`, refuses when a named task's
bead is already in flight or closed, and archives the document as provenance.
Bead consequences arrive on the next ordinary `refuel --speckit`.

The technically load-bearing piece is a **requirement-block parser with a
byte-identical round-trip over the live corpus** — 54 specs, 1,139 requirement
blocks. Everything else is assembly over surfaces that already exist.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: Click, Rich, Pydantic, `atomicwrites` via `utils/atomic.py`. No new third-party dependency.
**Storage**: `specs/<feature>/deltas/*.md` (pending), `deltas/archive/*.md` (applied)
**Testing**: pytest + pytest-asyncio + xdist; `CliRunner` via the `cli_runner` fixture
**Target Platform**: local developer checkout
**Project Type**: single project (CLI + library)
**Performance Goals**: parse+validate+apply completes without a model call; the round-trip test covers 54 files in seconds
**Constraints**: zero model calls on every path (FR-003, FR-019); no bead writes during apply (FR-011); no new `ErrorKind`; byte-identical round-trip (SC-010)
**Scale/Scope**: one new command group, one new parser module, one new subpackage (~6 modules), one `IngestionPlan` field, one new refuel step

No `NEEDS CLARIFICATION` remains — five were resolved in the 2026-08-23 clarify
session and are recorded in the spec's `## Clarifications`.

## Constitution Check

| Principle | Status | Note |
| --- | --- | --- |
| I. Async-first | PASS | The CLI is `@async_command`; bead reads use the async `BeadClient`. File I/O is synchronous but off the agent path — same shape as `speckit/parser.py` today. |
| II. Separation of concerns | PASS | Parsing / validation / apply / archive are separate modules; the CLI is dispatch and rendering only. |
| III. Dependency injection | PASS | `cwd` threaded from the CLI boundary; the bead client is injected. |
| IV. Fail gracefully | PASS | Validation reports every problem at once rather than the first; withdrawal closing is per-bead isolated, mirroring `_adopt_remediation_beads`. |
| V. Test-first | PASS | SC-010's round-trip is written before the parser; the guard's both-sides tests (SC-008, SC-008a) before the guard. |
| VI. Type safety | PASS | Frozen Pydantic models throughout (data-model.md); no `dict[str, Any]` at any boundary. |
| VII. Simplicity & DRY | PASS | Reuses `detect.resolve_feature`, `_TASK_LINE_RE`, `utils/atomic.py`, the shared JSON envelope. No new regex for anything already parsed. |
| VIII. Relentless progress | PASS | No deferrals; the two falsified assumptions were fixed in the spec rather than worked around here. |
| IX. Hardening by default | PASS | Every failure mode in `delta-document-format.md` has a named code and a test. |
| X. Architectural guardrails | PASS | See below. |
| XI. Modularize early | PASS | `speckit/delta/` is a package from the start, not a file that grows into one. |
| XIII. Determinism over inference | **PASS, and central** | Zero model calls anywhere. FR-007a forbids *inferring* requirement→task coverage — the one place a model would be tempting is explicitly closed. |

**Guardrail check**:

- **0 (single-repo; bd targets the checkout)**: PASS — no workspace; `BeadClient.close()` already calls `assert_checkout`.
- **1 (no blocking on the event loop)**: PASS — bead calls go through the async client; file reads are outside the agent path.
- **2 (deterministic ops belong to workflows, not agents)**: PASS — there is no agent in this feature at all.
- **3 (single typed contract)**: PASS.
- **5 (one canonical wrapper per external system)**: PASS — `BeadClient` for beads, existing task grammar reused verbatim, no new subprocess wrapper.
- **7 (explicit cwd threading)**: PASS — resolved once per command body, passed down.
- **8 (deterministic ingestion over model inference)**: PASS — this feature is an instance of the principle.

No entry needed in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```
specs/059-spec-delta-layer/
├── spec.md
├── plan.md                              # this file
├── research.md                          # R1–R11
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── requirement-block-grammar.md     # the spec.md block definition + round-trip
│   ├── delta-document-format.md         # the delta grammar + validation table
│   ├── cli-delta.md                     # command surface + human output
│   └── cli-delta-json.md                # JSON verbs
├── checklists/
│   └── requirements.md
└── tasks.md                             # (next: /speckit-tasks)
```

### Source Code (repository root)

```
src/maverick/
├── speckit/
│   ├── requirements.py          # NEW — RequirementBlock/Section, parse + render
│   │                            #   the round-trip invariant lives here
│   ├── delta/                   # NEW package
│   │   ├── __init__.py
│   │   ├── models.py            # DeltaDocument, RequirementEntry, TaskEntry,
│   │   │                        #   Impact, Acknowledgement, ApplicationRecord
│   │   ├── parser.py            # parse_delta_md
│   │   ├── validate.py          # every check in delta-document-format.md,
│   │   │                        #   incl. the content-loss guard
│   │   ├── apply.py             # in-memory rewrite of spec.md + tasks.md
│   │   ├── impacts.py           # task -> bead -> status, via existing_task_map
│   │   └── archive.py           # move + ApplicationRecord append
│   ├── build.py                 # MODIFIED — IngestionPlan.withdrawn
│   └── models.py                # unchanged
├── cli/commands/delta.py        # NEW — Click group: validate / apply / list
├── main.py                      # MODIFIED — one _LAZY_COMMANDS entry
└── workflows/refuel_speckit/
    └── workflow.py              # MODIFIED — withdrawal detection between
                                 #   _find_existing_epic and build_ingestion_plan,
                                 #   plus a close step modelled on
                                 #   _adopt_remediation_beads

tests/
├── unit/speckit/
│   ├── test_requirements.py     # block grammar edge cases from research R1
│   ├── delta/
│   │   ├── test_parser.py
│   │   ├── test_validate.py     # incl. both sides of the content-loss guard
│   │   ├── test_apply.py
│   │   ├── test_impacts.py
│   │   └── test_archive.py
│   └── test_build_withdrawn.py
├── unit/cli/
│   ├── test_delta_command.py
│   └── commands/test_delta_json.py
└── integration/delta/
    ├── test_requirement_roundtrip.py    # SC-010, over the LIVE specs/ tree
    ├── test_apply_atomicity.py          # FR-009
    ├── test_refusal_writes_nothing.py   # FR-014, FR-016
    └── test_withdrawal_ingestion.py     # SC-002
```

**Structure Decision**: single project. `speckit/delta/` is a package from the
start per the Debt Prevention split rule. `requirements.py` sits beside
`parser.py` rather than inside it — `parser.py` is already the tasks.md parser
and adding a second grammar to it would push a focused module toward a
god-module.

## Design

### Flow

```
delta validate                 delta apply
  ├─ resolve feature             ├─ validate (as left)
  ├─ parse delta doc             ├─ detect impacts ── bd read only
  ├─ parse spec.md blocks        │     └─ any blocking + unacked → REFUSE, write nothing
  ├─ parse tasks.md              ├─ compute new spec.md + tasks.md IN MEMORY
  └─ run every check ──► report  ├─ write both (atomic per file)
                                 ├─ move doc → archive/ + ApplicationRecord
                                 └─ report "next: maverick refuel <f> --speckit"

refuel --speckit  (separate, explicit run)
  ├─ _find_existing_epic ──► existing_task_map
  ├─ NEW: withdrawn = set(existing_task_map) - {parsed task ids}
  ├─ build_ingestion_plan (plan.withdrawn carries them → dry-run previews free)
  ├─ create new beads (unchanged)
  └─ NEW: close withdrawn beads, per-bead isolated, reason cites the delta
```

### Key decisions (rationale in research.md)

1. **Requirement operations govern `spec.md`; task entries govern beads** (R2) —
   requirement→task coverage is 6.4% in this corpus and cannot be derived.
2. **Content-loss guard replaces the scenario-loss guard** (R3) — requirements
   here carry no acceptance criteria; block content is what exists.
3. **`SHRINK_FLOOR = 0.6`, non-configurable** (R4) — pinned on both sides by
   SC-008 and SC-008a.
4. **Verbatim storage, never normalized** (R1) — normalization is what breaks
   round-trips.
5. **Withdrawal detected at the `_find_existing_epic` seam** (R6) — the only
   point holding both maps; no extra `bd` queries.
6. **Compute-then-write for atomicity** (R8) — a jj operation restore would turn
   a file edit into a VCS operation, which this is not.
7. **`confirmation-required` for the refusal** (R9) — an existing `ErrorKind`
   that means exactly this; no taxonomy widening.

### What this feature does *not* touch

- No Burr graph, no `@action`, no squadron, **no agent** — there is no model
  call anywhere in the feature.
- No change to `refuel`'s behavior on a repository without deltas (FR-005c,
  SC-004).
- No new `ErrorKind`, no change to the shared envelope.
- No fix for `set_state`'s non-atomicity (R7). The hazard is *reported* via
  FR-020's unstamped-bead case; fixing it is a separate change with its own
  blast radius.

## Testing Strategy

- **SC-010 (round-trip) is written first and runs against the live `specs/`
  tree**, not a fixture copy. A fixture freezes the corpus at capture time, so
  the next spec written in an unanticipated style would pass the suite and fail
  in use. This test is the design's falsification mechanism: every claim in
  `requirement-block-grammar.md` is a claim about real files, and a wrong one
  fails here rather than corrupting a spec.
- **The content-loss guard is tested on both sides.** SC-008 proves it catches
  truncation; **SC-008a proves it does not fire on ordinary tightening**. Only
  the second one can fail in a way that matters — a guard that fires on routine
  edits trains authors to mark everything, which is indistinguishable from
  having no guard.
- **The refusal is proved by snapshot**, like 058's read-only test: capture
  `git status --porcelain`, a content hash of both artifacts, and the full bead
  list before and after every refusing path, and assert byte-identical.
- **Withdrawal is proved against real bead state** — an epic with one closed,
  one in-progress, and one open-unstarted bead, asserting exactly one closes.

## Complexity Tracking

No constitutional violations require justification.
