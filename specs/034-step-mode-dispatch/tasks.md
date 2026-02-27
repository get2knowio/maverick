# Tasks: Mode-Aware Step Dispatch

**Input**: Design documents from `/specs/034-step-mode-dispatch/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included — the spec explicitly mandates test-first (Constitution Principle V, SC-001 through SC-006).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Relax existing validation to permit `mode: agent` on Python steps — prerequisite for all dispatch work.

- [X] T001 Modify `infer_step_mode()` to allow `StepType.PYTHON` + `StepMode.AGENT` by introducing `_MODE_OVERRIDABLE` frozenset in `src/maverick/dsl/executor/config.py`
- [X] T002 Update existing `infer_step_mode` tests for the new PYTHON+AGENT behavior in `tests/unit/dsl/executor/test_config.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create the `DispatchResult` dataclass and core dispatch module that ALL user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Create `DispatchResult` frozen dataclass with `to_dict()` in `src/maverick/dsl/serialization/executor/handlers/dispatch.py` (per data-model.md and contracts/dispatch.py)
- [X] T004 Create `_structurally_equivalent()` helper function in `src/maverick/dsl/serialization/executor/handlers/dispatch.py` for Collaborator-level comparison (dict, list, dataclass, Pydantic model support)
- [X] T005 [P] Create `build_agent_prompt()` function in `src/maverick/dsl/serialization/executor/handlers/dispatch.py` that constructs `(instructions, prompt)` tuple from intent, resolved inputs, and prompt suffix/file content

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 — Run a Python Step via an AI Agent (Priority: P1) 🎯 MVP

**Goal**: Enable `mode: agent` on any Python step, routing execution to a StepExecutor with an intent-based prompt instead of the deterministic handler.

**Independent Test**: Define a workflow with a single Python step, run once in deterministic mode and once in agent mode, verify both produce a valid result matching the step's output contract.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T006 [P] [US1] Test that `execute_python_step()` with no mode/autonomy config defaults to DETERMINISTIC+OPERATOR with zero behavior change (FR-008 default path) in `tests/unit/dsl/serialization/executor/handlers/test_python_step_dispatch.py`
- [X] T007 [P] [US1] Test that `execute_python_step()` with `mode: deterministic` calls the action directly (regression) in `tests/unit/dsl/serialization/executor/handlers/test_python_step_dispatch.py`
- [X] T008 [P] [US1] Test that `execute_python_step()` with `mode: agent` delegates to `dispatch_agent_mode()` in `tests/unit/dsl/serialization/executor/handlers/test_python_step_dispatch.py`
- [X] T009 [P] [US1] Test that mode-aware dispatch is NOT invoked for non-PYTHON step types (StepType.AGENT, VALIDATE, BRANCH, etc.) — FR-002 regression in `tests/unit/dsl/serialization/executor/handlers/test_python_step_dispatch.py`
- [X] T010 [P] [US1] Test `dispatch_agent_mode()` constructs prompt from intent + resolved inputs and calls `StepExecutor.execute()` in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`
- [X] T011 [P] [US1] Test `dispatch_agent_mode()` returns `DispatchResult` with correct metadata in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`

### Implementation for User Story 1

- [X] T012 [US1] Implement `dispatch_agent_mode()` in `src/maverick/dsl/serialization/executor/handlers/dispatch.py` — look up intent via `get_intent()`, build prompt via `build_agent_prompt()`, call `StepExecutor.execute()`, return `DispatchResult` with Approver-level acceptance (simplest path; autonomy gates and fallback are wired in US2/US3)
- [X] T013 [US1] Modify `execute_python_step()` in `src/maverick/dsl/serialization/executor/handlers/python_step.py` — accept resolved `StepConfig` via the `config` parameter (resolved by executor coordinator upstream), check `context.inputs.get("force_deterministic")`, dispatch by mode (deterministic=existing path, agent=`dispatch_agent_mode()`)

**Checkpoint**: A Python step configured with `mode: agent` delegates to a StepExecutor and returns a result. Deterministic mode is unchanged.

---

## Phase 4: User Story 2 — Autonomy Levels Control Agent Result Handling (Priority: P1)

**Goal**: Implement per-level validation/verification/acceptance gates so Collaborator validates, Consultant verifies, and Approver accepts agent results directly.

**Independent Test**: Run the same step at each autonomy level with a mock StepExecutor, verifying validation/verification/acceptance behavior differs at each level.

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T014 [P] [US2] Test `apply_autonomy_gate()` at Operator level warns and returns deterministic fallback in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`
- [X] T015 [P] [US2] Test `apply_autonomy_gate()` at Collaborator level re-executes deterministic handler and compares structurally in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`
- [X] T016 [P] [US2] Test `apply_autonomy_gate()` at Collaborator level on side-effecting action auto-downgrades to Consultant-level verification with warning in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`
- [X] T017 [P] [US2] Test `apply_autonomy_gate()` at Consultant level verifies output contract and accepts with logged discrepancies in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`
- [X] T018 [P] [US2] Test `apply_autonomy_gate()` at Approver level accepts agent result directly in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`
- [X] T019 [P] [US2] Test `_structurally_equivalent()` with dicts, lists, dataclasses, Pydantic models, and mismatched types in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`

