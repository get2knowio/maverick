# Tasks: Learned Assumption Resolution

**Input**: Design documents from `/specs/055-learned-assumption-resolution/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — the constitution (Principle V) mandates red-green TDD. Every
test task MUST be observed failing before its implementation task lands.

**Organization**: Grouped by user story so each story is an independently testable
increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on an incomplete task)
- **[Story]**: US1–US4, mapping to spec.md's prioritized stories
- Paths are repository-relative; single-project layout per plan.md

---

## Phase 1: Setup

**Purpose**: Confirm a clean baseline — no new project scaffolding is needed (all
work lands in existing packages).

- [X] T001 Verify clean baseline: run `make check` on the feature branch and confirm green before any change; note the runway/assumptions test layout (`tests/unit/runway/`, `tests/unit/assumptions/`, `tests/unit/workflows/fly_beads/`) for the new test modules below

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The pure matching module — every story consumes it (US1 stores
normalized questions; US2 scores; US3 folds feedback penalties; US4 gates on its
threshold constant).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 [P] Write failing tests for the matching module in `tests/unit/assumptions/test_matching.py`: `normalize_question` (casefold, strip punctuation, collapse whitespace — exact clarify-Q1 semantics), token extraction (drop 1-char tokens), `base_score` determinism and [0,1] bounds (SequenceMatcher/Jaccard 50/50 blend, empty-token-set guard), `PRESENTATION_THRESHOLD == 0.75`, `REJECTION_PENALTY == 0.30`, effective-confidence fold (`base - 0.30 * max(0, rejections - acceptances)`; assert one net rejection drops a base of 1.0 below the presentation threshold — the FR-015 suppression guarantee), and the deterministic best-candidate comparator (confidence desc, resolved_at desc, source_entry_id asc)
- [X] T003 Implement `src/maverick/assumptions/matching.py` per `contracts/decision-records.md`: pure sync module with `normalize_question`, `base_score`, `PRESENTATION_THRESHOLD: Final = 0.75`, `REJECTION_PENALTY: Final = 0.30`, effective-confidence helper, and best-candidate selection; no I/O, no model calls, full type hints, Google docstrings

**Checkpoint**: `make test-fast` green including `test_matching.py` — user stories can begin.

---

## Phase 3: User Story 1 — Terminal ledger outcomes become durable decision records (Priority: P1) 🎯 MVP

**Goal**: Every human answer/waive/re-answer persists a `DecisionRecord` in the
git-committed runway store, surviving specs and runs; machine waives are excluded;
failures degrade to warnings.

**Independent Test**: Answer, waive, and re-answer entries via `maverick review`;
verify `.maverick/runway/decisions.jsonl` lines with full provenance (quickstart
Scenario 1), persistence across runs, and zero records from a scheduler auto-waive.

### Tests for User Story 1 ⚠️ write first, observe failing

- [X] T004 [P] [US1] Write failing tests in `tests/unit/runway/test_store_decisions.py`: `DecisionRecord` to_dict/from_dict round-trip; `RunwayStore.append_decision`/`get_decisions` (append-only, filter by `source_entry_id`); `initialize()` touches `decisions.jsonl` and `match-feedback.jsonl`; malformed lines skipped with warning; `consolidate_runway` leaves both files byte-identical (regression binding to the real consolidation path)
- [X] T005 [P] [US1] Write failing tests in `tests/unit/cli/commands/review/test_decision_capture.py` (mirror the existing review CLI test layout): `--answer` and `--waive` each append one collapsed-correct record post-write; re-answer appends a second record for the same `source_entry_id` (latest authoritative via `collapse_decisions`); bulk waive appends one record per waived entry; a store write failure emits `[yellow]Warning:[/]` and the review action still succeeds (FR-004); `notify`'s `_execute_auto_waives` path appends nothing (FR-005)

### Implementation for User Story 1

- [X] T006 [P] [US1] Add frozen `DecisionRecord` Pydantic model to `src/maverick/runway/models.py` with fields per data-model.md (source_entry_id, question, normalized_question, adopted_answer, resolution_type, resolution, severity, owner_spec, resolved_by, resolved_at) and `to_dict`/`from_dict`, matching sibling conventions
- [X] T007 [US1] Add `_DECISIONS_FILE`/`_MATCH_FEEDBACK_FILE` constants, `append_decision`, `get_decisions`, and `initialize()` touch for both files to `src/maverick/runway/store.py`, following the existing `_append_jsonl`/`_read_jsonl` pattern (files at store root, NOT under `episodic/`)
- [X] T008 [US1] Create `src/maverick/assumptions/suggestions.py` with `record_decision(store, entry, *, resolution_type, resolution, resolved_by)` (best-effort: catches store errors, logs warning, never raises) and `collapse_decisions(records)` (group by `source_entry_id`, latest `resolved_at` authoritative), using `matching.normalize_question` for the stored `normalized_question`
- [X] T009 [US1] Wire decision capture into `_review_ledger_entry` in `src/maverick/cli/commands/review/entry_actions.py`: after a successful ledger write and outside the JSON error handler (the `_project_after_write` pattern), build the store from the command's cwd and call `record_decision`; `resolved_by` from the existing git user-name resolution
- [X] T010 [US1] Wire decision capture into `_bulk_waive_flow` in `src/maverick/cli/commands/review/entry_actions.py`: one record per successfully waived entry, same fail-soft contract

**Checkpoint**: US1 fully functional — quickstart Scenario 1 passes; MVP deliverable
as a standalone audit trail.

---

## Phase 4: User Story 2 — Prior decisions surface as suggested resolutions (Priority: P2)

**Goal**: New assumptions matched against the corpus carry a persisted suggestion
with provenance, projected on every entry-row surface and presented as the skill's
default; the land gate is untouched.

**Independent Test**: Seed a decision record, record a closely matching assumption,
verify the `suggestion` object in `review --list --json` with provenance and
`confidence >= 0.75`, `null` on non-matching entries, and unchanged land blocking
(quickstart Scenario 2).

### Tests for User Story 2 ⚠️ write first, observe failing

- [X] T011 [P] [US2] Write failing tests in `tests/unit/assumptions/test_suggestions.py`: `evaluate_suggestion` (below-threshold ⇒ None; self-match excluded; collapse applied so only the latest version of a re-answered decision matches; deterministic tie-break; exactly one suggestion); `attach_suggestions` (persists single JSON `assumption_suggestion` key via one `set_state` call; store-unavailable ⇒ no-op with debug log; set_state failure ⇒ warning, other entries still processed); `backfill_suggestions` (fills only entries with no stored key; never replaces an existing or unparseable stored value); and the SC-006 performance bound — evaluating one entry against a generated 500-record corpus (with feedback) completes in well under 1 second (assert < 1s wall clock)
- [X] T012 [P] [US2] Write failing tests in `tests/unit/assumptions/test_suggestion_projection.py`: `Suggestion` dataclass JSON round-trip; `report_entry_from_details` parses `assumption_suggestion` into `AssumptionReportEntry.suggestion` and `assumption_auto_resolved` into `.auto_resolved` (unparseable JSON ⇒ None + debug log); `entry_to_dict` emits `suggestion` object / `null` and `auto_resolved` bool; `_annotations` gains `"auto-resolved"`; land report `_entry_to_dict` alias picks the keys up unchanged; and the FR-013 guard — an open entry carrying a suggestion still projects `blocks_landing: true` and `frontier()`/`classify()` treat it identically to a suggestion-less open entry
- [X] T013 [P] [US2] Write failing tests in `tests/unit/cli/commands/review/test_listing_backfill.py`: `run_list` back-fills suggestions for entries lacking one before building rows (corpus loaded once), skips silently when the store is unavailable, and the human table marks suggested entries; JSON rows carry the new keys
- [X] T014 [P] [US2] Write failing tests for the recording call sites: extend `tests/unit/workflows/fly_beads/test_runway_recording.py` (or the `record_assumptions` action tests) to assert `attach_suggestions` is invoked with the newly recorded entries and that its failure is non-fatal to the action; add the equivalent assertion for `record_standalone_assumption` follow-up in the spec_chain workflow tests

### Implementation for User Story 2

- [X] T015 [US2] Add to `src/maverick/assumptions/models.py`: `KEY_SUGGESTION = "assumption_suggestion"`, `KEY_AUTO_RESOLVED = "assumption_auto_resolved"`, frozen `Suggestion` dataclass (resolution, resolution_type, source_entry_id, source_spec, resolved_at, confidence, computed_at) with JSON encode/decode helpers, and `AssumptionReportEntry.suggestion: Suggestion | None = None` / `auto_resolved: bool = False`
- [X] T016 [US2] Wire `KEY_SUGGESTION`/`KEY_AUTO_RESOLVED` into `report_entry_from_details` in `src/maverick/assumptions/ledger.py` as a minimal delta — the JSON decode/degrade logic lives in the `Suggestion` helper from T015 (`models.py`), and `ledger.py` (already past Principle XI's 1000-LOC hard stop) gains only the two field-populating call lines (degrade unparseable to absent with debug log; legacy entries always None/False)
- [X] T017 [US2] Extend `entry_to_dict` and `_annotations` in `src/maverick/assumptions/serialize.py` with `suggestion`/`auto_resolved` keys per `contracts/entry-row-suggestion.md`
- [X] T018 [US2] Implement `evaluate_suggestion`, `attach_suggestions`, and `backfill_suggestions` in `src/maverick/assumptions/suggestions.py` per research R5 (corpus + feedback loaded once per batch; single-key atomic `set_state` write; full degradation matrix from research R11)
- [X] T019 [US2] Call `attach_suggestions` from the `record_assumptions` action in `src/maverick/workflows/fly_beads/actions.py` after the recording loop (build `RunwayStore` from the action's `cwd`; failures logged, never fail the action)
- [X] T020 [US2] Call `attach_suggestions` after the `record_standalone_assumption` loop in `src/maverick/workflows/spec_chain/workflow.py` (user-checkout cwd, same non-fatal contract)
- [X] T021 [US2] Add back-fill + suggested-entry marker to `run_list` in `src/maverick/cli/commands/review/listing.py` (back-fill before `_filter_and_sort`; store unavailable ⇒ silent skip)
- [X] T022 [US2] Update the sweep in `src/maverick/skills/review_console/SKILL.md` per `contracts/skill-review-console-delta.md`: suggestion first with `(Recommended — prior decision from <spec>, <date>)`, adopted answer second without the suffix, waive-sourced suggestion pre-fills the reason, provenance always displayed

**Checkpoint**: US1 + US2 independently green — quickstart Scenarios 1–2 pass.

---

## Phase 5: User Story 3 — Rejected suggestions stop being suggested (Priority: P3)

**Goal**: Resolving contrary to a suggestion records a rejection that lowers the
pairing's effective confidence below the presentation threshold on repeat;
acceptances are recorded for auditability.

**Independent Test**: Present a suggestion, resolve differently, record a
same-shape assumption, verify no suggestion (or lowered confidence) and the
`rejected` feedback line (quickstart Scenario 3).

### Tests for User Story 3 ⚠️ write first, observe failing

- [X] T023 [P] [US3] Write failing tests: `MatchFeedbackRecord` round-trip + `append_match_feedback`/`get_match_feedback` in `tests/unit/runway/test_store_decisions.py`; feedback classification in `tests/unit/assumptions/test_suggestions.py` (accepted iff type matches AND normalized resolution text equals normalized suggestion text; waive-over-suggested-answer ⇒ rejected; answer-over-suggested-waive ⇒ rejected); end-to-end suppression (one net rejection drops the pairing 0.30 — below the presentation threshold even from a perfect base score, per FR-015; a subsequent acceptance restores it); capture wiring in `tests/unit/cli/commands/review/test_decision_capture.py` (single answer/waive + bulk waive each append feedback only when the entry carried a stored suggestion)

### Implementation for User Story 3

- [X] T024 [P] [US3] Add frozen `MatchFeedbackRecord` model (normalized_question, source_entry_id, outcome, recorded_at) to `src/maverick/runway/models.py`
- [X] T025 [US3] Add `append_match_feedback`/`get_match_feedback` to `src/maverick/runway/store.py` (same JSONL conventions; file already touched by T007's `initialize()`)
- [X] T026 [US3] Add `classify_feedback(entry, suggestion, *, resolution_type, resolution) -> Literal["accepted","rejected"]` and `record_feedback(store, entry, *, accepted)` to `src/maverick/assumptions/suggestions.py`, and make `evaluate_suggestion` consume the feedback fold (penalty per pairing) — the parameter exists since T018 with an empty default, so US2 behavior is unchanged until feedback exists
- [X] T027 [US3] Wire feedback capture into `src/maverick/cli/commands/review/entry_actions.py`: in `_review_ledger_entry` and `_bulk_waive_flow`, when the resolved entry carried a stored suggestion, classify and append feedback alongside the decision record (same fail-soft block)

**Checkpoint**: US1–US3 green — quickstart Scenarios 1–3 pass.

---

## Phase 6: User Story 4 — Opt-in auto-resolution for high-confidence low-severity entries (Priority: P4)

**Goal**: A default-off policy auto-waives low-severity entries at recording time
when effective confidence ≥ the configured threshold; stamped `maverick-resolver`
with provenance; land classifies at most conditionally-verified (existing
`classify()` — no gate changes); human override re-arms the entry and records a
rejection.

**Independent Test**: Enable the policy, record a matching low entry, verify
auto-waive with provenance + `auto_resolved: true`, conditionally-verified land,
medium-severity ineligibility, and the override path (quickstart Scenario 4).

### Tests for User Story 4 ⚠️ write first, observe failing

- [X] T028 [P] [US4] Write failing tests in `tests/unit/test_config.py` (or the existing config test module): `AssumptionResolutionConfig`/`AutoResolvePolicyConfig` defaults, `confidence_threshold` bounds (`0.5` fails, `0.75` passes, `1.0` passes), absent block ⇒ None, and the drift-pin asserting the Field's `ge` equals `matching.PRESENTATION_THRESHOLD`
- [X] T029 [P] [US4] Write failing tests in `tests/unit/assumptions/test_suggestions.py` + `tests/unit/cli/commands/review/test_decision_capture.py`: auto-resolve fires only for severity==low with policy enabled and confidence ≥ threshold (medium/high/legacy ineligible); waives via `ledger.waive` with `waived_by="maverick-resolver"` and a rationale citing source entry/spec/date; sets `assumption_auto_resolved="true"`; writes NO decision record and NO feedback; back-fill path never auto-resolves; `--answer` on an auto-resolved entry bypasses `ALREADY_RESOLVED` (human-waived still refused) and records a `rejected` feedback line for the auto-resolving pairing
- [X] T030 [P] [US4] Write failing rendering tests: auto-resolved entry counts in the `waived` bucket, `classify()` returns `CONDITIONALLY_VERIFIED`, land-report markdown row shows the `maverick-resolver` waiver and `auto-resolved` annotation — extend the existing `tests/unit/assumptions/` land-report tests

### Implementation for User Story 4

- [X] T031 [P] [US4] Add `AutoResolvePolicyConfig` and `AssumptionResolutionConfig` to `src/maverick/config.py` and mount `resolution` on `AssumptionsConfig`, per `contracts/config-schema.md` — use the literal bound `ge=0.75` (no import from `assumptions.matching`; the T028 drift-pin test is what keeps the literal equal to `PRESENTATION_THRESHOLD`)
- [X] T032 [US4] Implement the auto-resolve branch in `attach_suggestions` in `src/maverick/assumptions/suggestions.py`: `_AUTO_RESOLVE_ACTOR: Final = "maverick-resolver"`; eligibility per data-model invariant 4; waive + `KEY_AUTO_RESOLVED` write; failure degrades to warning leaving the entry open with its suggestion (research R11); recording-time only — `backfill_suggestions` never auto-resolves
- [X] T033 [US4] Thread the resolution policy config into the `attach_suggestions` call sites: `record_assumptions` bind in `src/maverick/workflows/fly_beads/actions.py`/`burr_graph.py` and the spec_chain call in `src/maverick/workflows/spec_chain/workflow.py`
- [X] T034 [US4] Update the `ALREADY_RESOLVED` pre-check in `src/maverick/cli/commands/review/entry_actions.py`: waived entries with `auto_resolved` are re-answerable (FR-020); on override, record the `rejected` feedback (uses T026) and let the normal answer path re-arm reconcile

**Checkpoint**: All four stories independently functional — quickstart Scenarios 1–4 pass.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T035 [P] Update `CLAUDE.md`: extend the assumption-ledger / review-console sections with decision records, suggestions, the `assumptions.resolution` block, and the `maverick-resolver` actor; note the runway `decisions.jsonl`/`match-feedback.jsonl` files are consolidation-exempt
- [X] T036 [P] Run all five `quickstart.md` scenarios end-to-end against a scratch repository (degradation Scenario 5 included) and record outcomes in the PR description — report faithfully anything not exercised
- [X] T037 Run `make format-fix && make ci`; verify Principle XI budgets (`matching.py` and `suggestions.py` each well under 500 LOC; `ledger.py` grew only by the state-key parse) and fix any collateral failures encountered (Principle XII)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: none
- **Phase 2 (Foundational)**: after Phase 1 — BLOCKS all stories (matching module)
- **US1 (Phase 3)**: after Phase 2 only
- **US2 (Phase 4)**: after Phase 2; consumes US1's `DecisionRecord`/store methods (T006–T008) — start its test tasks in parallel with US1 implementation if desired, but T018 depends on T007/T008
- **US3 (Phase 5)**: after US2 (feedback folds into `evaluate_suggestion`, capture rides `entry_actions` wiring from T009/T010)
- **US4 (Phase 6)**: after US2; T034's override-feedback depends on US3's T026
- **Phase 7 (Polish)**: after all delivered stories

### Within each story

Tests first and observed failing → models → store/library → CLI/workflow wiring →
checkpoint. `runway/models.py` and `store.py` are touched by US1 and US3 —
sequential within/across those stories (T024/T25 after T006/T007), hence no [P] on
T025.

### Parallel opportunities

- T002 alongside T001
- US1: T004 ∥ T005 (different files); T006 ∥ nothing until tests exist
- US2: T011 ∥ T012 ∥ T013 ∥ T014 (four different test files)
- US4: T028 ∥ T029 ∥ T030, then T031 ∥ (T032 → T033 → T034)
- Polish: T035 ∥ T036

## Parallel Example: User Story 2

```bash
# Launch all US2 test authoring together (different files):
Task: "Failing tests for evaluate/attach/backfill in tests/unit/assumptions/test_suggestions.py"
Task: "Failing tests for projection in tests/unit/assumptions/test_suggestion_projection.py"
Task: "Failing tests for listing back-fill in tests/unit/cli/commands/review/test_listing_backfill.py"
Task: "Failing tests for recording call sites in tests/unit/workflows/fly_beads/test_runway_recording.py"
```

## Implementation Strategy

**MVP first (US1)**: Phases 1–3 deliver a durable, auditable decision corpus with
zero behavior change to review/land — independently valuable and shippable.

**Incremental delivery**: US2 turns the corpus into visible suggestions (the
feature's payoff); US3 makes them trustworthy; US4 is the deliberate, revocable
automation step. Each checkpoint maps to a quickstart scenario, so `maverick fly`
can stop and validate after any phase.

## Notes

- Zero model calls anywhere — any task that seems to need one is mis-scoped (Guardrail X.10)
- The land gate (`classify()`, `frontier()`) is intentionally untouched; a diff there is a red flag
- Commit after each task or logical group; every test task must go red before its implementation task goes green
