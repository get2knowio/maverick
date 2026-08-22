---
description: "Task list for 058-standalone-code-review"
---

# Tasks: Standalone Code Review

**Input**: Design documents from `specs/058-standalone-code-review/`
**Prerequisites**: `plan.md`, `research.md`, `data-model.md`, `contracts/`

**Tests**: Included. Constitution Principle IV (test-first) is
non-negotiable in this repository, and three success criteria (SC-002,
SC-004, SC-005) are only meaningful as executable assertions.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: different file, no dependency on another unfinished task — safe to
  run in parallel
- **[Story]**: the user story this task serves

## Path Conventions

Single project: `src/maverick/`, `tests/unit/`, `tests/integration/`.

---

## Phase 1: Setup

- [X] T001 Create `src/maverick/critique/__init__.py` and
      `tests/unit/critique/__init__.py` package scaffolding (empty public
      surface for now).

---

## Phase 2: Foundational (blocking prerequisites)

**These block every user story. Nothing in Phase 3+ starts until Phase 2 is done.**

- [X] T002 [P] Add `review_payload_approved(payload)` to
      `src/maverick/payloads.py`, lifted verbatim from
      `workflows/fly_beads/actions.py::_payload_approved` (research R7), and
      update `actions.py` to import it instead of defining it. Tests in
      `tests/unit/test_payloads.py`.
- [X] T003 [P] Add `ReviewerAgent.critique(scope_summary, change_summary)` to
      `src/maverick/agents/reviewer.py` (research R2): rotates the session
      first, sends the scope-oriented prompt, returns the provenance-stamped
      `SubmitReviewPayload`. New `CRITIQUE_PROMPT_TIMEOUT_SECONDS` constant.
      Tests in `tests/unit/agents/test_reviewer_agent.py` — assert the prompt
      names the scope, does **not** mention beads or work units, and that
      `rotate_session` ran before the send.
- [X] T004 Extract `src/maverick/squadron/reviewers.py::build_reviewer_pair()`
      from `FlySquadron._build_reviewer_pair`
      (`squadron/fly.py:95-127`, research R1) and rewrite `fly.py` to delegate
      to it. Behavior-preserving: the existing `FlySquadron` tests must pass
      unchanged. New tests in `tests/unit/squadron/test_reviewers.py`.
- [X] T005 Add `src/maverick/squadron/critique.py::CritiqueSquadron` — one
      reviewer pair via T004, no `CodingAgent`, `workflow="critique"`.
      `_all_agents()` yields both so `close()` tears them down. Tests assert
      it opens with only an `agents.review` binding configured (research R1's
      rejected-alternative rationale).
- [X] T006 [P] Implement `src/maverick/critique/models.py` per
      `data-model.md`: `CritiqueScopeKind`, `ScopedCommit`, `ResolvedScope`,
      `LensOutcome`, `CritiqueReport`, the fixed `SEVERITY_ORDER` constant,
      and the finding-ordering function. Tests in
      `tests/unit/critique/test_models.py` — cover `is_empty`, `reviewed`,
      `exceeds()`, and that ordering is stable and severity-ordered by the
      constant rather than by string sort.

**Checkpoint**: the reviewer pair can be built and the report can be
constructed. No scope resolution, no CLI.

---

## Phase 3: User Story 1 — Review my uncommitted work (P1) 🎯 MVP

**Goal**: `maverick critique` with no arguments reviews the working copy
against `main` and prints grouped findings.

**Independent test**: change a file in a scratch repo, run the command, see
findings for that file, confirm the repo is byte-identical afterward.

### Tests for User Story 1

- [X] T007 [P] [US1] `tests/unit/critique/test_scope.py` — diff-scope
      resolution: changed-file union, `--base` threading, empty-diff →
      `is_empty`, `MAX_EMBEDDED_DIFF_CHARS` truncation sets
      `diff_truncated` and still populates the complete `paths` list
      (research R5).
