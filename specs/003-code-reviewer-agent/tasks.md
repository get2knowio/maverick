# Tasks: CodeReviewerAgent

**Input**: Design documents from `/specs/003-code-reviewer-agent/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in the feature specification. Test tasks are NOT included.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and directory structure

- [X] T001 Create directory structure: src/maverick/agents/, src/maverick/models/, tests/unit/agents/, tests/unit/models/, tests/integration/agents/
- [X] T002 [P] Create src/maverick/agents/__init__.py with agent exports
- [X] T003 [P] Create src/maverick/models/__init__.py with model exports
- [X] T004 [P] Create src/maverick/exceptions.py with MaverickError and AgentError exception classes

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**CRITICAL**: No user story work can begin until this phase is complete. These components are shared across all user stories.

**DEPENDENCY**: This phase requires the `MaverickAgent` base class from feature 002-base-agent. If 002-base-agent is not yet merged, create a minimal stub in `src/maverick/agents/base.py` with the abstract interface before proceeding.

### Data Models (from data-model.md)

- [X] T005 [P] Create ReviewSeverity enum in src/maverick/models/review.py (CRITICAL, MAJOR, MINOR, SUGGESTION)
- [X] T006 [P] Create UsageStats Pydantic model in src/maverick/models/review.py (input_tokens, output_tokens, total_cost, duration_ms)
- [X] T007 Create ReviewFinding Pydantic model in src/maverick/models/review.py (severity, file, line, message, suggestion, convention_ref)
- [X] T008 Create ReviewResult Pydantic model in src/maverick/models/review.py (success, findings, files_reviewed, summary, truncated, output, metadata, errors, usage)
- [X] T009 Create ReviewContext Pydantic model in src/maverick/models/review.py (branch, base_branch, file_list, cwd)
- [X] T010 Add ReviewResult helper properties in src/maverick/models/review.py (has_critical_findings, findings_by_severity, findings_by_file)
- [X] T011 Update src/maverick/models/__init__.py to export all review models

### Agent Base (from plan.md - depends on 002-base-agent)

- [X] T012 Create CodeReviewerAgent skeleton class in src/maverick/agents/code_reviewer.py extending MaverickAgent
- [X] T013 Add CodeReviewerAgent constants in src/maverick/agents/code_reviewer.py (MAX_DIFF_LINES=2000, MAX_DIFF_FILES=50, ALLOWED_TOOLS)
- [X] T014 Define CodeReviewerAgent system prompt in src/maverick/agents/code_reviewer.py (review dimensions, severity guidelines, JSON output format)
- [X] T015 Update src/maverick/agents/__init__.py to export CodeReviewerAgent

**Checkpoint**: Foundation ready - all data models and agent skeleton in place. User story implementation can now begin.

---

## Phase 3: User Story 1 - Review Code Changes on a Branch (Priority: P1)

**Goal**: Perform automated code review on a feature branch, analyzing all changes and returning structured findings

**Independent Test**: Create a branch with known code changes and verify the agent returns structured ReviewResult findings

### Git Integration (from research.md)

- [X] T016 [US1] Implement _get_diff_stats() method in src/maverick/agents/code_reviewer.py (two-phase: git diff --numstat for metadata)
- [X] T017 [US1] Implement _get_diff_content() method in src/maverick/agents/code_reviewer.py (git diff --patch for selected files)
- [X] T018 [US1] Implement _check_merge_conflicts() method in src/maverick/agents/code_reviewer.py (git diff --diff-filter=U)
- [X] T019 [US1] Implement _read_conventions() method in src/maverick/agents/code_reviewer.py (read CLAUDE.md if exists, return None otherwise)

### Core Review Logic

- [X] T020 [US1] Implement _build_review_prompt() method in src/maverick/agents/code_reviewer.py (diff + conventions + JSON schema instruction)
- [X] T021 [US1] Implement _parse_findings() method in src/maverick/agents/code_reviewer.py (parse Claude response to list[ReviewFinding])
- [X] T022 [US1] Implement execute() method in src/maverick/agents/code_reviewer.py (orchestrate diff retrieval, Claude interaction, result parsing)

### Error Handling (FR-018, FR-019)

- [X] T023 [US1] Add AgentError handling in execute() for INVALID_BRANCH, GIT_ERROR, MERGE_CONFLICTS, TIMEOUT in src/maverick/agents/code_reviewer.py
- [X] T024 [US1] Handle empty diff case in execute() returning ReviewResult with "No changes to review" in src/maverick/agents/code_reviewer.py

**Checkpoint**: User Story 1 complete - can review any branch and return structured findings

---

## Phase 4: User Story 2 - Review Specific Files Only (Priority: P2)

**Goal**: Allow developers to review only a subset of files rather than the entire branch diff

**Independent Test**: Provide a file_list and verify only those files appear in review findings

### File Filtering

- [X] T025 [US2] Modify _get_diff_content() in src/maverick/agents/code_reviewer.py to accept file_list parameter and filter to specified files
- [X] T026 [US2] Add file existence validation in execute() to skip non-existent/unchanged files silently in src/maverick/agents/code_reviewer.py
- [X] T027 [US2] Update execute() to pass context.file_list to diff methods in src/maverick/agents/code_reviewer.py

**Checkpoint**: User Story 2 complete - can filter reviews to specific files

---

## Phase 5: User Story 3 - Categorize Findings by Severity (Priority: P2)

**Goal**: Categorize each finding by severity (CRITICAL, MAJOR, MINOR, SUGGESTION) for prioritization

**Independent Test**: Review code with known issues of varying severity and verify correct categorization

### Severity Implementation

- [X] T028 [US3] Enhance system prompt in src/maverick/agents/code_reviewer.py with detailed severity guidelines from data-model.md
- [X] T029 [US3] Add severity validation in _parse_findings() ensuring all findings have valid ReviewSeverity in src/maverick/agents/code_reviewer.py
- [X] T030 [US3] Update summary generation to include severity counts (e.g., "found 3 issues: 1 critical, 2 minor") in src/maverick/agents/code_reviewer.py

**Checkpoint**: User Story 3 complete - findings are properly categorized by severity

---

## Phase 6: User Story 4 - Display Results in TUI (Priority: P3)

**Goal**: Ensure ReviewResult structure supports TUI display with file navigation and severity filtering

**Independent Test**: Verify ReviewResult contains all fields needed for TUI rendering

### TUI Support

- [X] T031 [US4] Verify ReviewResult.findings_by_file property returns dict[str, list[ReviewFinding]] suitable for file navigation in src/maverick/models/review.py
- [X] T032 [US4] Verify ReviewResult.findings_by_severity property returns dict[ReviewSeverity, list[ReviewFinding]] suitable for filtering in src/maverick/models/review.py
- [X] T033 [US4] Add model_dump_json() compatibility verification for ReviewResult serialization in src/maverick/models/review.py

**Checkpoint**: User Story 4 complete - ReviewResult fully supports TUI consumption

---

## Phase 7: User Story 5 - Provide Actionable Suggestions with Code Examples (Priority: P3)

**Goal**: Each finding includes specific suggestions with code examples showing how to fix the issue

**Independent Test**: Verify findings include non-empty suggestion fields with code examples where applicable

### Suggestion Enhancement

- [X] T034 [US5] Enhance system prompt in src/maverick/agents/code_reviewer.py to require code examples in suggestions
- [X] T035 [US5] Add suggestion validation in _parse_findings() ensuring suggestions are present and meaningful in src/maverick/agents/code_reviewer.py
- [X] T036 [US5] Add convention_ref population when findings relate to CLAUDE.md violations in src/maverick/agents/code_reviewer.py

**Checkpoint**: User Story 5 complete - all findings include actionable suggestions

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Large diff handling, token limits, and overall robustness

### Large Diff Handling (FR-017, FR-020)

- [X] T037 [P] Implement should_truncate() helper in src/maverick/agents/code_reviewer.py (check against MAX_DIFF_LINES, MAX_DIFF_FILES)
- [X] T038 [P] Implement _truncate_files() method in src/maverick/agents/code_reviewer.py (return truncated list + truncation notice)
- [X] T039 Implement binary file filtering in _get_diff_stats() using numstat detection in src/maverick/agents/code_reviewer.py
- [X] T040 Add truncated=True flag and notice in ReviewResult summary when truncation occurs in src/maverick/agents/code_reviewer.py

### Token Limit Handling (FR-021)

- [X] T041 Implement _estimate_tokens() helper in src/maverick/agents/code_reviewer.py (rough estimate: len(content) // 4)
- [X] T042 Implement _chunk_files() method in src/maverick/agents/code_reviewer.py (split files respecting MAX_TOKENS_PER_CHUNK)
- [X] T043 Implement chunked review logic in execute() with findings merge in src/maverick/agents/code_reviewer.py

### Final Integration

- [X] T044 Add metadata population in execute() (branch names, timestamps, duration_ms) in src/maverick/agents/code_reviewer.py
- [X] T045 Add usage stats tracking (input_tokens, output_tokens from Claude response) in src/maverick/agents/code_reviewer.py
- [X] T046 Run quickstart.md validation scenarios manually to verify implementation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-7)**: All depend on Foundational phase completion
  - US1 (Phase 3): No dependencies on other stories - MUST complete first (core functionality)
  - US2 (Phase 4): Depends on US1 (extends _get_diff_content)
  - US3 (Phase 5): Depends on US1 (extends severity handling)
  - US4 (Phase 6): Depends on US1 (validates ReviewResult structure)
  - US5 (Phase 7): Depends on US1 (extends suggestions)
- **Polish (Phase 8)**: Can start after US1, should complete before final delivery

### Within Each User Story

- Git operations before Claude interactions
- Prompt building before execution
- Result parsing after Claude response
- Error handling integrated throughout

### Parallel Opportunities

**Phase 1 (Setup)**: T002, T003, T004 can run in parallel

**Phase 2 (Foundational)**: T005, T006 can run in parallel; T007-T010 are sequential (model dependencies)

**Phase 3 (US1)**: T016-T019 can run in parallel (independent helpers); T020-T024 are sequential

**Phase 4-7 (US2-US5)**: These story phases are largely sequential but US4 and US5 can run in parallel with each other

**Phase 8 (Polish)**: T037, T038 can run in parallel; T039-T045 have dependencies

---

## Parallel Example: Phase 2 - Foundational

```bash
# Launch enum and stats models in parallel:
Task: "Create ReviewSeverity enum in src/maverick/models/review.py"
Task: "Create UsageStats Pydantic model in src/maverick/models/review.py"

