# Feature Specification: ImplementerAgent and IssueFixerAgent

**Feature Branch**: `004-implementer-issue-fixer-agents`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Create a spec for two related agents in Maverick: ImplementerAgent and IssueFixerAgent"

## Clarifications

### Session 2025-12-14

- Q: How should ImplementerAgent handle tasks marked for parallel execution ("P:" prefix)? → A: Agent spawns sub-agents for parallel task execution.
- Q: What format should task files follow for parsing? → A: Use `.specify` tasks.md format - checkbox items with `[ ]`, task IDs like `[T001]`, `P:` prefix for parallel.
- Q: How should parallel sub-agent failures be handled? → A: Retry failed sub-agent while others continue, then aggregate all results.
- Q: How should GitHub API failures be handled? → A: Retry up to 3 times with exponential backoff, then fail with actionable error message.
- Q: How should git commit failures be handled? → A: Auto-recover common issues (stash/unstash for dirty index, fix hook failures if possible), fail on merge conflicts.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Execute Implementation Tasks from Task File (Priority: P1)

A developer has a structured task list (tasks.md) defining implementation work for a feature. They invoke the ImplementerAgent with the task file path and branch name. The agent works through each task sequentially, writing code, adding tests, and committing after each logical unit of work.

**Why this priority**: This is the core use case for ImplementerAgent - automated execution of structured implementation tasks. Without this, the agent provides no value to the FlyWorkflow.

**Independent Test**: Can be fully tested by providing a task file with 2-3 tasks and verifying the agent produces commits with the expected code changes and tests.

**Acceptance Scenarios**:

1. **Given** a task file with a single implementation task, **When** the ImplementerAgent executes, **Then** the task is completed with corresponding code changes and a git commit.
2. **Given** a task file with multiple sequential tasks, **When** the ImplementerAgent executes, **Then** tasks are completed in order with separate commits for each logical unit.
3. **Given** a task that requires test-driven development, **When** the task is executed, **Then** tests are written before or alongside implementation code.
4. **Given** a completed task, **When** the agent commits, **Then** the commit message follows conventional commit format.

---

### User Story 2 - Fix GitHub Issue with Minimal Changes (Priority: P1)

A developer wants to fix a GitHub issue automatically. They invoke the IssueFixerAgent with an issue number. The agent fetches the issue details, analyzes the problem, implements a targeted fix with minimal code changes, and verifies the fix works.

**Why this priority**: This is the core use case for IssueFixerAgent - automated issue resolution for the RefuelWorkflow. Essential for tech-debt management automation.

**Independent Test**: Can be fully tested by providing a GitHub issue number for a known bug and verifying the agent produces a working fix with verification results.

**Acceptance Scenarios**:

1. **Given** a GitHub issue number, **When** the IssueFixerAgent executes, **Then** it fetches issue details and understands the problem context.
2. **Given** an issue describing a bug, **When** the fix is implemented, **Then** changes are minimal and targeted (no unrelated refactoring).
3. **Given** a completed fix, **When** verification runs, **Then** the agent confirms the issue is resolved.
4. **Given** a completed fix, **When** the agent commits, **Then** the commit message references the issue number.

---

### User Story 3 - Run Validation Before Completing Work (Priority: P2)

Both agents must ensure their work passes project validation before considering tasks complete. After implementation, the agent runs format, lint, and test commands. If validation fails, the agent attempts to fix issues iteratively.

**Why this priority**: Validation ensures code quality and prevents broken builds. Important for CI/CD integration but depends on core implementation working first.

**Independent Test**: Can be tested by having an agent complete work that introduces a linting error and verifying it auto-fixes before committing.

**Acceptance Scenarios**:

1. **Given** completed implementation work, **When** validation runs, **Then** format, lint, and test commands execute in sequence.
2. **Given** a validation failure, **When** the agent detects the failure, **Then** it attempts to fix the issue automatically.
3. **Given** validation passes after fixes, **When** work completes, **Then** the fix is included in the commit.
4. **Given** validation fails after maximum retry attempts, **When** work completes, **Then** the result indicates validation failure with details.

---

### User Story 4 - Provide Structured Implementation Summary (Priority: P2)

Workflow orchestrators need to understand what work was completed. Both agents return structured summaries including files changed, tests added, commits created, and any issues encountered.

**Why this priority**: Structured output enables TUI display and workflow decision-making. Important for integration but depends on core implementation.

**Independent Test**: Can be tested by verifying the result dataclass contains all expected fields after a successful execution.

**Acceptance Scenarios**:

1. **Given** ImplementerAgent completes work, **When** the result is returned, **Then** it includes files changed, tests added/modified, and commit references.
2. **Given** IssueFixerAgent completes work, **When** the result is returned, **Then** it includes issue reference, changes made, and verification results.
3. **Given** an agent encounters errors, **When** the result is returned, **Then** it includes error details with actionable context.