- [X] T008 [P] [US1] `tests/unit/critique/test_runner.py` — both lenses run
      via `asyncio.gather`; findings are the same `ReviewFindingPayload`
      objects the payload carried (SC-003); an empty scope never constructs a
      squadron (SC-004, by patching `runtime_for_agent` to raise).
- [X] T009 [P] [US1] `tests/unit/critique/test_render.py` — grouping by file
      in path order, severity order within a file, `(unattributed)` bucket
      last, `rich.markup.escape` applied to issue text, and the two distinct
      empty outcomes (FR-016).

### Implementation for User Story 1

- [X] T010 [US1] `src/maverick/critique/scope.py::resolve_diff_scope(cwd, base)`
      using `AsyncGitRepository.diff` / `diff_stats` / `get_changed_files`
      (Guardrail 1 — no blocking calls on the async path).
- [X] T011 [US1] `src/maverick/critique/runner.py::run_critique(...)` — opens
      `CritiqueSquadron`, `asyncio.gather(..., return_exceptions=True)` over
      both lenses, builds `CritiqueReport` with the fixed ordering. Empty
      scope short-circuits **before** the squadron is constructed.
- [X] T012 [US1] `src/maverick/critique/render.py` — the terminal renderer
      per `contracts/cli-critique.md`, writing to an injected console so
      `--json` mode can redirect it to `err_console`.
- [X] T013 [US1] `src/maverick/cli/commands/critique.py` — the Click command:
      options per the contract, `cwd = Path.cwd().resolve()`, config from
      `ctx.obj` with `load_config()` fallback, thin dispatch to
      `_run_critique_human`, wrapped in `cli_error_handler()`.
- [X] T014 [US1] Register `critique` in `_LAZY_COMMANDS`
      (`src/maverick/main.py`). Do **not** add it to
      `commands_needing_config` or `commands_needing_git_gh` (research R9).
- [X] T015 [US1] `tests/unit/cli/test_critique_command.py` — invoke through
      the root `cli` group per house convention; cover the default
      invocation, `--base`, conflicting-scope rejection, and exit code 0 with
      findings present.

**Checkpoint**: US1 is independently shippable.

---

## Phase 4: User Story 5 — Persisted findings artifact (P3, pulled forward)

**Pulled ahead of US2/US3/US4 deliberately**: the JSON verb (US4) emits
exactly the persisted projection, so building persistence first means US4 is
wiring rather than a second projection that could drift.

- [X] T016 [P] [US5] `tests/unit/critique/test_report.py` — `to_dict()` key
      order and omit-when-absent behavior, `render_markdown` content, and
      that a persistence `OSError` degrades to a warning with the exit code
      untouched (FR-018).
- [X] T017 [US5] `src/maverick/critique/report.py` — `to_dict()`,
      `render_markdown()`, and `persist_report(report, cwd)` writing
      `critique-report.{json,md}` via `atomic_write_json`/`atomic_write_text`,
      mirroring `assumptions/land_report.py:280-293`.
- [X] T018 [US5] Wire persistence into the command: mint
      `run_id = uuid.uuid4().hex[:8]`, persist after rendering, warn to
      `err_console` and set `degraded_persistence` on failure.

---

## Phase 5: User Story 4 — `--json` mode (P2)

- [X] T019 [P] [US4] `tests/unit/cli/commands/test_critique_json.py` — one
      JSON document on stdout with nothing else on that stream (SC-005), for
      success, empty scope, partial lens failure, and each failure kind in
      research R11.
- [X] T020 [US4] `_run_critique_json` in `cli/commands/critique.py`: verb
      `critique.run`, `json_error_handler(verb)`, `emit_json` + `SystemExit`
      on every terminal path (never `return`), progress routed to
      `err_console`.
- [X] T021 [US4] Failure-kind mapping per research R11 — including the
      `bd-unavailable` precondition translation the shared handler cannot do
      for a `verify_available()` that returns `False` rather than raising.
