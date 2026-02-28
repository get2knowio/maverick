# Tasks: Refuel Flight-Plan Subcommand

**Input**: Design documents from `/specs/039-refuel-flight-plan/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Tests**: Included — SC-006 explicitly requires automated test coverage for all new functionality.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/unit/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No setup tasks required — project infrastructure already exists. The `src/maverick/cli/commands/refuel/` package, `RefuelMaverickWorkflow`, and all supporting models are in place from specs 037 and 038.

**Checkpoint**: Ready to proceed directly to foundational implementation.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create the new CLI command module and register it with the `refuel` command group. These tasks MUST complete before any user story tests can be written.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T001 Create the `flight-plan` Click command module mirroring the existing `maverick_cmd.py` pattern in `src/maverick/cli/commands/refuel/flight_plan.py`. The module must: (1) import `refuel` group from `_group.py`, (2) define `_REFUEL_FLIGHT_PLAN_STEPS` list reusing constants from `maverick.workflows.refuel_maverick.constants`, (3) register `@refuel.command("flight-plan")` with function name `flight_plan_cmd`, (4) accept required `FLIGHT-PLAN-PATH` argument (`click.Path(exists=False, path_type=Path)`), (5) accept `--dry-run` flag (default False), `--list-steps` flag, and `--session-log` option (`click.Path(path_type=Path)`), (6) implement `--list-steps` early exit displaying all 7 step names with types, (7) delegate to `execute_python_workflow()` with `PythonWorkflowRunConfig` passing `RefuelMaverickWorkflow`, inputs `flight_plan_path` (as str) and `dry_run`, and `session_log_path`. Use `from __future__ import annotations`. See `src/maverick/cli/commands/refuel/maverick_cmd.py` as the exact reference.
- [X] T002 Register the `flight_plan` subcommand by adding `from maverick.cli.commands.refuel import flight_plan as _flight_plan  # noqa: F401` to `src/maverick/cli/commands/refuel/__init__.py` between the existing `maverick_cmd` import and the `# isort: on` comment.

**Checkpoint**: `maverick refuel flight-plan --help` should display the command help text with all options.

---

## Phase 3: User Story 1 — Decompose a Flight Plan into Beads (Priority: P1) 🎯 MVP

**Goal**: Verify the core `refuel flight-plan` command correctly delegates to `RefuelMaverickWorkflow` for full decomposition of a flight plan into work units and beads.

**Independent Test**: Run `maverick refuel flight-plan <path>` and confirm it delegates to the workflow with correct inputs. Verify command registration, required argument enforcement, step listing, and workflow delegation.

### Tests for User Story 1

- [X] T003 [US1] Write test `test_flight_plan_in_refuel_help` in `tests/unit/cli/commands/refuel/test_flight_plan.py` verifying that `"flight-plan"` appears in the output of `cli_runner.invoke(cli, ["refuel", "--help"])`. Follow the class structure `TestRefuelFlightPlanRegistered` matching `test_maverick_cmd.py` patterns — use `cli_runner`, `temp_dir`, `clean_env`, and `monkeypatch` fixtures.
- [X] T004 [US1] Write test `test_missing_flight_plan_arg` in `tests/unit/cli/commands/refuel/test_flight_plan.py` within class `TestRefuelFlightPlanCommand` verifying that invoking `["refuel", "flight-plan"]` without a path argument returns a non-zero exit code.
- [X] T005 [US1] Write test `test_list_steps_prints_step_names_and_exits` in `tests/unit/cli/commands/refuel/test_flight_plan.py` verifying that `["refuel", "flight-plan", "some-path.md", "--list-steps"]` exits with code 0 and the output contains all 7 step name constants (`PARSE_FLIGHT_PLAN`, `GATHER_CONTEXT`, `DECOMPOSE`, `VALIDATE`, `WRITE_WORK_UNITS`, `CREATE_BEADS`, `WIRE_DEPS`).
- [X] T006 [US1] Write test `test_delegates_to_refuel_maverick_workflow` in `tests/unit/cli/commands/refuel/test_flight_plan.py` that patches `maverick.cli.commands.refuel.flight_plan.execute_python_workflow` with `AsyncMock`, invokes `["refuel", "flight-plan", "my-plan.md"]`, and asserts the `run_config.workflow_class is RefuelMaverickWorkflow`.
- [X] T007 [US1] Write test `test_flight_plan_path_passed_as_string` in `tests/unit/cli/commands/refuel/test_flight_plan.py` that patches `execute_python_workflow`, invokes `["refuel", "flight-plan", "my-plan.md"]`, and asserts `run_config.inputs["flight_plan_path"] == "my-plan.md"`.

**Checkpoint**: Core delegation to `RefuelMaverickWorkflow` is verified — the command correctly parses the flight plan path and delegates workflow execution.

---

## Phase 4: User Story 2 — Preview Decomposition Without Creating Beads (Priority: P2)

**Goal**: Verify the `--dry-run` flag is correctly forwarded to the workflow, enabling decomposition preview without bead creation.

**Independent Test**: Run with `--dry-run` and confirm the flag is forwarded as `dry_run=True` in workflow inputs; run without the flag and confirm `dry_run=False`.

### Tests for User Story 2

- [X] T008 [US2] Write test `test_dry_run_flag_passed_to_workflow` in `tests/unit/cli/commands/refuel/test_flight_plan.py` that patches `execute_python_workflow`, invokes `["refuel", "flight-plan", "my-plan.md", "--dry-run"]`, and asserts `run_config.inputs["dry_run"] is True`.
- [X] T009 [US2] Write test `test_dry_run_is_false_by_default` in `tests/unit/cli/commands/refuel/test_flight_plan.py` that patches `execute_python_workflow`, invokes `["refuel", "flight-plan", "my-plan.md"]` (no `--dry-run`), and asserts `run_config.inputs["dry_run"] is False`.

