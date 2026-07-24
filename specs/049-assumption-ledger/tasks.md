# Tasks: Assumption Ledger

**Input**: Design documents from `/specs/049-assumption-ledger/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — the project constitution (Principle V, Test-First) mandates
red-green-refactor; every story writes failing tests before implementation.

**Organization**: Tasks grouped by user story (US1 record+stamp, US2 severity
policy, US3 queue surfacing, US4 reporting) so each story is independently
implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1–US4 from spec.md
- Run `make test-fast` / `make lint typecheck` while iterating; `make ci` before push

## Phase 1: Setup

**Purpose**: Package skeleton so all subsequent tasks have a home

- [X] T001 Create `src/maverick/assumptions/` package skeleton (`__init__.py`, empty `models.py`, `ledger.py`, `report.py`, `errors.py` with module docstrings) and `tests/unit/assumptions/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Typed primitives every story depends on — enum member, payload
models, domain dataclasses, and the one-canonical-wrapper cleanup that
validates the enum end-to-end.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 [P] Write failing tests for `DependencyType.DISCOVERED_FROM` (enum member value `"discovered-from"`, accepted by `BeadDependency`/`add_dependency` command construction) in `tests/unit/beads/test_models.py` and `tests/unit/beads/test_client.py`
- [X] T003 [P] Write failing tests for `AssumptionPayload` (required question/adopted_answer, alternatives default, severity coercion unknown/absent→`medium` with defaulted flag exposed, never raising on bad severity) and for the additive `assumptions` field on `SubmitImplementationPayload`/`SubmitReviewPayload`/`SubmitFixResultPayload` (absent field → empty tuple; existing payload dicts still validate; registry keys unchanged) in `tests/unit/test_payloads_assumptions.py` — per `contracts/payloads.md`
- [X] T004 [P] Write failing tests for `maverick.assumptions.models` (Severity StrEnum; frozen `AssumptionRecord` with `change_ids`/`is_legacy`; `PerSpecAssumptionCounts`; state-key/label constants exported, no magic strings) in `tests/unit/assumptions/test_models.py` — per `contracts/ledger-api.md`
- [X] T005 Add `DISCOVERED_FROM = "discovered-from"` to `DependencyType` in `src/maverick/beads/models.py` (T002 green)
- [X] T006 Implement `AssumptionPayload` and add `assumptions: tuple[AssumptionPayload, ...] = ()` to the three submit payloads in `src/maverick/payloads.py` (T003 green)
- [X] T007 Implement `src/maverick/assumptions/models.py` (Severity, AssumptionRecord, PerSpecAssumptionCounts, `ASSUMPTION_LABEL` + `KEY_*` constants) and `src/maverick/assumptions/errors.py` (`AssumptionLedgerError(MaverickError)`), re-export from `src/maverick/assumptions/__init__.py` (T004 green)
- [X] T008 Migrate the two raw `bd dep add ... --type discovered-from` call sites in `src/maverick/workflows/fly_beads/_commit.py:257-268,365-370` to `BeadClient.add_dependency` with `DependencyType.DISCOVERED_FROM`; update any affected tests in `tests/unit/workflows/fly_beads/` (research R11 cleanup)

**Checkpoint**: `make test-fast` green — foundation ready; user stories can begin.

---

## Phase 3: User Story 1 - Assumptions become structured ledger entries (Priority: P1) 🎯 MVP

**Goal**: Agent-reported assumptions become structured beads (question, answer,
alternatives, severity, owner spec, discovered-from edge) and get stamped with
jj change IDs at commit.

**Independent Test**: quickstart Scenario 1 — run fly with a stubbed
implementer payload containing an assumption; verify the bead's labels, state
keys, discovered-from edge, and post-commit `assumption_change_ids`; verify an
abandoned bead leaves an unstamped entry.

### Tests for User Story 1 (write first, ensure they FAIL)

