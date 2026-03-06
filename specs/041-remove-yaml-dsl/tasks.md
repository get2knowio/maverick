# Tasks: Remove Dead YAML DSL Infrastructure

**Input**: Design documents from `/specs/041-remove-yaml-dsl/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: Not explicitly requested. Existing tests are moved/updated as part of the refactoring; no new test authoring required.

**Organization**: Tasks grouped by user story. US1 (extract) must complete before US3 (CLI cleanup) and US2 (deletion). US4 (test cleanup) comes last.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Establish green baseline before refactoring

- [X] T001 Run `make check` to establish green baseline — lint, typecheck, and all tests must pass before any changes

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: No separate foundational work required — US1 (Phase 3) serves as the foundation for all subsequent phases.

**Checkpoint**: Proceed directly to Phase 3 (US1)

---

## Phase 3: User Story 1 — Extract Live Modules to Proper Locations (Priority: P1) 🎯 MVP

**Goal**: Move all actively-used code out of `maverick.dsl` to new top-level locations with zero behavior changes.

**Independent Test**: `make check` passes after extraction. All existing Python workflow tests pass with new import paths. Both old and new import paths coexist during this phase.

### Leaf Module Extraction (no internal dependencies)

- [X] T002 [P] [US1] Create `src/maverick/types.py` from `src/maverick/dsl/types.py` — keep StepType, StepMode, AutonomyLevel enums; remove dead type aliases (ContextBuilder, Predicate, RollbackAction) and the TYPE_CHECKING import of WorkflowContext
- [X] T003 [P] [US1] Create `src/maverick/constants.py` from `src/maverick/dsl/config.py` — extract active constants as module-level values: CHECKPOINT_DIR, COMMAND_TIMEOUT, DEFAULT_RETRY_ATTEMPTS, DEFAULT_RETRY_DELAY, RETRY_BACKOFF_MAX, RETRY_JITTER_MIN, MAX_STEP_OUTPUT_SIZE, MAX_CONTEXT_SIZE; do NOT copy dead constants (ASCII_DIAGRAM_*, PROJECT_STRUCTURE_MAX_DEPTH, DEFAULT_ISSUE_LIMIT, DEFAULT_RECENT_COMMIT_LIMIT) or the DSLDefaults dataclass wrapper
- [X] T004 [P] [US1] Add live error classes to `src/maverick/exceptions/workflow.py` — add WorkflowStepError (renamed from DSLWorkflowError), CheckpointNotFoundError, InputMismatchError, ReferenceResolutionError, DuplicateComponentError as subclasses of WorkflowError

### Dependent Module Extraction

- [X] T005 [P] [US1] Create `src/maverick/events.py` from `src/maverick/dsl/events.py` — update internal import: `maverick.dsl.types` → `maverick.types`
- [X] T006 [P] [US1] Create `src/maverick/results.py` from `src/maverick/dsl/results.py` — update internal import: `maverick.dsl.types` → `maverick.types`

### Package Extraction

- [X] T007 [P] [US1] Create `src/maverick/checkpoint/` package from `src/maverick/dsl/checkpoint/` — copy `__init__.py`, `store.py`, `data.py`; update `store.py` to import `CHECKPOINT_DIR` from `maverick.constants` instead of `DEFAULTS.CHECKPOINT_DIR` from `maverick.dsl.config`; update error imports: `maverick.dsl.errors.CheckpointNotFoundError` → `maverick.exceptions.workflow.CheckpointNotFoundError`, `maverick.dsl.errors.InputMismatchError` → `maverick.exceptions.workflow.InputMismatchError`
- [X] T008 [P] [US1] Create `src/maverick/registry/` package from `src/maverick/dsl/serialization/registry/` — copy `component_registry.py`, `protocol.py`, `validation.py`, `actions.py`, `agents.py`, `generators.py`, `__init__.py`; DELETE dead `WorkflowRegistry` and `ContextBuilderRegistry` content; remove `workflows` and `context_builders` attributes from `ComponentRegistry`; remove `WorkflowType` and `ContextBuilderType` from `protocol.py`; remove `validate_context_builder` from `validation.py`; update all internal self-references from `maverick.dsl.serialization.registry` → `maverick.registry`; update error imports: `maverick.dsl.errors.ReferenceResolutionError` → `maverick.exceptions.workflow.ReferenceResolutionError`, `maverick.dsl.errors.DuplicateComponentError` → `maverick.exceptions.workflow.DuplicateComponentError`
- [X] T009 [US1] Create `src/maverick/executor/` package from `src/maverick/dsl/executor/` — copy `__init__.py`, `protocol.py`, `claude.py`, `config.py`, `result.py`, `errors.py`; update internal imports: `maverick.dsl.events` → `maverick.events`, `maverick.dsl.executor.*` → `maverick.executor.*`, `maverick.dsl.serialization.registry` → `maverick.registry`, `maverick.dsl.types` → `maverick.types`

### Consumer Import Updates

- [X] T010 [P] [US1] Update imports in `src/maverick/config.py` — `maverick.dsl.executor.config.StepConfig` → `maverick.executor.config.StepConfig`
- [X] T011 [P] [US1] Update imports in `src/maverick/workflows/base.py` — `maverick.dsl.events` → `maverick.events`, `maverick.dsl.results` → `maverick.results`, `maverick.dsl.types` → `maverick.types`, `maverick.dsl.executor.protocol` → `maverick.executor.protocol`, `maverick.dsl.executor.config` → `maverick.executor.config`, `maverick.dsl.checkpoint` → `maverick.checkpoint`, `maverick.dsl.serialization.registry` → `maverick.registry`, `maverick.dsl.errors.DSLWorkflowError` → `maverick.exceptions.workflow.WorkflowStepError` (class rename)
- [X] T012 [P] [US1] Update imports in `src/maverick/workflows/generate_flight_plan/workflow.py` and `src/maverick/workflows/refuel_maverick/workflow.py` — `maverick.dsl.executor.errors` → `maverick.executor.errors`, `maverick.dsl.types` → `maverick.types`
- [X] T013 [P] [US1] Update imports in `src/maverick/cli/workflow_executor.py` — `maverick.dsl.events` → `maverick.events`, `maverick.dsl.executor.claude` → `maverick.executor.claude`, `maverick.dsl.checkpoint` → `maverick.checkpoint`; leave dead imports intact (removed in US3)
- [X] T014 [P] [US1] Update imports in `src/maverick/cli/common.py` — `maverick.dsl.serialization.registry.ComponentRegistry` → `maverick.registry.ComponentRegistry`; leave dead imports intact (removed in US3)
- [X] T015 [P] [US1] Update imports in `src/maverick/session_journal.py` — `maverick.dsl.events` → `maverick.events`
- [X] T016 [P] [US1] Update imports in `src/maverick/library/actions/preflight.py` and `src/maverick/library/actions/beads.py` — `maverick.dsl.events` → `maverick.events`
- [X] T017 [P] [US1] Update imports in `src/maverick/library/agents/__init__.py`, `src/maverick/library/actions/__init__.py`, and `src/maverick/library/generators/__init__.py` — `maverick.dsl.serialization.registry.ComponentRegistry` → `maverick.registry.ComponentRegistry`

### Verification

- [X] T018 [US1] Run `make check` — lint, typecheck, and all tests must pass with both old and new import paths coexisting

**Checkpoint**: All live modules extracted to new top-level locations. Old `dsl/` still exists but is no longer imported by active source code. Tests pass because both import paths resolve.

---

## Phase 4: User Story 3 — Clean Up CLI Entry Points (Priority: P2)

**Goal**: Remove dead YAML DSL functions and imports from CLI modules so no active file imports from `maverick.dsl` after this phase.

**Independent Test**: Dead functions no longer exist in CLI modules. `make lint` and `make typecheck` pass.

- [X] T019 [P] [US3] Remove dead functions and imports from `src/maverick/cli/workflow_executor.py` — delete `execute_workflow_run()` (defined but never called by any Click command), `format_workflow_not_found_error()` (only called by dead `execute_workflow_run`), and dead imports: `parse_workflow` from `maverick.dsl.serialization.parser`, `DiscoveryResult` (if present)
- [X] T020 [P] [US3] Remove dead function from `src/maverick/cli/helpers.py` — delete `execute_dsl_workflow()` and remove `"execute_dsl_workflow"` from `__all__`; remove associated dead imports
- [X] T021 [P] [US3] Clean up `src/maverick/cli/common.py` — remove dead imports (`register_all_context_builders`, `DiscoveryResult`, `create_discovery`, `load_workflows_into_registry`), dead function calls (`register_all_context_builders(registry)`, `load_workflows_into_registry(registry)`), and dead function `get_discovery_result()`
- [X] T022 [P] [US3] Clean up `src/maverick/library/builtins.py` — remove YAML-loading methods (`get_workflow()`, `get_fragment()` that call dead `parse_workflow`), remove `BuiltinWorkflowLibrary` class (entirely dead — no active code outside library/ references it); remove `BUILTIN_WORKFLOWS`, `BUILTIN_FRAGMENTS` frozensets and all `*_INFO` constants (`FLY_BEADS_WORKFLOW_INFO`, `REFUEL_SPECKIT_WORKFLOW_INFO`, `VALIDATE_AND_FIX_FRAGMENT_INFO`, `COMMIT_AND_PUSH_FRAGMENT_INFO`, `CREATE_PR_WITH_SUMMARY_FRAGMENT_INFO`), `BuiltinWorkflowInfo`, `BuiltinFragmentInfo` dataclasses — all only referenced within `library/builtins.py` and `library/__init__.py`; also clean up `src/maverick/library/__init__.py` to remove the dead re-exports and `__all__` entries for these symbols
- [X] T023 [US3] Run `make lint` and `make typecheck` to verify CLI cleanup — all imports must resolve cleanly

**Checkpoint**: All CLI and library files are clean of dead YAML DSL references. No active source file imports from `maverick.dsl`.

---

## Phase 5: User Story 2 — Delete Dead YAML DSL Code (Priority: P2)

**Goal**: Bulk-delete the entire dead `maverick.dsl` package, dead YAML files, and the `lark` dependency.

**Independent Test**: `src/maverick/dsl/` does not exist. `lark` is not in `pyproject.toml`. `uv sync` succeeds. `make lint` and `make typecheck` pass. Some test failures are expected until US4 completes.

- [X] T024 [P] [US2] Delete dead YAML workflow files — remove `src/maverick/library/workflows/fly-beads.yaml`, `src/maverick/library/workflows/refuel-speckit.yaml`, and `src/maverick/library/workflows/__init__.py`; remove directory if empty
- [X] T025 [P] [US2] Delete dead YAML fragment files — remove `src/maverick/library/fragments/validate_and_fix.yaml`, `src/maverick/library/fragments/commit_and_push.yaml`, `src/maverick/library/fragments/create_pr_with_summary.yaml`, `src/maverick/library/fragments/review_and_fix.yaml`, and `src/maverick/library/fragments/__init__.py`; do NOT delete `review-and-fix-with-registry.yaml` (actively used)
- [X] T026 [P] [US2] Delete entire `src/maverick/dsl/` package — rm -rf `src/maverick/dsl/` (~20,000 LOC of dead YAML DSL infrastructure)
- [X] T027 [US2] Remove `lark` dependency from `pyproject.toml` — delete the `lark>=1.2,<2` line and run `uv sync` to verify clean dependency resolution without lark
- [X] T028 [US2] Run `make lint` and `make typecheck` — must pass; test failures from dead test imports are expected and addressed in US4

**Checkpoint**: Dead YAML DSL source code is gone. `maverick.dsl` package no longer exists. Some test files that imported from `maverick.dsl` will fail — addressed in Phase 6.

---

## Phase 6: User Story 4 — Delete Dead Tests (Priority: P3)

**Goal**: Move live tests to match new source locations, delete all dead test code, verify full test suite passes with zero `maverick.dsl` references.

**Independent Test**: `make test` passes. `grep -r "maverick\.dsl" src/ tests/` returns no matches.

### Move Live Tests

- [X] T029 [P] [US4] Move live executor tests — move `tests/unit/dsl/executor/` to `tests/unit/executor/`, EXCLUDING `test_step_path.py` (dead — tests dead YAML step_path module); update all imports in moved files: `maverick.dsl.executor` → `maverick.executor`, `maverick.dsl.events` → `maverick.events`, `maverick.dsl.serialization.registry` → `maverick.registry`; also move any `conftest.py` with shared fixtures
- [X] T030 [P] [US4] Move live checkpoint tests — move `tests/unit/dsl/checkpoint/` to `tests/unit/checkpoint/`; update all imports: `maverick.dsl.checkpoint` → `maverick.checkpoint`, `maverick.dsl.config` → `maverick.constants`
- [X] T031 [P] [US4] Move live module tests — move `tests/unit/dsl/test_events.py` → `tests/unit/test_events.py`, `tests/unit/dsl/test_results.py` → `tests/unit/test_results.py`, `tests/unit/dsl/test_types.py` → `tests/unit/test_types.py`; update all imports: `maverick.dsl.*` → `maverick.*`
- [X] T032 [P] [US4] Move and update error tests — move `tests/unit/dsl/test_errors.py` → `tests/unit/test_workflow_errors.py`; update to test errors at `maverick.exceptions.workflow`; rename `DSLWorkflowError` references to `WorkflowStepError`

### Delete Dead Tests

- [X] T033 [US4] Delete remaining `tests/unit/dsl/` directory — everything left is dead: serialization/, expressions/, visualization/, discovery/, steps/, prerequisites/, context tests, streaming tests, protocols tests, test_step_path.py
- [X] T034 [P] [US4] Delete `tests/integration/dsl/` directory — entirely dead (~5,400 LOC of YAML integration tests)

### Verification

- [X] T035 [US4] Run `make check` and verify zero `maverick.dsl` references — `make lint`, `make typecheck`, `make test` must all pass; `grep -r "maverick\.dsl" src/ tests/` must return empty; note: documentation files (CLAUDE.md, .specify/) are updated separately by T036 and T037

**Checkpoint**: All dead tests removed. All live tests pass at new locations. Zero references to `maverick.dsl` anywhere in the codebase.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Update documentation to reflect the new architecture

- [X] T036 [P] Update `CLAUDE.md` — remove YAML DSL sections (Workflow Architecture: YAML-Based DSL, WorkflowFile serialization, Example YAML Workflow, Workflow Discovery Locations, Migration from Decorator DSL), update Architecture diagram to show new top-level modules (events, executor, checkpoint, registry, types, constants), update file organization table
- [X] T037 [P] Update `.specify/memory/constitution.md` — remove Guardrails #11 (workspace cwd threading for DSL) and #12 (DSL expression type safety); update Principle I and Guardrail #2 to remove "DSL PythonStep" references; update Guardrail #5 to remove "DSL/workflow definition" reference; remove DSL execution row from Appendix A split patterns; update Appendix C code example from `from maverick.dsl.events import StepOutput` to `from maverick.events import StepOutput`; update or remove Appendix E DSL-specific cwd threading content (reframe for Python workflows only); remove Guardrails #11/#12 references from Compliance Review section
- [X] T038 Run verification checklist in `specs/041-remove-yaml-dsl/quickstart.md` — validate all import checks, file existence checks, and CLI command checks
- [X] T039 Run `make ci` for final green validation — fail-fast mode, all checks must pass

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — establishes baseline
- **US1 (Phase 3)**: Depends on Setup — BLOCKS all subsequent phases
- **US3 (Phase 4)**: Depends on US1 — removes dead CLI code before bulk deletion
- **US2 (Phase 5)**: Depends on US1 and US3 — bulk-deletes `maverick.dsl/` after all active imports point to new locations
- **US4 (Phase 6)**: Depends on US2 — moves/deletes tests after source structure is finalized
- **Polish (Phase 7)**: Depends on US4 — documentation updates after all code changes are complete

### User Story Dependencies

- **US1 (P1)**: Can start after baseline — no dependencies on other stories
- **US3 (P2)**: Depends on US1 — CLI files must have live imports updated before dead code removal
- **US2 (P2)**: Depends on US1 and US3 — all active imports must point to new locations before `dsl/` deletion
- **US4 (P3)**: Depends on US2 — test moves must happen after source structure is finalized

### Within US1 (Extraction Order)

1. `types.py`, `constants.py`, error classes → leaf modules, no internal deps (parallel)
2. `events.py`, `results.py` → depend on types (parallel with each other)
3. `checkpoint/`, `registry/` → depend on constants (parallel with each other)
4. `executor/` → depends on events, results, registry (must come after steps 2-3)
5. Consumer import updates → all extraction must be complete (parallel within group)
6. Verification

### Parallel Opportunities

- T002, T003, T004 can run in parallel (leaf modules, no dependencies)
- T005, T006 can run in parallel (both depend only on types)
- T007, T008 can run in parallel (independent packages)
- T010–T017 can all run in parallel (independent consumer files)
- T019, T020, T021, T022 can run in parallel (independent source files)
- T024, T025, T026 can run in parallel (independent deletion targets)
- T029, T030, T031, T032 can run in parallel (independent test directories/files)
- T036, T037 can run in parallel (independent documentation files)

---

## Parallel Example: US1 Extraction

```text
# Wave 1: Leaf modules (no deps)
Task T002: "Create src/maverick/types.py"
Task T003: "Create src/maverick/constants.py"
Task T004: "Add live errors to src/maverick/exceptions/workflow.py"

