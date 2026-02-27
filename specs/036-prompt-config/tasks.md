# Tasks: Three-Tier Prompt Configuration

**Input**: Design documents from `/specs/036-prompt-config/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/prompt_api.py, quickstart.md

**Tests**: Included per constitution principle V (Test-First: TDD with Red-Green-Refactor).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create package structure and shared test fixtures

- [X] T001 Create `src/maverick/prompts/` package directory with `__init__.py` (add re-exports incrementally as modules are created in subsequent phases)
- [X] T002 [P] Create `tests/unit/prompts/` directory with shared fixtures (sample registries, entries, overrides) in `tests/unit/prompts/conftest.py`

---

## Phase 2: Foundational (Core Types & Registry)

**Purpose**: Core data models and registry that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

> **TDD Note**: Phase 2 implements types before tests (T003→T004) because tests need to import the foundational types. User story phases (3+) follow strict test-first ordering.

- [X] T003 Implement OverridePolicy enum, PromptSource enum, PromptEntry frozen dataclass, PromptResolution frozen dataclass (with `to_dict()`), and PromptConfigError exception in `src/maverick/prompts/models.py`
- [X] T004 Write tests for all core models (enum values, frozen immutability, PromptEntry defaults, PromptResolution.to_dict() serialization, PromptConfigError inheritance from ConfigError) in `tests/unit/prompts/test_models.py`
- [X] T005 [P] Implement PromptRegistry class (constructor with empty-check, `get()` with generic fallback, `get_policy()`, `has()`, `step_names()`, `validate_override()`) in `src/maverick/prompts/registry.py`
- [X] T006 [P] Write tests for PromptRegistry (construction, empty rejection, get with fallback, get_policy shortcut, has check, step_names dedup, validate_override policy enforcement) in `tests/unit/prompts/test_registry.py`
- [X] T007 [P] Implement PromptOverrideConfig Pydantic model with mutual exclusivity validator (prompt_suffix XOR prompt_file, at-least-one-set, empty string treated as None) in `src/maverick/prompts/config.py`
- [X] T008 [P] Write tests for PromptOverrideConfig validation (mutual exclusivity, at-least-one, empty string normalization) in `tests/unit/prompts/test_config.py`

**Checkpoint**: Core types and registry are tested and usable. User story implementation can begin.

---

## Phase 3: User Story 1 - Default Prompts Work Without Configuration (Priority: P1) MVP

**Goal**: Every agent and generator step receives its shipped default instructions automatically when no prompt configuration is present in `maverick.yaml`.

**Independent Test**: Call `resolve_prompt()` for any registered step with no override. Verify it returns the correct default text with `source=DEFAULT` and `override_applied=False`.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T009 [P] [US1] Write tests for build_default_registry() (all 12 agent/generator entries present, correct policies per data-model.md table, is_template flags correct, no empty text) in `tests/unit/prompts/test_defaults.py`
- [X] T010 [P] [US1] Write tests for resolve_prompt() default path — no override returns default text, source=DEFAULT, override_applied=False; missing step_name raises PromptConfigError (Quickstart Scenario 1) in `tests/unit/prompts/test_resolver.py`

### Implementation for User Story 1

- [X] T011 [US1] Implement build_default_registry() importing prompt constants by reference from agent modules (ImplementerAgent, CodeReviewerAgent, FixerAgent, IssueFixerAgent, CuratorAgent, CommitMessageGenerator, PRDescriptionGenerator, PRTitleGenerator, CodeAnalyzer, ErrorExplainer, DependencyExtractor, BeadEnricher) in `src/maverick/prompts/defaults.py`. **Note**: PRDescriptionGenerator uses a dynamic `_build_system_prompt()` method (not a constant) — call it with default sections to obtain a static default text. CodeAnalyzer has 3 variants (EXPLAIN/REVIEW/SUMMARIZE) — register the primary variant (`SYSTEM_PROMPT_REVIEW`) as `code_analyze` default; additional variants can be added as provider-keyed entries if needed.
- [X] T012 [US1] Implement resolve_prompt() base path — registry lookup, no-override return, structlog DEBUG `prompt_resolved` event with step_name/provider/source/override_applied fields in `src/maverick/prompts/resolver.py`

**Checkpoint**: `resolve_prompt("implement", registry)` returns shipped default. All existing workflows unaffected. Quickstart Scenario 1 passes.

---

## Phase 4: User Story 2 - Append Custom Guidance to a Step's Prompt (Priority: P2)

**Goal**: Users add project-specific conventions via `prompt_suffix` in config, appended to defaults with a separator heading. Template variables in both defaults and suffixes are rendered.

**Independent Test**: Configure `prompt_suffix` for the `implement` step, call `resolve_prompt()`, verify output contains both default text and suffix after separator.

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T013 [US2] Write tests for prompt_suffix resolution — suffix appended with `\n\n---\n\n## Project-Specific Instructions\n\n` separator, source=SUFFIX, override_applied=True; empty suffix treated as no-override; template variable rendering in base and suffix (Quickstart Scenarios 2, 6) in `tests/unit/prompts/test_resolver.py`