- [X] T009 [P] [US1] Write failing tests for `record_assumption` — bead shape per data-model (labels/title/description/priority-by-severity/assignee/parent), owner-spec derivation (`speckit_feature` → `flight_plan_name` → epic-ID fallback), severity coercion + `assumption_severity_defaulted`, dedup by normalized question under the same epic (returns existing record, appends discovered-from edge), discovered-from edge wiring, `AssumptionLedgerError` on bd failure — in `tests/unit/assumptions/test_ledger_record.py` (stub BeadClient)
- [X] T010 [P] [US1] Write failing tests for `stamp_change_id` — appends to comma-joined `assumption_change_ids`, append-only + idempotent per (entry, change_id), partial per-entry failures reported in `StampResult` and NEVER raised — in `tests/unit/assumptions/test_ledger_stamp.py`
- [X] T011 [P] [US1] Write failing tests for the fly wiring — implement/review/fix actions accumulate payload `assumptions` into `pending_assumptions` (cleared on bead start), `record_assumptions` action creates entries + writes `recorded_assumption_ids` and warns-but-continues on ledger errors, `commit` action captures `commit_change_id` from `jj_commit_bead` and stamps recorded entries non-fatally — in `tests/unit/workflows/fly_beads/test_assumption_actions.py`

### Implementation for User Story 1

- [X] T012 [US1] Implement `record_assumption` (creation, owner-spec derivation, coercion, dedup, discovered-from edge; severity *policy* hooks land in US2) in `src/maverick/assumptions/ledger.py` (T009 green)
- [X] T013 [US1] Implement `stamp_change_id` + `StampResult` in `src/maverick/assumptions/ledger.py` (T010 green)
- [X] T014 [US1] Extend `implement`/`review`/fix-result handling in `src/maverick/workflows/fly_beads/actions.py` to append validated payload `assumptions` to a `pending_assumptions` state key; reset `pending_assumptions`, `recorded_assumption_ids`, and `commit_change_id` in `process_bead_start` so no bead stamps or re-records a previous bead's entries
- [X] T015 [US1] Add `record_assumptions` burr action in `src/maverick/workflows/fly_beads/actions.py` — calls `ledger.record_assumption` per pending assumption (deduped), writes `recorded_assumption_ids`, non-fatal warning path mirrors `create_human_bead`
- [X] T016 [US1] Wire `record_assumptions` into `src/maverick/workflows/fly_beads/burr_graph.py` between review/create_human_bead and commit (both routes reach commit through it); register new state keys and `.bind` params (cwd, epic_id, events)
- [X] T017 [US1] Fix `commit` action in `src/maverick/workflows/fly_beads/actions.py:1163-1203` to capture `jj_commit_bead`'s returned `change_id` into `commit_change_id` state and stamp `recorded_assumption_ids` via `stamp_change_id` (warn on stamp failure, never fail the commit) (T011 green)
- [X] T018 [P] [US1] Update implementer/reviewer/fixer prompt builders in `src/maverick/agents/` (and `src/maverick/agents/system_prompts/` where applicable) with the assumption-reporting instruction from `contracts/payloads.md` (question / adopted answer / alternatives / severity-by-blast-radius)
- [X] T019 [US1] Add integration test for quickstart Scenario 1 (record → commit → stamped entry with resolvable state; abandoned bead → unstamped entry) in `tests/integration/test_assumption_ledger_flow.py` (stubbed agents, real bd fixture pattern from existing integration tests)

**Checkpoint**: US1 fully functional — entries recorded, linked, and stamped. MVP.

---

## Phase 4: User Story 2 - Severity drives escalation policy (Priority: P2)

**Goal**: low = advisory (deferred), medium/high = land gate with no bypass,
high = `blocks` edge onto the next spec's epic; answer/waive releases blocks.

**Independent Test**: quickstart Scenarios 2–4 — low entry absent from
`bd ready` and land passes; medium entry blocks land until answered/waived;
high entry blocks the next spec's epic in `bd ready` and releases on resolve.

### Tests for User Story 2 (write first, ensure they FAIL)

- [X] T020 [P] [US2] Write failing tests for severity policy in `record_assumption` — low entries deferred (`bd defer`) at creation; high entries wire `blocks` edge onto an existing chained next epic; medium entries do neither — in `tests/unit/assumptions/test_ledger_policy.py`
- [X] T021 [P] [US2] Write failing tests for `answer` (non-empty text required, sets state, closes bead) and `waive` (reason required, records who/when/why, closes bead) in `tests/unit/assumptions/test_ledger_resolve.py`
- [X] T022 [P] [US2] Write failing tests for `open_blocking_entries` (open medium/high only; legacy escalation beads surfaced as severity=medium with `is_legacy=True`; answered/waived/closed excluded) and `open_high_entries_before` in `tests/unit/assumptions/test_ledger_query.py`
- [X] T023 [P] [US2] Write failing CLI tests for the land assumption gate — blocks with per-spec table + `maverick review <id>` hint and non-zero exit; passes when only low/resolved entries exist; `--dry-run` still evaluates; `--help` exposes no bypass flag — in `tests/unit/cli/test_land_command.py`
- [X] T024 [P] [US2] Write failing tests for `_chain_epic` — deterministic tail selection by `speckit_feature` NNN-prefix sort, and `blocks` edges wired from open high-severity entries of earlier specs onto the newly created epic — in `tests/unit/workflows/refuel_speckit/test_chain_epic.py`