- [X] T022 [US4] `--fail-on` gating: a *success* envelope with a non-zero
      exit (contract `cli-critique-json.md`), so consumers branch on `ok`.

---

## Phase 6: User Story 2 — Epic scope (P2)

- [X] T023 [P] [US2] `tests/unit/critique/test_scope.py` (extended) — epic
      resolution: `BeadClient.children` intersection with
      `extract_bead_ids` (research R3), per-commit diff concatenation
      (research R4), unknown epic → `NOT_FOUND`, epic with zero commits →
      `is_empty`, and that an *interleaved unrelated commit is excluded* —
      the assertion that makes R4's choice load-bearing.
- [X] T024 [US2] `src/maverick/critique/scope.py::resolve_epic_scope(...)`.
      Reuses `library.actions.curation.extract_bead_ids`; writes no new regex
      (Guardrail 5).
- [X] T025 [US2] Wire `--epic` through the command and both output modes.
- [ ] T026 [US2] `tests/integration/critique/test_scope_resolution.py` — a
      real git repository with bead-prefixed commits plus unrelated ones.

---

## Phase 7: User Story 3 — Paths scope (P2)

- [X] T027 [P] [US3] `tests/unit/critique/test_scope.py` (extended) — path
      validation: nonexistent path → `VALIDATION`, absolute path outside the
      repository → `VALIDATION`, directory expansion, repo-relative
      normalization.
- [X] T028 [US3] `src/maverick/critique/scope.py::resolve_paths_scope(...)`.
- [X] T029 [US3] Wire positional paths through the command and both output
      modes.

---

## Phase 8: Cross-cutting, hardening, and the discovered defect

- [ ] T030 [P] `tests/integration/critique/test_read_only.py` — the SC-002
      proof: snapshot the jj operation log, the git object count, the full
      bead list, and a content hash of every tracked file; run `critique` on
      all three scopes **and** on every failure path; assert every snapshot
      is byte-identical.
- [X] T031 Fix `_safe_diff_stat` (`workflows/fly_beads/actions.py:2097`) to
      use the shared epic resolver instead of `git diff --stat HEAD~1..HEAD`
      (research R8), with a regression test in
      `tests/integration/critique/test_fly_aggregate_diff.py` asserting the
      aggregate review sees all of an epic's commits, not just the last one.
- [X] T032 [P] Add the `critique` section to `CLAUDE.md` under "CLI
      Workflows", and the command row to the shared-commands table.
- [X] T033 [P] Update `docs/specify-prompts-orchestration-roadmap.md`:
      mark Tier 1 item 5 delivered as spec 058.
- [ ] T034 Run `make format-fix && make ci` and fix everything it surfaces.

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1** → **Phase 2** → everything else.
- **Phase 3 (US1)** is the MVP and must land before Phases 4–7, which extend
  its command and its report.
- **Phase 4 (US5)** before **Phase 5 (US4)** — the JSON result *is* the
  persisted projection.
- **Phases 6 and 7** are independent of each other and may proceed in
  parallel once Phase 3 is done.
- **Phase 8** last; T031 additionally depends on Phase 6 (it consumes the
  epic resolver).

### Parallel opportunities

- T002, T003, T006 are all independent (different files) once T001 lands.
- T007, T008, T009 are independent test files.
- Phase 6 and Phase 7 are fully parallel with each other.
- T030, T032, T033 are independent of one another.

---

## Implementation Strategy

**MVP**: Phases 1–3. That alone delivers "review my uncommitted work", which
research showed has no workaround today short of manufacturing a bead and
running `fly` — a mutation-heavy detour for an advisory question.

**Then**: Phase 4 (persistence) → Phase 5 (JSON) → Phases 6 and 7 in
parallel → Phase 8.

**Do not**: introduce a Burr graph, add an `ErrorKind`, de-duplicate findings
across lenses, or let any code path write to the repository outside
`.maverick/runs/<run-id>/`.