**Checkpoint**: Dry-run flag forwarding is verified — users can preview decomposition safely.

---

## Phase 5: User Story 3 — Diagnose Issues via Session Log (Priority: P3)

**Goal**: Verify the `--session-log` option is correctly forwarded to `PythonWorkflowRunConfig.session_log_path` for diagnostic capture.

**Independent Test**: Run with `--session-log ./log.jsonl` and confirm the path is forwarded to the run config.

### Tests for User Story 3

- [X] T010 [US3] Write test `test_session_log_passed_to_run_config` in `tests/unit/cli/commands/refuel/test_flight_plan.py` that patches `execute_python_workflow`, invokes `["refuel", "flight-plan", "my-plan.md", "--session-log", str(log_path)]` (where `log_path = temp_dir / "session.log"`), and asserts `run_config.session_log_path == log_path`.

**Checkpoint**: Session log forwarding is verified — developers can capture diagnostic output for debugging.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verify help text completeness and run the full test suite.

- [X] T011 Write test `test_help_shows_correct_options` in `tests/unit/cli/commands/refuel/test_flight_plan.py` that invokes `["refuel", "flight-plan", "--help"]` and asserts the output contains `"--dry-run"`, `"--list-steps"`, and `"--session-log"`, with exit code 0.
- [X] T012 Run `make check` to verify all linting, type checking, and tests pass including the new `test_flight_plan.py` tests.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No tasks — existing infrastructure sufficient
- **Foundational (Phase 2)**: No prerequisites — can start immediately. **BLOCKS all user story tests.**
- **User Stories (Phases 3–5)**: All depend on Foundational phase completion (T001 + T002)
  - User stories can proceed sequentially in priority order (P1 → P2 → P3) since all tests target the same file
- **Polish (Phase 6)**: Depends on all user story phases being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) — no dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) — no dependencies on US1
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) — no dependencies on US1/US2

### Within Each User Story

- Tests verify behavior via mocked `execute_python_workflow` — no live workflow execution needed
- All tests in a story can be written together since they share the same test file

### Parallel Opportunities

- T001 and T002 are sequential (T002 imports the module created by T001)
- T003–T007 (US1 tests) all modify the same file — write together as a batch
- T008–T009 (US2 tests) append to the same file — write together as a batch
- T010 (US3 test) appends to the same file
- T011 (Polish test) appends to the same file
- **Practical parallelism**: Since all tests target one file, the most efficient approach is to create the complete test file in T003 and incrementally add test methods in subsequent tasks

---

## Parallel Example: User Story 1

```bash
# Foundational tasks must run sequentially:
Task T001: "Create flight_plan.py command module"
Task T002: "Register flight_plan in __init__.py"

# Then all US1 tests can be written together (same file):
Task T003: "Test flight-plan in refuel help"
Task T004: "Test missing argument"
Task T005: "Test list-steps"
Task T006: "Test delegates to workflow"
Task T007: "Test path passed as string"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 2: Foundational (T001–T002) — creates the command
2. Complete Phase 3: User Story 1 (T003–T007) — verifies core delegation
3. **STOP and VALIDATE**: Run `make test-fast` — command works end-to-end
4. The command is fully usable at this point

### Incremental Delivery

1. T001–T002 → Command module created and registered
2. T003–T007 → Core decomposition verified (MVP!)
3. T008–T009 → Dry-run forwarding verified
4. T010 → Session log forwarding verified
5. T011–T012 → Polish and full validation

### Practical Note

Given the ~50 LOC command module and ~200 LOC test file, an experienced implementer may complete all tasks in a single pass. The task decomposition exists for traceability to user stories, not because the implementation is complex.

---

## Delegated Coverage

The following functional requirements have no dedicated tasks in this task list because they are fully implemented and tested by the reused `RefuelMaverickWorkflow` from spec 038. The CLI command delegates to this workflow via `execute_python_workflow()`.

| Requirement | Description | Covered By |
|-------------|-------------|------------|
| FR-003 | Parse flight plan file | `RefuelMaverickWorkflow` step 1 (parse) |
| FR-004 | AI agent decomposition | `RefuelMaverickWorkflow` step 3 (decompose) |
| FR-005 | Write work unit files | `RefuelMaverickWorkflow` step 5 (write) |
| FR-006 | Create epic bead | `RefuelMaverickWorkflow` step 6 (create beads) |
| FR-007 | Create task beads with deps | `RefuelMaverickWorkflow` steps 6–7 (create beads, wire deps) |
| FR-010 | Real-time progress display | `execute_python_workflow()` event streaming |
| FR-011 | Error reporting (missing/malformed) | Workflow validation + `cli_error_handler()` |
| FR-014 | Fail completely on decomp failure | `RefuelMaverickWorkflow` error handling |
| FR-015 | Clean slate (remove stale files) | `RefuelMaverickWorkflow` step 5 (shutil.rmtree) |

Edge cases (EC-1 through EC-7 in spec.md) are also covered by the workflow's existing test suite.

---

## Notes

- The command module is a near-copy of `maverick_cmd.py` — use it as the primary reference
- No new models, workflows, or actions are needed — full reuse of spec 038
- All tests mock `execute_python_workflow` — no AI agent or bead infrastructure required for testing
- The `_PATCH_EXECUTE` path in tests must point to `maverick.cli.commands.refuel.flight_plan.execute_python_workflow`
- FR-012 compliance: existing `refuel speckit` and `refuel maverick` commands are not modified
