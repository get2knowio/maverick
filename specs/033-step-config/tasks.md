# Tasks: Step Configuration Model

**Input**: Design documents from `/specs/033-step-config/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are included per constitution principle V (Test-First) and CLAUDE.md ("Every public class and function MUST have tests").

**TDD Practice**: Per Principle V, within each implementation task apply red-green-refactor: write test assertions first (red), implement until tests pass (green), refactor. Task ordering reflects logical dependencies between deliverables; the TDD micro-cycle happens within each task.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/` at repository root

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Core enums and StepConfig model that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [X] T001 Add StepMode and AutonomyLevel enums (str, Enum) to src/maverick/dsl/types.py following existing StepType convention
- [X] T002 Replace StepExecutorConfig frozen dataclass with StepConfig Pydantic BaseModel in src/maverick/dsl/executor/config.py — include all 12 fields (mode, autonomy, provider, model_id, temperature, max_tokens, timeout, max_retries, allowed_tools, prompt_suffix, prompt_file, retry_policy), cross-field validators (validate_agent_only_fields, validate_prompt_exclusivity, validate_retry_migration), StepExecutorConfig backward-compat type alias, and update DEFAULT_EXECUTOR_CONFIG constant to use StepConfig
- [X] T003 [P] Add unit tests for StepMode and AutonomyLevel enums (values, str serialization, invalid member rejection) in tests/unit/dsl/test_types.py
- [X] T004 [P] Add unit tests for StepConfig model in tests/unit/dsl/executor/test_config.py — cover construction with defaults, field validation (temperature range 0.0–1.0, max_tokens gt=0 le=200000, provider Literal["claude"], timeout gt=0, max_retries ge=0, allowed_tools list[str]|None), cross-field validators (agent-only fields rejected on mode=deterministic, prompt_suffix/prompt_file mutual exclusivity, retry_policy/max_retries conflict), serialization via model_dump(exclude_none=True), and StepExecutorConfig alias identity

**Checkpoint**: Enums and StepConfig model ready — user story integration can now begin

---

## Phase 2: User Story 1 — Configure Step Execution Mode Per Workflow Step (Priority: P1) MVP

**Goal**: Workflow authors can declare execution mode (deterministic/agent) and autonomy level per step in YAML, with mode inferred from step type when omitted

**Independent Test**: Define a workflow YAML with mixed step modes (deterministic + agent) and verify each step's config reflects the correct mode and autonomy after loading

### Implementation for User Story 1

- [X] T005 [US1] Add config: dict[str, Any] | None field to StepRecord base class in src/maverick/dsl/serialization/schema.py (replaces per-subclass executor_config)
- [X] T006 [US1] Add executor_config → config backward-compat @model_validator(mode="before") on AgentStepRecord in src/maverick/dsl/serialization/schema.py — migrate executor_config to config with structlog deprecation warning, reject ambiguous dual-field usage, and rename legacy `model` key to `model_id` within the migrated config dict for FR-012 compatibility
- [X] T007 [P] [US1] Add infer_step_mode(step_type: StepType, explicit_mode: StepMode | None) helper and validate_mode_step_type_consistency() to src/maverick/dsl/executor/config.py — infer mode from step type when None (agent/generate→agent, python/validate→deterministic, subworkflow→agent, branch/loop/checkpoint→deterministic), reject mismatches when mode is explicitly set
- [X] T008 [P] [US1] Add unit tests for StepRecord.config field (present on all step types) and AgentStepRecord executor_config backward compat (migration, deprecation warning, dual-field rejection, legacy `model`→`model_id` key rename) in tests/unit/dsl/serialization/test_schema.py
- [X] T009 [P] [US1] Add unit tests for infer_step_mode (all 8 step types including subworkflow, branch, loop, checkpoint) and mode/type mismatch rejection in tests/unit/dsl/executor/test_config.py

**Checkpoint**: Steps can declare mode/autonomy in YAML; mode inferred from type; backward compat preserved

---

## Phase 3: User Story 2 — Override Model and Provider Settings Per Step (Priority: P1)

**Goal**: Each step can override model_id, temperature, max_tokens, and provider, with unset fields inherited from global ModelConfig via 4-layer resolution

**Independent Test**: Define steps with different model_id and temperature overrides, verify resolve_step_config returns correct merged values falling back to global defaults

### Implementation for User Story 2

