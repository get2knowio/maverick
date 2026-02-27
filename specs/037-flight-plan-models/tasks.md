# Tasks: Flight Plan and Work Unit Data Models

**Input**: Design documents from `/specs/037-flight-plan-models/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/api.py

**Tests**: Included per constitution mandate (Test-First TDD) and spec SC-007 (comprehensive automated test coverage).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the `src/maverick/flight/` package skeleton and error hierarchy

- [X] T001 Create src/maverick/flight/ package directory with __init__.py stub (empty __all__ list, `from __future__ import annotations`)
- [X] T002 [P] Create FlightError hierarchy in src/maverick/exceptions/flight.py (FlightError, FlightPlanParseError, FlightPlanValidationError, FlightPlanNotFoundError, WorkUnitValidationError, WorkUnitDependencyError — all inheriting from MaverickError via FlightError). Follow the jj.py __init__ pattern: each error accepts `message: str` plus contextual keyword-only args (e.g., `path: Path | None = None`, `field: str | None = None`) stored as instance attributes. Re-export all from exceptions/__init__.py.
- [X] T003 [P] Create error re-exports in src/maverick/flight/errors.py (import and re-export all errors from maverick.exceptions.flight)
- [X] T004 [P] Create test package with shared fixtures in tests/unit/flight/__init__.py and tests/unit/flight/conftest.py (sample Flight Plan markdown string, sample Work Unit markdown string, factory helpers for model instances)

---

## Phase 2: Foundational (Shared Parser)

**Purpose**: Core Markdown+YAML frontmatter parser used by ALL user stories — MUST complete before any story

**CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Write tests for core parser functions in tests/unit/flight/test_parser.py: valid frontmatter extraction, missing delimiters error, invalid YAML error, checkbox parsing ([x]/[X]/[ ]), bullet list parsing, empty content, content with YAML-like syntax in body. Tests should FAIL before T006 implementation.
- [X] T006 Implement core parser functions in src/maverick/flight/parser.py: parse_frontmatter(content) -> tuple[dict, str], parse_checkbox_list(content) -> list[tuple[bool, str]], parse_bullet_list(content) -> list[str]. Use manual `---` delimiter splitting with yaml.safe_load(). Raise FlightPlanParseError on malformed input.

**Checkpoint**: Parser ready — user story implementation can now begin

---

## Phase 3: User Story 1 — Author a Flight Plan (Priority: P1) MVP

**Goal**: Load Flight Plan Markdown files, validate structure, and provide completion introspection

**Independent Test**: Create a sample Flight Plan Markdown file, load it, verify all fields accessible as structured data, check completion percentage

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T007 [P] [US1] Write FlightPlan model tests in tests/unit/flight/test_models.py: construction with all fields, frozen immutability, computed completion property (some checked, all checked, none checked, zero criteria → None percentage, absent Success Criteria section → 0/0 treated as None), Scope model with in_scope/out_of_scope/boundaries tuples, SuccessCriterion checked/unchecked states, to_dict() output, validation error on missing required fields (name, version, created, tags)
- [X] T008 [P] [US1] Write FlightPlanFile loader tests in tests/unit/flight/test_loader.py: load() from valid file returns FlightPlan with correct fields, aload() async variant, FlightPlanNotFoundError on missing file, FlightPlanParseError on malformed frontmatter, FlightPlanValidationError on missing required fields, extra YAML fields ignored (forward compatibility), optional sections (context, constraints, notes) default gracefully

### Implementation for User Story 1

- [X] T009 [P] [US1] Implement FlightPlan, SuccessCriterion, CompletionStatus, and Scope frozen Pydantic models in src/maverick/flight/models.py (ConfigDict(frozen=True), field validators per data-model.md, completion computed property, to_dict() method). Include Field(description=...) on required fields per constitution VI.
- [X] T010 [US1] Implement parse_flight_plan_sections() in src/maverick/flight/parser.py: extract ## Objective, ## Success Criteria (parse checkboxes), ## Scope (with ### In/### Out/### Boundaries subsections), ## Context, ## Constraints (parse bullets), ## Notes from Markdown body
- [X] T011 [US1] Implement FlightPlanFile.load() and FlightPlanFile.aload() in src/maverick/flight/loader.py: read file, call parse_frontmatter, call parse_flight_plan_sections, construct FlightPlan model with source_path, handle FileNotFoundError → FlightPlanNotFoundError, handle ValidationError → FlightPlanValidationError. Async via asyncio.to_thread().

**Checkpoint**: Flight Plan loading and introspection fully functional and tested

---

## Phase 4: User Story 2 — Define and Load Work Units (Priority: P1)

**Goal**: Load Work Unit Markdown files, validate structure including kebab-case IDs, and link to Flight Plans

**Independent Test**: Create sample Work Unit Markdown files, load them individually and from a directory, verify all fields accessible and linked to Flight Plan reference

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T012 [P] [US2] Write WorkUnit model tests in tests/unit/flight/test_models.py: construction with all fields, frozen immutability, kebab-case ID validation (valid slugs pass, invalid formats reject), positive sequence validation, AcceptanceCriterion with and without trace_ref (SC-### format), FileScope with create/modify/protect tuples, optional parallel_group and depends_on defaults, to_dict() output
- [X] T013 [P] [US2] Write WorkUnitFile loader tests in tests/unit/flight/test_loader.py: load() from valid file, aload() async variant, load_directory() discovers ###-slug.md files and returns sorted list, aload_directory() async variant, empty directory returns empty list, WorkUnitValidationError on invalid ID format, optional provider_hints section

### Implementation for User Story 2

- [X] T014 [P] [US2] Implement WorkUnit, AcceptanceCriterion, and FileScope frozen Pydantic models in src/maverick/flight/models.py (kebab-case regex validator for id field, positive int validator for sequence, tuple defaults for depends_on). Include Field(description=...) on required fields per constitution VI.
- [X] T015 [US2] Implement parse_work_unit_sections() in src/maverick/flight/parser.py: extract ## Task, ## Acceptance Criteria (parse bullets with optional [SC-###] trace refs), ## File Scope (with ### Create/### Modify/### Protect subsections), ## Instructions, ## Verification (parse as command list), ## Provider Hints (optional)
- [X] T016 [US2] Implement WorkUnitFile.load(), aload(), load_directory(), aload_directory() in src/maverick/flight/loader.py: file discovery via ###-slug.md glob pattern, parse frontmatter + sections, construct WorkUnit model with source_path, sort by sequence number. Async via asyncio.to_thread().

**Checkpoint**: Work Unit loading and directory discovery fully functional and tested

---

## Phase 5: User Story 3 — Resolve Work Unit Dependencies and Ordering (Priority: P2)

**Goal**: Topologically sort Work Units by dependencies, group parallel-eligible units into batches

**Independent Test**: Create Work Units with various dependency graphs, resolve order, verify every unit appears after its dependencies and parallel groups are batched

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T017 [P] [US3] Write resolver tests in tests/unit/flight/test_resolver.py: linear chain ordering, diamond dependency, independent units in same batch, parallel_group batching, circular dependency raises WorkUnitDependencyError with cycle IDs, missing dependency raises WorkUnitDependencyError with missing ID, empty list returns empty batches, single unit returns single batch, ExecutionOrder and ExecutionBatch model construction

### Implementation for User Story 3

- [X] T018 [P] [US3] Implement ExecutionOrder and ExecutionBatch frozen Pydantic models in src/maverick/flight/models.py (ExecutionBatch with units tuple and optional parallel_group, ExecutionOrder with batches tuple)
- [X] T019 [US3] Implement resolve_execution_order(units) -> ExecutionOrder in src/maverick/flight/resolver.py: build adjacency map from depends_on, validate all referenced IDs exist, DFS topological sort with cycle detection (adapted from PrerequisiteRegistry pattern in src/maverick/dsl/prerequisites/registry.py), group units by parallel_group within dependency tiers, raise WorkUnitDependencyError on cycles or missing deps

**Checkpoint**: Dependency resolution and parallel batching fully functional and tested

---

## Phase 6: User Story 4 — Round-Trip Serialization (Priority: P2)

**Goal**: Serialize FlightPlan and WorkUnit models back to Markdown+YAML format with round-trip fidelity

**Independent Test**: Load a document, serialize it, reload the serialized output, verify identical structured data

### Tests for User Story 4

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T020 [P] [US4] Write serializer and round-trip tests in tests/unit/flight/test_serializer.py: serialize_flight_plan() produces valid YAML frontmatter + Markdown sections, serialize_work_unit() produces valid YAML frontmatter + Markdown sections, round-trip fidelity for FlightPlan (load → serialize → reload → compare), round-trip fidelity for WorkUnit, FlightPlanFile.save/asave write correct content, WorkUnitFile.save/asave write correct content

### Implementation for User Story 4

- [X] T021 [P] [US4] Implement serialize_flight_plan() in src/maverick/flight/serializer.py: build YAML frontmatter dict from model fields, render Markdown sections (## Objective, ## Success Criteria with checkboxes, ## Scope with subsections, etc.), join with `---` delimiters
- [X] T022 [P] [US4] Implement serialize_work_unit() in src/maverick/flight/serializer.py: build YAML frontmatter dict (work-unit, flight-plan, sequence, parallel-group, depends-on), render Markdown sections (## Task, ## Acceptance Criteria with trace refs, ## File Scope with subsections, etc.)
- [X] T023 [US4] Implement FlightPlanFile.save/asave and WorkUnitFile.save/asave in src/maverick/flight/loader.py: call serialize function, write to path, async via asyncio.to_thread()

**Checkpoint**: All models support round-trip Markdown+YAML serialization with fidelity

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Finalize package exports, validate all checks pass, verify quickstart examples

- [X] T024 Finalize src/maverick/flight/__init__.py with complete __all__ exports per contracts/api.py (all models, FlightPlanFile, WorkUnitFile, resolve_execution_order, serialize functions, parse_frontmatter, all error types)
- [X] T025 Run make check (lint + typecheck + test) and fix any issues across all src/maverick/flight/ and tests/unit/flight/ files
- [X] T026 Validate quickstart.md code examples against implemented API (verify imports, method signatures, and error types match)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup (T001-T004) — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational (T005-T006)
- **US2 (Phase 4)**: Depends on Foundational (T005-T006). Independent of US1 (models.py is additive, not conflicting)
- **US3 (Phase 5)**: Depends on US2 (needs WorkUnit model from T014)
- **US4 (Phase 6)**: Depends on US1 + US2 (needs both FlightPlan and WorkUnit models)
- **Polish (Phase 7)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational — no story dependencies
- **US2 (P1)**: Can start after Foundational — independent of US1 (shares models.py file but different classes)
- **US3 (P2)**: Depends on US2 (WorkUnit model + loader for test fixtures)
- **US4 (P2)**: Depends on US1 + US2 (needs both model types for serialization)

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Models before parser integration
- Parser integration before loader
- Core implementation before integration tests pass

### Parallel Opportunities

- **Phase 1**: T002, T003, T004 can run in parallel (different files)
- **Phase 2**: T005 (tests) then T006 (implementation) — TDD order, tests written first
- **US1**: T007 + T008 in parallel (test files), then T009 (models), T010 (parser), T011 (loader)
- **US2**: T012 + T013 in parallel (test files), then T014 (models), T015 (parser), T016 (loader)
- **US3**: T017 + T018 in parallel (test + models), then T019 (resolver)
- **US4**: T020 in parallel with T021 + T022, then T023 (loader save methods)
- **Cross-story**: US1 and US2 can run in parallel after Foundational phase

---

## Parallel Example: User Story 1

```bash
# TDD: Launch tests first (both test files in parallel):
Task: "Write FlightPlan model tests in tests/unit/flight/test_models.py"
Task: "Write FlightPlanFile loader tests in tests/unit/flight/test_loader.py"

