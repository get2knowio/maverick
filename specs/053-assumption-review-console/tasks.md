# Tasks: Assumption Review Console

**Input**: Design documents from `/specs/053-assumption-review-console/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — the project constitution (Principle V) mandates TDD. Test tasks are written first and must fail before their implementation tasks.

**Organization**: Tasks are grouped by user story. US1 (headless JSON verbs) is the MVP; US2 (guided sweep skill) and US3 (post-sweep flow) build on it.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 = headless verbs, US2 = guided sweep skill, US3 = batched reconcile/frontier/landing flow

## Path Conventions

Single project: `src/maverick/`, `tests/` at repository root (per plan.md).

---

## Phase 1: Setup

**Purpose**: No new project scaffolding is needed (existing package). The one structural preparation is the constitution-mandated split of the module every US1 review task touches.

- [X] T001 Split `src/maverick/cli/commands/review.py` into a behavior-preserving package `src/maverick/cli/commands/review/` with `__init__.py` (command definition + dispatch, re-exporting `review` so `main.py`'s lazy registration string keeps working), `listing.py` (empty stub for now), `entry_actions.py` (answer/waive/bulk-waive flows moved verbatim), `legacy.py` (legacy escalation-bead flow moved verbatim). All existing review tests must pass unchanged; no option or output changes in this task.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The two shared modules every JSON verb depends on — the canonical entry serializer and the envelope/error machinery.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 [P] Write failing unit tests for the canonical entry row projection in `tests/unit/assumptions/test_serialize.py`: field-for-field projection from a built `AssumptionReportEntry` (question, adopted_answer, alternatives, severity, severity_defaulted, owner_spec, status, bucket, blocks_landing, source_bead, is_legacy, final_answer, waiver, reconcile block, pending_reconcile, affected_change_ids, annotations), null-omission rules, and equality with the land-report row for the same entry.
- [X] T003 [P] Write failing unit tests for the JSON envelope machinery in `tests/unit/cli/test_json_output.py`: `JsonEnvelope.success`/`.failure` shape (result XOR error, absent branch omitted), `ErrorKind` registry values frozen per `contracts/error-envelope.md`, `emit_json` writes exactly one parseable document to stdout with nothing else (no markup, no wrapping), and `json_error_handler()` mapping table — `MaverickError` subclasses, bd-unavailable, dirty-working-copy, concurrent-run, locked, bare `Exception` → `internal` — each producing the right kind, stderr diagnostics, and non-zero exit.
- [X] T004 [P] Implement `src/maverick/assumptions/serialize.py` with public `entry_to_dict(entry: AssumptionReportEntry) -> dict[str, object]`, extracted from `land_report._entry_to_dict` and additively extended with `owner_spec`, `status`, `bucket`, `blocks_landing`; update `src/maverick/assumptions/land_report.py` to delegate to it (keep a `_entry_to_dict` alias for compatibility) and re-export from `src/maverick/assumptions/__init__.py`.
- [X] T005 [P] Implement `src/maverick/cli/json_output.py`: `ErrorKind` StrEnum (12 registry values), frozen dataclasses `JsonError` and `JsonEnvelope` (with `success()`/`failure()` constructors, `to_dict()`), `emit_json(envelope)` using a dedicated non-markup non-wrapping stdout Console (transport helper added to `src/maverick/cli/output.py`), and `json_error_handler(verb)` context manager mapping the exception hierarchy to error envelopes + `SystemExit(ExitCode.FAILURE)`, siblings of `cli_error_handler()` in style.

**Checkpoint**: `make test-fast` green with T002/T003 passing — user story phases may begin.

---

## Phase 3: User Story 1 - Headless review verbs with machine-readable output (Priority: P1) 🎯 MVP

**Goal**: Every review-lifecycle verb (list, answer, waive, bulk-waive, reconcile status, run reconcile, land status, land) invocable headlessly with enveloped JSON on stdout, structured errors, correct exit codes, and untouched human-mode behavior.

**Independent Test**: From a non-interactive shell against a repo with seeded ledger entries, invoke each verb with `--json` and verify parseable envelopes, real state changes, structured failures (unknown id, blocked land, dirty working copy), and byte-identical human-mode output without `--json` (quickstart Scenarios 1–3, 5).

### Tests for User Story 1 (write first, must fail) ⚠️

- [X] T006 [P] [US1] Write failing tests for `review --list` in `tests/unit/cli/commands/test_review_listing.py`: default open-only selection, repeatable `--status`/`--spec`/`--severity` filters (OR within, AND across), canonical ordering (owner_spec asc → severity high→low → ledger order), counts over the filtered selection, empty-queue success, `bd-unavailable` envelope, mutual exclusion with `BEAD_ID` and decision flags, human-table mode renders without `--json`.
- [X] T007 [P] [US1] Write failing tests for review JSON actions in `tests/unit/cli/commands/test_review_json.py`: `review.answer` and `review.waive` success envelopes (post-write row, `action` field, reconcile status `pending` after answer), `validation` when no decision flag / empty answer text in JSON mode, `already-resolved` guard with current row in `error.details.entry` (waived target), re-answer of an `answered` entry allowed (051 FR-017), `not-found`, legacy bead `--approve/--reject/--defer` JSON results, `review.bulk-waive` envelope (waived rows, failed map, zero-match success, exit 1 when failed non-empty).
- [X] T008 [P] [US1] Write failing tests for reconcile JSON modes in `tests/unit/cli/commands/test_reconcile_json.py`: `reconcile.run` success envelope wrapping `ReconcileReport.to_dict()`, exit 0 on empty/all-reconciled and exit 1 with `ok: true` on escalated outcomes, precondition envelopes (`bd-unavailable`, `vcs`, `dirty-working-copy`, `concurrent-run`, `locked`), `reconcile.dry-run` always exit 0 with predicted statuses only, workflow progress routed to stderr (stdout is exactly one document).
- [X] T009 [P] [US1] Write failing tests for land JSON modes in `tests/unit/cli/commands/test_land_json.py`: `land.status` result (frontier_clear, verification incl. degraded-null, blocking id lists, embedded report + paths, exit 0 even when blocked, no curation invoked), `--status` flag mutual exclusions, `land.run` gate refusal (`frontier-blocked` with full report in details, exit 1), `confirmation-required` on agent-curation path without `--yes`, success document (landed, mode, verification, curation summary, hint), nothing-to-land success, dry-run deferred exit.

### Implementation for User Story 1

- [X] T010 [US1] Implement `--list` mode in `src/maverick/cli/commands/review/listing.py` + option wiring in `review/__init__.py`: `report_entries()` sweep, in-process filtering, canonical sort, counts, `entry_to_dict` rows, `emit_json` envelope for `--json`, minimal human table via existing output helpers otherwise (satisfies T006).
- [X] T011 [US1] Implement JSON mode for single-entry actions in `src/maverick/cli/commands/review/entry_actions.py` and `review/legacy.py`: `--json` flag on the command, decision-flag requirement, empty-text rejection, already-resolved pre-check (read current status before `ledger.answer`/`ledger.waive`), post-write row in result, legacy-flow JSON results; all prompts unreachable in JSON mode (satisfies T007's single-entry cases).
- [X] T012 [US1] Implement `review.bulk-waive` JSON in `src/maverick/cli/commands/review/entry_actions.py`: envelope over `BulkWaiveResult` (waived rows via `entry_to_dict`, failed map, severities echoed), exit-code rule (satisfies remainder of T007).
- [X] T013 [US1] Implement `--json` on `src/maverick/cli/commands/reconcile.py` for run + dry-run: wrap precondition checks in `json_error_handler("reconcile.run"/"reconcile.dry-run")`, route `render_workflow_events` progress to `err_console` in JSON mode, emit `ReconcileReport.to_dict()`-based result, preserve existing exit semantics (satisfies T008).
- [X] T014 [US1] Implement `land --status` via new helper `src/maverick/cli/commands/land_status.py` (gate evaluation → `build_report`/`persist_report` → status result document) and dispatch + mutual-exclusion wiring in `src/maverick/cli/commands/land.py` (satisfies T009 status cases).
- [X] T015 [US1] Implement `--json` on the `land` apply path in `src/maverick/cli/commands/land.py`: `frontier-blocked` refusal envelope with embedded report, `confirmation-required` guard replacing `console.input` when `--yes` absent, success/nothing-to-land/dry-run documents, all narration to stderr in JSON mode (satisfies remainder of T009).
- [X] T016 [US1] Write end-to-end scenario test `tests/integration/cli/test_json_verbs_scenario.py`: seeded ledger → `review --list --json` → answer one + waive one + bulk-waive a spec → `reconcile --dry-run --json` → `land --status --json`, asserting envelope chain, state transitions, and stdout purity at every step (quickstart Scenarios 1–3 automated).

**Checkpoint**: US1 fully functional — any automation client can drive the whole lifecycle headlessly. MVP deliverable.

---

## Phase 4: User Story 2 - Guided sweep in the review console (Priority: P2)

**Goal**: The packaged `maverick-review` Claude Code skill exists, ships in the wheel, installs into user projects via `maverick init` (removed by `maverick uninstall`), and instructs a compliant sweep: one entry at a time in document order, adopted answer + alternatives + free-form + waive/skip, every decision applied immediately via exactly one verb.

**Independent Test**: `maverick init` in a project installs `.claude/skills/maverick-review/SKILL.md`; invoking `/maverick-review` in Claude Code walks a seeded queue per `contracts/skill-review-console.md` steps 1–8, with ledger state reflecting each decision and no direct jj/bd/file mutation by the skill (quickstart Scenario 4, steps 1–3).

### Tests for User Story 2 (write first, must fail) ⚠️

- [X] T017 [P] [US2] Write failing tests in `tests/unit/init/test_skill_install.py`: `maverick init` installs the packaged asset to `<project>/.claude/skills/maverick-review/SKILL.md`, re-running init overwrites a locally modified copy (Maverick-owned refresh), install failure is non-fatal/advisory, `maverick uninstall` removes the file and empty parent dirs, and the packaged source `src/maverick/skills/review_console/SKILL.md` has valid frontmatter (`name: maverick-review`, non-empty `description`, `user-invocable: true`).

### Implementation for User Story 2

- [X] T018 [P] [US2] Author `src/maverick/skills/review_console/SKILL.md` — identity, preflight, and sweep sections per `contracts/skill-review-console.md` (steps 1–8): `review --list --json` preflight with bd-unavailable stop, empty-queue branch, document-order presentation with spec-group announcements, per-entry AskUserQuestion layout (adopted answer first + "(Recommended)", alternatives, overflow follow-up so nothing is dropped, waive/skip reachable, Other = free-form), immediate verb invocation per decision, empty free-form re-prompt, already-resolved continue-not-abort, bulk-waive shortcut offer, prohibitions section.
- [X] T019 [US2] Add wheel packaging for the skill asset in `pyproject.toml` (include `src/maverick/skills/**/*.md`, same mechanism as `agents/system_prompts/*.md`) and verify the file lands in the built wheel.
- [X] T020 [US2] Implement the init install step in `src/maverick/init/__init__.py`: read the packaged asset (`importlib.resources`), write idempotently to `<project>/.claude/skills/maverick-review/SKILL.md` with always-overwrite + Maverick-owned header, non-fatal on failure, reported in init's summary output (satisfies T017 install cases).
- [X] T021 [US2] Implement skill removal in `src/maverick/cli/commands/uninstall.py` (including `--dry-run` listing), satisfying T017 removal cases.

**Checkpoint**: US1 + US2 — a human in Claude Code can complete a full guided sweep against a real queue.

---

## Phase 5: User Story 3 - Batched reconcile, frontier report, and landing offer (Priority: P3)

**Goal**: The skill closes the loop after the sweep: exactly one batched reconcile (skipped when no answers), plain-language frontier state, landing offered only when clear and executed only on explicit confirmation, all failures and interactive-review escalations surfaced verbatim with zero retries.

**Independent Test**: Complete a sweep with several answers; verify from the session transcript exactly one `maverick reconcile --json` invocation, a frontier report matching `land --status --json` output, landing gated on explicit confirmation via `land --yes --json`, and a forced failure (e.g. dirty working copy) reported once without retry (quickstart Scenario 4, steps 4–5).

### Implementation for User Story 3

- [X] T022 [US3] Extend `src/maverick/skills/review_console/SKILL.md` with the post-sweep sections per `contracts/skill-review-console.md` (steps 9–15): reconcile-once rule with zero-answers skip, outcome reporting (`needs_interactive_review`/`skipped` with reason + escalation bead id), no-retry rule with remedy suggestions for `dirty-working-copy`/`concurrent-run`/`locked`, `land --status --json` frontier report wording (verified / conditionally verified / still blocked with per-entry next steps), explicit-confirmation landing via `land --yes --json`, decline path, and the end-of-session summary.
- [X] T023 [US3] Manual validation pass of the full skill flow per quickstart Scenario 4 in a seeded sample project (sweep → single reconcile → frontier report → landing offer → land), recording the transcript evidence for SC-003/SC-004/SC-005 in the PR description; fix any SKILL.md instruction ambiguities surfaced.

**Checkpoint**: All three user stories independently functional — full console loop from queue to landed history.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T024 [P] Update `CLAUDE.md` (CLI Workflows table + a short "JSON verbs" note under the review/reconcile/land sections) and the 053 spec's `quickstart.md` if flags drifted during implementation.
- [X] T025 [P] Additively document the new entry-row keys (`owner_spec`, `status`, `bucket`, `blocks_landing`) in `specs/052-conditional-landing/contracts/land-report-schema.md` (additive evolution note, schema_version unchanged), and correct that contract's `reconcile.status` value list — it names `"skipped"`, which the ledger never persists (actual values: `reconciled | needs-interactive-review | pending`).
- [X] T026 Human-mode regression sweep: run the full existing CLI test suite and manually diff `review`/`reconcile --dry-run`/`land --dry-run`/`brief --format json` outputs against `main` to confirm FR-018 (no `--json` ⇒ byte-identical behavior); fix any drift found.
- [X] T027 Run `make format-fix && make ci` and execute `quickstart.md` Scenarios 1–3 + 5 verbatim in a scratch repo; fix anything red.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none — start immediately.
- **Foundational (Phase 2)**: independent of Phase 1 (different files) but both block Phase 3. T004/T005 require their tests T002/T003 first.
- **US1 (Phase 3)**: requires Phases 1 + 2. Internally: T006–T009 (tests) before their implementation tasks; T010→T012 share `review/` package files with T011 (T010 ∥ T011 touch different modules; T012 follows T011 — same file); T013, T014+T015 independent of the review tasks.
- **US2 (Phase 4)**: requires US1 (the skill invokes the verbs). T017 before T020/T021; T018/T019 parallel to T017.
- **US3 (Phase 5)**: requires US1 (reconcile/land verbs) and US2 (the SKILL.md artifact it extends).
- **Polish (Phase 6)**: after desired stories complete.

### User Story Dependencies

- **US1 (P1)**: only Foundational. Independently testable (headless verbs).
- **US2 (P2)**: consumes US1's verbs; independently testable given US1.
- **US3 (P3)**: extends US2's artifact, exercises US1's reconcile/land verbs.

### Parallel Opportunities

- Phase 2: T002 ∥ T003, then T004 ∥ T005 (and T001 ∥ all of Phase 2).
- US1 tests: T006 ∥ T007 ∥ T008 ∥ T009.
- US1 impl: {T010, T011} ∥ T013 ∥ {T014→T015}; T012 after T011; T016 last.
- US2: T017 ∥ T018; T019 ∥ T020 after T018.
- Polish: T024 ∥ T025.

---

## Parallel Example: User Story 1

```bash
# After Phase 2, launch all US1 test authoring together:
Task: "T006 failing tests for review --list in tests/unit/cli/commands/test_review_listing.py"
Task: "T007 failing tests for review JSON actions in tests/unit/cli/commands/test_review_json.py"
Task: "T008 failing tests for reconcile JSON in tests/unit/cli/commands/test_reconcile_json.py"
Task: "T009 failing tests for land JSON in tests/unit/cli/commands/test_land_json.py"

# Then implementation streams in parallel:
Task: "T010 review --list in src/maverick/cli/commands/review/listing.py"
Task: "T013 reconcile --json in src/maverick/cli/commands/reconcile.py"
Task: "T014 land --status helper in src/maverick/cli/commands/land_status.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 (T001) + Phase 2 (T002–T005).
2. Phase 3 complete (T006–T016).
3. **STOP and VALIDATE**: quickstart Scenarios 1–3 + 5; `make ci`.
4. Ship — scripts/CI/any agent can already drive the review lifecycle headlessly.

### Incremental Delivery

1. MVP (above).
2. Add US2 (T017–T021) → `maverick init` ships the console → validate Scenario 4 steps 1–3.
3. Add US3 (T022–T023) → full sweep-to-landing loop → validate Scenario 4 steps 4–5.
4. Polish (T024–T027) → `make ci` green, docs current.

---

## Notes

- Constitution Principle V: every test task precedes and must fail before its implementation task.
- Human-mode output is a compatibility surface (FR-018) — treat any diff without `--json` as a bug.
- Envelope keys, verb ids, and error kinds are frozen contracts once merged (additive only).
- Commit after each task or logical group (`bead(...)`-style subjects if driven via beads).
