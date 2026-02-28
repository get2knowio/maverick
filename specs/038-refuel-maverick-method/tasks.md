# Tasks: Refuel Maverick Method — Native Flight Plan Decomposition

**Input**: Design documents from `/specs/038-refuel-maverick-method/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Included — project conventions require tests for all public classes and functions (CLAUDE.md: Test-First).

**Organization**: Tasks grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/unit/` at repository root (Python package)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package scaffolding for the new workflow

- [x] T001 Create workflow package with exports (RefuelMaverickWorkflow, RefuelMaverickResult) in `src/maverick/workflows/refuel_maverick/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Models, constants, and data structures that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T002 [P] Create step name constants (PARSE_FLIGHT_PLAN, GATHER_CONTEXT, DECOMPOSE, VALIDATE, WRITE_WORK_UNITS, CREATE_BEADS, WIRE_DEPS, WORKFLOW_NAME="refuel-maverick") in `src/maverick/workflows/refuel_maverick/constants.py`
- [x] T003 [P] Create Pydantic agent output models (FileScopeSpec with create/modify/protect lists, AcceptanceCriterionSpec with text and optional trace_ref, WorkUnitSpec with kebab-case ID regex validator and sequence >= 1 and non-empty verification, DecompositionOutput with non-empty work_units and unique-ID validator and rationale) and RefuelMaverickResult frozen dataclass with to_dict() (work_units_written, work_units_dir, epic, work_beads, dependencies, errors, coverage_warnings, dry_run) in `src/maverick/workflows/refuel_maverick/models.py`
- [x] T004 [P] Create FileContent frozen dataclass (path: str, content: str) and CodebaseContext frozen dataclass (files: tuple[FileContent, ...], missing_files: tuple[str, ...], total_size: int) in `src/maverick/library/actions/decompose.py`

**Checkpoint**: Foundation ready — user story implementation can begin

---

## Phase 3: User Story 1 — Decompose a Flight Plan into Work Units (Priority: P1) MVP

**Goal**: Transform a flight plan file into ordered work units with bead creation and dependency wiring — the complete end-to-end pipeline.

**Independent Test**: Provide a sample flight plan, verify work unit files produced with correct structure (task, file scope, acceptance criteria with SC trace refs, verification commands), beads created (1 epic + N tasks), and dependencies match work unit ordering.

### Implementation for User Story 1

- [x] T005 [US1] Implement all decomposition actions in `src/maverick/library/actions/decompose.py`: gather_codebase_context (async read in-scope files via asyncio.to_thread, collect FileContent entries, note missing files as warnings per R3), build_decomposition_prompt (format flight plan content + CodebaseContext into agent prompt per workflow-contract.md template with 3-15 work unit guideline and protect boundary propagation instructions), validate_decomposition (acyclic dependency graph via ExecutionOrder.from_work_units per R10, unique work unit IDs, SC coverage check logging warnings for uncovered criteria per R9, dangling depends_on reference detection), convert_specs_to_work_units (map list of WorkUnitSpec to WorkUnit models setting flight_plan name and source_path)
- [x] T006 [US1] Implement RefuelMaverickWorkflow(PythonWorkflow) with async _run() executing 7 steps in `src/maverick/workflows/refuel_maverick/workflow.py`: (1) parse_flight_plan via FlightPlanFile.aload(), (2) gather_context via gather_codebase_context, (3) decompose via StepExecutor with DecompositionOutput output_schema and tenacity AsyncRetrying (stop_after_attempt(3), wait_exponential, retry only transient errors per R8), (4) validate via validate_decomposition, (5) write_work_units (clear output dir, write via WorkUnitFile format {sequence:03d}-{id}.md per R7), (6) create_beads via existing create_beads action (1 epic + N task beads), (7) wire_deps via existing wire_dependencies action mapping depends_on to bead IDs per R5. Emit step events (StepStarted, StepCompleted) for each step per FR-014. Return RefuelMaverickResult.
- [x] T007 [US1] Implement maverick CLI command in `src/maverick/cli/commands/refuel/maverick_cmd.py` (Click command with flight-plan-path PATH argument, --dry-run flag, --list-steps flag, --session-log PATH option; --list-steps prints step names and exits; normal mode delegates to execute_python_workflow with PythonWorkflowRunConfig matching speckit.py pattern) and register command in refuel group (add import and refuel.add_command) in `src/maverick/cli/commands/refuel/__init__.py`

### Tests for User Story 1

- [x] T008 [P] [US1] Create test fixtures in `tests/unit/workflows/refuel_maverick/conftest.py`: sample simple FlightPlan fixture (3 success criteria, 5 in-scope files), mock StepExecutor returning DecompositionOutput with 4 WorkUnitSpecs (sequential deps, SC trace refs, verification commands), mock BeadClient, mock FlightPlanFile.aload, standard MaverickConfig and ComponentRegistry mocks
- [x] T009 [US1] Write workflow happy-path integration tests in `tests/unit/workflows/refuel_maverick/test_workflow.py`: all 7 steps execute in sequence, correct StepStarted/StepCompleted events emitted for each step, RefuelMaverickResult fields populated correctly (work_units_written count, work_units_dir path, epic info, work_beads tuple, dependencies tuple, empty errors), work unit files written to expected directory with correct naming pattern, StepExecutor called with DecompositionOutput as output_schema, create_beads called with correct epic and work definitions, wire_dependencies called with correct created_map and dependency relationships
- [x] T010 [P] [US1] Write decompose action unit tests in `tests/unit/library/actions/test_decompose.py`: gather_codebase_context reads existing files and returns FileContent entries, gather_codebase_context notes missing files in CodebaseContext.missing_files, build_decomposition_prompt includes flight plan content and file contents with path headers, validate_decomposition passes for valid acyclic graph, validate_decomposition returns coverage warnings for uncovered SC, validate_decomposition raises on circular dependencies, validate_decomposition raises on dangling depends_on references, convert_specs_to_work_units maps all fields correctly including flight_plan name
- [x] T011 [P] [US1] Write CLI command tests in `tests/unit/cli/commands/refuel/test_maverick_cmd.py`: flight-plan-path argument is required, --list-steps prints step names and exits with code 0, --dry-run flag passed through to workflow inputs, --session-log path passed to PythonWorkflowRunConfig, successful execution exits with code 0, workflow failure exits with code 1

**Checkpoint**: Core decomposition pipeline functional — parse flight plan, produce work units, create beads, wire dependencies

---

## Phase 4: User Story 2 — Dry Run Preview (Priority: P2)

**Goal**: Preview decomposition without creating beads or committing — work unit files written for inspection, bead system untouched.

**Independent Test**: Run with --dry-run, verify work unit files exist on disk but no bead creation calls made and no commits.

### Implementation for User Story 2

- [x] T012 [US2] Ensure dry-run conditional logic in workflow: steps 6 (create_beads) and 7 (wire_deps) skipped when dry_run=True, skipped steps emit appropriate events (step started + step completed with skip indicator), RefuelMaverickResult populated with dry_run=True, epic=None, empty work_beads and dependencies tuples, output messaging clearly indicates dry-run mode in `src/maverick/workflows/refuel_maverick/workflow.py`

### Tests for User Story 2

- [x] T013 [US2] Write dry-run specific tests in `tests/unit/workflows/refuel_maverick/test_workflow.py`: work unit files written to disk (steps 1-5 execute normally), create_beads action NOT called, wire_dependencies action NOT called, result.dry_run is True, result.epic is None, result.work_beads is empty tuple, result.dependencies is empty tuple, result.work_units_written matches expected count, events show steps 6-7 skipped

**Checkpoint**: Dry-run mode verified — developers can safely preview decomposition

---

## Phase 5: User Story 3 — Complex Flight Plan with Parallel Groups (Priority: P2)

**Goal**: Decompose complex flight plans into work units with parallel group assignments — independent units within a group execute concurrently, groups execute sequentially.

**Independent Test**: Provide a complex flight plan with multiple independent components, verify work units have parallel_group labels, independent units share groups, and bead dependencies allow concurrent execution within groups.

### Implementation for User Story 3

- [x] T014 [US3] Ensure parallel_group handling: decomposition prompt includes explicit instruction for agent to assign parallel_group labels to independent work units, validate_decomposition verifies ExecutionOrder.from_work_units produces correct parallel batches, bead wiring maps parallel_group info through to dependency structure in `src/maverick/library/actions/decompose.py` and `src/maverick/workflows/refuel_maverick/workflow.py`

### Tests for User Story 3

- [x] T015 [P] [US3] Create complex flight plan fixture (multiple independent scope areas, 10+ work units expected, mixed parallel and sequential dependencies) in `tests/unit/workflows/refuel_maverick/conftest.py`
- [x] T016 [US3] Write parallel group tests in `tests/unit/workflows/refuel_maverick/test_workflow_edge_cases.py`: decomposition of complex plan produces work units with parallel_group assigned, independent work units share same parallel_group, dependent work units are in different sequential groups, bead dependencies wired correctly (units in same group have no inter-dependencies, units depending on prior group wait for group completion), ExecutionOrder.from_work_units produces expected batch count

**Checkpoint**: Complex flight plans produce correctly grouped and ordered work units

---

## Phase 6: User Story 4 — Codebase-Aware Decomposition (Priority: P3)

**Goal**: Decomposition agent receives actual codebase file contents for in-scope files, producing work units grounded in the real codebase.

**Independent Test**: Provide a flight plan referencing existing files, verify agent receives file contents and work units reference actual file paths.

### Implementation for User Story 4

- [x] T017 [US4] Enhance gather_codebase_context to handle directory paths in in_scope (expand explicitly-listed directories to their contained files, consistent with quickstart.md examples like `src/auth/`), handle unreadable files gracefully (permission errors, binary files), and format CodebaseContext for agent consumption with clear file path headers and content boundaries in `src/maverick/library/actions/decompose.py`

### Tests for User Story 4

- [x] T018 [US4] Write codebase context tests in `tests/unit/library/actions/test_decompose.py`: in-scope file contents read and included in CodebaseContext.files, in-scope directory expanded to files within it, missing files recorded in CodebaseContext.missing_files with warning log, CodebaseContext.total_size reflects actual content size, build_decomposition_prompt embeds file contents with path headers so agent receives context, unreadable files handled gracefully without crash

**Checkpoint**: Decomposition grounded in actual codebase contents

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Edge cases, error handling, and validation across all user stories

- [x] T019 Write edge case tests in `tests/unit/workflows/refuel_maverick/test_workflow_edge_cases.py`: malformed flight plan raises clear parse error, agent failure after retry exhaustion raises with context, circular dependency in work units detected and reported before bead creation, dangling depends_on reference detected and reported, output directory with pre-existing files cleared before writing new work units, empty in_scope list produces empty CodebaseContext, all protect boundaries from flight plan propagated to every work unit's file_scope.protect, partial bead creation failure returns exit code 2 and collects errors in RefuelMaverickResult.errors
- [x] T020 Run `make check` (lint + typecheck + tests) and fix all issues across all new files
- [x] T021 Validate quickstart.md scenarios match implementation (CLI invocation, expected output format, work unit file structure, error messages for troubleshooting table)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational phase completion
- **US2 (Phase 4)**: Depends on US1 workflow implementation (T006)
- **US3 (Phase 5)**: Depends on US1 decompose actions and workflow (T005, T006)
- **US4 (Phase 6)**: Depends on US1 gather_codebase_context (T005)
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) — No dependencies on other stories
- **User Story 2 (P2)**: Builds on US1 workflow — dry-run flag modifies step 6-7 behavior
- **User Story 3 (P2)**: Builds on US1 decomposition — parallel groups extend decomposition output
- **User Story 4 (P3)**: Builds on US1 context gathering — enhances context quality for agent

### Within Each User Story

- Models before actions (Phase 2 before Phase 3)
- Actions before workflow (T005 before T006)
- Workflow before CLI (T006 before T007)
- Implementation before tests
- Test fixtures can be written in parallel with implementation

### Parallel Opportunities

- All Foundational tasks (T002, T003, T004) can run in parallel (different files)
- Test fixtures (T008) can run in parallel with implementation tasks T005-T007 (different files)
- Decompose action tests (T010) and CLI tests (T011) can run in parallel (different files)
- US2 (Phase 4) and US3 (Phase 5) can proceed in parallel (different concerns, minimal file overlap)
- US4 tests (T018) can start as soon as US1 gather_context (T005) is implemented

---

## Parallel Example: User Story 1

```bash
# Phase 2: All foundational tasks in parallel:
Task: "Create step name constants in src/maverick/workflows/refuel_maverick/constants.py"
Task: "Create Pydantic models in src/maverick/workflows/refuel_maverick/models.py"
Task: "Create dataclasses in src/maverick/library/actions/decompose.py"

