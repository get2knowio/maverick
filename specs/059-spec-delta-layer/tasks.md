---
description: "Task list for 059-spec-delta-layer"
---

# Tasks: Spec Delta Layer

**Input**: Design documents from `specs/059-spec-delta-layer/`
**Prerequisites**: `plan.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: Included. Constitution Principle IV (test-first) is non-negotiable in
this repository, and three success criteria — SC-008a (the guard's false-positive
side), SC-010 (round-trip), SC-005 (no started bead touched) — exist only as
executable assertions.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: different file, no dependency on an unfinished task — safe to run in parallel
- **[Story]**: the user story the task serves

## Path Conventions

Single project: `src/maverick/`, `tests/unit/`, `tests/integration/`.

---

## Phase 1: Setup

- [ ] T001 Create `src/maverick/speckit/delta/__init__.py`, `tests/unit/speckit/delta/__init__.py`, and `tests/integration/delta/__init__.py` package scaffolding.

---

## Phase 2: Foundational (blocking prerequisites)

**Every user story depends on the requirement-block parser. Nothing in Phase 3+ starts until Phase 2 is done.**

This phase is where the feature's actual risk lives — see plan.md's Testing
Strategy. The round-trip test is written **before** the parser, and it runs
against the live `specs/` tree.

- [ ] T002 Write `tests/integration/delta/test_requirement_roundtrip.py` — SC-010: for every `specs/*/spec.md` in the **live** tree (not a fixture copy), assert `render(parse(text)) == text` byte-for-byte, naming the file and first differing line on failure.
- [ ] T003 [P] Write `tests/unit/speckit/test_requirements.py` covering each measured corpus reality from `contracts/requirement-block-grammar.md`: letter-suffixed ids (`FR-019c`), `####` headings that must **not** terminate a block, blank lines that must **not** terminate a block, indent-2 continuation lines, indent-2 sub-bullets both blank-separated and not, and out-of-numeric-order id sets that must not be reordered.
- [ ] T004 Implement `src/maverick/speckit/requirements.py` — `RequirementBlock`, `PassthroughLines`, `RequirementSection`, `parse_requirements(text)`, `render_requirements(section)` per `data-model.md`. Store every line **verbatim**; normalization is what breaks round-trips. Make T002 and T003 pass.
- [ ] T005 [P] Implement `src/maverick/speckit/delta/models.py` — `DeltaOperation` (with the `OPERATION_ORDER` module constant, not enum declaration order), `RequirementEntry`, `TaskEntry`, `DeltaDocument`, `Impact`, `Acknowledgement`, `ApplicationRecord`, and the `SHRINK_FLOOR = 0.6` contract constant. Tests in `tests/unit/speckit/delta/test_models.py`.

**Checkpoint**: `spec.md` can be parsed and re-rendered losslessly, and the delta types exist. No delta parsing, no CLI.

---

## Phase 3: User Story 1 — Express a requirement change as a structured document (P1) 🎯 MVP

**Goal**: `maverick delta validate` parses a delta document and reports every problem in it, with zero model calls.

**Independent test**: write a delta against an existing spec; a well-formed one passes, and each malformed case fails naming the offending entry and line.

### Tests for User Story 1

- [ ] T006 [P] [US1] Write `tests/unit/speckit/delta/test_parser.py` — the grammar in `contracts/delta-document-format.md`: header, all four operations, `### Before`/`### After` presence rules per operation, the `[shrink-intended]` marker, `## RENAMED` FROM/TO pairs, `## TASKS` entries, and an absent `## TASKS` section parsing as normal rather than an error.
- [ ] T007 [P] [US1] Write `tests/unit/speckit/delta/test_validate.py` — every row of the validation table, each asserting the stable `code` and the reported line number. Include **both** sides of the content-loss guard: SC-008 (a dropped sub-bullet, and a shrink past the floor, both rejected) and **SC-008a (a one-clause tightening that must NOT be rejected)**. SC-008a is the test that can fail in the way that matters — a guard firing on routine edits trains authors to mark everything.
- [ ] T008 [P] [US1] Write `tests/unit/speckit/delta/test_validate_stale.py` — a `### Before` block that does not match the spec's current block is rejected as `stale-before`, including the whitespace-normalization boundary.

### Implementation for User Story 1

- [ ] T009 [US1] Implement `src/maverick/speckit/delta/parser.py` — `parse_delta_md(text, *, path)` per the grammar contract. Reuse `speckit/parser.py`'s `_TASK_LINE_RE` for `ADDED` task lines rather than writing a second task grammar (Guardrail 5).
- [ ] T010 [US1] Implement `src/maverick/speckit/delta/validate.py` — every check in the validation table, collecting **all** problems rather than failing on the first, each with its stable `code` and line number.
- [ ] T011 [US1] Implement the content-loss guard in `validate.py`: reject on a dropped sub-bullet OR an after-block below `SHRINK_FLOOR` of the before-block's normalized length, suppressed per-entry by `[shrink-intended]` only. No global suppression exists.
- [ ] T012 [US1] Add `maverick delta validate` to `src/maverick/cli/commands/delta.py` — Click group + subcommand, `cwd = Path.cwd().resolve()`, config from `ctx.obj` with `load_config()` fallback, `cli_error_handler()`, human rendering per `contracts/cli-delta.md`.
- [ ] T013 [US1] Register `delta` in `_LAZY_COMMANDS` (`src/maverick/main.py`). Do **not** add it to `commands_needing_config` or `commands_needing_git_gh`.
- [ ] T014 [P] [US1] Write `tests/unit/cli/test_delta_command.py` for `validate` — invoke through the root `cli` group per house convention; cover a valid delta, a multi-problem delta, and feature resolution by exact name / `NNN` prefix / suffix.

**Checkpoint**: US1 is independently shippable — a delta is a reviewable, validated artifact even before anything applies it.

---

## Phase 4: User Story 2 — Apply a delta to produce the spec's new state (P1)

**Goal**: `maverick delta apply` rewrites `spec.md` and `tasks.md` to their post-delta state, atomically.

**Independent test**: apply against a fixture spec, compare output byte-for-byte to expected, then re-parse with the existing ingestion parsers to confirm the artifacts are still ordinary Spec Kit files.

### Tests for User Story 2

- [ ] T015 [P] [US2] Write `tests/unit/speckit/delta/test_apply.py` — all four operations applied in the fixed `RENAMED → REMOVED → MODIFIED → ADDED` order; a document naming one requirement through two operations yields the order-defined outcome, not the document-order one; requirements the delta does not name are byte-identical afterwards.
- [ ] T016 [P] [US2] Write `tests/integration/delta/test_apply_atomicity.py` — FR-009: inject a failure between the two file writes and assert the pre-apply state survives; assert nothing is written when validation fails.
- [ ] T017 [P] [US2] Write `tests/unit/speckit/delta/test_apply_idempotent.py` — FR-010: applying an already-applied delta is a reported no-op with the artifacts unchanged.

### Implementation for User Story 2

- [ ] T018 [US2] Implement `src/maverick/speckit/delta/apply.py` — compute both files' new contents **fully in memory**, validate, then write via `atomic_write_text`. Nothing is written before every computation succeeds (research R8).
- [ ] T019 [US2] Implement task-line application in `apply.py`: insert `ADDED` lines into the correct phase, remove `WITHDRAWN` ids, leave every other line byte-identical.
- [ ] T020 [US2] Add `maverick delta apply` and `--dry-run` to `cli/commands/delta.py` per `contracts/cli-delta.md`, including the "next: maverick refuel" hint.
- [ ] T021 [US2] Implement FR-007b: a delta with no task entries applies quietly — `tasks.md` untouched, exit 0, **no warning**. This is the dominant shape; warning here would appear on most applies and devalue every other warning the command emits.

---

## Phase 5: User Story 4 — In-flight work stops the apply (P1)

**Pulled ahead of US3 deliberately**: this is the safety property that makes the layer trustworthy, and US3 writes to beads. Refusal must exist before anything can close a bead.

**Goal**: apply refuses, writing nothing, when a named task's bead is in flight or closed.

**Independent test**: a spec with one closed and one in-progress bead; a delta withdrawing both tasks reports both impacts, exits non-zero, and leaves artifacts and beads untouched.

### Tests for User Story 4

- [ ] T022 [P] [US4] Write `tests/integration/delta/test_refusal_writes_nothing.py` — snapshot `git status --porcelain`, a content hash of both artifacts, and the full bead list before and after every refusing path; assert byte-identical. Mutation-test the helper so it is not a rubber stamp.
- [ ] T023 [P] [US4] Write `tests/unit/speckit/delta/test_impacts.py` — in-flight, closed, and open-unstarted bead states classified correctly; the **unstamped** case (a bead under the epic with no `speckit_task_id`, research R7) reported and never closed.
- [ ] T024 [P] [US4] Write `tests/unit/cli/test_delta_ack.py` — partial `--ack` still refuses; every impact named lets the apply proceed; an `--ack` naming a non-impact **fails** rather than being ignored (FR-015b); no blanket override flag exists.

### Implementation for User Story 4

- [ ] T025 [US4] Implement `src/maverick/speckit/delta/impacts.py` — resolve each task entry to its bead via the `speckit_task_id` state key, classify status, and surface unstamped beads.
- [ ] T026 [US4] Wire refusal into `apply.py`: detect impacts **before** computing any rewrite, and refuse with every outstanding impact listed.
- [ ] T027 [US4] Add the repeatable `--ack TASK_ID` option and its validation to `cli/commands/delta.py`.

---

## Phase 6: User Story 3 — Consequences flow into beads (P1)

**Goal**: a later `refuel --speckit` adds beads for new tasks and closes the open, unstarted beads of withdrawn ones.

**Independent test**: apply a delta adding two task lines and withdrawing one, run ingestion, verify exactly two new beads under the existing epic and exactly one previously-open bead closed, with zero model calls.

### Tests for User Story 3

- [ ] T028 [P] [US3] Write `tests/unit/speckit/test_build_withdrawn.py` — `IngestionPlan.withdrawn` is exactly `set(existing_task_map) - {parsed task ids}`; empty on a first run; empty when nothing was withdrawn.
- [ ] T029 [P] [US3] Write `tests/integration/delta/test_withdrawal_ingestion.py` — SC-002 and SC-005: an epic with one closed, one in-progress, and one open-unstarted bead; exactly the open-unstarted one closes, with a reason citing the delta, and no second epic is created. Assert zero model calls.

### Implementation for User Story 3

- [ ] T030 [US3] Add `withdrawn: tuple[WithdrawnTask, ...]` to `IngestionPlan` (`src/maverick/speckit/build.py`) and compute it in `build_ingestion_plan`.
- [ ] T031 [US3] Compute withdrawal detection in `workflows/refuel_speckit/workflow.py` between `_find_existing_epic` and `build_ingestion_plan` — the only point holding both maps, needing no extra `bd` queries (research R6).
- [ ] T032 [US3] Add the bead-closing step to `workflow.py`, modelled on `_adopt_remediation_beads`: per-bead `except Exception → logger.warning` isolation, its own `emit_step_started`/`emit_step_completed`, and `BeadClient.close(reason=...)` citing the delta.
- [ ] T033 [US3] Extend refuel's dry-run rendering (`workflow.py:298-319`) to preview withdrawals, so `refuel --dry-run` shows bead consequences before any write.

---

## Phase 7: User Story 5 — Applied deltas preserved as provenance (P2)

**Goal**: an applied delta moves to `deltas/archive/` carrying its application record.

**Independent test**: apply two deltas in sequence; the archive holds both in application order, each stating what changed, when, and which impacts were acknowledged.

### Tests for User Story 5

- [ ] T034 [P] [US5] Write `tests/unit/speckit/delta/test_archive.py` — the move happens last; the `## Applied` record carries operation counts with all four keys, task counts, acknowledgements with the bead status **at the time cleared**, and `[shrink-intended]` ids as declared reductions.
- [ ] T035 [P] [US5] Write a test asserting pending-versus-applied is determined by **location alone** — no status marker inside the document is ever read (FR-023).

### Implementation for User Story 5

- [ ] T036 [US5] Implement `src/maverick/speckit/delta/archive.py` — append the `ApplicationRecord` and move the document, ordering by numeric filename prefix.
- [ ] T037 [US5] Implement `maverick delta list` in `cli/commands/delta.py` — pending and applied per feature, and every feature with a `deltas/` directory when no feature is named.

---

## Phase 8: JSON verbs

- [ ] T038 [P] Write `tests/unit/cli/commands/test_delta_json.py` — exactly one JSON document on stdout on every path (success and failure), all four verbs, the `confirmation-required` refusal envelope with `outstanding`, `delta.dry-run`'s `would_block` in the **result** rather than an error, already-applied as `ok: true`, and an assertion that every emitted `error.kind` is an existing `ErrorKind` member.
- [ ] T039 Implement `--json` for all four verbs in `cli/commands/delta.py` — `json_error_handler(verb)`, `emit_json` + `SystemExit` on every terminal path (never `return`), narration to `err_console`.
- [ ] T040 Implement the problem-code projection so `delta.validate` failures carry the stable `code` per entry that `contracts/cli-delta-json.md` enumerates.

---

## Phase 9: Polish & cross-cutting

- [ ] T041 [P] Verify SC-004 — run the full existing suite unchanged and confirm byte-identical behavior on repositories with no `deltas/` directory.
- [ ] T042 [P] Add the `### delta` section to `CLAUDE.md` under "CLI Workflows" and the command row to the shared-commands table.
- [ ] T043 [P] Update `docs/specify-prompts-orchestration-roadmap.md` — mark Tier 1 item 6 delivered as spec 059, completing the tier.
- [ ] T044 Run `make format-fix && make ci` and fix everything it surfaces.

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1** → **Phase 2** → everything else. Phase 2 is genuinely blocking: every story reads or writes requirement blocks.
- **Phase 3 (US1)** is the MVP and precedes Phase 4, which applies what US1 validates.
- **Phase 5 (US4)** before **Phase 6 (US3)** — refusal must exist before anything can close a bead.
- **Phase 7 (US5)** depends on Phase 4 only.
- **Phase 8** depends on Phases 3–7 (it wraps all four verbs).
- **Phase 9** last; T043 depends on everything.

### Parallel opportunities

- T003 and T005 are independent of each other once T001 lands.
- T006, T007, T008 are independent test files.
- T015, T016, T017 are independent.
- T022, T023, T024 are independent.
- Phase 7 can run in parallel with Phase 6 — the archive touches no bead.
- T041, T042, T043 are mutually independent.

---

## Implementation Strategy

**MVP**: Phases 1–3. A validated, reviewable delta document is useful on its own
— it is a change proposal a human can read in a PR before anything acts on it.

**Then**: Phase 4 (apply) → Phase 5 (refusal) → Phase 6 (beads) → Phase 7
(archive) → Phase 8 (JSON) → Phase 9.

**Build the risk first.** T002's round-trip is the design's falsification
mechanism: every rule in `requirement-block-grammar.md` is a measured claim
about 54 real files, and a wrong one must fail there rather than corrupt a spec
in use. If T002 cannot be made to pass, the block model is wrong and the plan
needs revisiting before any of Phase 3 is written.

**Do not**: infer requirement→task coverage (FR-007a — it is 6.4% in this
corpus); add a blanket `--force`; make `SHRINK_FLOOR` configurable; call a model
on any path; write a bead during `delta apply`; or add an `ErrorKind`.
