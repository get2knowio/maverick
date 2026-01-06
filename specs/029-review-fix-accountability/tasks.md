# Tasks: Review-Fix Accountability Loop

**Input**: Design documents from `/specs/029-review-fix-accountability/`
**Prerequisites**: plan.md (required), spec.md (required)

## Format: `[ID] [P?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)

---

## Phase 1: Data Models

**Purpose**: Create core data structures for tracking findings through the fix loop.

- [x] T001 Create `src/maverick/models/review_registry.py` with Severity, FindingStatus, FindingCategory enums
- [x] T002 [P] Add ReviewFinding frozen dataclass to review_registry.py
- [x] T003 [P] Add FixAttempt dataclass to review_registry.py
- [x] T004 Add TrackedFinding dataclass with status tracking and add_attempt method
- [x] T005 Add IssueRegistry dataclass with get_actionable(), get_for_issues(), should_continue properties
- [x] T006 Add to_dict() and from_dict() serialization methods to IssueRegistry for checkpoint support
- [x] T007 Create `src/maverick/models/fixer_io.py` with FixerInputItem, FixerInput frozen dataclasses
- [x] T008 [P] Add FixerOutputItem, FixerOutput dataclasses to fixer_io.py
- [x] T009 Add validate_against_input() method to FixerOutput
- [x] T010 Add TechDebtIssueResult dataclass to `src/maverick/library/actions/types.py`
- [x] T011 Create unit tests in `tests/unit/models/test_review_registry.py`
- [x] T012 [P] Create unit tests in `tests/unit/models/test_fixer_io.py`

**Checkpoint**: All data models defined with serialization and validation

---

## Phase 2: Registry Actions

**Purpose**: Implement workflow actions for registry lifecycle management.

- [x] T013 Create `src/maverick/library/actions/review_registry.py` with module structure
- [x] T014 Implement create_issue_registry() action with finding merge and deduplication
- [x] T015 Implement prepare_fixer_input() action to filter and format actionable findings
- [x] T016 Implement update_issue_registry() action to apply fixer results with validation
- [x] T017 Implement check_fix_loop_exit() action with exit condition logic
- [x] T018 Implement create_tech_debt_issues() action with GitHub issue creation via gh CLI
- [x] T019 Implement detect_deleted_files() action to auto-block findings for deleted files in `src/maverick/library/actions/review_registry.py`
- [x] T020 Register all actions in `src/maverick/library/actions/__init__.py`
- [x] T021 Create unit tests in `tests/unit/library/actions/test_review_registry_actions.py`

**Checkpoint**: All registry actions implemented and unit tested

---

## Phase 3: Reviewer Structured Output

**Purpose**: Modify reviewers to output machine-parseable structured findings.

- [x] T022 Create `src/maverick/agents/prompts/reviewer_output.py` with REVIEWER_OUTPUT_SCHEMA constant
- [x] T023 Modify spec_reviewer system prompt to include structured output requirements
- [x] T024 [P] Modify tech_reviewer system prompt to include structured output requirements
- [x] T025 Add _parse_findings() helper to extract JSON findings from reviewer response
- [x] T026 Add _validate_findings() helper to ensure required fields present
- [x] T027 Update spec_reviewer.review() to return list[dict] of structured findings
- [x] T028 [P] Update tech_reviewer.review() to return list[dict] of structured findings
- [x] T029 Create unit tests for reviewer structured output parsing

**Checkpoint**: Both reviewers output structured findings that can be tracked

---

## Phase 4: Fixer Accountability

**Purpose**: Implement accountability-focused fixer agent that must report on every issue.

- [x] T030 Create `src/maverick/agents/prompts/review_fixer.py` with REVIEW_FIXER_SYSTEM_PROMPT
- [x] T031 Include invalid justification patterns in system prompt (pre-existing, out of scope, etc.)
- [x] T032 Include valid blocked reasons in system prompt (external deps, human decision, etc.)
- [x] T033 Include warning about deferred items being re-sent
- [x] T034 Update ReviewFixerAgent to use new accountability system prompt
- [x] T035 Implement _build_prompt() to format all issues with previous attempt history
- [x] T036 Implement _parse_output() to extract JSON response from fixer
- [x] T037 Implement _fill_missing() to auto-defer issues with no status
- [x] T038 Add review_fixer_context() to `src/maverick/dsl/context_builders.py`
- [x] T039 Register review_fixer_context in context builder registry
- [x] T040 Create unit tests for fixer prompt building and output parsing

**Checkpoint**: Fixer agent enforces accountability with structured I/O

---

## Phase 5: Workflow Integration

**Purpose**: Create workflow fragment that orchestrates the full accountability loop.

- [x] T041 Create `src/maverick/library/fragments/review-and-fix-with-registry.yaml`
- [x] T042 Add gather_context step (reuse existing)
- [x] T043 Add parallel_reviews step with spec_review and tech_review
- [x] T044 Add create_registry step calling create_issue_registry action
- [x] T045 Add detect_deleted step calling detect_deleted_files action (auto-block findings for deleted files)
- [x] T046 Add fix_loop with loop construct and break_when condition
- [x] T047 Add prepare_input, run_fixer, update_registry, check_exit steps inside loop
- [x] T048 Add create_issues step calling create_tech_debt_issues action
- [x] T049 Define workflow outputs: registry, issues_created, summary
- [x] T050 Register fragment in workflow discovery
- [x] T051 Update feature.yaml to use review-and-fix-with-registry (optional flag)

**Checkpoint**: Workflow fragment complete and integrated

---

## Phase 6: Testing & Documentation

**Purpose**: Comprehensive testing and documentation.

- [x] T052 Create integration test `tests/integration/workflows/test_review_fix_accountability.py`
- [x] T053 Test: Registry correctly filters actionable items by severity and status
- [x] T054 Test: Deferred items re-queue on next iteration
- [x] T055 Test: Blocked items do not re-queue
- [x] T056 Test: Missing fixer output auto-defers with justification
- [x] T057 Test: Loop exits at max iterations
- [x] T058 Test: Loop exits when no actionable items remain
- [x] T059 Test: Issue creation includes full attempt history in body
- [x] T060 Test: Issue labels include tech-debt and severity
- [x] T061 Test: Deleted file findings are auto-blocked with system justification
- [ ] T062 Manual test: Run full workflow on real codebase, verify issues created
- [x] T063 Update CLAUDE.md with new workflow fragment documentation

**Checkpoint**: All tests passing, documentation complete

---

## Summary

| Phase | Tasks | Parallel |
|-------|-------|----------|
| Phase 1: Data Models | T001-T012 | T002/T003, T007/T008, T011/T012 |
| Phase 2: Registry Actions | T013-T021 | None (sequential dependencies) |
| Phase 3: Reviewer Output | T022-T029 | T023/T024, T027/T028 |
| Phase 4: Fixer Accountability | T030-T040 | None (sequential dependencies) |
| Phase 5: Workflow Integration | T041-T051 | None (sequential dependencies) |
| Phase 6: Testing | T052-T063 | T053-T061 can run in parallel |

**Total Tasks**: 63
**Parallelizable**: ~16 tasks

## Changes from Clarifications

The following tasks were added based on spec clarifications (Session 2025-01-05):

- **T019**: `detect_deleted_files()` action - Auto-blocks findings for deleted files
- **T045**: `detect_deleted` workflow step - Invokes the action before fix loop
- **T061**: Test for deleted file auto-blocking behavior