### Implementation for User Story 2

- [X] T020 [US2] Implement `apply_autonomy_gate()` in `src/maverick/dsl/serialization/executor/handlers/dispatch.py` — Operator warns+fallback, Collaborator re-executes+compares (with side-effect guard: auto-downgrade to Consultant for actions with mutation metadata), Consultant verifies contract, Approver accepts
- [X] T021 [US2] Wire `apply_autonomy_gate()` into `dispatch_agent_mode()` in `src/maverick/dsl/serialization/executor/handlers/dispatch.py` (called after StepExecutor returns result, before returning DispatchResult)

**Checkpoint**: Each autonomy level produces observably different behavior. Collaborator validates before accepting, Consultant verifies after execution, Approver accepts directly. Side-effecting actions are protected from double-execution.

---

## Phase 5: User Story 3 — Agent Failures Fall Back to Deterministic Execution (Priority: P1)

**Goal**: When agent-mode fails (exception, timeout, schema violation), automatically fall back to the deterministic Python handler, ensuring agent mode never reduces reliability.

**Independent Test**: Configure a step in agent mode with a StepExecutor that raises an exception, verify the deterministic handler runs as fallback and produces a valid result.

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T022 [P] [US3] Test fallback on StepExecutor exception in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`
- [X] T023 [P] [US3] Test fallback on StepExecutor timeout in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`
- [X] T024 [P] [US3] Test fallback on agent result schema violation in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`
- [X] T025 [P] [US3] Test that fallback reuses already-resolved inputs (not re-resolved) in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`
- [X] T026 [P] [US3] Test that error propagates normally when no deterministic handler exists in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`
- [X] T027 [P] [US3] Test that when both agent AND deterministic fallback fail, the deterministic error propagates (A-006, no retry cascade) in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`

### Implementation for User Story 3

- [X] T028 [US3] Implement fallback logic in `dispatch_agent_mode()` in `src/maverick/dsl/serialization/executor/handlers/dispatch.py` — wrap agent execution in try/except, catch exceptions/timeout/schema violations, run deterministic handler with same resolved_inputs
- [X] T029 [US3] Add timeout enforcement using `StepConfig.timeout` via `asyncio.wait_for()` in `src/maverick/dsl/serialization/executor/handlers/dispatch.py`

**Checkpoint**: Agent failures never produce worse outcomes than deterministic-only execution. Every failure triggers a logged fallback.

---

## Phase 6: User Story 4 — Step Intent Descriptions Guide Agent Execution (Priority: P2)

**Goal**: Provide every Python step handler with a co-located intent description that serves as the agent's primary prompt. Non-empty, actionable descriptions for all ~61 registered actions.

**Independent Test**: Verify every registered action has a non-empty intent entry, and that dispatch includes the intent in the agent prompt.

### Tests for User Story 4

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T030 [P] [US4] Test that every registered action in `ComponentRegistry.actions` has a non-empty entry in `ACTION_INTENTS` in `tests/unit/library/actions/test_intents.py`
- [X] T031 [P] [US4] Test that no orphan keys exist in `ACTION_INTENTS` (keys must match registered actions) in `tests/unit/library/actions/test_intents.py`
- [X] T032 [P] [US4] Test `get_intent()` returns correct description for known actions and None for unknown in `tests/unit/library/actions/test_intents.py`

### Implementation for User Story 4

- [X] T033 [US4] Create `src/maverick/library/actions/intents.py` with `ACTION_INTENTS` dict covering all ~61 registered actions and `get_intent()` helper function
- [X] T034 [US4] Wire intent lookup into `dispatch_agent_mode()` — call `get_intent(step.action)` and pass to `build_agent_prompt()` in `src/maverick/dsl/serialization/executor/handlers/dispatch.py`

**Checkpoint**: Every Python step handler has a co-located intent description. Agent prompts include the intent when running in agent mode.

---

## Phase 7: User Story 5 — Structured Observability for Mode Dispatch Decisions (Priority: P2)

**Goal**: Emit structured log events for every dispatch decision: mode selection, autonomy checks, and fallback occurrences.

**Independent Test**: Run steps in various modes and autonomy levels, capture structured log output, verify expected events are emitted with correct fields.

