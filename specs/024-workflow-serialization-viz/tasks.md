# Tasks: Workflow Serialization & Visualization

**Input**: Design documents from `/specs/024-workflow-serialization-viz/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and new module structure

- [ ] T001 Create expression module structure in src/maverick/dsl/expressions/__init__.py
- [ ] T002 [P] Create serialization module structure in src/maverick/dsl/serialization/__init__.py
- [ ] T003 [P] Create visualization module structure in src/maverick/dsl/visualization/__init__.py
- [ ] T004 Add PyYAML dependency to project requirements

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**CRITICAL**: No user story work can begin until this phase is complete

### Error Types

- [ ] T005 Create serialization error hierarchy in src/maverick/dsl/serialization/errors.py (WorkflowSerializationError, WorkflowParseError, UnsupportedVersionError, ReferenceResolutionError)
- [ ] T006 [P] Create expression error types in src/maverick/dsl/expressions/errors.py (ExpressionSyntaxError, ExpressionEvaluationError)

### Schema Models (Pydantic)

- [ ] T007 Create InputType enum and InputDefinition model in src/maverick/dsl/serialization/schema.py
- [ ] T008 Create StepType enum extension and StepRecord base model in src/maverick/dsl/serialization/schema.py
- [ ] T009 Create PythonStepRecord and AgentStepRecord models in src/maverick/dsl/serialization/schema.py
- [ ] T010 Create GenerateStepRecord and ValidateStepRecord models in src/maverick/dsl/serialization/schema.py
- [ ] T011 Create SubWorkflowStepRecord, BranchStepRecord, ParallelStepRecord models in src/maverick/dsl/serialization/schema.py
- [ ] T012 Create WorkflowFile top-level schema model with version validation in src/maverick/dsl/serialization/schema.py
- [ ] T013 Configure Pydantic discriminated union for StepRecordUnion in src/maverick/dsl/serialization/schema.py

### Expression Models

- [ ] T014 Create ExpressionKind enum and Expression dataclass in src/maverick/dsl/expressions/parser.py
- [ ] T015 Create ExpressionError dataclass in src/maverick/dsl/expressions/errors.py

### Validation Result Models

- [ ] T016 Create ValidationError, ValidationWarning, ValidationResult dataclasses in src/maverick/dsl/serialization/schema.py

### Unit Tests for Foundational Models (TDD - write FIRST)

- [ ] T016a [P] Write tests for InputType enum and InputDefinition in tests/unit/dsl/serialization/test_schema.py
- [ ] T016b [P] Write tests for StepRecord models and discriminated union in tests/unit/dsl/serialization/test_schema.py
- [ ] T016c [P] Write tests for ValidationError and ValidationResult in tests/unit/dsl/serialization/test_schema.py
- [ ] T016d [P] Write tests for expression error types in tests/unit/dsl/expressions/test_errors.py

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Define workflows as files (Priority: P1)

**Goal**: Enable workflow authors to represent workflows as YAML/JSON and load them into Maverick for execution

**Independent Test**: Round-trip a workflow: serialize to YAML, parse back, verify semantic equivalence

### Tests for Expression Parser (TDD - write FIRST)

- [ ] T017a [US1] Write failing tests for expression tokenizer in tests/unit/dsl/expressions/test_parser.py
- [ ] T017b [US1] Write failing tests for recursive descent parser in tests/unit/dsl/expressions/test_parser.py
- [ ] T017c [US1] Write failing tests for extract_all() in tests/unit/dsl/expressions/test_parser.py

### Expression Parser Implementation

- [ ] T017 [US1] Implement expression tokenizer for ${{ }} syntax in src/maverick/dsl/expressions/parser.py
- [ ] T018 [US1] Implement recursive descent parser for expression AST in src/maverick/dsl/expressions/parser.py
- [ ] T019 [US1] Implement extract_all() to find all expressions in text in src/maverick/dsl/expressions/parser.py

### Tests for Expression Evaluator (TDD - write FIRST)

- [ ] T020a [US1] Write failing tests for input reference evaluation in tests/unit/dsl/expressions/test_evaluator.py
- [ ] T020b [US1] Write failing tests for step output reference evaluation in tests/unit/dsl/expressions/test_evaluator.py
- [ ] T020c [US1] Write failing tests for nested field access and negation in tests/unit/dsl/expressions/test_evaluator.py

### Expression Evaluator Implementation

- [ ] T020 [US1] Create ExpressionEvaluator class in src/maverick/dsl/expressions/evaluator.py
- [ ] T021 [US1] Implement input reference evaluation (inputs.name) in src/maverick/dsl/expressions/evaluator.py
- [ ] T022 [US1] Implement step output reference evaluation (steps.x.output) in src/maverick/dsl/expressions/evaluator.py
- [ ] T023 [US1] Implement nested field access and boolean negation in src/maverick/dsl/expressions/evaluator.py
- [ ] T024 [US1] Implement evaluate_string() for text with embedded expressions in src/maverick/dsl/expressions/evaluator.py

### Tests for Registries (TDD - write FIRST)

- [ ] T025a [US1] Write failing tests for Registry protocol in tests/unit/dsl/serialization/test_registry.py
- [ ] T025b [US1] Write failing tests for ComponentRegistry facade in tests/unit/dsl/serialization/test_registry.py

### Registry Implementation

- [ ] T025 [US1] Create generic Registry protocol and base implementation in src/maverick/dsl/serialization/registry.py
- [ ] T026 [P] [US1] Create ActionRegistry with decorator registration in src/maverick/dsl/serialization/registry.py
- [ ] T027 [P] [US1] Create GeneratorRegistry in src/maverick/dsl/serialization/registry.py
- [ ] T028 [P] [US1] Create ContextBuilderRegistry in src/maverick/dsl/serialization/registry.py
- [ ] T029 [P] [US1] Create WorkflowRegistry in src/maverick/dsl/serialization/registry.py
- [ ] T030 [US1] Create ComponentRegistry facade with strict/lenient modes in src/maverick/dsl/serialization/registry.py
- [ ] T031 [US1] Integrate existing AgentRegistry into ComponentRegistry in src/maverick/dsl/serialization/registry.py

### Tests for Workflow Parser (TDD - write FIRST)

- [ ] T032a [US1] Write failing tests for YAML parsing in tests/unit/dsl/serialization/test_parser.py
- [ ] T032b [US1] Write failing tests for schema validation in tests/unit/dsl/serialization/test_parser.py
- [ ] T032c [US1] Write failing tests for version validation in tests/unit/dsl/serialization/test_parser.py
- [ ] T032d [US1] Write failing tests for reference resolution in tests/unit/dsl/serialization/test_parser.py

### Workflow Parser Implementation

- [ ] T032 [US1] Implement YAML parsing to dict with error handling in src/maverick/dsl/serialization/parser.py
- [ ] T033 [US1] Implement schema validation using Pydantic WorkflowFile in src/maverick/dsl/serialization/parser.py
- [ ] T034 [US1] Implement version validation with supported versions check in src/maverick/dsl/serialization/parser.py
- [ ] T035 [US1] Implement expression extraction and static validation in src/maverick/dsl/serialization/parser.py
- [ ] T036 [US1] Implement reference resolution using ComponentRegistry in src/maverick/dsl/serialization/parser.py
- [ ] T037 [US1] Implement WorkflowFile to WorkflowDefinition conversion in src/maverick/dsl/serialization/parser.py
- [ ] T038 [US1] Implement validate_only() mode in src/maverick/dsl/serialization/parser.py
- [ ] T039 [US1] Implement parse_workflow() convenience function in src/maverick/dsl/serialization/parser.py

### Tests for Workflow Writer (TDD - write FIRST)

- [ ] T040a [US1] Write failing tests for to_dict() in tests/unit/dsl/serialization/test_writer.py
- [ ] T040b [US1] Write failing tests for to_yaml() in tests/unit/dsl/serialization/test_writer.py
- [ ] T040c [US1] Write failing round-trip tests in tests/integration/dsl/test_workflow_roundtrip.py

### Workflow Writer Implementation

- [ ] T040 [US1] Implement WorkflowWriter.to_dict() serialization in src/maverick/dsl/serialization/writer.py
- [ ] T041 [US1] Implement WorkflowWriter.to_yaml() serialization in src/maverick/dsl/serialization/writer.py
- [ ] T042 [US1] Implement WorkflowWriter.to_json() serialization in src/maverick/dsl/serialization/writer.py

### Integration with Existing DSL

- [ ] T043 [US1] Add to_dict() and to_yaml() methods to WorkflowDefinition in src/maverick/dsl/builder.py
- [ ] T044 [US1] Add from_dict() and from_yaml() class methods to Workflow in src/maverick/dsl/builder.py

**Checkpoint**: User Story 1 complete - workflows can be serialized and parsed from YAML/JSON

---

## Phase 4: User Story 2 - Visualize workflow execution paths (Priority: P2)

**Goal**: Enable workflow authors to generate Mermaid and ASCII diagrams from workflow definitions

**Independent Test**: Generate both Mermaid and ASCII output for a known workflow and verify all expected nodes and edges

### Tests for Visualization (TDD - write FIRST)

- [ ] T045a [US2] Write failing tests for WorkflowGraphBuilder in tests/unit/dsl/visualization/test_graph.py
- [ ] T045b [P] [US2] Write failing tests for MermaidGenerator in tests/unit/dsl/visualization/test_mermaid.py
- [ ] T045c [P] [US2] Write failing tests for ASCIIGenerator in tests/unit/dsl/visualization/test_ascii.py

### Graph Building

- [ ] T045 [US2] Create GraphNode and GraphEdge dataclasses in src/maverick/dsl/visualization/__init__.py
- [ ] T046 [US2] Create EdgeType enum (sequential, conditional, retry, branch) in src/maverick/dsl/visualization/__init__.py
- [ ] T047 [US2] Create WorkflowGraph dataclass in src/maverick/dsl/visualization/__init__.py
- [ ] T048 [US2] Implement WorkflowGraphBuilder.build() in src/maverick/dsl/visualization/__init__.py
- [ ] T049 [US2] Implement step unwrapping for ConditionalStep, RetryStep wrappers in src/maverick/dsl/visualization/__init__.py
- [ ] T050 [US2] Handle parallel and branch steps in graph building in src/maverick/dsl/visualization/__init__.py

### Mermaid Generator

- [ ] T051 [US2] Create MermaidGenerator class in src/maverick/dsl/visualization/mermaid.py
- [ ] T052 [US2] Implement node formatting with type-based shapes in src/maverick/dsl/visualization/mermaid.py
- [ ] T053 [US2] Implement edge formatting with labels in src/maverick/dsl/visualization/mermaid.py
- [ ] T054 [US2] Implement subgraph generation for parallel steps in src/maverick/dsl/visualization/mermaid.py
- [ ] T055 [US2] Implement retry loop edge generation in src/maverick/dsl/visualization/mermaid.py
- [ ] T056 [US2] Implement generate() with TD/LR direction support in src/maverick/dsl/visualization/mermaid.py

### ASCII Generator

- [ ] T057 [US2] Create ASCIIGenerator class in src/maverick/dsl/visualization/ascii.py
- [ ] T058 [US2] Implement box drawing with configurable width in src/maverick/dsl/visualization/ascii.py
- [ ] T059 [US2] Implement step rendering with type annotations in src/maverick/dsl/visualization/ascii.py
- [ ] T060 [US2] Implement arrow and connector rendering in src/maverick/dsl/visualization/ascii.py
- [ ] T061 [US2] Implement conditional and retry annotation rendering in src/maverick/dsl/visualization/ascii.py
- [ ] T062 [US2] Implement parallel and branch step indentation in src/maverick/dsl/visualization/ascii.py
- [ ] T063 [US2] Implement workflow header and input display in src/maverick/dsl/visualization/ascii.py

### Workflow Methods

- [ ] T064 [US2] Add to_mermaid() method to WorkflowDefinition in src/maverick/dsl/builder.py
- [ ] T065 [US2] Add to_ascii() method to WorkflowDefinition in src/maverick/dsl/builder.py

**Checkpoint**: User Story 2 complete - workflows can be visualized as Mermaid or ASCII diagrams

---

## Phase 5: User Story 3 - Manage workflows from the CLI (Priority: P3)

**Goal**: Enable users to list, validate, visualize, and run workflows from the command line

**Independent Test**: Run CLI commands to validate, show, visualize, and execute a workflow defined in a YAML file

### Tests for CLI Commands (TDD - write FIRST)

- [ ] T066a [US3] Write failing tests for workflow command group in tests/unit/cli/test_workflow_commands.py
- [ ] T066b [US3] Write failing tests for list/show commands in tests/unit/cli/test_workflow_commands.py
- [ ] T066c [US3] Write failing tests for validate/viz commands in tests/unit/cli/test_workflow_commands.py
- [ ] T066d [US3] Write failing tests for run command in tests/unit/cli/test_workflow_commands.py

### CLI Command Group

- [ ] T066 [US3] Create workflow command group in src/maverick/main.py
- [ ] T067 [US3] Add global --registry and --lenient options to workflow group in src/maverick/main.py

### List Command (FR-024)

- [ ] T068 [US3] Implement workflow list command in src/maverick/main.py
- [ ] T069 [US3] Add --format option (table, json, yaml) to list command in src/maverick/main.py

### Show Command (FR-025)

- [ ] T070 [US3] Implement workflow show command with NAME argument in src/maverick/main.py
- [ ] T071 [US3] Display workflow metadata, inputs, and steps in show command in src/maverick/main.py

### Validate Command (FR-026)

- [ ] T072 [US3] Implement workflow validate command with FILE argument in src/maverick/main.py
- [ ] T073 [US3] Display validation results with actionable error messages in src/maverick/main.py
- [ ] T074 [US3] Add --strict/--no-strict option to validate command in src/maverick/main.py

### Viz Command (FR-027)

- [ ] T075 [US3] Implement workflow viz command with NAME_OR_FILE argument in src/maverick/main.py
- [ ] T076 [US3] Add --format (ascii, mermaid) option to viz command in src/maverick/main.py
- [ ] T077 [US3] Add --output option to write diagram to file in src/maverick/main.py
- [ ] T078 [US3] Add --direction option (TD, LR) for Mermaid output in src/maverick/main.py

### Run Command (FR-028)

- [ ] T079 [US3] Implement workflow run command with NAME_OR_FILE argument in src/maverick/main.py
- [ ] T080 [US3] Implement -i/--input KEY=VALUE parsing for inputs in src/maverick/main.py
- [ ] T081 [US3] Implement --input-file option for JSON/YAML input files in src/maverick/main.py
- [ ] T082 [US3] Implement --dry-run option to show execution plan in src/maverick/main.py
- [ ] T083 [US3] Integrate workflow execution with WorkflowEngine in src/maverick/main.py
- [ ] T084 [US3] Display per-step progress and results during execution in src/maverick/main.py
- [ ] T085 [US3] Add --no-tui option for streaming output mode in src/maverick/main.py

**Checkpoint**: User Story 3 complete - CLI commands fully functional for workflow management

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

### Performance Validation

- [ ] T086 Validate parse_workflow performance (<2s for 100 steps) in tests/integration/dsl/test_workflow_roundtrip.py
- [ ] T087 Validate visualization performance (<1s for 50 steps) in tests/integration/dsl/test_workflow_roundtrip.py

### Editor Interface (FR-029)

- [ ] T088 [P] Create WorkflowEditorInterface protocol in src/maverick/dsl/serialization/editor.py
- [ ] T089 [P] Create EditorStepView and PropertySchema dataclasses in src/maverick/dsl/serialization/editor.py
- [ ] T090 [P] Create editor event types (WorkflowLoadedEvent, StepAddedEvent, etc.) in src/maverick/dsl/serialization/editor.py

### Module Exports

- [ ] T091 Export public APIs from src/maverick/dsl/expressions/__init__.py
- [ ] T092 [P] Export public APIs from src/maverick/dsl/serialization/__init__.py
- [ ] T093 [P] Export public APIs from src/maverick/dsl/visualization/__init__.py

### Quickstart Validation

- [ ] T094 Run and validate all quickstart.md examples work correctly

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion
  - User stories can proceed in priority order (P1 → P2 → P3)
  - Some independence: P2 (visualization) only needs WorkflowDefinition, not full parsing
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - Core serialization
- **User Story 2 (P2)**: Can start after Phase 2; requires WorkflowDefinition from US1
- **User Story 3 (P3)**: Requires US1 (serialization) and US2 (visualization) for full CLI

### Within Each User Story

- Schema models before parser/evaluator
- Parser before writer (for testing round-trip)
- Graph builder before generators
- All core logic before CLI integration

### Parallel Opportunities

- T002/T003: Module structures can be created in parallel
- T005/T006: Error types can be created in parallel
- T026/T027/T028/T029: Individual registries can be created in parallel
- T051-T056 and T057-T063: Mermaid and ASCII generators can be developed in parallel
- T088/T089/T090 and T091/T092/T093: Editor interface and module exports in parallel

---

## Parallel Example: User Story 1 (Expression & Registry)

```bash
# Launch registry implementations together (after T025):
Task: "Create ActionRegistry with decorator registration in src/maverick/dsl/serialization/registry.py"
Task: "Create GeneratorRegistry in src/maverick/dsl/serialization/registry.py"
Task: "Create ContextBuilderRegistry in src/maverick/dsl/serialization/registry.py"
Task: "Create WorkflowRegistry in src/maverick/dsl/serialization/registry.py"
```

---

## Parallel Example: User Story 2 (Visualization)

```bash
# Launch Mermaid and ASCII generators in parallel (after T050):
Task: "Create MermaidGenerator class in src/maverick/dsl/visualization/mermaid.py"
Task: "Create ASCIIGenerator class in src/maverick/dsl/visualization/ascii.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Define workflows as files)
4. **STOP and VALIDATE**: Test round-trip serialization independently
5. Workflows can now be defined in YAML and executed

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test round-trip → YAML workflows work (MVP!)
3. Add User Story 2 → Test visualizations → Diagrams generated
4. Add User Story 3 → Test CLI → Full user interface complete
5. Each story adds value without breaking previous stories

