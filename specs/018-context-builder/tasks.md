# Tasks: Context Builder Utilities

**Input**: Design documents from `/specs/018-context-builder/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included per constitution principle V (Test-First)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Source**: `src/maverick/utils/context.py`
- **Tests**: `tests/unit/utils/test_context.py`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Module structure and foundational utilities

- [X] T001 Create module file `src/maverick/utils/context.py` with docstring and imports
- [X] T002 [P] Create test file `tests/unit/utils/test_context.py` with imports and fixtures
- [X] T003 [P] Create `tests/unit/utils/__init__.py` if not exists
- [X] T004 Add module exports to `src/maverick/utils/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core utilities that ALL context builders depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Implement `estimate_tokens(text: str) -> int` utility in `src/maverick/utils/context.py` (FR-006: chars / 4)
- [X] T006 [P] Implement `truncate_line(line: str, max_chars: int = 2000) -> str` utility in `src/maverick/utils/context.py`
- [X] T007 [P] Implement `detect_secrets(content: str) -> list[tuple[int, str]]` utility in `src/maverick/utils/context.py` (FR-015)
- [X] T008 Implement `truncate_file(content: str, max_lines: int, around_lines: list[int] | None, context_lines: int = 10) -> str` in `src/maverick/utils/context.py` (FR-005, FR-011)
- [X] T009 [P] Implement `extract_file_paths(text: str) -> list[str]` utility in `src/maverick/utils/context.py`
- [X] T010 [P] Implement `_read_file_safely(path: Path, max_lines: int = 50000) -> tuple[str, bool]` internal helper in `src/maverick/utils/context.py`
- [X] T011 [P] Implement `_read_conventions(path: Path | None) -> str` internal helper in `src/maverick/utils/context.py`
- [X] T012 [P] Add tests for `estimate_tokens` in `tests/unit/utils/test_context.py`
- [X] T013 [P] Add tests for `truncate_line` in `tests/unit/utils/test_context.py`
- [X] T014 [P] Add tests for `detect_secrets` in `tests/unit/utils/test_context.py`
- [X] T015 Add tests for `truncate_file` in `tests/unit/utils/test_context.py`
- [X] T016 [P] Add tests for `extract_file_paths` in `tests/unit/utils/test_context.py`

**Checkpoint**: Foundation ready - all utility functions tested and working

---

## Phase 3: User Story 1 - Build Implementation Context (Priority: P1) 🎯 MVP

**Goal**: Provide implementation agents with task definitions, conventions, branch info, and recent commits

**Independent Test**: Call `build_implementation_context()` with task file and GitOperations mock, verify returned dict contains all expected keys

### Tests for User Story 1

> **NOTE: Write tests FIRST, ensure they FAIL before implementation**

- [X] T017 [P] [US1] Add test for happy path (valid task file, git operations) in `tests/unit/utils/test_context.py`
- [X] T018 [P] [US1] Add test for missing task file returns empty content with metadata in `tests/unit/utils/test_context.py`
- [X] T019 [P] [US1] Add test for large CLAUDE.md truncation with metadata in `tests/unit/utils/test_context.py`
- [X] T020 [P] [US1] Add test for secret detection logging in `tests/unit/utils/test_context.py`

### Implementation for User Story 1

- [X] T021 [US1] Implement `build_implementation_context(task_file: Path, git: GitOperations, *, conventions_path: Path | None = None) -> ContextDict` in `src/maverick/utils/context.py` (FR-001)
- [X] T022 [US1] Add metadata population logic with `truncated`, `original_lines`, `kept_lines`, `sections_affected` fields (FR-010)
- [X] T023 [US1] Add secret detection logging calls within `build_implementation_context` (FR-015)
- [X] T024 [US1] Verify all tests pass for User Story 1

**Checkpoint**: User Story 1 fully functional and testable independently

---

## Phase 4: User Story 2 - Build Review Context (Priority: P1)

**Goal**: Provide code review agents with diffs, changed file contents, and conventions

**Independent Test**: Call `build_review_context()` with GitOperations mock and base branch, verify returned dict contains diff, changed_files, stats

### Tests for User Story 2

