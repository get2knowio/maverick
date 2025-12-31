# Tasks: Git Operations Module

**Input**: Design documents from `/specs/016-git-operations/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: Tests are included as this is a utility module requiring 100% test coverage (SC-008).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/unit/` at repository root
- Exception types: `src/maverick/exceptions.py`
- Git operations module: `src/maverick/utils/git_operations.py`
- Tests: `tests/unit/utils/test_git_operations.py`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and module structure

- [X] T001 Create git_operations module skeleton in src/maverick/utils/git_operations.py with module docstring and imports
- [X] T002 Create test file skeleton in tests/unit/utils/test_git_operations.py with pytest fixtures for temp git repos

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Exception types and dataclass definitions that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 [P] Add GitNotFoundError exception class to src/maverick/exceptions.py (extends GitError, operation="git_check", recoverable=False)
- [X] T004 [P] Add NotARepositoryError exception class to src/maverick/exceptions.py (extends GitError, adds path attribute)
- [X] T005 [P] Add BranchExistsError exception class to src/maverick/exceptions.py (extends GitError, adds branch_name attribute)
- [X] T006 [P] Add MergeConflictError exception class to src/maverick/exceptions.py (extends GitError, adds conflicted_files tuple)
- [X] T007 [P] Add PushRejectedError exception class to src/maverick/exceptions.py (extends GitError, adds reason attribute)
- [X] T008 [P] Add NothingToCommitError exception class to src/maverick/exceptions.py (extends GitError, for empty commits)
- [X] T009 [P] Add NoStashError exception class to src/maverick/exceptions.py (extends GitError, for stash_pop with no stash)
- [X] T010 [P] Add CheckoutConflictError exception class to src/maverick/exceptions.py (extends GitError, for checkout with uncommitted conflicts)
- [X] T011 [P] Define GitStatus frozen dataclass in src/maverick/utils/git_operations.py (staged, unstaged, untracked, branch, ahead, behind)
- [X] T012 [P] Define CommitInfo frozen dataclass in src/maverick/utils/git_operations.py (hash, short_hash, message, author, date)
- [X] T013 [P] Define DiffStats frozen dataclass in src/maverick/utils/git_operations.py (files_changed, insertions, deletions, file_list)
- [X] T014 Implement GitOperations class constructor with _cwd Path attribute and lazy git check in src/maverick/utils/git_operations.py
- [X] T015 Implement private _run helper method for subprocess execution (no shell=True) in src/maverick/utils/git_operations.py
- [X] T016 Implement _check_git_installed method with GitNotFoundError in src/maverick/utils/git_operations.py
- [X] T017 Implement _check_repository method with NotARepositoryError in src/maverick/utils/git_operations.py

**Checkpoint**: Foundation ready - all exception types, dataclasses, and base GitOperations class complete

---

## Phase 3: User Story 1 - Query Repository State (Priority: P1)

**Goal**: Enable workflows to understand current repository state (branch, status, log)

**Independent Test**: Initialize temp git repo, make changes, verify correct reporting of branch name, file status, and commit history

### Tests for User Story 1

- [X] T018 [P] [US1] Test current_branch returns branch name for normal branch in tests/unit/utils/test_git_operations.py
- [X] T019 [P] [US1] Test current_branch returns commit hash for detached HEAD in tests/unit/utils/test_git_operations.py
- [X] T020 [P] [US1] Test status returns GitStatus with staged, unstaged, untracked files in tests/unit/utils/test_git_operations.py
- [X] T021 [P] [US1] Test status returns ahead/behind counts when tracking branch exists in tests/unit/utils/test_git_operations.py
- [X] T022 [P] [US1] Test log returns list of CommitInfo for n most recent commits in tests/unit/utils/test_git_operations.py
- [X] T023 [P] [US1] Test NotARepositoryError raised when cwd is not a git repo in tests/unit/utils/test_git_operations.py

### Implementation for User Story 1

- [X] T024 [US1] Implement current_branch() method using git rev-parse --abbrev-ref HEAD in src/maverick/utils/git_operations.py
- [X] T025 [US1] Handle detached HEAD case in current_branch() returning full SHA in src/maverick/utils/git_operations.py
- [X] T026 [US1] Implement status() method parsing git status --porcelain and --branch in src/maverick/utils/git_operations.py
- [X] T027 [US1] Parse ahead/behind counts from git status --branch output in status() method in src/maverick/utils/git_operations.py
- [X] T028 [US1] Implement log(n) method using git log --format with pipe delimiter in src/maverick/utils/git_operations.py

**Checkpoint**: User Story 1 complete - current_branch(), status(), log() all functional and tested

---

## Phase 4: User Story 2 - Create and Manage Branches (Priority: P1)

**Goal**: Enable workflows to create feature branches and switch between branches safely

**Independent Test**: Create branches, switch between them, verify correct branch is active

