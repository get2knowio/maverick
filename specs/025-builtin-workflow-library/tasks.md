# Tasks: Built-in Workflow Library

**Input**: Design documents from `/specs/025-builtin-workflow-library/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/` at repository root
- Project structure from plan.md:
  - Discovery: `src/maverick/dsl/discovery/`
  - Library: `src/maverick/library/`
  - Templates: `src/maverick/library/templates/`
  - CLI: `src/maverick/cli/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and module structure

- [X] T001 Create discovery module structure in src/maverick/dsl/discovery/__init__.py
- [X] T002 [P] Create library module structure in src/maverick/library/__init__.py
- [X] T003 [P] Create workflows submodule in src/maverick/library/workflows/__init__.py
- [X] T004 [P] Create fragments submodule in src/maverick/library/fragments/__init__.py
- [X] T005 [P] Create templates submodule in src/maverick/library/templates/__init__.py
- [X] T006 Add jinja2 dependency to pyproject.toml

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models and base classes that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [X] T007 Implement WorkflowSource enum in src/maverick/dsl/discovery/models.py
- [X] T008 Implement WorkflowMetadata dataclass in src/maverick/dsl/discovery/models.py
- [X] T009 Implement DiscoveredWorkflow dataclass in src/maverick/dsl/discovery/models.py
- [X] T010 [P] Implement SkippedWorkflow dataclass in src/maverick/dsl/discovery/models.py
- [X] T011 [P] Implement WorkflowConflict dataclass in src/maverick/dsl/discovery/models.py
- [X] T012 Implement DiscoveryResult dataclass with workflow_names, fragment_names, get_workflow, get_fragment in src/maverick/dsl/discovery/models.py
- [X] T013 Implement WorkflowDiscoveryError and WorkflowConflictError exceptions in src/maverick/dsl/discovery/exceptions.py
- [X] T014 [P] Implement ScaffoldError, InvalidNameError, OutputExistsError, TemplateRenderError in src/maverick/library/scaffold.py
- [X] T015 [P] Implement TemplateType and TemplateFormat enums in src/maverick/library/scaffold.py
- [X] T016 [P] Implement TemplateInfo, ScaffoldRequest, and ScaffoldResult dataclasses in src/maverick/library/scaffold.py
- [X] T017 [P] Implement BuiltinWorkflowInfo and BuiltinFragmentInfo dataclasses in src/maverick/library/builtins.py
- [X] T018 Export all models from src/maverick/dsl/discovery/__init__.py
- [X] T019 Export all models from src/maverick/library/__init__.py
- [X] T019a Verify existing SubWorkflowStep (from spec 022/023) resolves fragment names from DiscoveryResult; if not supported, extend WorkflowFileExecutor to lookup fragments by name during execution

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Use built-in workflows out of the box (Priority: P1) MVP

**Goal**: Users can run built-in workflows (fly, refuel, review, validate, quick_fix) with documented inputs

**Independent Test**: List available workflows, show details for one workflow, validate each built-in workflow declares required inputs and step sequence

### Implementation for User Story 1

- [X] T020 [US1] Create fly.yaml workflow definition in src/maverick/library/workflows/fly.yaml with init, implement, validate/fix loop, commit, review, create_pr steps; include header comments describing purpose, all inputs with types/defaults, step intent, and customization guidance per FR-003
- [X] T021 [P] [US1] Create refuel.yaml workflow definition in src/maverick/library/workflows/refuel.yaml with fetch_issues, branch, fix, validate, commit, pr steps
- [X] T022 [P] [US1] Create review.yaml workflow definition in src/maverick/library/workflows/review.yaml with gather_context, run_coderabbit, agent_review, combine_results steps
- [X] T023 [P] [US1] Create validate.yaml workflow definition in src/maverick/library/workflows/validate.yaml with run_validation, fix loop, report steps
- [X] T024 [P] [US1] Create quick_fix.yaml workflow definition in src/maverick/library/workflows/quick_fix.yaml with fetch_issue, branch, fix, validate, commit, pr steps
- [X] T025 [US1] Create validate_and_fix.yaml fragment in src/maverick/library/fragments/validate_and_fix.yaml with stages, max_attempts, fixer_agent inputs
- [X] T026 [P] [US1] Create commit_and_push.yaml fragment in src/maverick/library/fragments/commit_and_push.yaml with message, push inputs
- [X] T027 [P] [US1] Create create_pr_with_summary.yaml fragment in src/maverick/library/fragments/create_pr_with_summary.yaml with base_branch, draft, title inputs
- [X] T027a [US1] Verify all 5 workflow YAML files and 3 fragment YAML files include inline documentation: purpose header, input descriptions, step-by-step comments, and customization guidance per FR-003
- [X] T028 [US1] Implement BuiltinLibrary class in src/maverick/library/builtins.py with list_workflows, list_fragments, get_workflow, get_fragment, get_workflow_path, get_fragment_path, has_workflow, has_fragment
- [X] T029 [US1] Implement create_builtin_library factory function in src/maverick/library/builtins.py
- [X] T030 [US1] Add BUILTIN_WORKFLOWS and BUILTIN_FRAGMENTS constants to src/maverick/library/builtins.py
- [X] T031 [US1] Add FLY_WORKFLOW_INFO, REFUEL_WORKFLOW_INFO, REVIEW_WORKFLOW_INFO, VALIDATE_WORKFLOW_INFO, QUICK_FIX_WORKFLOW_INFO to src/maverick/library/builtins.py
- [X] T032 [US1] Add VALIDATE_AND_FIX_FRAGMENT_INFO, COMMIT_AND_PUSH_FRAGMENT_INFO, CREATE_PR_WITH_SUMMARY_FRAGMENT_INFO to src/maverick/library/builtins.py
- [X] T033 [US1] Write unit tests for BuiltinLibrary in tests/unit/library/test_builtins.py

**Checkpoint**: User Story 1 complete - built-in workflows discoverable and accessible

---

## Phase 4: User Story 2 - Override built-ins with user/project workflows (Priority: P2)

**Goal**: Users can define workflows in user or project locations that override built-in workflows of the same name

**Independent Test**: Define a workflow named fly in project scope, confirm it takes precedence over built-in fly

### Implementation for User Story 2

- [X] T034 [US2] Implement WorkflowLocator class in src/maverick/dsl/discovery/locator.py with scan method for finding workflow YAML files
- [X] T035 [US2] Implement WorkflowLoader class in src/maverick/dsl/discovery/loader.py with load_metadata and load_full methods
- [X] T036 [US2] Implement DefaultWorkflowDiscovery class in src/maverick/dsl/discovery/registry.py with discover, get_builtin_path, get_user_path, get_project_path methods
- [X] T037 [US2] Implement precedence logic in DefaultWorkflowDiscovery (project > user > builtin)
- [X] T038 [US2] Implement conflict detection for same-name workflows at same precedence level
- [X] T039 [US2] Implement skip-and-continue logic for invalid/unreadable workflow files
- [X] T040 [US2] Implement create_discovery factory function in src/maverick/dsl/discovery/__init__.py
- [X] T041 [US2] Write unit tests for WorkflowLocator in tests/unit/dsl/discovery/test_locator.py
- [X] T042 [P] [US2] Write unit tests for WorkflowLoader in tests/unit/dsl/discovery/test_loader.py
- [X] T043 [US2] Write unit tests for DefaultWorkflowDiscovery in tests/unit/dsl/discovery/test_registry.py
- [X] T044 [US2] Write integration test for override precedence in tests/integration/test_workflow_discovery.py

**Checkpoint**: User Story 2 complete - override precedence working

---

## Phase 5: User Story 3 - Scaffold new workflows from templates (Priority: P3)

**Goal**: Workflow authors can scaffold new workflows using templates (basic, full, parallel)

**Independent Test**: Generate workflows from each template, verify output file created with expected structure and documentation

### Implementation for User Story 3

- [X] T045 [US3] Create basic.yaml.j2 template in src/maverick/library/templates/basic.yaml.j2 with linear workflow structure
- [X] T046 [P] [US3] Create full.yaml.j2 template in src/maverick/library/templates/full.yaml.j2 with validation, review, PR patterns
- [X] T047 [P] [US3] Create parallel.yaml.j2 template in src/maverick/library/templates/parallel.yaml.j2 demonstrating parallel step interface
- [X] T048 [P] [US3] Create basic.py.j2 template in src/maverick/library/templates/basic.py.j2 for Python variant
- [X] T049 [P] [US3] Create full.py.j2 template in src/maverick/library/templates/full.py.j2 for Python variant
- [X] T050 [P] [US3] Create parallel.py.j2 template in src/maverick/library/templates/parallel.py.j2 for Python variant
- [X] T052 [US3] Implement DefaultTemplateScaffolder class in src/maverick/library/scaffold.py with list_templates, preview, scaffold, get_template_path methods
- [X] T053 [US3] Implement validate_workflow_name function in src/maverick/library/scaffold.py
- [X] T054 [US3] Implement get_default_output_dir function in src/maverick/library/scaffold.py
- [X] T055 [US3] Implement create_scaffolder factory function in src/maverick/library/scaffold.py
- [X] T056 [US3] Extend workflow CLI group with new subcommand in src/maverick/cli/workflow.py
- [X] T057 [US3] Implement maverick workflow new command with --template, --format, --output-dir options
- [X] T058 [US3] Write unit tests for DefaultTemplateScaffolder in tests/unit/library/test_templates.py
- [X] T059 [US3] Write unit tests for validate_workflow_name in tests/unit/library/test_scaffold.py
- [X] T060 [US3] Write integration test for maverick workflow new command in tests/integration/test_workflow_new.py

**Checkpoint**: User Story 3 complete - template scaffolding working

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T061 [P] Verify all YAML workflow files parse correctly with existing WorkflowFile schema
- [X] T062 Integrate WorkflowDiscovery with application startup: call discover() when CLI/TUI initializes, populate workflow registry, and use DiscoveryResult for workflow list/show/run commands per FR-014
- [X] T063 Add source information display to maverick workflow show output
- [X] T064 [P] Verify discovery performance < 500ms for test suite with 100 workflow files
- [X] T065 Run quickstart.md validation scenarios manually

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational completion
- **User Story 2 (Phase 4)**: Depends on Foundational completion, benefits from US1 workflows existing
- **User Story 3 (Phase 5)**: Depends on Foundational completion
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Benefits from US1 workflows but not required
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - Independent of US1 and US2

### Within Each User Story

- Models/dataclasses before services
- Services before CLI commands
- Core implementation before tests
- YAML workflow definitions are independent within a story

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel
- Built-in workflow YAML files (T021-T024) can be created in parallel
- Fragment YAML files (T026-T027) can be created in parallel
- Template files (T046-T050) can be created in parallel
- Test files for different modules can be written in parallel

---

## Parallel Example: User Story 1

```bash
# Launch all workflow YAML files together:
Task: "Create refuel.yaml workflow definition in src/maverick/library/workflows/refuel.yaml"
Task: "Create review.yaml workflow definition in src/maverick/library/workflows/review.yaml"
Task: "Create validate.yaml workflow definition in src/maverick/library/workflows/validate.yaml"
Task: "Create quick_fix.yaml workflow definition in src/maverick/library/workflows/quick_fix.yaml"

# Launch all fragment YAML files together:
Task: "Create commit_and_push.yaml fragment in src/maverick/library/fragments/commit_and_push.yaml"
Task: "Create create_pr_with_summary.yaml fragment in src/maverick/library/fragments/create_pr_with_summary.yaml"
```

---

## Parallel Example: User Story 3

```bash
# Launch all template files together:
Task: "Create full.yaml.j2 template in src/maverick/library/templates/full.yaml.j2"
Task: "Create parallel.yaml.j2 template in src/maverick/library/templates/parallel.yaml.j2"
Task: "Create basic.py.j2 template in src/maverick/library/templates/basic.py.j2"
Task: "Create full.py.j2 template in src/maverick/library/templates/full.py.j2"
Task: "Create parallel.py.j2 template in src/maverick/library/templates/parallel.py.j2"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently with `maverick workflow list` and `maverick workflow show fly`
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo (override capability)
4. Add User Story 3 → Test independently → Deploy/Demo (scaffolding)
5. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (built-in workflows)
   - Developer B: User Story 2 (discovery/override)
   - Developer C: User Story 3 (templates/scaffolding)
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
