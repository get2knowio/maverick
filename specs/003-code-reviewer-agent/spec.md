# Feature Specification: CodeReviewerAgent

**Feature Branch**: `003-code-reviewer-agent`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Create a spec for the CodeReviewerAgent in Maverick, extending the base MaverickAgent."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Review Code Changes on a Branch (Priority: P1)

A developer has completed work on a feature branch and wants an automated code review before creating a pull request. They invoke the CodeReviewerAgent with their branch name, and it analyzes all changes compared to the base branch, providing structured feedback on code quality, style, and potential issues.

**Why this priority**: This is the primary use case - getting comprehensive code review feedback on a feature branch. Without this working, the agent has no value.

**Independent Test**: Can be fully tested by creating a branch with known code changes and verifying the agent returns structured review findings for those changes.

**Acceptance Scenarios**:

1. **Given** a feature branch with code changes, **When** the developer invokes CodeReviewerAgent with the branch name and base branch, **Then** the agent analyzes all changed files and returns structured review findings.
2. **Given** changes include violations of project conventions documented in CLAUDE.md, **When** the review completes, **Then** findings reference the specific convention violated and suggest corrections.
3. **Given** changes include potential security issues, **When** the review completes, **Then** findings are categorized as critical severity with clear explanations.

---

### User Story 2 - Review Specific Files Only (Priority: P2)

A developer wants to review only a subset of files rather than the entire branch diff. They provide an optional file list to focus the review scope, reducing noise and review time for targeted feedback.

**Why this priority**: Important for iterative development where only certain files need re-review after addressing previous feedback.

**Independent Test**: Can be tested by providing a file list and verifying only those files appear in review findings.

**Acceptance Scenarios**:

1. **Given** a file list is provided in the context, **When** the review executes, **Then** only the specified files are reviewed (even if more files changed on the branch).
2. **Given** an empty file list, **When** the review executes, **Then** all changed files are reviewed (default behavior).
3. **Given** a file in the list doesn't exist or wasn't changed, **When** the review executes, **Then** that file is skipped without error.

---

### User Story 3 - Categorize Findings by Severity (Priority: P2)

A developer needs to quickly identify the most important issues to address. The agent categorizes each finding by severity (critical, major, minor, suggestion) so developers can prioritize fixes effectively.

**Why this priority**: Severity categorization is essential for triaging review feedback efficiently in real projects.

**Independent Test**: Can be tested by reviewing code with known issues of varying severity and verifying correct categorization.

**Acceptance Scenarios**:

1. **Given** code with a security vulnerability, **When** the review completes, **Then** the finding is categorized as "critical".
2. **Given** code with incorrect logic, **When** the review completes, **Then** the finding is categorized as "major".
3. **Given** code with style inconsistencies, **When** the review completes, **Then** the finding is categorized as "minor".
4. **Given** code with potential improvements, **When** the review completes, **Then** the finding is categorized as "suggestion".

---

### User Story 4 - Display Results in TUI (Priority: P3)

A workflow orchestrator needs to display review results in the Maverick TUI. The structured output format enables rich display of findings with file navigation, severity filtering, and actionable suggestions.

**Why this priority**: TUI integration depends on the structured output from P1 stories. This validates the data format is suitable for display.

**Independent Test**: Can be tested by verifying the ReviewResult structure contains all fields needed for TUI rendering.

**Acceptance Scenarios**:

1. **Given** a completed review, **When** the ReviewResult is returned, **Then** it contains a list of ReviewFinding objects with severity, file, line, message, and suggestion fields.
2. **Given** a ReviewResult, **When** the TUI renders it, **Then** findings can be grouped by file and filtered by severity.
3. **Given** a ReviewResult, **When** accessed programmatically, **Then** all fields are typed and documented for IDE support.

---

### User Story 5 - Provide Actionable Suggestions with Code Examples (Priority: P3)

A developer wants to quickly fix identified issues. Each finding includes not just what's wrong but a specific suggestion with example code showing how to fix it.

**Why this priority**: Actionable suggestions accelerate the fix cycle but depend on core review functionality working first.

**Independent Test**: Can be tested by verifying findings include non-empty suggestion fields with code examples where applicable.

**Acceptance Scenarios**:

1. **Given** a finding about incorrect code, **When** the suggestion is generated, **Then** it includes example code showing the recommended fix.
2. **Given** a style violation, **When** the suggestion is generated, **Then** it references the specific convention and shows compliant code.
3. **Given** a finding where no code example applies, **When** the suggestion is generated, **Then** it provides clear textual guidance instead.

---

### Edge Cases