### Implementation for User Story 2

- [X] T025 [US2] Implement severity policy in `src/maverick/assumptions/ledger.py`: defer low entries after creation; implement `next_chained_epic` (open epic with smallest `speckit_feature` NNN prefix strictly greater than the owning epic's; `None` for flight-plan epics) and wire the high-severity `blocks` edge when it returns an epic (T020 green)
- [X] T026 [US2] Implement `answer` and `waive` in `src/maverick/assumptions/ledger.py` (T021 green)
- [X] T027 [US2] Implement `open_blocking_entries` and `open_high_entries_before` in `src/maverick/assumptions/ledger.py` (T022 green)
- [X] T028 [US2] Add the pre-curation assumption gate to `src/maverick/cli/commands/land.py` (after the human-review manifest display at land.py:151, before curation; Rich table grouped by owning spec; exit non-zero; no bypass flag) per `contracts/cli.md` (T023 green)
- [X] T029 [US2] Extend `src/maverick/cli/commands/review.py` with answer/waive flows for `assumption`-labeled beads (prompt or options; empty answer/reason rejected; delegates to `ledger.answer`/`ledger.waive`; legacy beads keep current behavior)
- [X] T030 [US2] Update `_chain_epic` in `src/maverick/workflows/refuel_speckit/workflow.py:442-462`: sort open epics deterministically by `speckit_feature` NNN prefix and wire `blocks` edges from `open_high_entries_before` onto the new epic (T024 green)
- [X] T031 [US2] Add integration test for quickstart Scenarios 3–4 (medium blocks land → answer unblocks; high blocks next epic in `bd ready` → waive releases; high-on-last-spec degrades to medium) in `tests/integration/test_assumption_ledger_flow.py`

**Checkpoint**: Severity policy enforced end-to-end; US1 + US2 both work.

---

## Phase 5: User Story 3 - Human queue surfaces through bd (Priority: P3)

**Goal**: Open medium/high entries appear in `bd ready` as human work with
full decision context reachable from `maverick review`; agents keep skipping
them.

**Independent Test**: quickstart Scenario 5 — `bd ready` lists entries,
`maverick review <id>` shows question/answer/alternatives/severity/spec/
stamps/source, `select_next_bead` still skips them.

### Tests for User Story 3 (write first, ensure they FAIL)

- [X] T032 [P] [US3] Write failing tests for the review command's ledger display — question, adopted answer, alternatives, severity with `(defaulted)` marker, owning spec, change stamps or `unstamped`, discovered-from source — in `tests/unit/cli/test_review_command.py`
- [X] T033 [P] [US3] Add regression tests that ledger beads (new `assumption` label set) are skipped by `select_next_bead` in `tests/unit/library/actions/test_beads_actions.py` (existing select-next-bead test module)
- [X] T034 [P] [US3] Add regression tests that `brief --human` lists ledger entries with their state context in `tests/unit/cli/test_brief_command.py`

### Implementation for User Story 3

- [X] T035 [US3] Implement the full-context ledger display in `src/maverick/cli/commands/review.py` (reads via a `ledger` load helper returning `AssumptionRecord`; Rich formatting per CLI standards) (T032 green)
- [X] T036 [US3] Verify/adjust `_brief_human` in `src/maverick/cli/commands/brief.py` so ledger entries render alongside legacy escalation beads without error (new state keys shown when present) (T034 green)

**Checkpoint**: Human queue fully navigable; all three enforcement/queue stories done.

---

## Phase 6: User Story 4 - Per-spec assumption counts (Priority: P4)

**Goal**: `maverick brief` reports per-spec assumption counts (severity ×
open/answered/waived, legacy bucket, explicit zero rows) as a spec-quality
signal.

**Independent Test**: quickstart Scenario 6 — two specs (one with entries, one
without) both appear in the brief table and `--format json` output.

### Tests for User Story 4 (write first, ensure they FAIL)

- [X] T037 [P] [US4] Write failing tests for `per_spec_counts` — grouping by `assumption_owner_spec`, severity × status matrix, legacy bucket, zero rows for entry-less epics, deterministic ordering — in `tests/unit/assumptions/test_report.py`
- [X] T038 [P] [US4] Write failing CLI tests for the brief Assumptions section — default text table incl. zero rows, `--human` inclusion, `--format json` `assumption_counts` array, section omitted when bead store absent — in `tests/unit/cli/test_brief_command.py`

### Implementation for User Story 4

- [X] T039 [US4] Implement `per_spec_counts` in `src/maverick/assumptions/report.py` (T037 green)
- [X] T040 [US4] Add the Assumptions section to `src/maverick/cli/commands/brief.py` (text table, `--human` view, JSON output) per `contracts/cli.md` (T038 green)

**Checkpoint**: All four user stories independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T041 [P] Update `CLAUDE.md` (CLI Workflows section: land gate, review answer/waive, brief assumptions section) and add `docs/` notes if a docs page covers fly/land behavior
- [X] T042 [P] Add FR-013 legacy-compatibility integration coverage: a pre-feature escalation bead (old labels, no ledger state) flows through brief, review, and the land gate without errors in `tests/integration/test_assumption_ledger_flow.py`
- [X] T043 Execute quickstart.md scenarios end-to-end against a throwaway repo fixture; fix any drift between quickstart and behavior
- [X] T044 Run `make format-fix && make ci`; fix all failures (tree stays green per Constitution XII)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none — start immediately
- **Foundational (Phase 2)**: after T001; **blocks all stories** (enum, payloads, domain models)
- **US1 (Phase 3)**: after Phase 2 — the MVP; no dependency on other stories
- **US2 (Phase 4)**: after Phase 2; policy hooks (T025) extend `record_assumption` from T012, so schedule after US1's ledger core (T012–T013) if run sequentially
- **US3 (Phase 5)**: after Phase 2; display tasks touch `review.py` — coordinate with US2's T029 (same file) if parallelizing
- **US4 (Phase 6)**: after Phase 2; T040 touches `brief.py` — coordinate with US3's T036 (same file)
- **Polish (Phase 7)**: after all desired stories

### Key task-level dependencies

- T005–T007 unblock everything downstream; T008 needs T005
- T012 ← T009; T013 ← T010; T014–T017 ← T011 + T012 + T013; T016 ← T015; T017 ← T016
- T025 ← T012 + T020; T026 ← T021; T027 ← T022; T028 ← T023 + T027; T029 ← T026; T030 ← T024 + T027
- T035 ← T032 (+ record loading from T012); T036 ← T034
- T039 ← T037; T040 ← T038 + T039

### Parallel Opportunities

- Phase 2 test-writing: T002, T003, T004 in parallel (different files)
- US1 test-writing: T009, T010, T011 in parallel; T018 (prompts) parallel with T012–T017 (different files)
- US2 test-writing: T020–T024 all parallel (five different files)
- Cross-story: after Phase 2, US1 and the US2 CLI/refuel test authoring (T023, T024) can proceed concurrently; US3/US4 test authoring likewise
- Same-file collision watch: `actions.py` (T014, T015, T017 — sequential), `ledger.py` (T012, T013, T025–T027 — sequential), `review.py` (T029, T035), `brief.py` (T036, T040)

## Parallel Example: User Story 1

```bash
# Launch US1 test authoring together (three different files):
Task: "record_assumption tests in tests/unit/assumptions/test_ledger_record.py"
Task: "stamp_change_id tests in tests/unit/assumptions/test_ledger_stamp.py"
Task: "fly wiring tests in tests/unit/workflows/fly_beads/test_assumption_actions.py"

# Then implement sequentially where files collide (ledger.py, actions.py),
# with prompt updates in parallel:
Task: "Prompt-builder updates in src/maverick/agents/"
```

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1 + Phase 2 (T001–T008)
2. Phase 3 (T009–T019)
3. **STOP and VALIDATE**: quickstart Scenario 1 — entries recorded, linked, stamped
4. Ship: the ledger records everything even before policy/queue/report exist

### Incremental Delivery

1. + US2 → severity enforcement (land gate, next-epic blocking, answer/waive) → Scenarios 2–4
2. + US3 → queue navigability → Scenario 5
3. + US4 → per-spec quality signal → Scenario 6
4. Polish → legacy coverage, docs, `make ci`

Each increment leaves earlier stories fully working; nothing in a later story
rewrites an earlier contract.
