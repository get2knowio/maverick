# Tasks: Spec Kit Ingestion Mode for Refuel

**Input**: Design documents from `/specs/048-speckit-refuel-ingestion/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — the project constitution mandates test-first (Principle V: TDD red-green-refactor; Debt Prevention: "Tests are not optional"). Test tasks precede their implementation tasks and must fail before implementation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1 = core ingestion, US2 = auto-detection, US3 = dry-run, US4 = enrichment)
- Include exact file paths in descriptions

## Path Conventions

Single project per plan.md: `src/maverick/`, `tests/` at repository root.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package skeletons and shared test fixtures for all subsequent work

- [X] T001 Create package skeletons: `src/maverick/speckit/{__init__.py,models.py,parser.py,detect.py,build.py,errors.py}` and `src/maverick/workflows/refuel_speckit/{__init__.py,constants.py,models.py,workflow.py}` (module docstrings + `from __future__ import annotations` only; `__init__.py` re-exports to be filled as modules land)
- [X] T002 [P] Define the Spec Kit error hierarchy in `src/maverick/speckit/errors.py`: `SpeckitError(MaverickError)`, `SpeckitParseError` (fields: file, line, expected, suggestion), `SpeckitValidationError` (duplicate IDs / unknown dep refs / cycles), `AmbiguousFeatureError` (candidates list), `UnsupportedTemplateError` (found version, supported range), `NothingToIngestError` — matching error catalog E01–E07 in contracts/cli-refuel-speckit.md; unit tests in `tests/unit/speckit/test_errors.py` asserting message content
- [X] T003 [P] Create `tests/unit/speckit/conftest.py` and `tests/unit/workflows/refuel_speckit/conftest.py`: reuse/extend the Spec Kit fixtures from `tests/unit/beads/conftest.py` (`SAMPLE_TASKS_MD`, `SAMPLE_TASKS_MD_WITH_DEPS`, `spec_dir_with_tasks`, `spec_dir_with_deps`, `mock_runner` BeadClient stubbing pattern); add a full-featured fixture feature dir (multi-phase, `[P]`/`[US]` markers, checked tasks, explicit `depends on` notes, fenced code block, Dependencies section) plus a matching spec.md with SC bullets and story Acceptance Scenarios

**Checkpoint**: Skeletons importable, fixtures available — foundational work can begin

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The pure parsing/detection layer every user story depends on (data-model.md parsing layer; contracts/tasks-md-grammar.md)

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 [P] Write failing tests for the frozen Pydantic models in `tests/unit/speckit/test_models.py`: `SpeckitTask` (task_id pattern, non-empty description), `SpeckitPhase`, `ParsedSpec`, `SpeckitFeature`, `TemplateCompatibility` status literals, `FeatureResolution` mode literals — per data-model.md field rules
- [X] T005 Implement `src/maverick/speckit/models.py` (all frozen Pydantic models from data-model.md parsing layer) until T004 passes
- [X] T006 [P] Write failing table-driven tests for the tasks.md grammar in `tests/unit/speckit/test_parser_tasks.py`: happy path (phases, `[P]`, `[USn]`, checked/unchecked, line numbers), explicit `depends on T###` extraction, file-path token extraction, fenced-code-block skipping, non-`## Phase` heading terminating a section, Dependencies-section story pairs, and hard errors E05 (malformed task-shaped line, non-increasing phase numbers — with file/line/expected/suggestion) and E06 (duplicate task ID with both line numbers, unknown dep ref)
- [X] T007 [P] Write failing tests for spec.md extraction in `tests/unit/speckit/test_parser_spec.py`: title extraction + fallback, `SC-\d+` bullets, per-story Acceptance Scenarios keyed `USn`, empty-spec E05 case, missing-sections warnings
- [X] T008 Implement the tasks.md grammar in `src/maverick/speckit/parser.py` (pure functions, no I/O — model on `src/maverick/flight/parser.py` primitives) until T006 passes
- [X] T009 Implement spec.md extraction in `src/maverick/speckit/parser.py` (`_split_h2_sections`/`_split_h3_sections`-style helpers) until T007 passes
- [X] T010 [P] Write failing tests for detection in `tests/unit/speckit/test_detect.py`: name resolution (exact dir / `NNN` prefix / exact suffix / multiple candidates → `AmbiguousFeatureError`), shape check (spec.md + tasks.md required, plan.md optional), classic-vs-speckit `FeatureResolution` modes, version gate (`supported` / `unsupported` → `UnsupportedTemplateError` / missing metadata → `unknown` + warning) reading `.specify/init-options.json`
- [X] T011 Implement `src/maverick/speckit/detect.py` (`resolve_feature()`, `check_template_compatibility()`, `SUPPORTED_SPECKIT_RANGE = ">=0.14,<0.15"`) until T010 passes

