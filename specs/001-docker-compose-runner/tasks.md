---

description: "Task list for Docker Compose Runner feature implementation"
---

# Tasks: Containerized Validation with Docker Compose

**Input**: Design documents from `/specs/001-docker-compose-runner/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/openapi.yaml ✅

**Tests**: This feature does NOT explicitly request tests in the specification, so test tasks are OMITTED per template guidelines.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Single project structure: `src/`, `tests/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and dependency management

- [X] T001 Add PyYAML dependency via `uv add pyyaml` in pyproject.toml
- [X] T002 Verify Docker Compose V2 availability by running `docker compose version` in worker startup
- [X] T003 [P] Create src/models/compose.py for Docker Compose data models
- [X] T004 [P] Create src/activities/compose.py for Docker Compose activities

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models and validation that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Implement ComposeConfig dataclass in src/models/compose.py
- [X] T006 Implement ComposeEnvironment dataclass in src/models/compose.py
- [X] T007 Implement ComposeUpResult dataclass in src/models/compose.py
- [X] T008 Implement ComposeCleanupParams dataclass in src/models/compose.py
- [X] T009 Implement ValidateInContainerParams dataclass in src/models/compose.py
- [X] T010 Implement ValidationResult dataclass in src/models/compose.py
- [X] T011 Implement resolve_target_service() function in src/models/compose.py
- [X] T012 Add compose_config: ComposeConfig | None field to WorkflowParameters in src/models/parameters.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Run validations inside a container (Priority: P1) 🎯 MVP

**Goal**: Enable developers to provide a Docker Compose YAML so the workflow brings up a fresh containerized environment before any checks, and all existing validation steps execute inside that environment.

**Independent Test**: Trigger the workflow with a valid Compose YAML that starts a single service. Verify the environment starts, validations run inside the container, and the workflow returns a readiness summary.

### Implementation for User Story 1

- [X] T013 [P] [US1] Implement compose_up_activity() in src/activities/compose.py to start Docker Compose environment with health checks
- [X] T014 [P] [US1] Implement validate_in_container_activity() in src/activities/compose.py to execute commands inside target container
- [X] T015 [P] [US1] Implement compose_down_activity() in src/activities/compose.py for cleanup operations
- [X] T016 [US1] Modify ReadinessWorkflow in src/workflows/readiness.py to add compose setup step before existing validations
- [X] T017 [US1] Modify ReadinessWorkflow in src/workflows/readiness.py to wrap existing validation activities with container execution when compose_config is provided
- [X] T018 [US1] Modify ReadinessWorkflow in src/workflows/readiness.py to add graceful cleanup step on success
- [X] T019 [US1] Update worker registration in src/workers/main.py to include new compose activities
- [X] T020 [US1] Modify CLI in src/cli/readiness.py to accept --compose-file parameter
- [X] T021 [US1] Implement YAML file reading and parsing in src/cli/readiness.py
- [X] T022 [US1] Implement ComposeConfig creation from parsed YAML in src/cli/readiness.py
- [X] T023 [US1] Update workflow invocation in src/cli/readiness.py to pass ComposeConfig parameter

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently. A developer can run the readiness workflow with a Docker Compose file, and validations will execute inside the container.

---

## Phase 4: User Story 2 - Fail fast on invalid configuration (Priority: P2)

**Goal**: Provide clear, actionable errors when Compose YAML is invalid or environment fails to start, with automatic cleanup of resources on validation errors and preserved resources on runtime failures.

**Independent Test**: Provide malformed YAML or a service that cannot start. Verify the workflow fails with a clear message and resources are handled appropriately (cleaned on validation errors, preserved on runtime failures).

### Implementation for User Story 2

- [X] T024 [US2] Implement early YAML validation in src/cli/readiness.py to check file size limit (1 MB)
- [X] T025 [US2] Implement YAML syntax validation in src/cli/readiness.py using yaml.safe_load with error handling
- [X] T026 [US2] Implement health check presence validation in src/cli/readiness.py for target service
- [X] T027 [US2] Enhance compose_up_activity() error handling in src/activities/compose.py to categorize error types (validation_error, docker_unavailable, startup_failed, health_check_timeout, health_check_failed)
- [X] T028 [US2] Implement stderr capture and last-50-lines extraction in src/activities/compose.py with tolerant decoding (errors='replace')
- [X] T029 [US2] Modify ReadinessWorkflow in src/workflows/readiness.py to add error handling for compose_up failures
- [X] T030 [US2] Implement conditional cleanup logic in src/workflows/readiness.py (preserve on runtime failures, cleanup on validation errors)
- [X] T031 [US2] Add cleanup instructions to workflow result in src/workflows/readiness.py when resources are preserved
- [X] T032 [US2] Update CLI error reporting in src/cli/readiness.py to display detailed error messages and cleanup instructions

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently. Invalid configurations are caught early with clear messages, and failed environments are preserved for troubleshooting.

---

## Phase 5: User Story 3 - Target a specific service (Priority: P3)

**Goal**: Enable developers to specify which service in a multi-service Compose file is used for executing validations, with sensible defaults when omitted.

**Independent Test**: Provide a Compose file with multiple services and specify the target service; verify checks run in that service. Repeat without specifying target to exercise default selection behavior.

### Implementation for User Story 3