# Then implement (models first, no deps between them):
Task: "Implement FlightPlan, SuccessCriterion, CompletionStatus, Scope models in src/maverick/flight/models.py"

# Then sequential (parser integration depends on models, loader depends on both):
Task: "Implement parse_flight_plan_sections() in src/maverick/flight/parser.py"
Task: "Implement FlightPlanFile.load/aload in src/maverick/flight/loader.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 2: Foundational parser (T005-T006)
3. Complete Phase 3: User Story 1 — Flight Plan loading + introspection (T007-T011)
4. **STOP and VALIDATE**: `make test-fast` — Flight Plan tests pass independently
5. Deliver: Flight Plans can be loaded, validated, and queried for completion

### Incremental Delivery

1. Setup + Foundational → Parser ready
2. Add US1 → Flight Plans loadable → **MVP!**
3. Add US2 → Work Units loadable → Complete read-path
4. Add US3 → Dependency resolution → Execution ordering
5. Add US4 → Serialization → Full round-trip capability
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: US1 (Flight Plan models + loader)
   - Developer B: US2 (Work Unit models + loader)
3. After US1 + US2 complete:
   - Developer A: US4 (Serialization — needs both models)
   - Developer B: US3 (Resolver — needs WorkUnit model)
4. Polish phase together

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing (TDD)
- Commit after each task or logical group
- All models use `ConfigDict(frozen=True)` — mutations via `model_copy(update={...})`
- Parser uses manual `---` splitting + PyYAML — no new dependencies
- Resolver adapts DFS pattern from `src/maverick/dsl/prerequisites/registry.py`
- Module size constraint: each file < 500 LOC per constitution
