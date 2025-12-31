# Tasks: Safety and Logging Hooks

**Input**: Design documents from `/specs/007-safety-hooks/`
**Prerequisites**: plan.md (complete), spec.md (complete), research.md (complete), data-model.md (complete), contracts/hooks-api.md (complete)

**Tests**: Tests are included as this feature involves safety-critical validation that requires verification.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4, US5)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/hooks/`, `tests/unit/hooks/`, `tests/integration/hooks/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and hooks module structure

- [X] T001 Create hooks module directory structure at src/maverick/hooks/
- [ ] T002 Create hooks module __init__.py with public API exports in src/maverick/hooks/__init__.py
- [X] T003 [P] Create test directory structure for hooks at tests/unit/hooks/ and tests/integration/hooks/
- [X] T004 [P] Add hook exceptions (HookError, SafetyHookError, HookConfigError) to src/maverick/exceptions.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core types and configuration that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Create types module with ValidationResult dataclass in src/maverick/hooks/types.py
- [X] T006 [P] Add ToolExecutionLog dataclass to src/maverick/hooks/types.py
- [X] T007 [P] Add ToolMetricEntry and ToolMetrics dataclasses to src/maverick/hooks/types.py
- [X] T008 Create SafetyConfig Pydantic model with default sensitive paths in src/maverick/hooks/config.py
- [X] T009 [P] Add LoggingConfig Pydantic model to src/maverick/hooks/config.py
- [X] T010 [P] Add MetricsConfig Pydantic model to src/maverick/hooks/config.py
- [X] T011 Add HookConfig root model combining all config types in src/maverick/hooks/config.py
- [X] T012 [P] Unit tests for types module in tests/unit/hooks/test_types.py
- [X] T013 [P] Unit tests for config module in tests/unit/hooks/test_config.py
- [X] T013a [P] Unit tests for malformed regex validation in SafetyConfig.bash_blocklist in tests/unit/hooks/test_config.py

**Checkpoint**: Foundation ready - types and configuration complete, user story implementation can begin

---

## Phase 3: User Story 1 - Block Dangerous Bash Commands (Priority: P1)

**Goal**: PreToolUse safety hook that blocks destructive bash commands (rm -rf, fork bombs, disk formatting)

**Independent Test**: Configure hook, attempt dangerous commands → blocked; attempt safe commands → allowed

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T014 [P] [US1] Unit tests for dangerous pattern detection in tests/unit/hooks/test_safety.py
- [X] T015 [P] [US1] Unit tests for compound command parsing in tests/unit/hooks/test_safety.py
- [X] T016 [P] [US1] Unit tests for environment variable expansion in tests/unit/hooks/test_safety.py
- [X] T017 [P] [US1] Unit tests for unicode/escape normalization in tests/unit/hooks/test_safety.py

### Implementation for User Story 1

- [X] T018 [US1] Create bash command normalizer (unicode, escapes) in src/maverick/hooks/safety.py
- [X] T019 [US1] Implement environment variable expansion in src/maverick/hooks/safety.py
- [X] T020 [US1] Implement compound command parser (&&, ||, ;, |) in src/maverick/hooks/safety.py
- [X] T021 [US1] Create dangerous pattern blocklist (rm -rf, fork bombs, mkfs, dd, shutdown) in src/maverick/hooks/safety.py
- [X] T022 [US1] Implement validate_bash_command async hook function in src/maverick/hooks/safety.py
- [X] T023 [US1] Add fail-closed exception handling wrapper to validate_bash_command in src/maverick/hooks/safety.py
- [X] T024 [US1] Add custom blocklist support from SafetyConfig in src/maverick/hooks/safety.py
- [X] T025 [US1] Add allow-override support from SafetyConfig in src/maverick/hooks/safety.py

**Checkpoint**: User Story 1 complete - bash command validation fully functional and tested

---

## Phase 4: User Story 2 - Block Writes to Sensitive Paths (Priority: P1)

**Goal**: PreToolUse safety hook that blocks writes to sensitive paths (.env, .ssh, /etc)

**Independent Test**: Configure hook, attempt writes to sensitive paths → blocked; attempt writes to normal paths → allowed

### Tests for User Story 2

- [X] T026 [P] [US2] Unit tests for path canonicalization in tests/unit/hooks/test_safety.py
- [X] T027 [P] [US2] Unit tests for sensitive path pattern matching in tests/unit/hooks/test_safety.py
- [X] T028 [P] [US2] Unit tests for allowlist/blocklist handling in tests/unit/hooks/test_safety.py

### Implementation for User Story 2

