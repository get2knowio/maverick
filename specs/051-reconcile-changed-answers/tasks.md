# Tasks: Transactional Reconcile of Changed Human Answers

**Input**: Design documents from `/specs/051-reconcile-changed-answers/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — the constitution (Principle V) mandates test-first; every
implementation task is preceded by (or bundled with) failing tests.

**Organization**: Tasks grouped by user story (US1–US5 from spec.md) so each
story is an independently testable increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 (retroactive apply), US2 (all-or-nothing), US3 (conflict
  budget), US4 (semantic dependents), US5 (batch/order/immutability)

## Phase 1: Setup

**Purpose**: Package scaffolding so all later tasks land in real modules

- [X] T001 Create `src/maverick/workflows/reconcile/` package (`__init__.py`, empty `models.py`, `state.py`, `detection.py`, `correction.py`, `conflicts.py`, `semantic.py`, `workflow.py` with module docstrings) and test packages `tests/unit/workflows/reconcile/__init__.py`, `tests/unit/assumptions/` additions dir check, `tests/integration/workflows/` (exists — add `test_reconcile_jj.py` placeholder)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared contracts every story builds on — ledger keys, payloads,
config, jj actions, value objects, run state, agents, squadron

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T002 [P] Add reconcile state-key constants (`KEY_RECONCILE_STATUS`, `KEY_RECONCILED_AT`, `KEY_RECONCILED_ANSWER`, `KEY_RECONCILE_CHANGE_ID`, `KEY_RECONCILE_REASON`) and status values (`RECONCILE_STATUS_RECONCILED`, `RECONCILE_STATUS_NEEDS_REVIEW`) plus `normalize_answer()` helper to `src/maverick/assumptions/models.py`, with tests in `tests/unit/assumptions/test_models.py` (data-model §1)
- [X] T003 [P] Add `SubmitCorrectionPayload`, `SubmitConflictResolutionPayload`, `SubmitSemanticDependentsPayload`, `SemanticFinding` to `src/maverick/payloads.py`, register the three submit keys in `SUPERVISOR_TOOL_PAYLOAD_MODELS`, enforce validators from contracts/payloads.md (no-change⇒no-files; dependent⇒non-empty fix_instructions), with tests in `tests/unit/test_payloads.py` (write failing tests first)
- [X] T004 [P] Add `ReconcileConfig` (`resolution_rounds: int = 3`, `semantic_rounds: int = 3`, both `ge=1`) to `src/maverick/config.py`, mount `reconcile:` field on `MaverickConfig`, export in `__all__`, with tests in `tests/unit/config/test_reconcile_config.py` covering YAML + `MAVERICK_RECONCILE__*` env override (data-model §5)
- [X] T005 [P] Add typed jj action wrappers `jj_new_child(parent, cwd)`, `jj_squash_into(revision, into, cwd)`, `jj_list_conflicts(revset_scope, cwd)` (via `log(revset="… & conflicts()")`), `jj_check_mutability(target, cwd)` (empty `immutable()` intersection over target+descendants) to `src/maverick/library/actions/jj.py`, export in `src/maverick/library/actions/__init__.py` + `intents.py`, with tests in `tests/unit/library/actions/test_jj_reconcile_actions.py` using the mocked-runner pattern from `tests/unit/jj/conftest.py` (research R3/R4)
- [X] T006 [P] Implement frozen dataclasses `ChangedAnswer`, `AnswerOutcome`, `ReconcileReport`, enum `ReconcileStage` in `src/maverick/workflows/reconcile/models.py` per data-model §2–§3, with tests in `tests/unit/workflows/reconcile/test_models.py`
- [X] T007 Extend `src/maverick/assumptions/ledger.py` with `answered_unreconciled_entries()` (closed-bead query, detection predicate incl. idempotence check), `mark_reconciled()`, `mark_needs_interactive_review()`, `create_reconcile_escalation()` (never-raise semantics), and the one-line re-arm in `answer()` (clear `assumption_reconcile_status`); write failing tests FIRST in `tests/unit/assumptions/test_ledger_reconcile.py` covering contracts/ledger-state.md predicate rules 1–5, re-arm, and legacy-bead exclusion (depends on T002)
- [X] T008 [P] Implement `ReconcileRunState`/`AnswerState` persistence in `src/maverick/workflows/reconcile/state.py` (`.maverick/runs/<run-id>/reconcile.json`, atomic write via `maverick.utils.atomic`, `discover_resumable()`, spec-chain pattern from `src/maverick/workflows/spec_chain/state.py`), plus pid-stamped lockfile helpers (`acquire_lock`/`release_lock`/stale detection), with tests in `tests/unit/workflows/reconcile/test_state.py`
- [X] T009 [P] Write agent personas `src/maverick/agents/system_prompts/maverick.reconciler.md` (correction + conflict-resolution behavior: favor new answer, never adopt new assumptions, edit files only — no jj/bd commands) and `src/maverick/agents/system_prompts/maverick.semantic-reviewer.md` (diff-vs-diff dependency analysis, findings only)
- [X] T010 Implement `ReconcilerAgent` in `src/maverick/agents/reconciler.py` (`provider_tier="implement"`, `persona_name="maverick.reconciler"`, methods `correct(...)` → `SubmitCorrectionPayload` and `resolve_conflicts(...)` → `SubmitConflictResolutionPayload`, prompt builders receiving question/old answer/new answer per contracts/payloads.md), with tests in `tests/unit/agents/test_reconciler.py` (depends on T003, T009)
- [X] T011 [P] Implement `SemanticDependentsAgent` in `src/maverick/agents/semantic_reviewer.py` (`provider_tier="review"`, `persona_name="maverick.semantic-reviewer"`, method `analyze(...)` → `SubmitSemanticDependentsPayload`), with tests in `tests/unit/agents/test_semantic_reviewer.py` (depends on T003, T009)
- [X] T012 Implement `ReconcileSquadron` in `src/maverick/squadron/reconcile.py` (builds both agents via `runtime_for_agent("implement"/"review", agents_config=...)`, exposes `.reconciler`/`.semantic`, `_all_agents`, rotate-between-answers), export from `src/maverick/squadron/__init__.py`, with tests in `tests/unit/squadron/test_reconcile_squadron.py` following the `PlanSquadron` template (depends on T010, T011)

**Checkpoint**: Foundation ready — user story phases can begin

---

## Phase 3: User Story 1 — Retroactively apply a changed answer (Priority: P1) 🎯 MVP

**Goal**: `maverick reconcile` detects one changed answer, folds the correction
into the ledger-stamped change, auto-rebases descendants, runs the gate suite,
marks the entry reconciled — end-to-end with zero human intervention.

**Independent Test**: quickstart.md Scenario 1 — stack `base←A←B←C`, answered
entry stamped on `A`; after reconcile, `A` contains the fix, no fixup at tip,
gates pass, re-run is a no-op (SC-001, SC-008).

- [X] T013 [P] [US1] Write failing unit tests for detection in `tests/unit/workflows/reconcile/test_detection.py`: changed vs unchanged (normalization), waived/legacy/reconciled-answer exclusions, earliest-stamp target resolution, unlocatable target → `target_change_id=None` (research R1/R2)
- [X] T014 [US1] Implement `src/maverick/workflows/reconcile/detection.py`: build `ChangedAnswer` list from `answered_unreconciled_entries()`, resolve earliest existing stamp via one `log(revset="::@", limit=1000)` index, compute `stack_index` (depends on T006, T007; makes T013 pass)
- [X] T015 [P] [US1] Write failing unit tests for correction in `tests/unit/workflows/reconcile/test_correction.py`: child→agent→verify→squash-into sequence, empty-delta/`no_change_required` agreement and mismatch failure, absorb path selected only for multi-stamp entries, correction diff captured pre-squash (research R3)
- [X] T016 [US1] Implement `src/maverick/workflows/reconcile/correction.py`: `jj_new_child` → `ReconcilerAgent.correct` → `diff_stat`/payload cross-check → capture correction diff → `jj_squash_into` (or `jj_absorb` for multi-stamp) returning a typed `CorrectionResult` (depends on T005, T010, T014; makes T015 pass)
- [X] T017 [US1] Implement `ReconcileWorkflow` happy path in `src/maverick/workflows/reconcile/workflow.py`: preconditions (clean `@`), per-answer pipeline snapshot→correct→gate (`run_independent_gate` with format/lint/typecheck/test from `ValidationConfig`, research R7)→`mark_reconciled`, `ProgressEvent`/`StepOutput` emission, final fresh empty `@` on the new head (R13), run-state persistence at each stage transition; unit tests with stub squadron in `tests/unit/workflows/reconcile/test_workflow.py` (write failing tests first; depends on T008, T012, T016)
- [X] T018 [US1] Implement CLI command in `src/maverick/cli/commands/reconcile.py` (`@async_command`, `cli_error_handler`, `verify_bd_ready`, `cwd = Path.cwd().resolve()`, Rich per-answer summary table + `maverick review <id>` hint, exit codes per contracts/cli-reconcile.md) and register `"reconcile"` in `_LAZY_COMMANDS` + `commands_needing_git_gh` in `src/maverick/main.py`; tests in `tests/unit/cli/test_reconcile_command.py` (CliRunner + mocked workflow; write failing tests first; depends on T017)
- [X] T019 [US1] Integration test (real colocated jj repo + real bd fixture, stubbed agent runtime) in `tests/integration/workflows/test_reconcile_jj.py`: quickstart Scenario 1 — fold lands in `A`, descendants rebased conflict-free, no tip fixup, entry state `reconciled`, immediate re-run makes zero history mutations (depends on T018)

**Checkpoint**: MVP — clean-path reconcile fully functional and demoable

---

## Phase 4: User Story 2 — All-or-nothing safety with automatic restore (Priority: P2)

**Goal**: Any stage failure restores the repo to the per-answer restore point
via `jj op restore`, marks the entry needs-interactive-review, and the run
continues with remaining answers; interrupted runs recover on next invocation.

**Independent Test**: quickstart.md Scenario 2 — sabotaged gate: byte-identical
restore on affected files, entry flagged, re-arm via `maverick review --answer`
(SC-002).

- [X] T020 [US2] Write failing unit tests in `tests/unit/workflows/reconcile/test_workflow.py`: failure at each stage (correction error, payload mismatch, gate fail) triggers `restore_operation(restore_op_id)` then terminal bd write (ordering asserted — no bd writes before restore, research R8), third-answer-continues-after-second-fails, one-terminal-status-per-answer invariant (FR-019)
- [X] T021 [US2] Implement transaction boundaries in `src/maverick/workflows/reconcile/workflow.py`: restore-point capture (`jj_snapshot_operation`) at answer start, try/except per stage → op restore → `mark_needs_interactive_review(reason)`, deferred-bd-write ordering, continue-with-next loop, `AnswerOutcome` aggregation into `ReconcileReport` (makes T020 pass; depends on T017)
- [X] T022 [US2] Implement interrupted-run recovery + concurrency guards in `workflow.py` + `state.py`: on start, `discover_resumable()` → restore in-flight answer's `restore_op_id`, mark it needs-interactive-review (reason "interrupted"), resume remaining pending answers; lockfile acquire/release around the run + refuse when a fly run is `flying` (`maverick.runway.run_metadata`); tests in `tests/unit/workflows/reconcile/test_state.py` (failing first) covering FR-016 and stale-lock reclaim (depends on T021)
- [X] T023 [US2] Integration test in `tests/integration/workflows/test_reconcile_jj.py`: gate-failure rollback leaves `jj log`/file contents byte-identical to pre-answer snapshot while a previously applied answer in the same run stays applied; re-answering via `ledger.answer()` re-arms detection (quickstart Scenario 2; depends on T021)

**Checkpoint**: Reconcile is safe to run unattended

---

## Phase 5: User Story 3 — Budget-capped conflict resolution with escalation (Priority: P3)

**Goal**: Rebase conflicts are resolved by the reconciler agent within
`reconcile.resolution_rounds`; exhaustion rolls back and files an escalation
bead instead of looping.

**Independent Test**: quickstart.md Scenario 3 — conflicting descendant
resolved in favor of the new answer; with `resolution_rounds: 1` and an
unresolvable conflict, rollback + one `reconcile_exhaustion` bead (SC-004).

- [X] T024 [P] [US3] Write failing unit tests in `tests/unit/workflows/reconcile/test_conflicts.py`: round loop over `jj_list_conflicts` ground truth (topological order), resolution folded via child→squash into the conflicted change, re-list between rounds, budget exhaustion after N rounds, non-empty `unresolvable` short-circuits remaining rounds (contracts/payloads.md)
- [X] T025 [US3] Implement `src/maverick/workflows/reconcile/conflicts.py`: round-budgeted loop (default from `ReconcileConfig.resolution_rounds`), per-conflicted-change `jj_new_child` → `ReconcilerAgent.resolve_conflicts` (context: question, old answer, new answer, conflicted files) → `jj_squash_into`, revset-verified completion, typed `ConflictOutcome` (makes T024 pass; depends on T005, T010, T021)
- [X] T026 [US3] Wire conflicts stage into `workflow.py` between correction and gate; on exhaustion: rollback then `create_reconcile_escalation(kind="conflicts")` with question/old/new answers + remaining conflict locations, `escalation_bead_id` on the outcome; extend `tests/unit/workflows/reconcile/test_workflow.py` (failing first; depends on T025)
- [X] T027 [US3] Integration test in `tests/integration/workflows/test_reconcile_jj.py`: real conflicting stack resolved within budget (`conflicts()` revset empty after), and budget-exhaustion variant produces rollback + escalation bead with correct description sections (quickstart Scenario 3; depends on T026)

**Checkpoint**: Real stacks with conflicts are handled or cleanly escalated

---

## Phase 6: User Story 4 — Semantic dependents (Priority: P4)

**Goal**: Code written because of the old assumption — but not textually
conflicting — is flagged by diff-vs-diff analysis and fixed in the descendant
that introduced it, under its own round budget.

**Independent Test**: quickstart.md Scenario 4 — seeded derived value in
descendant `C` corrected; unrelated descendant `B` byte-identical (SC-007).

- [X] T028 [P] [US4] Write failing unit tests in `tests/unit/workflows/reconcile/test_semantic.py`: descendant enumeration revset, per-descendant analyze fan-out with correction diff, `dependent=false` → untouched, fixes applied via correction mechanism into the flagged descendant, follow-up round re-analyzes only flagged descendants, `semantic_rounds` exhaustion semantics
- [X] T029 [US4] Implement `src/maverick/workflows/reconcile/semantic.py`: enumerate `descendants(target) & mutable() & ~target`, capture per-descendant diffs, `SemanticDependentsAgent.analyze` batches, apply fixes via `correction.py` mechanics targeted at each flagged descendant, budget from `ReconcileConfig.semantic_rounds` (makes T028 pass; depends on T011, T016, T021)
- [X] T030 [US4] Wire semantic stage into `workflow.py` between conflicts and gate; exhaustion → rollback + `create_reconcile_escalation(kind="semantic")`; extend `tests/unit/workflows/reconcile/test_workflow.py` (failing first; depends on T029)
- [X] T031 [US4] Integration test in `tests/integration/workflows/test_reconcile_jj.py`: seeded semantically dependent value fixed in the introducing descendant, unrelated descendant byte-identical, gates pass (quickstart Scenario 4; depends on T030)

**Checkpoint**: Reconcile is semantically trustworthy, not just mechanically consistent

---

## Phase 7: User Story 5 — Batched sweeps, stack order, bounded blast radius (Priority: P5)

**Goal**: One invocation drains all changed answers earliest-in-stack first;
immutable targets are skipped with reasons; `--dry-run` previews everything
with zero mutations.

**Independent Test**: quickstart.md Scenario 5 — two answers at different
depths processed earliest-first in one run; immutable third reported
needs-interactive-review, history untouched (SC-003, SC-005).

- [X] T032 [US5] Write failing unit tests: multi-answer stack ordering + later-answer-applies-against-repaired-history in `tests/unit/workflows/reconcile/test_detection.py` and `test_workflow.py`; mutability-guard skip path (target or descendant immutable → no mutation, reason recorded) in `test_workflow.py`; `--dry-run` zero-mutation contract in `tests/unit/cli/test_reconcile_command.py`
- [X] T033 [US5] Implement batch ordering in `detection.py`/`workflow.py`: sort by `stack_index` ascending, re-resolve each subsequent answer's target against post-repair history (change IDs are stable across rebase — verify stamp still resolves), same-target sequential handling (makes ordering tests pass; depends on T021)
- [X] T034 [US5] Implement pre-answer skip guards in `workflow.py`: mutability check via `jj_check_mutability` (target + all descendants) AND unlocatable-target handling (`ChangedAnswer.target_change_id is None`, FR-015); either violation → `AnswerOutcome(status="skipped", reason=...)` with zero jj mutations, bd state set to `needs-interactive-review` (re-arm applies per FR-019 taxonomy), run continues (FR-011/FR-012/FR-015; depends on T033)
- [X] T035 [US5] Implement `--dry-run` in `src/maverick/cli/commands/reconcile.py` + a report-only workflow path: detection, ordering, target resolution, mutability checks; `would reconcile`/`would skip` table, `Dry run — no changes made.` footer, exit 0; extend `tests/unit/cli/test_reconcile_command.py` (failing first; depends on T034)
- [X] T036 [US5] Integration test in `tests/integration/workflows/test_reconcile_jj.py`: three-answer sweep — two applied earliest-first (output order asserted), immutable one untouched (configured via repo-local `revset-aliases."immutable_heads()"`), exit 1, applied answers persist (quickstart Scenario 5; depends on T035)

**Checkpoint**: Full spec surface implemented

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T037 [P] Update `CLAUDE.md`: add `maverick reconcile` row to the CLI Workflows table and a `### reconcile` section (detection rule, transaction model, budgets, re-arm path); note the ledger lifecycle extension in the Assumption ledger section
- [X] T038 [P] Docstring + Rich-output audit across new modules (Google style, no `click.echo`/`print`, structured warnings) and module-size check (<500 LOC soft limit — split `workflow.py` if exceeded per Principle XI)
- [X] T039 Execute quickstart.md Scenarios 1–6 against a scratch sample project with live agent bindings, including the SC-007 seeded evaluation (seed ≥5 semantically dependent sites across descendants; assert ≥80% flagged and fixed, unrelated descendants byte-identical); fix any drift between docs and behavior
- [X] T040 Run `make format-fix && make ci` (full gate: format, lint, typecheck, tests incl. integration) and fix all findings — tree green before push

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 → Phase 2**: T001 scaffolding first
- **Phase 2 (Foundational)**: blocks all stories. Internal deps:
  T002/T003/T004/T005/T006/T008/T009 are parallel; T007 needs T002;
  T010/T011 need T003+T009; T12 needs T010+T011
