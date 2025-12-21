# Feature Specification: Context Builder Utilities

**Feature Branch**: `018-context-builder`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Create context builder utilities in Maverick that prepare optimized context for agent prompts"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Build Implementation Context (Priority: P1)

A workflow needs to provide an implementation agent with all relevant context for executing a task: the task definition, project conventions, current branch info, and recent commits.

**Why this priority**: Implementation is the core workflow, and every code-writing agent needs properly formatted context to understand what to build and how to follow project standards.

**Independent Test**: Can be tested by calling `build_implementation_context()` with a task file path and GitOperations instance, verifying the returned dict contains all expected keys with valid content.

**Acceptance Scenarios**:

1. **Given** a valid task file path and GitOperations instance, **When** `build_implementation_context()` is called, **Then** a dict is returned containing `tasks`, `conventions`, `branch`, and `recent_commits` keys
2. **Given** a task file that doesn't exist, **When** `build_implementation_context()` is called, **Then** the function handles the error gracefully and returns appropriate metadata indicating missing content
3. **Given** a very large CLAUDE.md file, **When** `build_implementation_context()` is called, **Then** the conventions content is truncated with metadata indicating truncation occurred

---

### User Story 2 - Build Review Context (Priority: P1)

A code review agent needs diff information, changed file contents, and project conventions to provide meaningful review feedback.

**Why this priority**: Code review is a critical quality gate that runs after implementation. Without proper diff and file context, the review agent cannot perform its job effectively.

**Independent Test**: Can be tested by calling `build_review_context()` with a GitOperations instance and base branch, verifying the returned dict contains properly formatted diff and file contents.

**Acceptance Scenarios**:

1. **Given** a GitOperations instance and base branch, **When** `build_review_context()` is called, **Then** a dict is returned containing `diff`, `changed_files`, `conventions`, and `stats` keys
2. **Given** changed files of varying sizes, **When** `build_review_context()` is called, **Then** small files are included in full while large files are truncated with metadata
3. **Given** no changes against the base branch, **When** `build_review_context()` is called, **Then** the function returns an empty diff with appropriate stats

---

### User Story 3 - Build Fix Context (Priority: P2)

A fix agent needs to understand validation errors and see the relevant source code around error locations to make targeted fixes.

**Why this priority**: Fix context is used during iterative validation loops. While important, it builds on the pattern established by implementation and review contexts.

**Independent Test**: Can be tested by calling `build_fix_context()` with validation output and file list, verifying source files are truncated around error lines.

**Acceptance Scenarios**:

1. **Given** validation output with errors and file paths, **When** `build_fix_context()` is called, **Then** a dict is returned containing `errors`, `source_files`, and `error_summary` keys
2. **Given** errors at specific line numbers, **When** `build_fix_context()` is called, **Then** source file content is truncated to show context around those line numbers
3. **Given** validation output with no errors, **When** `build_fix_context()` is called, **Then** the function returns an empty errors section with appropriate summary

---

### User Story 4 - Build Issue Context (Priority: P2)

A workflow processing GitHub issues needs comprehensive issue information plus related code context to understand the problem.

**Why this priority**: Issue context supports the RefuelWorkflow which handles tech debt. It extends the pattern to external data sources.

**Independent Test**: Can be tested by calling `build_issue_context()` with a GitHubIssue object and GitOperations, verifying issue details and related files are included.

**Acceptance Scenarios**:

1. **Given** a GitHubIssue object and GitOperations instance, **When** `build_issue_context()` is called, **Then** a dict is returned containing `issue`, `related_files`, and `recent_changes` keys
2. **Given** an issue body mentioning file paths, **When** `build_issue_context()` is called, **Then** those files are included in `related_files` if they exist
3. **Given** an issue with no file references, **When** `build_issue_context()` is called, **Then** `related_files` is empty but the function completes successfully

---

### User Story 5 - Token Budget Management (Priority: P3)

Workflows need to fit context within token limits while preserving the most important information across all sections.

**Why this priority**: Budget management is an optimization that enhances all other context builders. It can be added after core functionality works.

**Independent Test**: Can be tested by calling `fit_to_budget()` with sections exceeding the budget, verifying proportional truncation.

**Acceptance Scenarios**:

1. **Given** sections totaling more tokens than the budget, **When** `fit_to_budget()` is called, **Then** sections are proportionally truncated to fit within budget
2. **Given** sections totaling fewer tokens than the budget, **When** `fit_to_budget()` is called, **Then** sections are returned unchanged
3. **Given** a budget that cannot accommodate minimum content, **When** `fit_to_budget()` is called, **Then** the function prioritizes larger sections and includes truncation metadata