- [X] T029 [US2] Create path normalizer (unicode, expand ~, resolve symlinks) in src/maverick/hooks/safety.py
- [X] T030 [US2] Implement path canonicalization with realpath() in src/maverick/hooks/safety.py
- [X] T031 [US2] Create default sensitive path patterns from SafetyConfig in src/maverick/hooks/safety.py
- [X] T032 [US2] Implement validate_file_write async hook function in src/maverick/hooks/safety.py
- [X] T033 [US2] Add fail-closed exception handling wrapper to validate_file_write in src/maverick/hooks/safety.py
- [X] T034 [US2] Add custom allowlist support from SafetyConfig in src/maverick/hooks/safety.py
- [X] T035 [US2] Add custom blocklist support from SafetyConfig in src/maverick/hooks/safety.py

**Checkpoint**: User Story 2 complete - file write validation fully functional and tested

---

## Phase 5: User Story 3 - Log All Tool Executions (Priority: P2)

**Goal**: PostToolUse logging hook that records tool executions with sanitized inputs

**Independent Test**: Execute tools, verify log entries contain expected fields with sensitive data redacted

### Tests for User Story 3

- [X] T036 [P] [US3] Unit tests for sensitive pattern sanitization in tests/unit/hooks/test_logging.py
- [X] T037 [P] [US3] Unit tests for output truncation in tests/unit/hooks/test_logging.py
- [X] T038 [P] [US3] Unit tests for log entry creation in tests/unit/hooks/test_logging.py

### Implementation for User Story 3

- [X] T039 [US3] Create sensitive data patterns (passwords, API keys, tokens) in src/maverick/hooks/logging.py
- [X] T040 [US3] Implement sanitize_string function for secret redaction in src/maverick/hooks/logging.py
- [X] T041 [US3] Implement truncate_output function in src/maverick/hooks/logging.py
- [X] T042 [US3] Implement log_tool_execution async hook function in src/maverick/hooks/logging.py
- [X] T043 [US3] Configure Python logger per LoggingConfig settings in src/maverick/hooks/logging.py
- [X] T044 [US3] Add custom sensitive pattern support from LoggingConfig in src/maverick/hooks/logging.py

**Checkpoint**: User Story 3 complete - execution logging fully functional and tested

---

## Phase 6: User Story 4 - Collect Execution Metrics (Priority: P2)

**Goal**: PostToolUse hook with MetricsCollector for tracking call counts, success rates, and timing

**Independent Test**: Execute series of tools, query MetricsCollector, verify accurate counts and timing statistics

### Tests for User Story 4

- [X] T045 [P] [US4] Unit tests for MetricsCollector record and query operations in tests/unit/hooks/test_metrics.py
- [X] T046 [P] [US4] Unit tests for rolling window eviction in tests/unit/hooks/test_metrics.py
- [X] T047 [P] [US4] Unit tests for thread-safety under concurrent access in tests/unit/hooks/test_metrics.py
- [X] T048 [P] [US4] Unit tests for percentile calculations in tests/unit/hooks/test_metrics.py

### Implementation for User Story 4

- [X] T049 [US4] Create MetricsCollector class with asyncio.Lock in src/maverick/hooks/metrics.py
- [X] T050 [US4] Implement rolling window with deque(maxlen) in MetricsCollector in src/maverick/hooks/metrics.py
- [X] T051 [US4] Implement record() async method in MetricsCollector in src/maverick/hooks/metrics.py
- [X] T052 [US4] Implement get_metrics() async method with filtering in src/maverick/hooks/metrics.py
- [X] T053 [US4] Implement percentile calculations (p50, p95, p99) in get_metrics() in src/maverick/hooks/metrics.py
- [X] T054 [US4] Implement clear() async method in MetricsCollector in src/maverick/hooks/metrics.py
- [X] T055 [US4] Create collect_metrics async hook function in src/maverick/hooks/metrics.py

**Checkpoint**: User Story 4 complete - metrics collection fully functional and tested

---

## Phase 7: User Story 5 - Configure Hooks Per-Project (Priority: P3)

**Goal**: Factory functions to create configured hooks, supporting enable/disable and custom patterns

**Independent Test**: Load different HookConfig configurations, verify hooks behave according to config

### Tests for User Story 5

- [x] T056 [P] [US5] Unit tests for create_safety_hooks factory in tests/unit/hooks/test_config.py
- [x] T057 [P] [US5] Unit tests for create_logging_hooks factory in tests/unit/hooks/test_config.py
- [x] T058 [P] [US5] Unit tests for hook disable flags in tests/unit/hooks/test_config.py
- [x] T059 [P] [US5] Unit tests for secure defaults when no config in tests/unit/hooks/test_config.py

### Implementation for User Story 5