# Phase 3: Test fixtures in parallel with later implementation tasks:
Task: "Create test fixtures in tests/unit/workflows/refuel_maverick/conftest.py"
# ...while workflow and CLI are being implemented

# Phase 3: Test tasks in parallel (different files):
Task: "Decompose action tests in tests/unit/library/actions/test_decompose.py"
Task: "CLI command tests in tests/unit/cli/commands/refuel/test_maverick_cmd.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Run `make test-fast`, verify work units are generated correctly
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational -> Foundation ready
2. Add User Story 1 -> Test independently -> MVP ready!
3. Add User Story 2 -> Dry-run support -> Safe preview
4. Add User Story 3 -> Parallel groups -> Complex features supported
5. Add User Story 4 -> Codebase-aware -> Higher quality decomposition
6. Polish -> Edge cases, validation -> Production-ready

### Key Research Decisions Applied

- **R1**: StepExecutor with output_schema for decompose step (not GeneratorAgent)
- **R2**: Separate WorkUnitSpec model for agent output (not full WorkUnit)
- **R3**: Direct file reading via asyncio.to_thread (not gather_local_review_context)
- **R4**: Reuse existing create_beads and wire_dependencies actions
- **R5**: Explicit depends_on mapping to bead deps (no DependencyExtractor needed)
- **R6**: File named maverick_cmd.py to avoid package collision
- **R7**: Work unit files named {sequence:03d}-{id}.md
- **R8**: tenacity AsyncRetrying stop_after_attempt(3) for agent retries
- **R9**: Warning-level SC coverage validation (non-blocking)
- **R10**: ExecutionOrder.from_work_units for cycle detection

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Existing models (FlightPlan, WorkUnit, FlightPlanFile, WorkUnitFile, BeadClient, bead actions) are reused unchanged
- All new code requires `from __future__ import annotations` per project convention
- Use structlog for logging, tenacity for retries, Pydantic for models per CLAUDE.md standards