- [X] T010 [US2] Implement resolve_step_config() function in src/maverick/dsl/executor/config.py — 4-layer precedence merge (inline_config > project_step_config > agent_config > global_model), mode inference via infer_step_mode, autonomy default to operator, model field inheritance, handle legacy `model` key in inline_config (rename to `model_id`), and validate prompt_file path existence when set (or document deferral to executor)
- [X] T011 [P] [US2] Update StepExecutor protocol config parameter type from StepExecutorConfig to StepConfig in src/maverick/dsl/executor/protocol.py (import change only; StepExecutorConfig alias ensures no runtime breakage)
- [X] T012 [US2] Replace _resolve_executor_config() with call to resolve_step_config() in src/maverick/dsl/serialization/executor/handlers/agent_step.py — pass step.config dict, update imports, wire existing context.step_executor config parameter
- [X] T013 [US2] Add unit tests for resolve_step_config in tests/unit/dsl/executor/test_config.py — cover 4-layer precedence (inline wins over project, project over agent, agent over global), model field inheritance for unset fields, provider defaults to "claude", mode inference integration

**Checkpoint**: Steps can override model settings; 4-layer resolution operational

---

## Phase 4: User Story 3 — Configure Operational Limits Per Step (Priority: P2)

**Goal**: Steps can set per-step timeout, max_retries, and allowed_tools, with values correctly resolved and passed to executors

**Independent Test**: Define steps with explicit timeout/max_retries/allowed_tools and verify resolved config reflects those limits; verify defaults when omitted

### Implementation for User Story 3

- [X] T014 [P] [US3] Add unit tests for timeout and max_retries resolution through resolve_step_config (explicit values, None fallback, project-level defaults) in tests/unit/dsl/executor/test_config.py
- [X] T015 [P] [US3] Add unit tests for allowed_tools resolution (None=all tools, []=no tools, explicit list, rejected when mode=deterministic) in tests/unit/dsl/executor/test_config.py

**Checkpoint**: Operational limits correctly validated and resolved per step

---

## Phase 5: User Story 4 — Extend Agent Prompts Per Step (Priority: P2)

**Goal**: Steps can extend agent instructions via prompt_suffix (inline) or prompt_file (external file path), with mutual exclusivity enforced

**Independent Test**: Define steps with prompt_suffix or prompt_file and verify resolved config includes the prompt content; verify both-set rejection

### Implementation for User Story 4

- [X] T016 [P] [US4] Add unit tests for prompt_suffix and prompt_file resolution through resolve_step_config (suffix present, file path present, neither set) in tests/unit/dsl/executor/test_config.py
- [X] T017 [P] [US4] Add integration test for step with prompt extension loaded from workflow YAML (prompt_suffix and prompt_file scenarios) in tests/integration/test_config_loading.py

**Checkpoint**: Prompt extension correctly validated and resolved per step

---

## Phase 6: User Story 5 — Configure Steps in maverick.yaml (Priority: P3)

**Goal**: Project maintainers define default step configurations in maverick.yaml under a `steps` key; these merge with workflow-level overrides following 4-layer precedence

**Independent Test**: Set step defaults in maverick.yaml, define a workflow with a matching step name, verify resolved config merges correctly (workflow inline > project steps > agent config > global model)

### Implementation for User Story 5

- [X] T018 [US5] Add steps: dict[str, StepConfig] field to MaverickConfig in src/maverick/config.py — include in __all__, default to empty dict, add StepConfig import
- [X] T019 [US5] Wire MaverickConfig.steps lookup into resolve_step_config call site in src/maverick/dsl/serialization/executor/handlers/agent_step.py — retrieve project_step_config from MaverickConfig.steps[step.name] when available
- [X] T020 [P] [US5] Add unit tests for MaverickConfig.steps field (empty default, valid StepConfig values, invalid values rejected) in tests/unit/test_config.py
- [X] T021 [US5] Add integration test for full 4-layer resolution from maverick.yaml + workflow YAML in tests/integration/test_config_loading.py — verify inline > project steps > agent config > global model precedence end-to-end

**Checkpoint**: Project-level step defaults operational; full 4-layer resolution verified

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Cleanup and validation across all user stories

