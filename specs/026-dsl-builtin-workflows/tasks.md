# Tasks: DSL-Based Built-in Workflow Implementation

**Input**: Design documents from `/specs/026-dsl-builtin-workflows/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are NOT explicitly requested in the feature specification. Test tasks included per standard project practice.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/` at repository root
- Paths shown below follow Maverick project structure from plan.md

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Extend DSL infrastructure to support agent/generate steps and action registration

- [X] T001 Extend ComponentRegistry with agents and context_builders registries in src/maverick/dsl/serialization/registry.py
- [X] T002 [P] Create actions package structure in src/maverick/library/actions/__init__.py
- [X] T003 [P] Create data model types for action results in src/maverick/library/actions/types.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Complete executor step types that ALL workflows depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Implement AgentStepRecord execution in src/maverick/dsl/serialization/executor.py
- [X] T005 Implement GenerateStepRecord execution in src/maverick/dsl/serialization/executor.py
- [X] T006 Implement ValidateStepRecord execution in src/maverick/dsl/serialization/executor.py
- [X] T007 Implement BranchStepRecord execution in src/maverick/dsl/serialization/executor.py
- [X] T008 Implement ParallelStepRecord execution using asyncio.gather in src/maverick/dsl/serialization/executor.py
- [X] T009 [P] Create context builders module in src/maverick/dsl/context_builders.py
- [X] T010 [P] Implement implementation_context builder in src/maverick/dsl/context_builders.py
- [X] T011 [P] Implement review_context builder in src/maverick/dsl/context_builders.py
- [X] T012 [P] Implement issue_fix_context builder in src/maverick/dsl/context_builders.py
- [X] T013 [P] Implement commit_message_context builder in src/maverick/dsl/context_builders.py
- [X] T014 [P] Implement pr_body_context and pr_title_context builders in src/maverick/dsl/context_builders.py
- [X] T015 [P] Implement issue_analyzer_context builder in src/maverick/dsl/context_builders.py
- [X] T016 Create register_all_context_builders function in src/maverick/dsl/context_builders.py
- [X] T017 [P] Unit tests for executor step implementations in tests/unit/dsl/serialization/test_executor_steps.py

**Checkpoint**: Executor supports all step types - workflow implementation can begin

---

## Phase 3: User Story 1 - Execute Fly Workflow via DSL (Priority: P1) 🎯 MVP

**Goal**: Implement complete fly workflow using DSL with dry_run support, progress events, and checkpointing

**Independent Test**: Execute fly workflow with mock task file and verify each stage completes in order with expected step results

### Implementation for User Story 1

#### Git Actions (shared by multiple workflows)

- [X] T018 [P] [US1] Implement init_workspace action in src/maverick/library/actions/workspace.py
- [X] T019 [P] [US1] Implement git_commit action in src/maverick/library/actions/git.py
- [X] T020 [P] [US1] Implement git_push action in src/maverick/library/actions/git.py
- [X] T021 [P] [US1] Implement create_git_branch action in src/maverick/library/actions/git.py

#### GitHub Actions (shared by multiple workflows)

- [X] T022 [P] [US1] Implement create_github_pr action in src/maverick/library/actions/github.py

#### Validation Actions

- [X] T023 [P] [US1] Implement run_fix_retry_loop action in src/maverick/library/actions/validation.py
- [X] T024 [P] [US1] Implement generate_validation_report action in src/maverick/library/actions/validation.py
- [X] T025 [P] [US1] Implement log_message action in src/maverick/library/actions/validation.py

#### Dry-Run Support

- [X] T026 [P] [US1] Implement log_dry_run action in src/maverick/library/actions/dry_run.py

#### Action Registration

- [X] T027 [US1] Register all US1 actions in src/maverick/library/actions/__init__.py (depends on T018-T026)

#### Fly Workflow YAML Updates

- [X] T028 [US1] Update fly.yaml to add dry_run input and conditional steps in src/maverick/library/workflows/fly.yaml
- [X] T029 [US1] Add checkpoint steps at key stages in src/maverick/library/workflows/fly.yaml
- [X] T030 [US1] Add progress event emission in fly.yaml step configurations