# Wave 2: Dependent modules (parallel with each other)
Task T005: "Create src/maverick/events.py"
Task T006: "Create src/maverick/results.py"
Task T007: "Create src/maverick/checkpoint/ package"
Task T008: "Create src/maverick/registry/ package"

# Wave 3: Executor (depends on waves 1-2)
Task T009: "Create src/maverick/executor/ package"

# Wave 4: Import updates (all parallel)
Tasks T010–T017: "Update consumer imports across all active source files"
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup (baseline verification)
2. Complete Phase 3: US1 — Extract all live modules to new locations
3. **STOP and VALIDATE**: `make check` passes, all active code uses new imports
4. Safe stopping point — codebase works identically with old `dsl/` still present

### Incremental Delivery

1. US1 (Extract) → Validate → Safe stopping point (MVP)
2. US3 (CLI Cleanup) → Validate → Dead CLI functions removed
3. US2 (Bulk Delete) → Validate → ~20,000 lines of dead source removed
4. US4 (Test Cleanup) → Validate → ~33,400 lines of dead tests removed; zero `maverick.dsl` references
5. Polish → Final CI green → Feature complete

### Key Metrics

| Metric | Value |
|--------|-------|
| Source lines removed | ~20,000 (entire `maverick.dsl` package; ~16,300 dead + ~3,700 relocated) |
| Test lines removed | ~33,400 (dead YAML DSL tests: ~28,000 unit + ~5,400 integration) |
| Dependencies removed | 1 (`lark` parser library) |
| Dead functions removed | 4 (CLI) + YAML-loading methods (`library/builtins.py`) |
| Dead YAML files removed | 6 (2 workflows + 4 fragments) |
| New top-level modules | 7 (`types`, `constants`, `events`, `results`, `executor/`, `checkpoint/`, `registry/`) |

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Both old and new import paths coexist during US1 — tests pass because `dsl/` is not yet deleted
- US3 MUST complete before US2 to avoid broken imports during CLI cleanup
- Dead `test_step_path.py` in executor tests must NOT be moved (tests dead YAML step_path module)
- Do NOT delete `review-and-fix-with-registry.yaml` from fragments/ — it is actively used
- Checkpoint data uses JSON, not pickled classes — no serialization impact from module moves
- Verify `library/builtins.py` metadata references before removing — some constants may be active
