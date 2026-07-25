# Tasks: Conditional Landing on the Assumption Frontier

**Input**: Design documents from `/specs/052-conditional-landing/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — the project constitution mandates Test-First
(red-green-refactor); every test task is written and observed failing before
its implementation task.

**Organization**: Tasks are grouped by user story so each story is an
independently testable increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 (frontier gate + verification state), US2 (provenance report), US3 (mid-flight answering)

## Path Conventions

Single project: `src/maverick/`, `tests/` at repository root (per plan.md).

---

## Phase 1: Setup

**Purpose**: Confirm a green baseline so red tests are unambiguously ours.

- [X] T001 Run `make check` on a clean tree and confirm it passes; note any pre-existing failures (constitution: fix what you find — they get fixed, not stepped around)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The read-side ledger surface (full-entry materialization) that
both the gate (US1) and the report (US2) consume. No user story can start
until this is done.

**⚠️ CRITICAL**: US1 and US2 both build on `report_entries()` and the new
model types.

- [X] T002 [P] Add failing unit tests for `AssumptionReportEntry` (bucket derivation open/resolved/waived, `affected_change_ids` merge + dedup, `blocks_landing` incl. low severity and pending_reconcile) and the `LandVerification` StrEnum vocabulary in tests/unit/assumptions/test_models.py
- [X] T003 [P] Add failing unit tests for `ledger.report_entries()` (all-status query incl. closed beads, legacy `assumption-review` synthesis, state-key materialization of answer/waiver/reconcile fields, `pending_reconcile` flag sourced from `answered_unreconciled_entries`) in tests/unit/assumptions/test_ledger_frontier.py
- [X] T004 Implement `AssumptionReportEntry`, `LandFrontier`, `LandVerification` per data-model.md in src/maverick/assumptions/models.py
- [X] T005 Implement `report_entries(client)` in src/maverick/assumptions/ledger.py (reuse `_record_from_details`/`_legacy_record_from_details` + `_ALL_STATUS_TASK_FILTER` pattern; one bd sweep, no per-entry queries)
- [X] T006 Re-export the new public surface from src/maverick/assumptions/__init__.py and confirm T002–T003 tests go green

**Checkpoint**: `report_entries()` returns complete typed entries — user
stories can begin (US1 and US2 in parallel if staffed; US3 is independent of
both after this phase).

---

## Phase 3: User Story 1 — Land gated on the assumption frontier with an explicit verification state (Priority: P1) 🎯 MVP

**Goal**: Land refuses while any entry is open (any severity) or pending
reconciliation; successful lands are classified verified / conditionally
verified; bulk waive keeps the strict gate workable.

**Independent Test**: Seed low/medium/high entries; land blocks on all three
open (incl. low-only); answer two + waive one → lands as conditionally
verified; answer all → verified; no bypass flag exists (quickstart Scenarios
1 and 3).

### Tests for User Story 1 (write first, observe failing)

- [X] T007 [P] [US1] Add failing unit tests for `frontier(entries)` and `classify(entries)` (BLOCKED on open-low; BLOCKED on pending_reconcile; terminal reconcile states don't block; waived-only → CONDITIONALLY_VERIFIED; all-answered and zero-entries → VERIFIED) in tests/unit/assumptions/test_land_report.py
- [X] T008 [P] [US1] Extend tests/unit/cli/test_land_command.py `TestAssumptionGate`: open low-severity entry blocks with non-zero exit; pending-reconciliation entry blocks with `maverick reconcile` hint; waived-only frontier lands with "Conditionally verified" output and exit 0; all-answered lands with "Verified"; bd-unavailable still degrades open with warning and no classification; `--dry-run` exits non-zero when blocked on **all three curation paths** — including agent curation, whose current early `SystemExit(SUCCESS)` (land.py:332-334) pre-empts the gate exit today (pre-existing bug, analysis I1); no-bypass help test still passes
- [X] T009 [P] [US1] Add failing unit tests for `ledger.bulk_waive()` (spec+severity selection defaults to low only, legacy included only with medium, open-only selection, per-entry waiver metadata, zero-match returns empty, partial-failure aggregation) in tests/unit/assumptions/test_ledger_resolve.py
- [X] T010 [P] [US1] Extend tests/unit/cli/test_review_command.py: bulk waive via `--spec` + `--waive`; `BEAD_ID` and `--spec` mutually exclusive; `--spec` without `--waive` errors; `--spec` with `--answer` errors; zero matches exits 0 with message; partial failure exits non-zero listing failures

### Implementation for User Story 1

- [X] T011 [US1] Create src/maverick/assumptions/land_report.py with pure `frontier(entries) -> LandFrontier` and `classify(entries) -> LandVerification` per data-model.md rules (T007 green)
- [X] T012 [US1] Swap `_check_assumption_gate` in src/maverick/cli/commands/land.py to the frontier: build entries via `report_entries()`, block on `LandFrontier.is_empty is False`, render blocked table with per-row action hints (`maverick review <id>` for open, `maverick reconcile` for pending), print classification line on success, preserve degrade-open behavior, and fix the dry-run exit-code flow so `gate_blocks` determines the final exit on all curation paths — `_agent_curate`'s dry-run `SystemExit(SUCCESS)` must not pre-empt a blocked gate (T008 green)
- [X] T013 [US1] Implement `ledger.bulk_waive(client, *, owner_spec, severities, reason, waived_by)` in src/maverick/assumptions/ledger.py looping the existing `waive()` (T009 green)
- [X] T014 [US1] Make `BEAD_ID` optional and add `--spec` / repeatable `--severity` (default low) to src/maverick/cli/commands/review.py per contracts/cli-review-bulk-waive.md, with validation and per-entry failure reporting (T010 green)
- [X] T015 [US1] Extend tests/integration/test_assumption_ledger_flow.py (real bd + jj): low-severity entry blocks land until waived; bulk waive clears several low entries in one invocation; frontier-empty-with-waivers classifies conditionally verified

**Checkpoint**: US1 fully functional — strict gate + states + bulk waive,
independently verifiable via quickstart Scenarios 1 and 3.

---

## Phase 4: User Story 2 — Land report enumerates every assumption with full provenance (Priority: P2)

**Goal**: Every land evaluation (blocked, verified, conditional, dry-run)
renders and persists a grouped provenance report; PR-ready markdown is
generated and referenced by the mode hints.

**Independent Test**: Land a spec with one reconciled-answer entry, one
waived entry, and (blocked attempt) one open entry — report groups all three
with question / adopted answer / final answer / affected changes, and
`.maverick/runs/<id>/land-report.{json,md}` exist (quickstart Scenario 2).

### Tests for User Story 2 (write first, observe failing)

- [X] T016 [P] [US2] Add failing unit tests for `build_report()` + persistence: JSON output conforms to contracts/land-report-schema.md (schema_version, totals, per-spec counts, waiver only on waived rows, affected_change_ids includes reconcile correction, annotations, degraded flag); markdown contains classification banner, per-spec sections, omits empty buckets — in tests/unit/assumptions/test_land_report.py
- [X] T017 [P] [US2] Extend tests/unit/cli/test_land_command.py: report rendered on blocked AND successful AND `--dry-run` evaluations; artifact path printed; persistence failure degrades to warning without changing exit code; `--finalize` hint contains `--body-file .maverick/runs/<id>/land-report.md`; zero-entry evaluation prints "No assumptions adopted"
- [X] T018 [US2] Implement `LandReport` / `SpecReportSection` frozen dataclasses with `to_dict()` and `build_report(entries, verification, *, run_id, dry_run, degraded)` in src/maverick/assumptions/land_report.py (T016 partially green)
- [X] T019 [US2] Implement persistence in src/maverick/assumptions/land_report.py: atomic `land-report.json` via `maverick.utils.atomic` + `land-report.md` renderer per contracts/land-report-schema.md (T016 fully green)
- [X] T020 [US2] Wire into src/maverick/cli/commands/land.py: mint 8-hex land run-id, render grouped Rich report in all outcomes, persist both artifacts on every evaluation, update `--eject`/`--finalize`/default hints to reference the markdown artifact (T017 green)
- [X] T021 [US2] Extend tests/integration/test_assumption_ledger_flow.py: full provenance round-trip — answer an entry, change the answer, reconcile, land: report row shows both original and correction change ids plus final answer; waived row carries who/when/why

**Checkpoint**: US1 + US2 together deliver the complete landing contract;
report is the audit trail for the states introduced in US1.

---

## Phase 5: User Story 3 — Mid-flight answers trigger reconcile without stopping the drain loop (Priority: P3)

**Goal**: A running fly detects answers at every bead boundary, runs the
reconcile workflow in-process (excluding itself from the concurrent-fly
guard), never stalls or crashes the drain loop, and processes everything
detected before the run completes.

**Independent Test**: Drive the Burr graph with stubbed squadrons: enqueue a
changed answer between beads → reconcile pass fires at the boundary, later
beads still complete, outcome recorded; failure and graceful-stop paths leave
the loop unharmed (quickstart Scenario 4 for the manual version).

### Tests for User Story 3 (write first, observe failing)

- [X] T022 [P] [US3] Add failing unit test for `ReconcileConfig.mid_flight` (default True, `maverick.yaml` `reconcile.mid_flight: false` parses) in tests/unit/config/test_reconcile_config.py
- [X] T023 [P] [US3] Extend tests/unit/workflows/reconcile/test_workflow.py: `_find_flying_run` ignores the excluded run id but still raises on a *different* `"flying"` run; `active_fly_run_id` input threads through `_run`; omitted input preserves existing guard behavior
- [X] T024 [P] [US3] Add failing unit tests for `run_mid_flight_pass()` in tests/unit/workflows/fly_beads/test_mid_flight.py: skip outcomes for disabled / graceful-stop / none-detected; non-empty detection invokes `ReconcileWorkflow` with `{run_id, cwd, dry_run: False, active_fly_run_id}`; progress events forwarded to the fly event sink; `WorkflowError` from the child → `MidFlightOutcome(error=…)` + warning event, never raises; detection query failure treated as none-detected + warning
- [X] T025 [P] [US3] Extend tests/unit/workflows/fly_beads/test_burr_graph.py (StubFlySquadron pattern): `reconcile_answers` runs on the `record_outcome → select_next_bead` and `abandon_bead → select_next_bead` edges and once on the loop-exit path before `aggregate_review`; a boundary pass does not prevent the next bead from being selected

### Implementation for User Story 3

- [X] T026 [P] [US3] Add `mid_flight: bool = True` to `ReconcileConfig` in src/maverick/config.py (T022 green)
- [X] T027 [P] [US3] Add optional `active_fly_run_id` input to `ReconcileWorkflow._run` and `exclude_run_id` parameter to `_find_flying_run` in src/maverick/workflows/reconcile/workflow.py (T023 green)
- [X] T028 [US3] Create src/maverick/workflows/fly_beads/mid_flight.py: `MidFlightOutcome` frozen dataclass + `run_mid_flight_pass(*, cwd, config, fly_run_id, event_sink)` per contracts/mid-flight-reconcile.md (T024 green; depends on T026 + T027)
- [X] T029 [US3] Add thin `reconcile_answers` Burr action delegating to `run_mid_flight_pass` in src/maverick/workflows/fly_beads/actions.py (thread fly run-id + config through Burr state; no logic in the action body)
- [X] T030 [US3] Splice the action into the graph edges + final loop-exit pass in src/maverick/workflows/fly_beads/burr_graph.py and thread the fly run id from src/maverick/workflows/fly_beads/workflow.py (T025 green)
- [X] T031 [US3] End-to-end graph scenario in tests/unit/workflows/fly_beads/test_mid_flight.py: two-bead run with a changed answer appearing after bead 1 — pass fires at the boundary, bead 2 still implements and commits, final pass runs before `aggregate_review`, and a second detection returns nothing (idempotence, FR-015); additionally assert FR-012: a bead whose `blocks` edge is released by a mid-flight answer/waive (entry bead closed between boundaries) is returned by the stubbed `bd_select` and picked up by a later `select_next_bead` cycle in the same run

**Checkpoint**: All three stories functional; mid-flight passes feed the
US1 gate (entries reconciled in-run no longer block landing).

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T032 [P] Fix stale xoscar-era docstrings (`FlySupervisor` references) in src/maverick/workflows/fly_beads/graceful_stop.py and src/maverick/workflows/fly_beads/actions.py (research R11)
- [X] T033 [P] Update CLAUDE.md: note fly's drain loop is Burr-driven; document the land verification states + report artifacts, `reconcile.mid_flight`, and bulk waive under the `### land` / `### reconcile` / CLI workflow sections
- [X] T034 Run quickstart.md automated validation (`make test-fast`, `make test-integration`) and the full pre-push gate `make ci`; fix anything red

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: after Setup. Blocks US1 and US2 (both consume `report_entries()` + models). US3 technically depends only on Phase 2 being merged for none of its files — but keep the phase gate for a single review stream.
- **US1 (Phase 3)**: after Phase 2. No dependency on US2/US3.
- **US2 (Phase 4)**: after Phase 2. Reuses `classify()` from US1's T011 — if US2 starts first, T011 moves with it; in priority order this never arises.
- **US3 (Phase 5)**: after Phase 2 (independent of US1/US2 files entirely — touches workflows/config only).
- **Polish (Phase 6)**: after desired stories complete.