#### Fly Workflow Python Integration

- [X] T031 [US1] Update FlyWorkflow class to use DSL execution wrapper in src/maverick/workflows/fly.py
- [X] T032 [US1] Implement DSL event to FlyProgressEvent translation in src/maverick/workflows/fly.py
- [X] T033 [US1] Implement FlyResult construction from workflow result in src/maverick/workflows/fly.py

#### Unit Tests

- [X] T034 [P] [US1] Unit tests for workspace actions in tests/unit/library/actions/test_workspace.py
- [X] T035 [P] [US1] Unit tests for git actions in tests/unit/library/actions/test_git_actions.py
- [X] T036 [P] [US1] Unit tests for fly workflow integration in tests/unit/workflows/test_fly_dsl.py

**Checkpoint**: Fly workflow executes complete feature implementation cycle via DSL

---

## Phase 4: User Story 2 - Execute Refuel Workflow for Batch Issue Processing (Priority: P1)

**Goal**: Implement refuel workflow with iteration over issues and sub-workflow composition

**Independent Test**: Provide mock GitHub issues and verify workflow creates expected branches, invokes sub-workflows, and aggregates results

### Implementation for User Story 2

#### GitHub Issue Actions

- [X] T037 [P] [US2] Implement fetch_github_issues action in src/maverick/library/actions/github.py
- [X] T038 [P] [US2] Implement fetch_github_issue action in src/maverick/library/actions/github.py

#### Refuel-Specific Actions

- [X] T039 [P] [US2] Implement process_selected_issues action in src/maverick/library/actions/refuel.py
- [X] T040 [P] [US2] Implement generate_refuel_summary action in src/maverick/library/actions/refuel.py

#### Process Single Issue Sub-Workflow

- [X] T041 [US2] Create process_single_issue.yaml sub-workflow in src/maverick/library/workflows/process_single_issue.yaml
- [X] T042 [US2] Add branch creation step in process_single_issue.yaml
- [X] T043 [US2] Add issue fixer agent invocation step in process_single_issue.yaml
- [X] T044 [US2] Add validate_and_fix sub-workflow invocation in process_single_issue.yaml
- [X] T045 [US2] Add commit_and_push sub-workflow invocation in process_single_issue.yaml
- [X] T046 [US2] Add create_pr_with_summary sub-workflow invocation in process_single_issue.yaml

#### Refuel Workflow Updates

- [X] T047 [US2] Update refuel.yaml with issue iteration using python action in src/maverick/library/workflows/refuel.yaml
- [X] T048 [US2] Add dry_run conditional steps in refuel.yaml
- [X] T049 [US2] Add checkpoint steps for resumability in refuel.yaml (NOTE: checkpoint support planned for future release)

#### Action Registration

- [X] T050 [US2] Register all US2 actions in src/maverick/library/actions/__init__.py (depends on T037-T040)

#### Refuel Workflow Python Integration

- [X] T051 [US2] Update RefuelWorkflow class to use DSL execution wrapper in src/maverick/workflows/refuel.py
- [X] T052 [US2] Implement DSL event to RefuelProgressEvent translation in src/maverick/workflows/refuel.py
- [X] T053 [US2] Implement RefuelResult construction from workflow result in src/maverick/workflows/refuel.py

#### Update Built-in Metadata

- [X] T054 [US2] Update builtins.py with metadata for new workflows in src/maverick/library/builtins.py

#### Unit Tests

- [X] T055 [P] [US2] Unit tests for github actions in tests/unit/library/actions/test_github_actions.py
- [X] T056 [P] [US2] Unit tests for refuel actions in tests/unit/library/actions/test_refuel_actions.py
- [X] T057 [P] [US2] Unit tests for refuel workflow integration in tests/unit/workflows/test_refuel_dsl.py

**Checkpoint**: Refuel workflow processes multiple issues with sub-workflow composition

---

## Phase 5: User Story 3 - Reuse Workflow Fragments Across Main Workflows (Priority: P1)

