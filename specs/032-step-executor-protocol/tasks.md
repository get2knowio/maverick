# Tasks: StepExecutor Protocol

**Input**: Design documents from `/specs/032-step-executor-protocol/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Feature Branch**: `032-step-executor-protocol`
**Tech Stack**: Python 3.10+ · `from __future__ import annotations` · Pydantic · tenacity · structlog

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US4)
- Exact file paths included in every description

---

## Phase 1: Setup

**Purpose**: Create the new `maverick.dsl.executor` package skeleton and test package markers so all subsequent parallel tasks have a landing zone.

- [x] T001 Create `src/maverick/dsl/executor/` package with a stub `__init__.py` (empty or single comment line)
- [x] T002 Create `tests/unit/dsl/executor/__init__.py` package marker

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Define all shared value objects and the provider-agnostic protocol. Everything in Phase 3+ depends on these types being correct and importable.

**⚠️ CRITICAL**: No user-story work can begin until this phase is complete.

- [x] T003 [P] Create `RetryPolicy` and `StepExecutorConfig` frozen dataclasses with `to_dict()` in `src/maverick/dsl/executor/config.py` (stdlib only — no maverick imports)
- [x] T004 [P] Create `UsageMetadata` and `ExecutorResult` frozen dataclasses with `to_dict()` in `src/maverick/dsl/executor/result.py`; import `AgentStreamChunk` under `TYPE_CHECKING`
- [x] T005 [P] Create `ExecutorError` and `OutputSchemaValidationError` in `src/maverick/dsl/executor/errors.py`; inherit from `MaverickError`; store `step_name`, `schema_type`, `validation_errors`
- [x] T006 Create `StepExecutor` `@runtime_checkable Protocol` in `src/maverick/dsl/executor/protocol.py`; signature per contract (`step_name`, `agent_name`, `prompt`, `instructions`, `allowed_tools`, `cwd`, `output_schema`, `config`, `event_callback`); **NO** `maverick.agents` or `claude-agent-sdk` imports
- [x] T007 Finalize `src/maverick/dsl/executor/__init__.py` with full public API exports: `StepExecutor`, `ExecutorResult`, `StepExecutorConfig`, `RetryPolicy`, `UsageMetadata`, `ClaudeStepExecutor`, `DEFAULT_EXECUTOR_CONFIG`; re-export from sub-modules; add `__all__`

**Note**: T003, T004, T005 are fully independent and can run in parallel. T006 depends on T003+T004. T007 depends on T003–T006 (including `ClaudeStepExecutor` from Phase 3 — update `__init__.py` again at T008 completion).

**Checkpoint**: Protocol package importable — all value object types stable and tested independently.

---

## Phase 3: User Stories 1 & 2 — Provider-Agnostic Routing + Behavior Preservation (Priority: P1) 🎯 MVP

**Goal**: Route all YAML workflow agent steps through the `StepExecutor` abstraction (US1) while preserving exact existing streaming, retry, circuit-breaker, and error-wrapping behavior via `ClaudeStepExecutor` (US2).

**Independent Test**: Run the full existing test suite with `ClaudeStepExecutor` wired in; all tests pass without modification (SC-001). Inject a mock `StepExecutor` via `context.step_executor` and verify `execute_agent_step` delegates correctly.

### Implementation for US1 & US2

- [x] T008 [US1] [US2] Create `ClaudeStepExecutor` class in `src/maverick/dsl/executor/claude.py`; implement `execute()` with: `executor.step_start` log, agent class lookup via `registry.agents.get()`, agent instantiation with `_build_agent_kwargs()`, stream callback injection, thinking indicator event emission, `asyncio.wait_for` timeout when `config.timeout` is set, `AsyncRetrying` retry loop when `config.retry_policy` is set, `output_schema.model_validate()` on result, `executor.step_complete`/`executor.step_error` logs, return `ExecutorResult`; imports `MaverickAgent`, tenacity, structlog

- [x] T009 [P] [US1] [US2] Add `step_executor: StepExecutor | None = None` field to `WorkflowContext` dataclass in `src/maverick/dsl/context.py`; guard import with `TYPE_CHECKING` to avoid circular dependency at runtime

- [x] T010 [P] [US1] [US2] Add `output_schema: str | None = Field(None, ...)` to `AgentStepRecord` in `src/maverick/dsl/serialization/schema.py`; include docstring describing dotted-Python-path format (e.g. `"maverick.agents.reviewer.ReviewResult"`)

- [x] T011 [US1] [US2] Inject `ClaudeStepExecutor(registry=self._registry)` onto `exec_context.step_executor` immediately after `create_execution_context()` call (line ~356) in `src/maverick/dsl/serialization/executor/executor.py`

- [x] T012 [US1] [US2] Refactor `execute_agent_step` in `src/maverick/dsl/serialization/executor/handlers/agent_step.py`: keep registry validation and context-building logic; extract `_convert_to_implementer_context()` private helper; add `_resolve_output_schema(step)` helper that uses `importlib` to resolve dotted path (raises `ConfigError` on import failure); delegate execution to `context.step_executor.execute(...)` (fallback to `ClaudeStepExecutor(registry)` when `context.step_executor` is `None`); return `HandlerOutput(result=executor_result.output, events=list(executor_result.events))`

### Tests for US1 & US2

- [x] T013 [P] [US1] [US2] Write `tests/unit/dsl/executor/test_protocol.py`: verify `isinstance(mock_impl, StepExecutor)` passes for conforming object; verify `isinstance(ClaudeStepExecutor(...), StepExecutor)` passes; verify non-conforming object fails `isinstance` check

- [x] T014 [P] [US1] [US2] Write `tests/unit/dsl/executor/test_claude.py`: cover happy path (mock agent returns result → `ExecutorResult(success=True)`), streaming (mock stream_callback emits events → events in `ExecutorResult.events`), retry policy (mock agent raises once, succeeds on second attempt), timeout (mock agent sleeps → `asyncio.TimeoutError`), unknown agent raises `ReferenceResolutionError`, agent error propagation, observability log events (`executor.step_start`, `executor.step_complete`, `executor.step_error`), `event_callback` forwarding in real-time

- [x] T015 [US1] [US2] Write `tests/integration/dsl/test_step_executor_integration.py`: run `execute_agent_step` with a mock `StepExecutor` injected via `context.step_executor`; verify mock's `execute()` called with correct params; verify `HandlerOutput.result == ExecutorResult.output`; verify `HandlerOutput.events` matches `ExecutorResult.events`; run with `ClaudeStepExecutor` + mock `MaverickAgent` to verify identical output to pre-refactor path

- [x] T016 [US2] Run `make test` to execute full regression suite; confirm all pre-existing tests in `tests/unit/dsl/serialization/executor/handlers/test_agent_step_streaming.py`, `tests/unit/dsl/serialization/test_executor.py`, `tests/unit/dsl/serialization/test_executor_steps.py`, and `tests/integration/test_executor_step_paths.py` pass without modification (SC-001)

**Checkpoint**: All existing behavior preserved. Mock executor injection works. `ClaudeStepExecutor` passes conformance check. Full test suite green.

---

## Phase 4: User Story 3 — Typed Output Contracts Through the Executor (Priority: P2)

**Goal**: `output_schema` YAML field validated end-to-end: YAML `str` path → `importlib` resolution → Pydantic `model_validate()` → typed `ExecutorResult.output` or `OutputSchemaValidationError`.

**Independent Test**: Define a step with `output_schema: maverick.agents.reviewer.ReviewResult`, run it with a mock agent returning conforming data — verify `ExecutorResult.output` is a validated `ReviewResult`. Run with non-conforming data — verify `OutputSchemaValidationError` raised with correct `step_name` and `schema_type`.

### Implementation for US3

- [x] T017 [US3] Extend `tests/unit/dsl/executor/test_claude.py` with output-schema scenarios: (a) conforming output → `ExecutorResult.output` is validated Pydantic instance; (b) non-conforming output → `OutputSchemaValidationError` with correct `step_name`/`schema_type`/`validation_errors`; (c) no `output_schema` → raw agent result returned unchanged (backward compat)

- [x] T018 [US3] Add output_schema integration scenario to `tests/integration/dsl/test_step_executor_integration.py`: YAML step with `output_schema` dotted path; verify `_resolve_output_schema()` resolves the class correctly; verify end-to-end validated result flows into `HandlerOutput.result`

**Checkpoint**: Typed output contracts work end-to-end from YAML through to validated Pydantic model instance in `HandlerOutput`.

---

## Phase 5: User Story 4 — StepExecutorConfig via Workflow Context (Priority: P3)

**Goal**: Per-step `executor_config` YAML field deserialized to `StepExecutorConfig` and applied independently per step (timeout, retry, model overrides).

**Independent Test**: Define two identical agent steps with different `executor_config` values (different timeouts); run both; verify each step's executor enforces its own config independently.

### Implementation for US4

- [x] T019 [US4] Add `executor_config: dict[str, Any] | None = Field(None, ...)` field to `AgentStepRecord` in `src/maverick/dsl/serialization/schema.py`; include docstring with example YAML keys (`timeout`, `retry_policy.max_attempts`, `model`, `temperature`, `max_tokens`)

- [x] T020 [US4] In `execute_agent_step` (`src/maverick/dsl/serialization/executor/handlers/agent_step.py`): deserialize `step.executor_config` dict to `StepExecutorConfig` (and nested `RetryPolicy`) if present; pass as `config=` argument to `executor.execute()`; raise `ConfigError` for unrecognized config keys

- [x] T021 [US4] Add per-step config test scenarios to `tests/unit/dsl/executor/test_claude.py`: (a) custom timeout enforced — verify `asyncio.wait_for` called with step-specific value; (b) no config → `DEFAULT_EXECUTOR_CONFIG` applied; (c) two steps with different configs each enforce their own independently

**Checkpoint**: Per-step executor configuration functional end-to-end from YAML to enforcement in `ClaudeStepExecutor`.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Complete foundational unit test coverage and verify the full project remains green.

- [x] T022 [P] Write `tests/unit/dsl/executor/test_config.py`: `RetryPolicy` defaults and `to_dict()` roundtrip; `StepExecutorConfig` all-None defaults, partial config, `to_dict()` roundtrip; `DEFAULT_EXECUTOR_CONFIG` has `timeout=300` and `retry_policy=None`
- [x] T023 [P] Write `tests/unit/dsl/executor/test_result.py`: `UsageMetadata` defaults and `to_dict()` roundtrip; `ExecutorResult` construction with all fields, `to_dict()`, immutability (frozen dataclass cannot be mutated)
- [x] T024 [P] Write `tests/unit/dsl/executor/test_errors.py`: `OutputSchemaValidationError` stores `step_name`, `schema_type`, `validation_errors`; inherits from `MaverickError`; `str()` message includes step name and schema class name
- [x] T025 Run `make check` (lint + typecheck + full test suite) to verify the repository tree is fully green

**Checkpoint**: Complete. All 25 tasks done. Protocol package stable. Full regression passing.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — blocks all user stories
- **US1 & US2 (Phase 3)**: Depends on Phase 2 — T009, T010, T013 can start in parallel after T007; T008 is the main blocker for T011, T012, T014, T015
- **US3 (Phase 4)**: Depends on Phase 3 (T012 must include `_resolve_output_schema`) — T017, T018 are test-only additions
- **US4 (Phase 5)**: Depends on Phase 3 complete — T019 → T020 → T021
- **Polish (Phase 6)**: T022, T023, T024 can run any time after Phase 2; T025 must be last

### User Story Dependencies

- **US1 & US2 (P1)**: Can start after Phase 2 — no dependency on US3 or US4
- **US3 (P2)**: Depends on US1 & US2 (Phase 3 complete) — needs `_resolve_output_schema` in place
- **US4 (P3)**: Depends on US1 & US2 (Phase 3 complete) — schema field + handler wiring

### Within Phase 3

- T008 (claude.py) → T011 (executor.py, inject) → T012 (agent_step.py, wire)
- T009 (context.py) → T011 (executor.py, uses step_executor field)
- T010 (schema.py) → T012 (agent_step.py, accesses step.output_schema)
- T013 (test_protocol.py), T014 (test_claude.py) → run in parallel after T008
- T015 (integration test) → depends on T012
- T016 (regression) → depends on T015

### Parallel Opportunities

- Phase 2: T003, T004, T005 all parallel (different files, no shared deps)
- Phase 3: T009, T010, T013 parallel after T007 + T008 available
- Phase 6: T022, T023, T024 all parallel (different test files, no shared deps)

---

## Parallel Execution Examples

### Phase 2 — Foundation (run all 3 simultaneously)

```
Task A: Create src/maverick/dsl/executor/config.py (RetryPolicy, StepExecutorConfig, DEFAULT_EXECUTOR_CONFIG)
Task B: Create src/maverick/dsl/executor/result.py (UsageMetadata, ExecutorResult)
Task C: Create src/maverick/dsl/executor/errors.py (ExecutorError, OutputSchemaValidationError)
→ then: T006 protocol.py, T007 __init__.py (sequential)
```

### Phase 3 — After T008 completes

```
Task A: Add step_executor field to src/maverick/dsl/context.py (T009)
Task B: Add output_schema field to src/maverick/dsl/serialization/schema.py (T010)
Task C: Write tests/unit/dsl/executor/test_protocol.py (T013)
Task D: Write tests/unit/dsl/executor/test_claude.py (T014)
→ then: T011 (executor.py), T012 (agent_step.py), T015 (integration), T016 (regression)
```

### Phase 6 — Polish (run all 3 simultaneously)

```
Task A: Write tests/unit/dsl/executor/test_config.py (T022)
Task B: Write tests/unit/dsl/executor/test_result.py (T023)
Task C: Write tests/unit/dsl/executor/test_errors.py (T024)
→ then: T025 make check
```

---

## Implementation Strategy

### MVP First (US1 + US2 only — Phases 1–3)

1. Complete Phase 1: Create package skeletons
2. Complete Phase 2: Protocol types (parallel where possible)
3. Complete Phase 3: ClaudeStepExecutor + integration + tests
4. **STOP and VALIDATE**: Run `make test` — all existing tests must pass (SC-001)
5. Verify mock executor injection works end-to-end

### Incremental Delivery

1. Setup + Foundational → Protocol package importable, stable API
2. US1 & US2 → Core decoupling shipped; existing behavior 100% preserved
3. US3 → Typed output contracts unlocked for workflow authors
4. US4 → Per-step config flexibility added
5. Polish → Full coverage + green tree

### Key Constraints

- **SC-001**: Zero regressions — existing tests must pass without modification after Phase 3
- **SC-004**: `src/maverick/dsl/executor/protocol.py`, `config.py`, `result.py`, `errors.py` must have no `maverick.agents` or `claude-agent-sdk` imports
- **SC-002**: A new provider adapter can be built by satisfying the contract in `contracts/step_executor_interface.py` alone
- **ClaudeStepExecutor lifecycle**: Created once per workflow run (in `WorkflowFileExecutor.execute()`), discarded at completion — not a singleton

---

## Notes

- `[P]` tasks = different files, no dependencies on incomplete tasks in the same phase
- `[Story]` label maps each task to a specific user story for traceability
- US1 and US2 are both P1 and implemented together (they are architecturally interdependent)
- US3 is implemented primarily via tests — the core validation logic (`output_schema.model_validate()`) is already part of `ClaudeStepExecutor.execute()` (T008); US3 adds YAML-level wiring and test coverage
- US4 (`executor_config` per-step) is lowest priority; defer if capacity is limited
- `AgentStepRecord.output_schema` is added in Phase 3 (T010) because `agent_step.py` (T012) accesses `step.output_schema` — the field default of `None` is backward-compatible
- All structured log events (`executor.step_start`, `executor.step_complete`, `executor.step_error`) are implemented inside `claude.py` (T008), satisfying NFR-001