- **Phase 3 (US1)**: needs full Phase 2 — MVP checkpoint
- **Phase 4 (US2)**: needs US1's workflow core (T017); extends the same files
- **Phase 5 (US3)**: needs US2's transaction boundaries (T021)
- **Phase 6 (US4)**: needs US2 (T021) + correction mechanics (T016); independent of US3 except workflow.py merge order (T030 after T026 when both land)
- **Phase 7 (US5)**: needs US2 (T021); independent of US3/US4 logic
- **Phase 8**: after all desired stories

### Story Dependency Note

US2–US5 all build on US1's workflow core rather than being fully independent —
inherent to a single-command pipeline feature. Each story remains
*independently testable* (its own scenarios/tests) even though implementation
is layered. US3, US4, and US5 are mutually independent once US2 lands and can
proceed in parallel except for shared edits to `workflow.py` (T026/T030/T034 —
serialize those three merges).

### Parallel Opportunities

```text
Phase 2 wave 1: T002 ∥ T003 ∥ T004 ∥ T005 ∥ T006 ∥ T008 ∥ T009
Phase 2 wave 2: T007 ∥ T010 ∥ T011   →   T012
Phase 3 tests:  T013 ∥ T015 (before their implementations)
Post-US2:       US3 (T024–T027) ∥ US4 (T028–T031) ∥ US5 (T032–T036),
                serializing only the workflow.py wiring tasks T026/T030/T034
Phase 8:        T037 ∥ T038
```

---

## Implementation Strategy

**MVP first**: Phases 1–3 (T001–T019) deliver a demoable clean-path reconcile
(quickstart Scenario 1). **Stop and validate** before proceeding.

**Safety second**: Phase 4 (US2) is the highest-value increment after MVP —
it's what makes the command safe to recommend. Ship US1+US2 together if
releasing incrementally.

**Then parallelize**: US3/US4/US5 are separable capability layers; land in
priority order when solo, or in parallel with serialized `workflow.py` merges.

**Throughout**: TDD ordering within every story (failing tests → impl), commit
per task or logical group, `make ci` before any push.