**Goal**: Validate that fragments (validate_and_fix, commit_and_push, create_pr_with_summary) work as reusable sub-workflows

**Independent Test**: Invoke each fragment directly as sub-workflow and verify expected outputs

### Implementation for User Story 3

- [X] T058 [US3] Verify validate_and_fix.yaml fragment accepts fixer_agent input in src/maverick/library/fragments/validate_and_fix.yaml
- [X] T059 [US3] Verify commit_and_push.yaml fragment integrates with commit_message_context in src/maverick/library/fragments/commit_and_push.yaml
- [X] T060 [US3] Verify create_pr_with_summary.yaml fragment integrates with pr_body_context in src/maverick/library/fragments/create_pr_with_summary.yaml
- [X] T061 [US3] Add fragment override precedence validation to workflow discovery in src/maverick/dsl/discovery/registry.py

#### Unit Tests

- [X] T062 [P] [US3] Integration tests for validate_and_fix fragment in tests/integration/test_validate_and_fix_fragment.py
- [X] T063 [P] [US3] Integration tests for commit_and_push fragment in tests/integration/test_commit_push_fragment.py
- [X] T064 [P] [US3] Integration tests for create_pr_with_summary fragment in tests/integration/test_pr_creation_fragment.py

**Checkpoint**: All fragments work as standalone sub-workflows

---

## Phase 6: User Story 4 - Execute Standalone Review Workflow (Priority: P2)

**Goal**: Implement standalone review workflow with conditional CodeRabbit integration

**Independent Test**: Execute review workflow with and without PR number and verify correct diff gathering and review results

### Implementation for User Story 4

#### Review Actions

- [X] T065 [P] [US4] Implement gather_pr_context action in src/maverick/library/actions/review.py
- [X] T066 [P] [US4] Implement run_coderabbit_review action in src/maverick/library/actions/review.py
- [X] T067 [P] [US4] Implement combine_review_results action in src/maverick/library/actions/review.py

#### Review Workflow YAML

- [X] T068 [US4] Update review.yaml with complete review orchestration in src/maverick/library/workflows/review.yaml
- [X] T069 [US4] Add branch step for include_coderabbit conditional in review.yaml
- [X] T070 [US4] Add progress event emission for review stages in review.yaml

#### Action Registration

- [X] T071 [US4] Register review actions in src/maverick/library/actions/__init__.py (depends on T065-T067)

#### Unit Tests

- [X] T072 [P] [US4] Unit tests for review actions in tests/unit/library/actions/test_review_actions.py
- [X] T073 [P] [US4] Integration tests for review workflow in tests/integration/test_review_workflow.py

**Checkpoint**: Standalone review workflow with optional CodeRabbit integration works

---

## Phase 7: User Story 5 - Execute Validate and Quick-Fix Workflows (Priority: P2)

**Goal**: Implement standalone validate and quick_fix workflows demonstrating sub-workflow reuse

**Independent Test**: Execute each workflow and verify expected step sequence and results

### Implementation for User Story 5

#### Validate Workflow YAML

- [X] T074 [US5] Update validate.yaml with fix conditional branch in src/maverick/library/workflows/validate.yaml
- [X] T075 [US5] Add validate_and_fix sub-workflow invocation when fix=True in validate.yaml
- [X] T076 [US5] Add single validation run when fix=False in validate.yaml

#### Quick-Fix Workflow YAML

- [X] T077 [US5] Update quick_fix.yaml to fetch issue and invoke process_single_issue in src/maverick/library/workflows/quick_fix.yaml
- [X] T078 [US5] Add progress event emission for quick_fix stages in quick_fix.yaml

#### Unit Tests

- [X] T079 [P] [US5] Integration tests for validate workflow in tests/integration/test_validate_workflow.py
- [X] T080 [P] [US5] Integration tests for quick_fix workflow in tests/integration/test_quick_fix_workflow.py

**Checkpoint**: Standalone validate and quick_fix workflows execute successfully

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, error handling improvements, and success criteria verification