### Tests for User Story 5

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T035 [P] [US5] Test `dispatch.mode_selected` event emitted for deterministic execution in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`
- [X] T036 [P] [US5] Test `dispatch.agent_completed` event emitted with duration and acceptance status in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`
- [X] T037 [P] [US5] Test `dispatch.autonomy_validation` event emitted with outcome field in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`
- [X] T038 [P] [US5] Test `dispatch.fallback` event emitted with failure reason in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`
- [X] T039 [P] [US5] Test `dispatch.deterministic_completed` event emitted with duration in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`

### Implementation for User Story 5

- [X] T040 [US5] Add structured log events to `dispatch_agent_mode()` and `execute_python_step()` in `src/maverick/dsl/serialization/executor/handlers/dispatch.py` and `src/maverick/dsl/serialization/executor/handlers/python_step.py` — emit `dispatch.mode_selected`, `dispatch.agent_completed`, `dispatch.autonomy_validation`, `dispatch.fallback`, `dispatch.deterministic_completed`

**Checkpoint**: All dispatch decisions emit structured log events with correct fields per plan.md log event table.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: CLI flag, edge-case hardening, and final validation.

- [X] T041 Add `--deterministic` flag to `fly` command in `src/maverick/cli/commands/fly/_group.py` and pass as `force_deterministic=true` in workflow input_parts
- [X] T042 [P] Test `--deterministic` flag forces all Python steps to deterministic mode in `tests/unit/dsl/serialization/executor/handlers/test_python_step_dispatch.py`
- [X] T043 [P] Test edge case: `mode: agent` on step with no intent description falls back with warning in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`
- [X] T044 [P] Test edge case: `mode: agent` but no StepExecutor available falls back with warning in `tests/unit/dsl/serialization/executor/handlers/test_dispatch.py`
- [X] T045 Run `make check` to verify lint, typecheck, and all tests pass
- [X] T046 Run quickstart.md validation — verify usage examples match implementation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (needs relaxed `infer_step_mode`)
- **US1 (Phase 3)**: Depends on Phase 2 (`DispatchResult`, `build_agent_prompt`, structural equiv)
- **US2 (Phase 4)**: Depends on Phase 3 (`dispatch_agent_mode` must exist for autonomy gates)
- **US3 (Phase 5)**: Depends on Phase 3 (fallback wraps around agent execution path)
- **US4 (Phase 6)**: Can start after Phase 2 (intent registry is independent of dispatch logic)
- **US5 (Phase 7)**: Depends on Phase 3 (logging wraps dispatch functions)
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (P1)**: Core dispatch — all other stories depend on this
- **US2 (P1)**: Autonomy gates — depends on US1 dispatch path
- **US3 (P1)**: Fallback safety — depends on US1 dispatch path; can run in parallel with US2
- **US4 (P2)**: Intent registry — depends only on Phase 2; can run in parallel with US1/US2/US3
- **US5 (P2)**: Observability — depends on US1 dispatch functions existing to add logging

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Implementation follows contract definitions from `contracts/`
- Story complete before moving to next priority

### Parallel Opportunities

- T001 and T002 are sequential (modify then test)
- T003 then T004 are sequential (T003 creates the module), T005 can run in parallel with T004
- All tests within a phase marked [P] can run in parallel
- US4 (intent registry) can be developed in parallel with US1/US2/US3
- US2 and US3 can be developed in parallel after US1

---

## Parallel Example: User Story 2

```bash
# Launch all tests for US2 together (all [P], different test functions):
Task: "Test apply_autonomy_gate() at Operator level" (T014)
Task: "Test apply_autonomy_gate() at Collaborator level" (T015)
Task: "Test apply_autonomy_gate() at Collaborator side-effect guard" (T016)
Task: "Test apply_autonomy_gate() at Consultant level" (T017)
Task: "Test apply_autonomy_gate() at Approver level" (T018)
Task: "Test _structurally_equivalent()" (T019)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (relax `infer_step_mode`)
2. Complete Phase 2: Foundational (`DispatchResult`, helpers)
3. Complete Phase 3: User Story 1 (mode-aware dispatch)
4. **STOP and VALIDATE**: Test deterministic regression + agent dispatch independently
5. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 (core dispatch) → Test independently → **MVP!**
3. Add US2 (autonomy gates) + US3 (fallback) → Test independently
4. Add US4 (intents) + US5 (observability) → Test independently
5. Polish (CLI flag, edge cases, full validation)
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: US1 (core dispatch) — MUST complete first
   - Developer B: US4 (intent registry) — independent of US1
3. After US1 completes:
   - Developer A: US2 (autonomy gates)
   - Developer C: US3 (fallback safety)
   - Developer B: US5 (observability)
4. All converge for Polish phase

---

## Notes

- [P] tasks = different files or functions, no dependencies
- [Story] label maps task to specific user story for traceability
- All new code in `dispatch.py` targets ~200 LOC (well under 500 LOC soft limit)
- Intent registry in `intents.py` targets ~150 LOC
- Existing `python_step.py` modifications ~30 LOC (mode check + delegation)
- `_group.py` modification ~10 LOC (--deterministic flag)
- Zero behavioral regression for existing workflows (SC-001)