- [X] T025 [P] [US2] Add test for happy path (diff with changed files) in `tests/unit/utils/test_context.py`
- [X] T026 [P] [US2] Add test for large files truncation (>500 lines) in `tests/unit/utils/test_context.py`
- [X] T027 [P] [US2] Add test for no changes returns empty diff with stats in `tests/unit/utils/test_context.py`
- [X] T028 [P] [US2] Add test for binary files are skipped in `tests/unit/utils/test_context.py`

### Implementation for User Story 2

- [X] T029 [US2] Implement `build_review_context(git: GitOperations, base_branch: str, *, conventions_path: Path | None = None, max_file_lines: int = 500) -> ContextDict` in `src/maverick/utils/context.py` (FR-002, FR-012)
- [X] T030 [US2] Add file content reading with truncation for files >= 500 lines (FR-012)
- [X] T031 [US2] Add binary file detection and skipping with metadata note
- [X] T032 [US2] Add stats dict population (files_changed, insertions, deletions)
- [X] T033 [US2] Verify all tests pass for User Story 2

**Checkpoint**: User Stories 1 AND 2 both work independently

---

## Phase 5: User Story 3 - Build Fix Context (Priority: P2)

**Goal**: Provide fix agents with validation errors and surrounding source code context

**Independent Test**: Call `build_fix_context()` with ValidationOutput mock and file list, verify source files show context around error lines

### Tests for User Story 3

- [X] T034 [P] [US3] Add test for happy path (errors with source context) in `tests/unit/utils/test_context.py`
- [X] T035 [P] [US3] Add test for ±10 lines context around error lines in `tests/unit/utils/test_context.py`
- [X] T036 [P] [US3] Add test for no errors returns empty errors section in `tests/unit/utils/test_context.py`
- [X] T037 [P] [US3] Add test for overlapping error regions are merged in `tests/unit/utils/test_context.py`

### Implementation for User Story 3

- [X] T038 [US3] Implement `build_fix_context(validation_output: ValidationOutput, files: list[Path], *, context_lines: int = 10) -> ContextDict` in `src/maverick/utils/context.py` (FR-003, FR-013)
- [X] T039 [US3] Add error extraction from ValidationOutput.stages[].errors
- [X] T040 [US3] Add source file truncation using `truncate_file` with around_lines from errors
- [X] T041 [US3] Add error_summary generation (e.g., "3 errors in 2 files")
- [X] T042 [US3] Verify all tests pass for User Story 3

**Checkpoint**: User Stories 1, 2, AND 3 all work independently

---

## Phase 6: User Story 4 - Build Issue Context (Priority: P2)

**Goal**: Provide issue-related agents with issue details and referenced file content

**Independent Test**: Call `build_issue_context()` with GitHubIssue mock and GitOperations, verify issue dict and related_files populated

### Tests for User Story 4

- [X] T043 [P] [US4] Add test for happy path (issue with file references) in `tests/unit/utils/test_context.py`
- [X] T044 [P] [US4] Add test for file path extraction from issue body in `tests/unit/utils/test_context.py`
- [X] T045 [P] [US4] Add test for non-existent referenced files handled gracefully in `tests/unit/utils/test_context.py`
- [X] T046 [P] [US4] Add test for issue with no file references returns empty related_files in `tests/unit/utils/test_context.py`

### Implementation for User Story 4

- [X] T047 [US4] Implement `build_issue_context(issue: GitHubIssue, git: GitOperations, *, max_related_files: int = 10) -> ContextDict` in `src/maverick/utils/context.py` (FR-004) - import `GitHubIssue` from `maverick.runners.models`
- [X] T048 [US4] Add issue dict conversion (number, title, body, labels, state, url)
- [X] T049 [US4] Add file path extraction from issue body using `extract_file_paths`
- [X] T050 [US4] Add related file content reading with existence checks
- [X] T051 [US4] Add recent_changes population (last 5 commits)
- [X] T052 [US4] Verify all tests pass for User Story 4

**Checkpoint**: User Stories 1-4 all work independently

---

## Phase 7: User Story 5 - Token Budget Management (Priority: P3)

**Goal**: Fit context sections within token limits using proportional truncation

**Independent Test**: Call `fit_to_budget()` with sections exceeding budget, verify proportional truncation within 5% of budget

### Tests for User Story 5