### Tests for User Story 2

- [X] T029 [P] [US2] Test create_branch with checkout=True creates and switches to new branch in tests/unit/utils/test_git_operations.py
- [X] T030 [P] [US2] Test create_branch with checkout=False creates branch but stays on current in tests/unit/utils/test_git_operations.py
- [X] T031 [P] [US2] Test create_branch raises BranchExistsError for existing branch in tests/unit/utils/test_git_operations.py
- [X] T032 [P] [US2] Test checkout switches to existing branch in tests/unit/utils/test_git_operations.py
- [X] T033 [P] [US2] Test checkout raises CheckoutConflictError when uncommitted changes conflict in tests/unit/utils/test_git_operations.py

### Implementation for User Story 2

- [X] T034 [US2] Implement create_branch(name, checkout) using git branch and git checkout in src/maverick/utils/git_operations.py
- [X] T035 [US2] Add BranchExistsError detection in create_branch from stderr parsing in src/maverick/utils/git_operations.py
- [X] T036 [US2] Implement checkout(branch) using git checkout in src/maverick/utils/git_operations.py
- [X] T037 [US2] Add CheckoutConflictError detection in checkout from stderr parsing in src/maverick/utils/git_operations.py

**Checkpoint**: User Story 2 complete - create_branch(), checkout() functional and tested

---

## Phase 5: User Story 3 - Commit and Push Changes (Priority: P1)

**Goal**: Enable workflows to commit work and push to remote repositories

**Independent Test**: Make file changes, commit them, verify commit exists with correct message, push succeeds

### Tests for User Story 3

- [X] T038 [P] [US3] Test commit with add_all=True stages and commits all changes in tests/unit/utils/test_git_operations.py
- [X] T039 [P] [US3] Test commit with add_all=False commits only staged changes in tests/unit/utils/test_git_operations.py
- [X] T040 [P] [US3] Test commit returns commit hash on success in tests/unit/utils/test_git_operations.py
- [X] T041 [P] [US3] Test commit raises NothingToCommitError when no changes in tests/unit/utils/test_git_operations.py
- [X] T042 [P] [US3] Test push with set_upstream=True sets tracking branch in tests/unit/utils/test_git_operations.py
- [X] T043 [P] [US3] Test push raises PushRejectedError when remote rejects in tests/unit/utils/test_git_operations.py

### Implementation for User Story 3

- [X] T044 [US3] Implement commit(message, add_all) using git add -A and git commit in src/maverick/utils/git_operations.py
- [X] T045 [US3] Return commit SHA from commit() by parsing git output in src/maverick/utils/git_operations.py
- [X] T046 [US3] Add NothingToCommitError detection in commit from stderr parsing in src/maverick/utils/git_operations.py
- [X] T047 [US3] Implement push(remote, set_upstream) using git push in src/maverick/utils/git_operations.py
- [X] T048 [US3] Add PushRejectedError detection in push from stderr parsing in src/maverick/utils/git_operations.py

**Checkpoint**: User Story 3 complete - commit(), push() functional and tested

---

## Phase 6: User Story 4 - Analyze Code Changes (Priority: P2)

**Goal**: Enable workflows to understand code changes for PR descriptions and reviews

**Independent Test**: Make changes on feature branch, request diffs against main, verify correct output

### Tests for User Story 4

- [X] T049 [P] [US4] Test diff returns full diff string between refs in tests/unit/utils/test_git_operations.py
- [X] T050 [P] [US4] Test diff returns empty string when no changes in tests/unit/utils/test_git_operations.py
- [X] T051 [P] [US4] Test diff_stats returns DiffStats with files_changed, insertions, deletions in tests/unit/utils/test_git_operations.py
- [X] T052 [P] [US4] Test diff_stats returns zero values when no changes in tests/unit/utils/test_git_operations.py

### Implementation for User Story 4

- [X] T053 [US4] Implement diff(base, head) using git diff in src/maverick/utils/git_operations.py
- [X] T054 [US4] Implement diff_stats(base) using git diff --numstat in src/maverick/utils/git_operations.py
- [X] T055 [US4] Parse numstat output into DiffStats dataclass in src/maverick/utils/git_operations.py

**Checkpoint**: User Story 4 complete - diff(), diff_stats() functional and tested

---

## Phase 7: User Story 5 - Sync with Remote (Priority: P2)

**Goal**: Enable workflows to pull latest changes and stay synchronized

**Independent Test**: Set up remote with newer commits, verify pull retrieves them

### Tests for User Story 5

- [X] T056 [P] [US5] Test pull fast-forwards local branch with new remote commits in tests/unit/utils/test_git_operations.py
- [X] T057 [P] [US5] Test pull raises MergeConflictError when conflicts occur in tests/unit/utils/test_git_operations.py
- [X] T058 [P] [US5] Test pull raises appropriate error when remote branch does not exist in tests/unit/utils/test_git_operations.py