---

### Edge Cases

- What happens when a file path in the context doesn't exist? Return empty content with metadata indicating the file was missing.
- How does the system handle binary files in changed_files? Skip binary files and note them in metadata.
- What happens when git operations fail? Handle git errors gracefully by logging a warning and returning default values (empty strings, empty lists). This ensures workflows can continue with partial context rather than failing entirely.
- How are very long lines handled? Lines exceeding 2000 characters are truncated with "..." appended.
- What happens when truncation removes all meaningful content? Include minimum context (first/last N lines) and clearly indicate severe truncation in metadata.

## Clarifications

### Session 2025-12-18

- Q: How should sensitive content (API keys, credentials) in files be handled? → A: Log warning for suspected secrets, include content as-is
- Q: What fields should the `_metadata` dictionary contain? → A: Standard fields: `truncated` (bool), `original_lines` (int), `kept_lines` (int), `sections_affected` (list[str])
- Q: What's the maximum memory budget for a single context-building operation? → A: 100MB maximum memory per operation
- Q: What should be the default token budget for `fit_to_budget()`? → A: 32,000 tokens default
- Q: How many commits should `build_implementation_context()` include in `recent_commits`? → A: 10 commits

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a `build_implementation_context(task_file: Path, git: GitOperations) -> dict` function that returns a dict with `tasks`, `conventions`, `branch`, and `recent_commits` (last 10 commits) keys
- **FR-002**: System MUST provide a `build_review_context(git: GitOperations, base_branch: str) -> dict` function that returns a dict with `diff`, `changed_files`, `conventions`, and `stats` keys
- **FR-003**: System MUST provide a `build_fix_context(validation_output: ValidationOutput, files: list[Path]) -> dict` function that returns a dict with `errors`, `source_files`, and `error_summary` keys
- **FR-004**: System MUST provide a `build_issue_context(issue: GitHubIssue, git: GitOperations) -> dict` function that returns a dict with `issue`, `related_files`, and `recent_changes` keys
- **FR-005**: System MUST provide a `truncate_file(content: str, max_lines: int, around_lines: list[int]) -> str` utility that preserves content around specified line numbers
- **FR-006**: System MUST provide an `estimate_tokens(text: str) -> int` utility that returns an approximate token count (characters divided by 4)
- **FR-007**: System MUST provide a `fit_to_budget(sections: dict[str, str], budget: int = 32000) -> dict[str, str]` utility that proportionally truncates sections to fit token budget (default: 32,000 tokens)
- **FR-008**: All context builder functions MUST be synchronous (file I/O and string manipulation only)
- **FR-009**: All context builder functions MUST return plain dicts (not dataclasses) for easy prompt interpolation
- **FR-010**: All returned dicts MUST include `_metadata` key with truncation information when content has been truncated
- **FR-011**: The `truncate_file` function MUST replace removed content with "..." markers to indicate truncation
- **FR-012**: The `build_review_context` function MUST include full content for files under 500 lines and truncated content for larger files
- **FR-013**: The `build_fix_context` function MUST preserve at least 10 lines of context around each error line number
- **FR-014**: Context builders MUST handle missing files gracefully by returning empty content with appropriate metadata
- **FR-015**: Context builders MUST log a warning (via standard logging) when file content matches common secret patterns (API keys, tokens, credentials) but MUST still include the content as-is for agent accuracy

### Key Entities

- **ContextDict**: A plain Python dict containing context sections as string values, plus a `_metadata` key with truncation info
- **TruncationMetadata**: A dict with fields: `truncated` (bool), `original_lines` (int), `kept_lines` (int), `sections_affected` (list[str] naming which context sections were truncated)
- **ValidationOutput**: External type from `maverick.runners.models` containing staged validation results with `ParsedError` details (file paths, line numbers, error messages)
- **GitHubIssue**: External type from `maverick.runners.models` representing a GitHub issue with number, title, body, labels, state, assignees, and url
- **GitOperations**: External type from `maverick.utils.git_operations` providing git functionality (branch info, diffs, commit history)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All four context builder functions return valid dicts within 500ms for typical repository sizes (up to 10,000 files)
- **SC-002**: Context returned by `fit_to_budget` stays within 5% of the specified token budget
- **SC-003**: Token estimation accuracy is within 20% of actual token count for typical source code content
- **SC-004**: Truncated content always includes metadata allowing agents to request more context if needed
- **SC-005**: All context builders have 100% test coverage for both happy path and error scenarios
- **SC-006**: Context builders reduce prompt context usage by at least 40% compared to including full file contents for large repositories
- **SC-007**: Memory usage for any single context-building operation MUST NOT exceed 100MB