- No changes compared to base: return empty ReviewResult with success=True and summary "No changes to review".
- Binary files in the diff are skipped silently (excluded from review, not mentioned in findings).
- CLAUDE.md not found: proceed without convention checking and note this in the summary (per FR-015).
- Large diffs are truncated: review files in git diff order (typically alphabetical by path) up to the threshold, and note truncation in the summary including count of skipped files.
- Git failures (invalid branch, command errors) raise AgentError with diagnostic details for caller handling.
- Merge conflicts in diff raise AgentError; caller should resolve conflicts before review.
- Token limits during review: automatically chunk remaining work and merge all findings.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a `CodeReviewerAgent` class that extends `MaverickAgent`.
- **FR-002**: `CodeReviewerAgent` MUST have a system prompt that instructs Claude to review code for correctness, style, security, and performance.
- **FR-003**: `CodeReviewerAgent` MUST have a system prompt that instructs Claude to check compliance with project conventions from CLAUDE.md.
- **FR-004**: `CodeReviewerAgent` MUST have a system prompt that instructs Claude to categorize findings by severity: critical, major, minor, suggestion.
- **FR-005**: `CodeReviewerAgent` MUST have a system prompt that instructs Claude to provide specific, actionable feedback with code examples.
- **FR-006**: `CodeReviewerAgent` MUST specify allowed tools: Read, Glob, Grep, and Bash (read-only operations).
- **FR-007**: `CodeReviewerAgent` MUST implement an `execute()` method that accepts context containing: branch name, base branch, and optional file list.
- **FR-008**: The `execute()` method MUST run git diff to retrieve changes between the feature branch and base branch.
- **FR-009**: The `execute()` method MUST read CLAUDE.md to provide project conventions to the review.
- **FR-010**: The `execute()` method MUST return structured review results as a `ReviewResult` dataclass.
- **FR-011**: System MUST provide a `ReviewFinding` dataclass with fields: severity (enum), file (str), line (int or None), message (str), suggestion (str).
- **FR-012**: System MUST provide a `ReviewResult` dataclass extending `AgentResult` with fields: findings (list of ReviewFinding), files_reviewed (int), summary (str).
- **FR-013**: The severity field MUST be an enum with values: CRITICAL, MAJOR, MINOR, SUGGESTION.
- **FR-014**: If a file list is provided in context, `execute()` MUST limit review to only those files.
- **FR-015**: If CLAUDE.md is not found, the review MUST proceed without convention checking and note this in the summary.
- **FR-016**: The agent MUST produce machine-parseable output (JSON-structured) that can be deserialized into `ReviewResult`.
- **FR-017**: If the diff exceeds a configurable threshold (default: 2000 lines or 50 files), the agent MUST truncate to the threshold and include a truncation notice in the summary.
- **FR-018**: If git operations fail (invalid branch, merge conflicts, command errors), the agent MUST raise an `AgentError` with diagnostic details.
- **FR-019**: If no changes exist between the feature branch and base branch, the agent MUST return an empty ReviewResult with success=True and a summary indicating no changes to review.
- **FR-020**: Binary files in the diff MUST be silently excluded from review (not counted in files_reviewed, no findings generated).
- **FR-021**: If token limits are approached during review, the agent MUST automatically chunk remaining files into separate review passes and merge all findings into a single ReviewResult.

### Key Entities

- **CodeReviewerAgent**: Concrete agent specializing in code review. Extends MaverickAgent with code-review-specific system prompt and tools. Executes reviews and returns structured findings.
- **ReviewFinding**: Value object representing a single review issue. Contains severity level, file path, optional line number, description message, and suggested fix.
- **ReviewResult**: Value object extending AgentResult for code review outcomes. Contains list of findings, count of files reviewed, and summary text.
- **ReviewSeverity**: Enumeration of finding severity levels (CRITICAL, MAJOR, MINOR, SUGGESTION) for prioritization.
- **ReviewContext**: Context object for code review containing branch name, base branch, optional file list, and any additional review parameters.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Developers can invoke a code review on any branch with a single method call and receive structured feedback.
- **SC-002**: Review findings are categorized using severity definitions that align with industry standards (CRITICAL for security/data-loss, MAJOR for logic errors, MINOR for style, SUGGESTION for improvements).
- **SC-003**: All findings include actionable suggestions that developers can implement without further clarification.
- **SC-004**: Reviews complete within 2 minutes for typical PRs (under 500 lines changed across 10 files).
- **SC-005**: The ReviewResult structure can be serialized to JSON and deserialized without data loss.
- **SC-006**: Convention violations reference the specific CLAUDE.md section being violated.
- **SC-007**: Security-related findings (injection, XSS, secrets exposure) are always categorized as critical.

## Clarifications

### Session 2025-12-13

- Q: How should large diffs (hundreds of files or thousands of lines) be handled? → A: Truncate with summary (review first N lines/files, note truncation in summary)
- Q: When git operations fail (invalid branch, merge conflicts, command errors), what should the agent do? → A: Raise exception (throw AgentError with details, let caller handle)
- Q: When the branch has no changes compared to base, what should the agent return? → A: Return empty ReviewResult with success=True and summary noting "No changes to review"
- Q: How should binary files in the diff be handled? → A: Skip silently (exclude from review, don't mention in findings)
- Q: When the agent reaches token limits during review, what should happen? → A: Automatic chunking (internally split remaining work, merge all findings)

## Assumptions

- The base `MaverickAgent` class exists and provides the abstract interface (from feature 002-base-agent).
- `AgentResult` and `AgentContext` dataclasses are available from the base agent module.
- Git is installed and the working directory is a git repository.
- The feature branch and base branch exist and are valid git references.
- Read-only Bash operations include: git diff, git log, git show, cat, head, tail, wc.
- CLAUDE.md is located at the repository root if it exists.
- The Claude model can produce structured JSON output when prompted appropriately.

## Dependencies

- Feature 002-base-agent: `MaverickAgent`, `AgentResult`, `AgentContext` classes
- Claude Agent SDK: Core AI interaction capability
- Pydantic: For dataclass validation and serialization
- Git CLI: For retrieving diffs and branch information