---

### User Story 5 - Execute Task from Direct Description (Priority: P3)

A developer wants to execute a single implementation task without creating a task file. They provide a task description directly to the ImplementerAgent, which executes it as if it were a single-task file.

**Why this priority**: Convenience feature for ad-hoc tasks. Nice to have but not essential for workflow integration.

**Independent Test**: Can be tested by providing a task description string and verifying execution matches task file behavior.

**Acceptance Scenarios**:

1. **Given** a task description string instead of file path, **When** the ImplementerAgent executes, **Then** it treats the description as a single task and completes it.
2. **Given** both task description and task file, **When** execution begins, **Then** an error is raised indicating conflicting inputs.

---

### User Story 6 - Accept Issue Data Dictionary (Priority: P3)

For workflow optimization, the IssueFixerAgent can accept pre-fetched issue data instead of fetching from GitHub. This avoids redundant API calls when the workflow has already loaded issue details.

**Why this priority**: Performance optimization for RefuelWorkflow. Nice to have but not essential for basic functionality.

**Independent Test**: Can be tested by providing issue data dict and verifying the agent skips GitHub fetch.

**Acceptance Scenarios**:

1. **Given** issue data dictionary instead of issue number, **When** the IssueFixerAgent executes, **Then** it uses the provided data without GitHub API calls.
2. **Given** incomplete issue data, **When** execution begins, **Then** an error is raised indicating missing required fields.

---

### Edge Cases

- Task file has invalid format or syntax: Raise `TaskParseError` with line number and description (e.g., "Line 42: Invalid task ID format 'TX1', expected 'T###'"). Do not attempt partial execution.
- GitHub issue doesn't exist: Return error with "Issue #N not found" after retry exhaustion.
- GitHub inaccessible: Retry with exponential backoff, then fail with actionable error.
- Very large task files (50+ tasks): Process all tasks sequentially/parallel as normal. Log warning at 100+ tasks ("Large task file detected: 150 tasks. Consider splitting into phases."). No hard limit.
- Git commit fails (dirty index): Auto-stash, commit, unstash. Pre-commit hook failure: Attempt auto-fix, retry. Merge conflict: Fail with descriptive error.
- Issue has no clear reproduction steps: Attempt best-effort fix based on issue title, description, and code analysis. Set `verification_passed=False` in result. Add note to `fix_description`: "Unable to verify fix - no reproduction steps provided."
- Validation commands not configured: Check for ruff/mypy/pytest in pyproject.toml or environment. If missing, skip that validation step with warning logged. Set `validation_passed=True` with note in metadata: `{"skipped_validation": ["lint", "typecheck"]}`.
- Tasks with external dependencies (APIs, databases): Treat as out of scope for agent. Task description should include any required mock setup. Agent will not provision infrastructure. If external dependency blocks execution, fail task with error: "External dependency unavailable: {description}".

## Requirements *(mandatory)*

### Functional Requirements - ImplementerAgent

- **FR-001**: System MUST provide an `ImplementerAgent` class that extends `MaverickAgent`.
- **FR-002**: `ImplementerAgent` MUST have a system prompt focused on methodical, test-driven implementation following project conventions.
- **FR-003**: `ImplementerAgent` MUST specify allowed tools: Read, Write, Edit, MultiEdit, Bash, Glob, Grep.
- **FR-004**: `ImplementerAgent` MUST implement an `execute()` method that accepts context containing: task file path OR task description, and branch name.
- **FR-005**: The `execute()` method MUST parse task files to extract individual tasks with their metadata (priority, dependencies, parallel markers).
- **FR-006**: The `execute()` method MUST work through tasks sequentially unless marked for parallel execution ("P:" prefix), in which case it spawns sub-agents to execute parallel tasks concurrently using asyncio.
- **FR-006a**: When a parallel sub-agent fails, the system MUST retry the failed sub-agent (up to 3 attempts) while other sub-agents continue, then aggregate all results.
- **FR-007**: The `execute()` method MUST create git commits after each logical unit of work with conventional commit messages.
- **FR-008**: The `execute()` method MUST run validation (format, lint, test) before considering any task complete.
- **FR-009**: The `execute()` method MUST return an `ImplementationResult` dataclass with files changed, tests added, and commits created.
- **FR-010**: If task file parsing fails, `execute()` MUST raise a descriptive error indicating the format issue.

### Functional Requirements - IssueFixerAgent