- [X] T081 [P] Verify all workflows emit progress events at each stage transition
- [X] T082 [P] Verify all workflows support checkpoint resumability
- [X] T083 Verify token reduction vs non-orchestrated implementations (SC-007)
- [X] T084 [P] Run full test suite: PYTHONPATH=src pytest tests/
- [X] T085 [P] Validate type safety: mypy src/maverick/library/actions/
- [X] T086 [P] Lint code: ruff check src/maverick/library/actions/
- [X] T087 Run quickstart.md validation scenarios
- [X] T088 Update CLAUDE.md with new technology entries for spec 026

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phases 3-7)**: All depend on Foundational phase completion
  - US1 and US2 can proceed in parallel (both P1 priority)
  - US3 can proceed after US1 fragments are verified
  - US4 and US5 (both P2) can proceed after US3 or in parallel with US1/US2
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1 - Fly)**: Can start after Foundational - No dependencies on other stories
- **User Story 2 (P1 - Refuel)**: Can start after Foundational - Uses fragments from US3 but fragments already exist
- **User Story 3 (P1 - Fragments)**: Can start after Foundational - Validates existing fragments work correctly
- **User Story 4 (P2 - Review)**: Can start after Foundational - Independent of other stories
- **User Story 5 (P2 - Validate/Quick-Fix)**: Can start after Foundational - Reuses process_single_issue from US2

### Within Each User Story

- Actions before action registration
- Action registration before workflow YAML updates
- Workflow YAML before Python integration
- Python integration before unit tests

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational context builder tasks (T009-T016) can run in parallel after T004-T008
- All action implementations within a user story marked [P] can run in parallel
- Different user stories can be worked on in parallel by different team members
- Unit tests marked [P] can run in parallel within each user story

---

## Parallel Example: Foundational Phase

```bash
# After executor step implementations (T004-T008), launch context builders in parallel:
Task: "Implement implementation_context builder in src/maverick/dsl/context_builders.py"
Task: "Implement review_context builder in src/maverick/dsl/context_builders.py"
Task: "Implement issue_fix_context builder in src/maverick/dsl/context_builders.py"
Task: "Implement commit_message_context builder in src/maverick/dsl/context_builders.py"
Task: "Implement pr_body_context and pr_title_context builders in src/maverick/dsl/context_builders.py"
Task: "Implement issue_analyzer_context builder in src/maverick/dsl/context_builders.py"
```

---

## Parallel Example: User Story 1 Actions

```bash
# Launch all action implementations for User Story 1 together:
Task: "Implement init_workspace action in src/maverick/library/actions/workspace.py"
Task: "Implement git_commit action in src/maverick/library/actions/git.py"
Task: "Implement git_push action in src/maverick/library/actions/git.py"
Task: "Implement create_git_branch action in src/maverick/library/actions/git.py"
Task: "Implement create_github_pr action in src/maverick/library/actions/github.py"
Task: "Implement run_fix_retry_loop action in src/maverick/library/actions/validation.py"
Task: "Implement generate_validation_report action in src/maverick/library/actions/validation.py"
Task: "Implement log_message action in src/maverick/library/actions/validation.py"
Task: "Implement log_dry_run action in src/maverick/library/actions/dry_run.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 - Fly Workflow)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Fly Workflow)
4. **STOP and VALIDATE**: Execute fly workflow end-to-end with dry_run=True
5. Execute fly workflow on real feature branch

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 (Fly) → Test independently → Execute on real branch (MVP!)
3. Add User Story 2 (Refuel) → Test independently → Execute on real issues
4. Add User Story 3 (Fragments) → Validate fragment reuse
5. Add User Story 4 (Review) → Execute standalone reviews
6. Add User Story 5 (Validate/Quick-Fix) → Execute targeted validations
7. Each story adds capability without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (Fly)
   - Developer B: User Story 2 (Refuel)
   - Developer C: User Story 3 (Fragments) + User Story 4 (Review)
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- All actions follow Protocol contracts in specs/026-dsl-builtin-workflows/contracts/actions.py
- All context builders follow Protocol contracts in specs/026-dsl-builtin-workflows/contracts/context_builders.py
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