### Implementation for User Story 2

- [X] T014 [US2] Extend resolve_prompt() with prompt_suffix appending (separator + suffix), empty-string bypass, and render_prompt() template integration (reuse `render_prompt` from `src/maverick/agents/skill_prompts.py` per A-002) in `src/maverick/prompts/resolver.py`

**Checkpoint**: `resolve_prompt("implement", registry, override=PromptOverrideConfig(prompt_suffix="Use snake_case"))` returns default + separator + suffix. Quickstart Scenarios 2, 6 pass.

---

## Phase 5: User Story 3 - Replace a Step's Prompt via File (Priority: P3)

**Goal**: Power users fully replace prompts for steps with `replace` policy via `prompt_file`. Steps with `augment_only` policy reject file replacement. All config validated at startup.

**Independent Test**: Create a prompt file, configure `prompt_file` for `pr_description` (replace policy), verify resolved prompt is file contents only. Verify `implement` (augment_only) rejects `prompt_file` with clear error.

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T015 [P] [US3] Write tests for prompt_file resolution — file contents replace default for `replace` policy steps, source=FILE, override_applied=True; PromptConfigError raised for `augment_only` steps; PromptConfigError for missing file; PromptConfigError for path outside project root; template rendering applied to file contents when is_template=True (Quickstart Scenarios 3, 4) in `tests/unit/prompts/test_resolver.py`
- [X] T016 [P] [US3] Write tests for validate_prompt_config() — unknown step name raises error, policy violation (prompt_file on augment_only) raises error, missing prompt_file raises error, absolute path rejected, `../` traversal outside project root rejected, valid config passes (Quickstart Scenario 7) in `tests/unit/prompts/test_validation.py`

### Implementation for User Story 3