- [x] T060 [US5] Implement create_safety_hooks(config) factory in src/maverick/hooks/__init__.py
- [x] T061 [US5] Implement create_logging_hooks(config, collector) factory in src/maverick/hooks/__init__.py
- [x] T062 [US5] Wire enable/disable flags to factory hook creation in src/maverick/hooks/__init__.py
- [x] T063 [US5] Implement HookMatcher creation for PreToolUse/PostToolUse in src/maverick/hooks/__init__.py
- [x] T064 [US5] Update public exports in src/maverick/hooks/__init__.py

**Checkpoint**: User Story 5 complete - configuration system fully functional and tested

---

## Phase 8: Integration & Polish

**Purpose**: Cross-cutting concerns and integration verification

- [X] T065 [P] Integration test for safety hooks with MaverickAgent in tests/integration/hooks/test_hook_composition.py
- [X] T066 [P] Integration test for logging hooks with MetricsCollector in tests/integration/hooks/test_hook_composition.py
- [X] T067 Integration test for combined safety + logging hooks (verify execution order: safety blocks before logging records) in tests/integration/hooks/test_hook_composition.py
- [X] T068 [P] Verify fail-closed behavior with hook exception injection in tests/integration/hooks/test_hook_composition.py
- [X] T069 [P] Performance test for <10ms hook overhead (SC-004) in tests/integration/hooks/test_hook_composition.py
- [X] T070 Run quickstart.md examples to validate documentation accuracy
- [X] T071 Verify all public exports match contracts/hooks-api.md
- [X] T072 Run mypy type checking on hooks module
- [X] T073 Run ruff linting and formatting on hooks module

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phases 3-7)**: All depend on Foundational phase completion
  - US1 and US2 are both P1 priority and can proceed in parallel
  - US3 and US4 are both P2 priority and can proceed in parallel
  - US5 depends on US1-US4 hooks being implemented for factory wiring
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 3 (P2)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 4 (P2)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 5 (P3)**: Depends on US1-US4 hooks existing for factory integration

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Normalizers/parsers before validation functions
- Core validation before exception handling wrappers
- Core implementation before config integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes:
  - US1 and US2 can start in parallel (both P1)
  - US3 and US4 can start in parallel (both P2)
- All tests for a user story marked [P] can run in parallel
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 1 Tests

```bash
# Launch all tests for User Story 1 together:
Task: "Unit tests for dangerous pattern detection in tests/unit/hooks/test_safety.py"
Task: "Unit tests for compound command parsing in tests/unit/hooks/test_safety.py"
Task: "Unit tests for environment variable expansion in tests/unit/hooks/test_safety.py"
Task: "Unit tests for unicode/escape normalization in tests/unit/hooks/test_safety.py"
```

## Parallel Example: Foundational Phase

```bash
# After T005 (ValidationResult), launch these in parallel:
Task: "Add ToolExecutionLog dataclass to src/maverick/hooks/types.py"
Task: "Add ToolMetricEntry and ToolMetrics dataclasses to src/maverick/hooks/types.py"

# After T008 (SafetyConfig), launch these in parallel:
Task: "Add LoggingConfig Pydantic model to src/maverick/hooks/config.py"
Task: "Add MetricsConfig Pydantic model to src/maverick/hooks/config.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Block Dangerous Bash Commands)
4. Complete Phase 4: User Story 2 (Block Writes to Sensitive Paths)
5. **STOP and VALIDATE**: Test safety hooks independently - core safety is now operational
6. Deploy/demo if ready - logging and metrics can be added later

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Safety for bash commands (MVP Step 1)
3. Add User Story 2 → Test independently → Safety for file writes (MVP Step 2)
4. Add User Story 3 → Test independently → Execution logging (Observability)
5. Add User Story 4 → Test independently → Metrics collection (Monitoring)
6. Add User Story 5 → Test independently → Configuration flexibility
7. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (Bash validation)
   - Developer B: User Story 2 (File write validation)
3. After P1 stories complete:
   - Developer A: User Story 3 (Logging)
   - Developer B: User Story 4 (Metrics)
4. User Story 5 (Configuration) requires US1-US4 to be integrated

---

## Task Summary

| Phase | Task Count | Parallel Tasks |
|-------|------------|----------------|
| Setup | 4 | 2 |
| Foundational | 10 | 7 |
| User Story 1 | 12 | 4 (tests) |
| User Story 2 | 10 | 3 (tests) |
| User Story 3 | 9 | 3 (tests) |
| User Story 4 | 11 | 4 (tests) |
| User Story 5 | 9 | 4 (tests) |
| Integration | 9 | 4 |
| **Total** | **74** | **31** |

### MVP Scope (User Stories 1 + 2)

- Tasks: T001-T035 (35 tasks)
- Core safety functionality for bash commands and file writes
- Independent test criteria for each story

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