**Checkpoint**: `SpeckitFeature` can be produced from any fixture dir; all error paths typed — user stories can now proceed

---

## Phase 3: User Story 1 - Ingest a Spec Kit feature into work items (Priority: P1) 🎯 MVP

**Goal**: `maverick refuel <feature> --speckit` deterministically creates one epic + one task bead per open task with preserved IDs/phases/markers/file scope, phase-barrier + explicit dependency wiring, epic chaining, delta re-runs, and run metadata — zero LLM calls.

**Independent Test**: quickstart.md Scenarios 2–5 — ingest a fixture feature dir with a stubbed (unit) or real (integration) `bd`, verify bead set, ready-ordering, chaining, delta, and fail-before-write.

### Tests for User Story 1

- [X] T012 [P] [US1] Write failing tests for dependency-edge derivation in `tests/unit/speckit/test_build_edges.py`: intra-phase serial chain of non-`[P]` tasks, `[P]` tasks with no implicit intra-phase deps, phase barrier as sinks(N)×sources(N+1) with transitivity assertion (topological order = valid tasks.md execution order), explicit-note edges, story-dep edges only when not implied, cycle detection → `SpeckitValidationError`, delta edge resolution through `existing_task_map` and dropping edges from completed blockers — per data-model.md "Derived dependency edges"
- [X] T013 [P] [US1] Write failing tests for ingestion-plan building in `tests/unit/speckit/test_build_plan.py`: `PlannedBead` titles (`T###: …` ≤ 490 chars), description markdown exactly per contracts/bead-encoding.md (Task/Acceptance Criteria with story scenarios/File Scope/never-empty Verification with rg-based file checks), epic `PlannedBead` (SC bullets, Source section), `skipped_completed`, delta filtering (`skipped_existing`, no epic on delta), build-time validation failures before any plan is returned, zero-open-tasks → `NothingToIngestError`
- [X] T014 [US1] Implement edge derivation in `src/maverick/speckit/build.py` until T012 passes
- [X] T015 [US1] Implement `IngestionPlan`/`PlannedBead` building in `src/maverick/speckit/build.py` (description assembly, default verification per research D8, delta filtering, acyclic validation) until T013 passes
- [X] T016 [P] [US1] Write failing workflow tests in `tests/unit/workflows/refuel_speckit/test_workflow.py` using the `mock_runner` BeadClient stubbing pattern: fresh run (epic + tasks + `set_state` provenance calls + dependency wiring + epic chaining behind open-epic tail + `RunMetadata` written with status refueled), delta run (existing epic adopted via `speckit_feature` state, only new tasks created, no re-chaining), multiple matching open epics → error, mid-creation failure reports created IDs, validation failure → zero `bd` write calls (FR-015)

### Implementation for User Story 1