# Then sequential model building (ReviewFinding depends on ReviewSeverity):
Task: "Create ReviewFinding Pydantic model in src/maverick/models/review.py"
Task: "Create ReviewResult Pydantic model in src/maverick/models/review.py"
Task: "Create ReviewContext Pydantic model in src/maverick/models/review.py"
```

## Parallel Example: Phase 3 - User Story 1 Git Helpers

```bash
# Launch all git helper methods in parallel (independent implementations):
Task: "Implement _get_diff_stats() method in src/maverick/agents/code_reviewer.py"
Task: "Implement _get_diff_content() method in src/maverick/agents/code_reviewer.py"
Task: "Implement _check_merge_conflicts() method in src/maverick/agents/code_reviewer.py"
Task: "Implement _read_conventions() method in src/maverick/agents/code_reviewer.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 2: Foundational (T005-T015)
3. Complete Phase 3: User Story 1 (T016-T024)
4. **STOP and VALIDATE**: Test basic code review functionality independently
5. Can demo/use for basic reviews at this point

### Incremental Delivery

1. MVP (Setup + Foundational + US1) → Basic code review works
2. Add US2 (file filtering) → Targeted reviews work
3. Add US3 (severity) → Prioritized findings work
4. Add US4 (TUI support) → TUI integration ready
5. Add US5 (suggestions) → Full actionable feedback
6. Add Polish → Production-ready with large diff handling

### Suggested MVP Scope

- **Phase 1**: T001-T004 (4 tasks)
- **Phase 2**: T005-T015 (11 tasks)
- **Phase 3 (US1)**: T016-T024 (9 tasks)
- **Total MVP**: 24 tasks

---

## Summary

| Phase | Description | Task Count |
|-------|-------------|------------|
| Phase 1 | Setup | 4 |
| Phase 2 | Foundational | 11 |
| Phase 3 | US1 - Review Branch | 9 |
| Phase 4 | US2 - File Filter | 3 |
| Phase 5 | US3 - Severity | 3 |
| Phase 6 | US4 - TUI Support | 3 |
| Phase 7 | US5 - Suggestions | 3 |
| Phase 8 | Polish | 10 |
| **Total** | | **46** |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