- [X] T022 [P] Update remaining references to StepExecutorConfig throughout codebase (imports, docstrings, type hints) to use StepConfig — verify StepExecutorConfig alias provides backward compat
- [X] T023 Run full regression test suite (`make test`) to verify SC-001 (zero behavioral regressions) — all existing tests must pass unchanged
- [X] T024 Run quickstart.md validation against implemented code in specs/033-step-config/quickstart.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — can start immediately. BLOCKS all user stories.
- **US1 (Phase 2)**: Depends on Foundational completion. Provides schema integration needed by US2+.
- **US2 (Phase 3)**: Depends on US1 (needs StepRecord.config and backward compat to be in place). Provides resolve_step_config needed by US3/US4/US5.
- **US3 (Phase 4)**: Depends on US2 (tests exercise resolve_step_config). Can run in parallel with US4.
- **US4 (Phase 5)**: Depends on US2 (tests exercise resolve_step_config). Can run in parallel with US3.
- **US5 (Phase 6)**: Depends on US2 (wires MaverickConfig into resolve_step_config).
- **Polish (Phase 7)**: Depends on all user stories being complete.

### User Story Dependencies

- **US1 (P1)**: Start after Foundational — MVP story, no dependencies on other stories
- **US2 (P1)**: Start after US1 — needs StepRecord.config field and backward compat
- **US3 (P2)**: Start after US2 — validates operational limits through resolve_step_config
- **US4 (P2)**: Start after US2 — validates prompt fields through resolve_step_config. **Parallel with US3**
- **US5 (P3)**: Start after US2 — extends resolve_step_config with project-level layer

### Within Each User Story

- Implementation tasks listed before test tasks (logical dependency ordering); TDD micro-cycle (red-green-refactor) applied within each task per Principle V
- Schema changes before handler changes
- Config model changes before resolution function changes

### Parallel Opportunities

- T003/T004: Foundational tests can run in parallel (different files)
- T007/T008/T009: US1 mode inference helper, schema tests, and config tests can run in parallel
- T011: Protocol update can run in parallel with T010 (different files)
- T014/T015: US3 tests can run in parallel (same file but independent test classes)
- T016/T017: US4 tests can run in parallel (different files)
- T020: US5 config tests can run in parallel with T018/T019 implementation
- US3 and US4 phases can run entirely in parallel with each other

---

## Parallel Example: User Story 1

```bash
# After T005/T006 complete (schema changes), launch in parallel:
Task: "T007 [P] [US1] Add infer_step_mode helper in src/maverick/dsl/executor/config.py"
Task: "T008 [P] [US1] Add tests for StepRecord.config and backward compat in tests/unit/dsl/serialization/test_schema.py"
Task: "T009 [P] [US1] Add tests for mode inference in tests/unit/dsl/executor/test_config.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Foundational (enums + StepConfig model)
2. Complete Phase 2: User Story 1 (schema integration, mode inference, backward compat)
3. **STOP and VALIDATE**: Test that existing workflows still load, new `config` field works, `executor_config` triggers deprecation warning
4. Existing tests pass (`make test-fast`)

### Incremental Delivery

1. Foundational → Enums and StepConfig model ready
2. US1 → Schema integration, backward compat → Test independently (MVP!)
3. US2 → 4-layer resolution, protocol update → Test independently
4. US3 + US4 (parallel) → Operational limits + prompt extension → Test independently
5. US5 → Project-level defaults → Full integration test
6. Polish → Cleanup, quickstart validation

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks in same phase
- [Story] label maps task to specific user story for traceability
- StepConfig is a single Pydantic model (all 12 fields) created in Foundational; user story phases focus on integration, wiring, and testing
- StepExecutorConfig frozen dataclass is REPLACED by StepConfig Pydantic BaseModel; type alias preserves backward compat
- RetryPolicy frozen dataclass is UNCHANGED (no cross-field validation needed)
- DEFAULT_EXECUTOR_CONFIG constant updated in T002 alongside the StepConfig migration
- executor_config field on AgentStepRecord is migrated to config on StepRecord base with deprecation path
- **FR-004 clarification**: "Safe-by-default" means autonomy defaults to `operator` (most restrictive). Mode is NOT statically `deterministic` — it is inferred from step type via FR-008 (agent steps→`agent`, python steps→`deterministic`). The StepConfig model stores `mode=None`; resolution applies inference.
- **Backward compat field rename**: Legacy `executor_config` used `model` key; new `config` uses `model_id`. The migration validator (T006) and `resolve_step_config` (T010) both handle this rename.