- [X] T053 [P] [US5] Add test for sections under budget returned unchanged in `tests/unit/utils/test_context.py`
- [X] T054 [P] [US5] Add test for sections over budget proportionally truncated in `tests/unit/utils/test_context.py`
- [X] T055 [P] [US5] Add test for result within 5% of budget (SC-002) in `tests/unit/utils/test_context.py`
- [X] T056 [P] [US5] Add test for minimum section tokens honored in `tests/unit/utils/test_context.py`

### Implementation for User Story 5

- [X] T057 [US5] Implement `fit_to_budget(sections: dict[str, str], budget: int = 32000, *, min_section_tokens: int = 100) -> dict[str, str]` in `src/maverick/utils/context.py` (FR-007)
- [X] T058 [US5] Add proportional allocation algorithm (section_budget = budget * section_tokens / total_tokens)
- [X] T059 [US5] Add minimum token guarantee per section
- [X] T060 [US5] Add _metadata key with truncation info when budget exceeded
- [X] T061 [US5] Verify all tests pass for User Story 5

**Checkpoint**: All user stories fully functional

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final verification and integration

- [X] T062 Run all tests with pytest: `PYTHONPATH=src pytest tests/unit/utils/test_context.py -v`
- [X] T063 Run type checking: `PYTHONPATH=src mypy src/maverick/utils/context.py --strict`
- [X] T064 Run linting: `ruff check src/maverick/utils/context.py`
- [X] T065 [P] Verify test coverage >= 100% for happy path and error scenarios (SC-005)
- [ ] T066 Run quickstart.md code examples to validate usage documentation
- [X] T067 Final code cleanup and docstring review

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-7)**: All depend on Foundational phase completion
  - P1 stories (US1, US2) should complete before P2 stories (US3, US4)
  - P3 story (US5) should complete last
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational - No dependencies on other stories
- **User Story 3 (P2)**: Can start after Foundational - No dependencies on other stories
- **User Story 4 (P2)**: Can start after Foundational - Uses `extract_file_paths` from Foundational
- **User Story 5 (P3)**: Can start after Foundational - No dependencies on other stories

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Implementation completes story
- All tests pass before moving to next story

### Parallel Opportunities

- T002, T003 can run in parallel with T001
- T006, T007, T009, T010, T011 can run in parallel after T005
- T012-T016 (tests) can run in parallel with each other
- US1, US2, US3, US4, US5 tests can all be written in parallel
- Within each story: all test tasks marked [P] can run in parallel

---

## Parallel Example: Foundational Phase

```bash
# After T005 (estimate_tokens) is complete, launch in parallel:
Task: "T006 Implement truncate_line"
Task: "T007 Implement detect_secrets"
Task: "T009 Implement extract_file_paths"
Task: "T010 Implement _read_file_safely"
Task: "T011 Implement _read_conventions"
```

## Parallel Example: User Story Tests

```bash
# All US1 tests can be written in parallel:
Task: "T017 Test happy path"
Task: "T018 Test missing task file"
Task: "T019 Test large CLAUDE.md truncation"
Task: "T020 Test secret detection logging"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (build_implementation_context)
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Proceed with remaining stories

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently (MVP!)
3. Add User Story 2 → Test independently
4. Add User Story 3 → Test independently
5. Add User Story 4 → Test independently
6. Add User Story 5 → Test independently
7. Polish phase → All stories complete

---

## Summary

| Phase | Tasks | Parallel Opportunities |
|-------|-------|----------------------|
| Setup | T001-T004 (4 tasks) | T002, T003 parallel |
| Foundational | T005-T016 (12 tasks) | T006-T011 parallel, T012-T016 parallel |
| US1 (P1) | T017-T024 (8 tasks) | T017-T020 parallel |
| US2 (P1) | T025-T033 (9 tasks) | T025-T028 parallel |
| US3 (P2) | T034-T042 (9 tasks) | T034-T037 parallel |
| US4 (P2) | T043-T052 (10 tasks) | T043-T046 parallel |
| US5 (P3) | T053-T061 (9 tasks) | T053-T056 parallel |
| Polish | T062-T067 (6 tasks) | T065 parallel |

**Total**: 67 tasks
**MVP Scope**: Phases 1-3 (24 tasks) delivers `build_implementation_context`