- [X] T033 [US3] Add --target-service parameter to CLI in src/cli/readiness.py
- [X] T034 [US3] Implement default target selection logic in resolve_target_service() in src/models/compose.py (single service → use it, multiple → use "app", else → require explicit)
- [X] T035 [US3] Call resolve_target_service() during compose_up_activity() in src/activities/compose.py before starting environment
- [X] T036 [US3] Update error messages in resolve_target_service() in src/models/compose.py to list available services when target cannot be determined
- [X] T037 [US3] Store resolved target_service in ComposeEnvironment in src/activities/compose.py
- [X] T038 [US3] Use resolved target_service in validate_in_container_activity() in src/activities/compose.py
- [X] T039 [US3] Include resolved target_service in workflow result in src/workflows/readiness.py
- [X] T040 [US3] Update CLI help text in src/cli/readiness.py to document default selection policy

**Checkpoint**: All three user stories are now independently functional. Multi-service Compose files are fully supported with explicit or automatic service selection.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T041 [P] Add structured logging to compose_up_activity() in src/activities/compose.py for startup progress
- [X] T042 [P] Add structured logging to compose_down_activity() in src/activities/compose.py for cleanup operations
- [X] T043 [P] Add workflow.logger calls in ReadinessWorkflow in src/workflows/readiness.py for compose lifecycle events
- [X] T044 Implement exponential backoff health check polling in compose_up_activity() in src/activities/compose.py (1s, 2s, 4s, 8s, ..., max 30s)
- [X] T045 Implement unique project naming using workflow.info().workflow_id and workflow.info().run_id in src/workflows/readiness.py
- [X] T046 Implement temporary directory management using tempfile.mkdtemp() in compose_up_activity() in src/activities/compose.py
- [X] T047 Add duration tracking (workflow.now()) to compose operations in src/workflows/readiness.py
- [X] T048 Update README.md with Docker Compose feature overview and prerequisites
- [X] T049 Update AGENTS.md via update-agent-context.sh script to reflect new compose activities
- [X] T050 Validate quickstart.md examples by running through documented scenarios

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion (T001-T004) - BLOCKS all user stories
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion (T005-T012)
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Phase 6)**: Depends on desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Extends US1 activities with error handling (ideally implement after US1)
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - Extends US1 service resolution logic (ideally implement after US1)

### Within Each User Story

**User Story 1**:
- T013-T015 (activities) can run in parallel
- T016-T018 (workflow modifications) must be sequential
- T019 (worker registration) depends on T013-T015
- T020-T022 (CLI modifications) can run in parallel
- T023 (workflow invocation) depends on T020-T022

**User Story 2**:
- T024-T026 (CLI validation) can run in parallel
- T027-T028 (activity error handling) must follow T024-T026
- T029-T031 (workflow error handling) must follow T027-T028
- T032 (CLI error reporting) must follow T029-T031

**User Story 3**:
- T033 (CLI parameter) can run independently
- T034-T036 (resolution logic) must be sequential
- T037-T038 (activity usage) depend on T034-T036
- T039 (workflow result) depends on T037-T038
- T040 (CLI help) depends on T033

### Parallel Opportunities

- All Setup tasks marked [P] (T003, T004) can run in parallel after T001-T002
- Within US1: T013-T015 (activities) can run in parallel
- Within US1: T020-T022 (CLI modifications) can run in parallel
- All Polish tasks marked [P] (T041-T043) can run in parallel

---

## Parallel Example: User Story 1

```bash
# After Phase 2 completion, launch US1 activities together:
Task T013: "Implement compose_up_activity() in src/activities/compose.py"
Task T014: "Implement validate_in_container_activity() in src/activities/compose.py"
Task T015: "Implement compose_down_activity() in src/activities/compose.py"

# And launch US1 CLI modifications together:
Task T020: "Modify CLI in src/cli/readiness.py to accept --compose-file parameter"
Task T021: "Implement YAML file reading and parsing in src/cli/readiness.py"
Task T022: "Implement ComposeConfig creation from parsed YAML in src/cli/readiness.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 2: Foundational (T005-T012) - CRITICAL - blocks all stories
3. Complete Phase 3: User Story 1 (T013-T023)
4. **STOP and VALIDATE**: Test User Story 1 independently with a simple single-service Compose file
5. Deploy/demo if ready - this is a complete MVP!

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready (T001-T012)
2. Add User Story 1 (T013-T023) → Test independently → Deploy/Demo (MVP!)
   - Developers can now run validations in containers
3. Add User Story 2 (T024-T032) → Test independently → Deploy/Demo
   - Better error handling and resource management
4. Add User Story 3 (T033-T040) → Test independently → Deploy/Demo
   - Multi-service support with smart defaults
5. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together (T001-T012)
2. Once Foundational is done:
   - Developer A: User Story 1 (T013-T023)
   - Developer B: User Story 2 (T024-T032) - can start in parallel but may have merge conflicts with US1
   - Developer C: User Story 3 (T033-T040) - can start in parallel but may have merge conflicts with US1
3. **Recommended**: Complete US1 first, then US2 and US3 in parallel (reduces conflicts)

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- MVP (User Story 1) delivers core value: run validations in containers
- US2 adds production-ready error handling
- US3 adds convenience for multi-service scenarios
- All tasks follow TDD principles per constitution (activities are pure functions, workflows orchestrate)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Constitution compliance: PyYAML via uv (T001), workflow.logger only (T043), workflow.now() for timing (T047), structured logging (T041-T043)

---

## Success Metrics (from spec.md)

After completion of all phases:

- **SC-001**: With valid configuration, workflow starts environment and completes validations within 5 minutes for 95% of runs
- **SC-002**: On invalid configuration or startup failure, workflow terminates within 60 seconds with clear error message
- **SC-003**: Validation outcomes inside containers match non-containerized baseline in 95% of cases
- **SC-004**: 100% of environment resources cleaned up automatically on success; 100% preserved indefinitely on failure

**Test these metrics** at checkpoints after US1, US2, and US3 completion.