### Within Each Story

Tests (fail) → models/helpers → service/module → CLI/graph wiring →
integration. Same-file tasks are sequential: T012→T020 (land.py),
T011→T018→T019 (land_report.py), T005→T013 (ledger.py), T029→T030 order with
T028.

### Parallel Opportunities

- Phase 2: T002 ∥ T003 (different test files).
- US1 tests: T007 ∥ T008 ∥ T009 ∥ T010 (four different files).
- US2 tests: T016 ∥ T017.
- US3: T022 ∥ T023 ∥ T024 ∥ T025, then T026 ∥ T027.
- **Cross-story**: after Phase 2, US3 (workflows/config files) overlaps with
  US1/US2 (assumptions/CLI files) with zero file conflicts — two developers
  can run P1 and P3 concurrently.

## Parallel Example: User Story 1

```bash
# Launch all US1 test tasks together (different files):
Task: "T007 unit tests for frontier()/classify() in tests/unit/assumptions/test_land_report.py"
Task: "T008 land gate CLI tests in tests/unit/cli/test_land_command.py"
Task: "T009 bulk_waive ledger tests in tests/unit/assumptions/test_ledger_resolve.py"
Task: "T010 review bulk-waive CLI tests in tests/unit/cli/test_review_command.py"
# Then implement sequentially where files are shared:
# T011 (land_report.py) ∥ T013 (ledger.py) → T012 (land.py) ∥ T014 (review.py) → T015
```

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1 → Phase 2 → Phase 3 (US1).
2. **STOP and VALIDATE**: quickstart Scenarios 1 + 3 — strict gate, states,
   bulk waive. This alone changes landing semantics visibly and is
   shippable.

### Incremental Delivery

1. + US2 → the states gain their audit trail (report + artifacts + PR body).
   Validate with quickstart Scenario 2.
2. + US3 → the human-latency loop closes (mid-flight reconcile). Validate
   with quickstart Scenario 4.
3. Polish → docs + full `make ci`.

Each story lands without breaking the previous ones; US3 touches disjoint
files and can be developed in parallel with US1/US2 after Phase 2.

## Notes

- Constitution: TDD is mandatory — every test task must be observed failing
  before its paired implementation task is written.
- `assumptions/` must not import workflow/CLI modules (package charter);
  `land_report.py` stays pure of Rich/Click.
- No new bypass flags on land — `test_help_exposes_no_bypass_flag` guards
  this; do not weaken it.
- Commit after each task or logical group (bead-sized commits).