- [X] T017 [US1] Implement `src/maverick/workflows/refuel_speckit/constants.py` (step names: `RESOLVE_FEATURE`, `CHECK_TEMPLATE`, `PARSE_ARTIFACTS`, `PLAN_INGESTION`, `ENRICH`, `CREATE_BEADS`, `WIRE_DEPS`, `CHAIN_EPIC`, `RECORD_RUN`, `COMMIT_OUTPUT`, `WORKFLOW_NAME = "refuel-speckit"`) and `src/maverick/workflows/refuel_speckit/models.py` (`SpeckitRefuelResult` dataclass with `to_dict()`, per data-model.md workflow layer)
- [X] T018 [US1] Implement `SpeckitRefuelWorkflow(PythonWorkflow)` in `src/maverick/workflows/refuel_speckit/workflow.py` until T016 passes: sequential steps with `ProgressEvent` emission, delta epic lookup (`query("type=epic AND status=open")` + `show()` state match), `library/actions/beads.create_beads` + `wire_dependencies` + `BeadClient.add_dependency` for barrier/explicit edges, `set_state` provenance (epic `speckit_feature`; task `speckit_task_id`/`speckit_phase`/`speckit_parallel`), epic chaining (mirror `workflows/refuel_maverick/workflow.py:625-654`), `RunMetadata` via `maverick.runway.run_metadata`, partial-failure ID reporting, `COMMIT_OUTPUT` step honoring `auto_commit` via jj snapshot (mirror classic refuel's `COMMIT_OUTPUT` in `workflows/refuel_maverick/workflow.py`), explicit `cwd` threading throughout (no `Path.cwd()`)
- [X] T019 [US1] Verify `select_next_bead`'s `flight_plan_name` epic-state read (`src/maverick/library/actions/beads.py:342-347`) tolerates a speckit epic without that state key (research D12); if not, set `flight_plan_name=<feature dir basename>` on the epic in `workflow.py` and cover with a test in `tests/unit/workflows/refuel_speckit/test_workflow.py`
- [X] T020 [P] [US1] Write failing CLI tests in `tests/unit/cli/commands/refuel/test_speckit_dispatch.py`: `--speckit` forces ingestion mode with mode announcement, `--speckit` + unresolvable name → E02, error rendering for E04–E07 (Rich `err_console`, no tracebacks), `--list-steps` with `--speckit` lists the speckit step names, `--skip-briefing` on the speckit path warns and is ignored, success summary + `Next: maverick fly --epic <id>` hint via `find_latest_run`
- [X] T021 [US1] Implement the `--speckit` flag and explicit-mode dispatch in `src/maverick/cli/commands/refuel/_group.py` (resolve `cwd` once, call `speckit.detect.resolve_feature`, dispatch to `SpeckitRefuelWorkflow` via `execute_python_workflow`, keep classic path untouched) until T020 passes

**Checkpoint**: MVP — explicit `--speckit` ingestion works end-to-end including delta re-runs; `fly` can implement the resulting beads

---

## Phase 4: User Story 2 - Auto-detection of Spec Kit feature directories (Priority: P2)

**Goal**: `maverick refuel <feature>` without the flag picks the right mode from repository shape; ambiguity stops with clear instructions.

**Independent Test**: run refuel without `--speckit` against speckit-only, classic-only, both-match, and neither fixtures; verify dispatch matrix in contracts/cli-refuel-speckit.md.

- [X] T022 [P] [US2] Write failing tests for the auto-detection dispatch matrix in `tests/unit/cli/commands/refuel/test_speckit_dispatch.py`: speckit-only → ingestion with announcement, classic-only → classic workflow unchanged, both → E01 disambiguation error, neither → E02, both + `--speckit` → ingestion
- [X] T023 [US2] Implement no-flag auto-detection in `src/maverick/cli/commands/refuel/_group.py` using `FeatureResolution.mode` (dispatch matrix per contract; announce selected mode via `console`) until T022 passes

**Checkpoint**: Flag-free UX complete; classic refuel behavior verifiably unchanged

---

## Phase 5: User Story 3 - Preview ingestion without creating anything (Priority: P2)

**Goal**: `--dry-run` renders the complete would-be plan (epic, tasks, edges, skipped) with zero writes, and validates identically to a real run.

**Independent Test**: quickstart.md Scenario 1 — dry-run against valid and malformed fixtures; assert zero `bd` mutations and preview/real-run parity.

- [X] T024 [P] [US3] Write failing tests in `tests/unit/workflows/refuel_speckit/test_dry_run.py`: dry-run issues zero `bd` write commands (assert against `mock_runner` call list), skips `set_state`/chaining/run-metadata, renders per-task preview (ID, title, phase, `[P]`, blockers) + `Dry run — no beads created.` summary, parse/validation errors surface identically to real runs, result dict marks `dry_run=True` with same planned content as a real run over the same fixture (SC-005 parity), and dry-run over a delta state (existing epic in stub) previews only new tasks with `skipped_existing` listed and still writes nothing
- [X] T025 [US3] Implement dry-run: add `--dry-run` flag in `src/maverick/cli/commands/refuel/_group.py`, thread `dry_run` workflow input in `src/maverick/workflows/refuel_speckit/workflow.py`, pass `dry_run=True` to `create_beads`/`wire_dependencies`, branch out state/chaining/metadata writes, emit preview via `emit_output` until T024 passes

**Checkpoint**: Safe preview complete; SC-005 verifiable

---

## Phase 6: User Story 4 - Optional enrichment with verification commands (Priority: P3)

**Goal**: Opt-in `--enrich` runs one batched persona-agent call that attaches verification commands to new task beads; failure degrades to a warning; structure never changes.

**Independent Test**: quickstart.md Scenario 6 — enriched run has identical bead set/graph with augmented `## Verification`; broken provider auth still ingests with a warning.

- [X] T026 [P] [US4] Write failing tests in `tests/unit/speckit/test_enrichment.py` and `tests/unit/workflows/refuel_speckit/test_enrichment_step.py`: batched prompt covers all new tasks in one call, per-task command parsing merges into `## Verification` without touching any other description section, task set/edges byte-identical to unenriched plan otherwise, agent failure → structured warning + successful unenriched ingestion, no model construction at all when `--enrich` absent (FR-010), and `--dry-run --enrich` previews enriched verification content without any `bd` writes (research D9)
- [X] T027 [P] [US4] Add `SpeckitEnrichmentAgent` to `src/maverick/agents/personas.py` (one-shot persona, `provider_tier = "generate"`, modeled on `VerificationPropertiesAgent`; single batched prompt over task IDs + descriptions, returns commands keyed by task ID)
- [X] T028 [US4] Wire enrichment into `src/maverick/workflows/refuel_speckit/workflow.py` (`ENRICH` step between `PLAN_INGESTION` and `CREATE_BEADS`, so dry-run previews enriched output) and add `--enrich` flag in `src/maverick/cli/commands/refuel/_group.py`, runtime via `runtime_for_agent("generate", agents_config=config.agents)`, failure → warning path, until T026 passes

**Checkpoint**: All four user stories independently functional

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T029 [P] Add integration test `tests/integration/test_speckit_refuel.py` (marked for `make test-integration`; skips when `bd` unavailable) automating quickstart.md Scenarios 2 and 4 against a real temp `bd` database: fresh ingest → ready-order assertion → delta append → no-op run; log elapsed wall-clock per run and warn (not fail) if ingestion exceeds the SC-001 30 s bound
- [X] T030 [P] Update docs: CLAUDE.md CLI Workflows table (refuel speckit mode, `--dry-run`, `--enrich`) and `maverick refuel` Click help text/examples in `src/maverick/cli/commands/refuel/_group.py`
- [X] T031 Run `make format-fix && make ci` and fix all fallout (ruff, strict mypy, full test suite); confirm quickstart.md Scenario 7 (zero-model guarantee) by grepping the speckit/refuel_speckit packages for agent/runtime imports outside the enrichment path

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational. Core MVP.
- **US2 (Phase 4)**: Depends on Foundational + T021 (dispatch code it extends). Touches only `_group.py` + its test file.
- **US3 (Phase 5)**: Depends on US1 (T018 workflow, T021 CLI).
- **US4 (Phase 6)**: Depends on US1 (T015 plan builder, T018 workflow); independent of US2/US3.
- **Polish (Phase 7)**: Depends on desired user stories being complete (T029 needs US1; T030–T031 last)

### Within User Story 1

- T012, T013 (tests) before T014, T015 (build.py implementation); T014 before T015 (same file)
- T016 (workflow tests) before T017 → T018 → T019
- T020 (CLI tests) before T021; T021 after T018 (dispatch target must exist)

### Parallel Opportunities

- Phase 1: T002 ∥ T003 (after T001)
- Phase 2: T004 ∥ T006 ∥ T007 ∥ T010 (all test files, distinct); then T005 ∥ (T008→T009) ∥ T011
- Phase 3: T012 ∥ T013 ∥ T016 ∥ T020 (four distinct test files); T014→T015 ∥ T017
- US2 ∥ US4 once their prerequisites land (distinct files)
- Phase 7: T029 ∥ T030

---

## Parallel Example: User Story 1

```bash
# Write all US1 test files together (distinct files, all designed to fail first):
Task: "Edge-derivation tests in tests/unit/speckit/test_build_edges.py"
Task: "Plan-builder tests in tests/unit/speckit/test_build_plan.py"
Task: "Workflow tests in tests/unit/workflows/refuel_speckit/test_workflow.py"
Task: "CLI dispatch tests in tests/unit/cli/commands/refuel/test_speckit_dispatch.py"

# Then implement in dependency order:
Task: "build.py edges (T014) then plan builder (T015)" ∥ Task: "constants.py + models.py (T017)"
Task: "workflow.py (T018)" → Task: "flight_plan_name shim check (T019)" → Task: "CLI --speckit (T021)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phases 1–2 (Setup + Foundational: models, parser, detect)
2. Phase 3 (US1): explicit `--speckit` ingestion incl. delta + chaining
3. **STOP and VALIDATE**: quickstart.md Scenarios 2–5 + `make test-fast`
4. MVP is shippable — auto-detection, dry-run, and enrichment are additive

### Incremental Delivery

1. Setup + Foundational → parser provably correct on fixtures
2. US1 → deterministic ingestion usable via explicit flag (MVP)
3. US2 → flag-free UX
4. US3 → dry-run preview
5. US4 → optional enrichment
6. Polish → integration test, docs, `make ci` green

---

## Notes

- Every implementation task is gated by a named failing-test task (constitution Principle V)
- `[P]` tasks touch different files with no dependency on an incomplete task
- FR-010 invariant: nothing outside T027/T028 may import agent/runtime machinery
- Commit after each task or logical group (`bead(<id>)` prefixes when driven via maverick itself)