### Suggested MVP Scope

**User Story 1** is the MVP:
- 39 tasks (T001-T044, minus foundational)
- Enables file-based workflow definitions
- Supports round-trip serialization
- Provides expression evaluation at runtime
- Component registries for reference resolution

---

## Summary

| Phase | Task Count | Description |
|-------|------------|-------------|
| Phase 1: Setup | 4 | Module structure, dependencies |
| Phase 2: Foundational | 16 | Error types, schema models, foundational tests |
| Phase 3: User Story 1 | 40 | Serialization, expressions, registries (with TDD tests) |
| Phase 4: User Story 2 | 24 | Visualization (Mermaid, ASCII) with tests |
| Phase 5: User Story 3 | 24 | CLI commands with tests |
| Phase 6: Polish | 9 | Performance, editor interface, exports |

**Total**: 117 tasks (94 implementation + 23 test tasks)
- **User Story 1 (P1)**: 40 tasks (28 impl + 12 tests)
- **User Story 2 (P2)**: 24 tasks (21 impl + 3 tests)
- **User Story 3 (P3)**: 24 tasks (20 impl + 4 tests)
- **Foundational tests**: 4 tasks
- **Parallel opportunities**: 21 tasks marked [P]
- **Independent test criteria per story**: Yes (defined in phase headers)
- **TDD Compliance**: ✅ Test tasks precede implementation tasks per Constitution V

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