### Implementation for User Story 5

- [X] T059 [US5] Implement pull(remote, branch) using git pull in src/maverick/utils/git_operations.py
- [X] T060 [US5] Add MergeConflictError detection in pull with conflicted_files from stderr in src/maverick/utils/git_operations.py

**Checkpoint**: User Story 5 complete - pull() functional and tested

---

## Phase 8: User Story 6 - Stash Work in Progress (Priority: P3)

**Goal**: Enable workflows to temporarily set aside uncommitted changes

**Independent Test**: Make changes, stash them, verify working directory is clean, restore stash

### Tests for User Story 6

- [X] T061 [P] [US6] Test stash with message saves changes and cleans working directory in tests/unit/utils/test_git_operations.py
- [X] T062 [P] [US6] Test stash without message uses default message in tests/unit/utils/test_git_operations.py
- [X] T063 [P] [US6] Test stash_pop restores most recent stash in tests/unit/utils/test_git_operations.py
- [X] T064 [P] [US6] Test stash_pop raises NoStashError when no stash exists in tests/unit/utils/test_git_operations.py

### Implementation for User Story 6

- [X] T065 [US6] Implement stash(message) using git stash push -m in src/maverick/utils/git_operations.py
- [X] T066 [US6] Implement stash_pop() using git stash pop in src/maverick/utils/git_operations.py
- [X] T067 [US6] Add NoStashError detection in stash_pop from stderr parsing in src/maverick/utils/git_operations.py

**Checkpoint**: User Story 6 complete - stash(), stash_pop() functional and tested

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, edge cases, and code quality

- [X] T068 [P] Test GitNotFoundError raised when git is not installed in tests/unit/utils/test_git_operations.py
- [X] T069 [P] Test thread safety with concurrent operations on same GitOperations instance in tests/unit/utils/test_git_operations.py
- [X] T070 Verify no shell=True usage in all subprocess calls (code review) in src/maverick/utils/git_operations.py
- [X] T071 Add module-level __all__ export list in src/maverick/utils/git_operations.py
- [X] T072 Run mypy type checking on src/maverick/utils/git_operations.py
- [X] T073 Run ruff linting on src/maverick/utils/git_operations.py
- [X] T074 Run pytest with coverage and verify 100% coverage for git_operations.py
- [X] T075 Run quickstart.md validation scenarios manually

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-8)**: All depend on Foundational phase completion
  - US1, US2, US3 (P1): Can proceed in priority order or parallel
  - US4, US5 (P2): Can start after Foundational, independent of P1 stories
  - US6 (P3): Can start after Foundational, independent of other stories
- **Polish (Phase 9)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Query State - No dependencies on other stories
- **User Story 2 (P1)**: Branch Management - No dependencies on other stories
- **User Story 3 (P1)**: Commit/Push - No dependencies on other stories
- **User Story 4 (P2)**: Diff Analysis - No dependencies on other stories
- **User Story 5 (P2)**: Sync/Pull - No dependencies on other stories
- **User Story 6 (P3)**: Stash - No dependencies on other stories

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Implementation follows test completion
- Each story complete before moving to next priority (or parallel execution)

### Parallel Opportunities

- All Foundational exception/dataclass tasks (T003-T013) can run in parallel
- All tests within a user story can run in parallel (marked [P])
- Different user stories can be worked on in parallel by different team members
- After Foundational phase, US1-US6 can technically all start in parallel

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Test current_branch returns branch name for normal branch"
Task: "Test current_branch returns commit hash for detached HEAD"
Task: "Test status returns GitStatus with staged, unstaged, untracked files"
Task: "Test status returns ahead/behind counts when tracking branch exists"
Task: "Test log returns list of CommitInfo for n most recent commits"
Task: "Test NotARepositoryError raised when cwd is not a git repo"
```

---

## Implementation Strategy

### MVP First (User Stories 1-3 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Query State)
4. Complete Phase 4: User Story 2 (Branch Management)
5. Complete Phase 5: User Story 3 (Commit/Push)
6. **STOP and VALIDATE**: Core operations functional
7. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational -> Foundation ready
2. Add User Story 1 -> Test independently -> current_branch, status, log work
3. Add User Story 2 -> Test independently -> create_branch, checkout work
4. Add User Story 3 -> Test independently -> commit, push work
5. Add User Story 4 -> Test independently -> diff, diff_stats work
6. Add User Story 5 -> Test independently -> pull works
7. Add User Story 6 -> Test independently -> stash, stash_pop work
8. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (Query State)
   - Developer B: User Story 2 (Branch Management)
   - Developer C: User Story 3 (Commit/Push)
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- All subprocess calls MUST use explicit argument lists (no shell=True)
- Use frozen dataclasses with slots=True for all return types