- [X] T017 [US3] Extend resolve_prompt() with prompt_file replacement — policy check, path resolution relative to project_root, `Path.resolve()` canonicalization, project root prefix security check, file reading, template rendering in `src/maverick/prompts/resolver.py`
- [X] T018 [US3] Implement validate_prompt_config() — validate step names against registry, delegate policy checks to registry.validate_override(), validate prompt_file paths (exist, readable, within project root) in `src/maverick/prompts/validation.py`
- [X] T019 [US3] Add `prompts: dict[str, PromptOverrideConfig]` field to MaverickConfig with model_validator that merges prompt overrides into `steps:` dict (conflict detection if both prompts: and steps: configure same step's prompt fields) in `src/maverick/config.py`

**Checkpoint**: Full replacement works for `replace`-policy steps. `augment_only` steps reject prompt_file. Startup validation catches all misconfigurations. Quickstart Scenarios 3, 4, 7 pass.

---

## Phase 6: User Story 4 - Provider-Specific Prompt Variants (Priority: P4)

**Goal**: Registry supports `(step_name, provider)` two-level keys. Provider-specific variants are selected automatically with fallback to generic default.

**Independent Test**: Register a provider-specific variant for `review`, resolve with that provider, verify provider variant returned. Resolve without provider, verify generic default returned.

### Tests for User Story 4

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T020 [US4] Write tests for provider-specific resolution — provider variant selected when available (source=PROVIDER_VARIANT), generic fallback when no provider variant exists (source=DEFAULT), default provider returns generic not provider-specific (Quickstart Scenario 5) in `tests/unit/prompts/test_resolver.py`

### Implementation for User Story 4

- [X] T021 [US4] Extend resolve_prompt() provider lookup — try (step_name, provider) first, fall back to (step_name, GENERIC_PROVIDER), set source=PROVIDER_VARIANT when provider-specific entry matched in `src/maverick/prompts/resolver.py`

**Checkpoint**: Provider-specific prompts work with transparent fallback. Quickstart Scenario 5 passes.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Public API surface, handler integration, and final validation

- [X] T022 Verify all public API re-exports are complete and match contracts (PromptRegistry, PromptEntry, PromptResolution, PromptOverrideConfig, PromptConfigError, OverridePolicy, PromptSource, GENERIC_PROVIDER, resolve_prompt, build_default_registry, validate_prompt_config) in `src/maverick/prompts/__init__.py`
- [X] T023 [P] Add integration hooks in agent step handler to call resolve_prompt() before StepExecutor.execute() in `src/maverick/dsl/serialization/executor/handlers/agent_step.py`
- [X] T024 [P] Add integration hooks in generator step handler to override system_prompt with resolved prompt in `src/maverick/dsl/serialization/executor/handlers/generate_step.py`
- [X] T025 [P] Add integration hooks in dispatch handler to use resolve_prompt() for consistency with agent/generator handlers in `src/maverick/dsl/serialization/executor/handlers/dispatch.py`
- [X] T026 Run `make check` (lint, typecheck, test) — all checks must pass with zero failures

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational (Phase 2)
- **User Story 2 (Phase 4)**: Depends on US1 (Phase 3) — extends resolve_prompt()
- **User Story 3 (Phase 5)**: Depends on US2 (Phase 4) — extends resolve_prompt() further
- **User Story 4 (Phase 6)**: Depends on US1 (Phase 3) — extends resolve_prompt() provider logic; can run in parallel with US2/US3
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (P1)**: Foundation only — no dependencies on other stories
- **US2 (P2)**: Builds on US1's resolve_prompt() base implementation
- **US3 (P3)**: Builds on US2's resolve_prompt() (adds file path alongside suffix)
- **US4 (P4)**: Builds on US1's resolve_prompt() base (provider lookup is independent of suffix/file)

### Within Each User Story

- Tests MUST be written and FAIL before implementation (TDD)
- Implementation makes tests pass
- Story complete before moving to next priority

### Parallel Opportunities

- **Phase 1**: T001 and T002 can run in parallel (different directories)
- **Phase 2**: T005+T006 (registry) and T007+T008 (config) can run in parallel after T003+T004 (models)
- **Phase 3**: T009 and T010 (tests) can run in parallel before implementation
- **Phase 5**: T015 and T016 (tests) can run in parallel before implementation
- **Phase 6**: US4 can run in parallel with US2/US3 (independent resolve_prompt extension)
- **Phase 7**: T023, T024, and T025 (handler integration) can run in parallel

---

## Parallel Example: Phase 2 (Foundational)

```bash
# Step 1: Models first (everything depends on these)
Task: T003 "Implement core models in src/maverick/prompts/models.py"

# Step 2: Tests + independent modules in parallel
Task: T004 "Write model tests in tests/unit/prompts/test_models.py"
Task: T005 "Implement PromptRegistry in src/maverick/prompts/registry.py"  # parallel
Task: T007 "Implement PromptOverrideConfig in src/maverick/prompts/config.py"  # parallel

# Step 3: Registry and config tests in parallel
Task: T006 "Write registry tests in tests/unit/prompts/test_registry.py"
Task: T008 "Write config tests in tests/unit/prompts/test_config.py"  # parallel
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (core types + registry)
3. Complete Phase 3: User Story 1 (default prompts)
4. **STOP and VALIDATE**: `resolve_prompt()` returns correct defaults for all 12 registered steps
5. All existing workflows unaffected (zero regression)

### Incremental Delivery

1. Setup + Foundational -> Core types tested
2. US1 -> Default resolution works -> Validate (MVP!)
3. US2 -> Suffix appending works -> Validate
4. US3 -> File replacement + startup validation -> Validate
5. US4 -> Provider variants with fallback -> Validate
6. Polish -> Handler integration, public API, full check

### Key Risk: Agent Prompt Constants

T011 (build_default_registry) imports from 12 agent modules. If any agent module's prompt constant has been renamed, moved, or made dynamic (e.g., PRDescriptionGenerator's `_build_system_prompt()`), the import will need adaptation. Research R-001 documents current locations — verify before implementing.

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- All resolve_prompt() extensions are additive — each story adds a code path without breaking previous ones
- PromptOverrideConfig is Pydantic (config parsing); PromptEntry/PromptResolution are frozen dataclasses (runtime data)
- Template rendering reuses existing `render_prompt()` from `src/maverick/agents/skill_prompts.py` (A-002)
- Security: prompt_file paths restricted to project root via `Path.resolve()` + prefix check (FR-010)
- Logging: structlog DEBUG `prompt_resolved` event on every resolution (FR-015)