- **FR-011**: System MUST provide an `IssueFixerAgent` class that extends `MaverickAgent`.
- **FR-012**: `IssueFixerAgent` MUST have a system prompt focused on minimal, targeted changes to fix specific issues.
- **FR-013**: `IssueFixerAgent` MUST specify allowed tools: Read, Write, Edit, Bash, Glob, Grep, plus GitHub MCP tools for issue interaction.
- **FR-014**: `IssueFixerAgent` MUST implement an `execute()` method that accepts context containing: issue number OR issue data dictionary.
- **FR-015**: The `execute()` method MUST fetch issue details from GitHub when given an issue number.
- **FR-015a**: GitHub API calls MUST retry up to 3 times with exponential backoff on failure, then raise an error with actionable message (e.g., "GitHub rate limit exceeded, retry after X seconds").
- **FR-016**: The `execute()` method MUST analyze the issue to understand the problem and identify affected code.
- **FR-017**: The `execute()` method MUST implement a fix with minimal code changes (no unrelated refactoring).
- **FR-018**: The `execute()` method MUST verify the fix works by running relevant tests or reproduction steps.
- **FR-019**: The `execute()` method MUST create a git commit referencing the issue number in the commit message.
- **FR-020**: The `execute()` method MUST return a `FixResult` dataclass with issue reference, changes made, and verification results.
- **FR-021**: The `execute()` method MUST run validation (format, lint, test) before considering the fix complete.

### Functional Requirements - Shared

- **FR-022**: Both agents MUST follow project conventions documented in CLAUDE.md if present.
- **FR-023**: Both agents MUST produce conventional commit messages following the pattern: `type(scope): description`.
- **FR-024**: Both agents MUST handle validation failures by attempting auto-fix up to 3 times before failing.
- **FR-024a**: Both agents MUST auto-recover from common git failures: stash/unstash for dirty index, retry after fixing pre-commit hook issues. Merge conflicts MUST fail with descriptive error.
- **FR-025**: Both agents MUST provide machine-parseable output (JSON-structured) that can be deserialized into result dataclasses.

### Key Entities

- **ImplementerAgent**: Concrete agent specializing in task implementation. Extends MaverickAgent with implementation-focused system prompt and tools. Executes tasks from structured task lists with TDD approach.
- **IssueFixerAgent**: Concrete agent specializing in issue resolution. Extends MaverickAgent with fix-focused system prompt and tools. Fetches issues, implements minimal fixes, and verifies resolution.
- **ImplementationResult**: Value object extending AgentResult for implementation outcomes. Contains files changed, tests added/modified, commits created, and task completion status.
- **FixResult**: Value object extending AgentResult for fix outcomes. Contains issue reference, changes made, verification results, and fix status.
- **ImplementerContext**: Context object for implementation containing task file path or description, branch name, and optional configuration.
- **IssueFixerContext**: Context object for issue fixing containing issue number or data dictionary, and optional configuration.
- **TaskFile**: Parsed representation of a tasks.md file with individual task objects, priorities, dependencies, and parallel markers.
- **Task**: Individual task from a task file with description, priority, dependencies, and execution status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Developers can execute a complete task file with multiple tasks through a single method call.
- **SC-002**: Implementation tasks result in working code that passes all project validation checks.
- **SC-003**: Issue fixes resolve the described problem with minimal, targeted code changes (under 100 lines for typical bugs).
- **SC-004**: All commits produced by both agents follow conventional commit format and pass pre-commit hooks.
- **SC-005**: Task execution completes within 5 minutes per task for typical implementation work.
- **SC-006**: Issue fixes complete within 10 minutes for typical bugs.
- **SC-007**: Validation failures are auto-corrected in 80%+ of cases within 3 retry attempts.
- **SC-008**: Result dataclasses can be serialized to JSON and deserialized without data loss.
- **SC-009**: IssueFixerAgent successfully fetches and parses GitHub issue details for any valid issue number.

## Assumptions

- The base `MaverickAgent` class exists and provides the abstract interface (from feature 002-base-agent).
- `AgentResult` and `AgentContext` dataclasses are available from the base agent module.
- Git is installed and the working directory is a git repository.
- Task files follow the `.specify` tasks.md format: checkbox items with `[ ]` or `[x]`, task IDs like `[T001]`, optional `P:` prefix for parallel execution markers.
- GitHub CLI (`gh`) is installed and authenticated for issue fetching.
- Project validation commands (format, lint, test) are configured via pyproject.toml or similar.
- CLAUDE.md is located at the repository root if it exists.
- MultiEdit tool is available for batch file edits (or falls back to multiple Edit calls).
- GitHub MCP tools are available for IssueFixerAgent (issue read, comment).

## Dependencies

- Feature 002-base-agent: `MaverickAgent`, `AgentResult`, `AgentContext` classes
- Claude Agent SDK: Core AI interaction capability
- Pydantic: For dataclass validation and serialization
- Git CLI: For commits and branch operations
- GitHub CLI: For issue fetching and interaction
- GitHub MCP Server: For issue-related tool access (optional, can fall back to CLI)
