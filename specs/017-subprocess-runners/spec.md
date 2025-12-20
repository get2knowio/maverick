# Feature Specification: Subprocess Execution Module

**Feature Branch**: `017-subprocess-runners`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Create a spec for a subprocess execution module in Maverick that runs external commands and parses their output."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Execute External Commands Safely (Priority: P1)

A workflow needs to run arbitrary shell commands (like `ruff check`, `pytest`, `npm build`) and capture their results to determine next steps. The workflow must handle commands that succeed, fail, or timeout without crashing the application.

**Why this priority**: This is the foundational capability that all other runners depend on. Without safe command execution, no other functionality can work.

**Independent Test**: Can be fully tested by running simple commands like `echo "test"` and `ls` and verifying return codes, stdout, stderr, and timing are correctly captured.

**Acceptance Scenarios**:

1. **Given** a valid command like `echo "hello"`, **When** the command is executed, **Then** the result contains returncode 0, stdout "hello\n", empty stderr, and duration in milliseconds
2. **Given** a command that produces stderr output, **When** the command is executed, **Then** both stdout and stderr are captured separately
3. **Given** a command that takes longer than the specified timeout, **When** the timeout is reached, **Then** the command is terminated and the result indicates it timed out
4. **Given** an invalid command that doesn't exist, **When** execution is attempted, **Then** the result contains a non-zero return code with appropriate error information

---

### User Story 2 - Stream Command Output in Real-Time (Priority: P1)

A workflow running long-lived commands (like `npm install` or `cargo build`) needs to display progress to users in real-time rather than waiting for the command to complete entirely.

**Why this priority**: Real-time feedback is essential for user experience during long-running operations. Tied with P1 as it's a core capability.

**Independent Test**: Can be tested by running a command that produces multiple lines of output over time and verifying each line is yielded as it becomes available.

**Acceptance Scenarios**:

1. **Given** a command that outputs multiple lines over several seconds, **When** streaming is enabled, **Then** each line is yielded as an async iterator item as soon as it's available
2. **Given** a streaming command that times out, **When** the timeout is reached, **Then** the stream terminates cleanly with a timeout indicator
3. **Given** a streaming command that fails mid-execution, **When** the failure occurs, **Then** partial output is preserved and the error is communicated

---

### User Story 3 - Run Validation Stages Sequentially (Priority: P2)

A workflow needs to run a series of validation checks (format, lint, type-check, test, build) in order, stopping on first failure or continuing through all stages, with structured results showing which stages passed or failed.

**Why this priority**: Validation is a core workflow step but depends on basic command execution being functional first.

**Independent Test**: Can be tested by defining 3 validation stages where the second one fails, and verifying that results show stage 1 passed, stage 2 failed with captured output, and stage 3 was not executed (or all ran if configured to continue).

**Acceptance Scenarios**:

1. **Given** a list of validation stages with all passing commands, **When** validation is run, **Then** all stages execute and overall success is true
2. **Given** a validation stage that fails, **When** validation encounters the failure, **Then** results show which stage failed and include the error output
3. **Given** a fixable validation stage that fails, **When** the stage has a fix_command defined, **Then** the fix is attempted and the stage is re-run
4. **Given** validation output in a known format (Python traceback, ESLint JSON), **When** results are returned, **Then** errors are parsed into structured data with file, line, and message

---

### User Story 4 - Get GitHub Issues and Pull Requests (Priority: P2)

A workflow needs to retrieve information about GitHub issues and pull requests to determine what work to do (RefuelWorkflow) or to manage PR lifecycle (FlyWorkflow).

**Why this priority**: Essential for the RefuelWorkflow to discover issues and for FlyWorkflow to manage PRs. Depends on basic command execution.

**Independent Test**: Can be tested by mocking `gh` CLI output or using a test repository to fetch a known issue and verify all fields are correctly parsed.

**Acceptance Scenarios**:

1. **Given** a valid issue number, **When** get_issue is called, **Then** a structured GitHubIssue object is returned with number, title, body, labels, state, assignees, and url
2. **Given** a label filter, **When** list_issues is called, **Then** only issues with that label are returned
3. **Given** `gh` CLI is not installed, **When** any GitHub operation is attempted, **Then** a specific GitHubCLINotFoundError is raised with installation instructions
4. **Given** valid PR parameters, **When** create_pr is called, **Then** a PR is created and a PullRequest object is returned with the PR URL
5. **Given** a PR number, **When** get_pr_checks is called, **Then** a list of CheckStatus objects is returned showing CI status

---

### User Story 5 - Run CodeRabbit Reviews (Priority: P3)

A workflow wants to run CodeRabbit code review on changed files and receive structured findings to display to users or use in decision-making.

**Why this priority**: CodeRabbit is an optional enhancement tool, not critical path. Workflows must function without it.

**Independent Test**: Can be tested by mocking CodeRabbit CLI output and verifying findings are correctly parsed into structured objects.

**Acceptance Scenarios**:

1. **Given** CodeRabbit is installed and files to review, **When** run_review is called, **Then** structured findings are returned with file, line, severity, message, and suggestion
2. **Given** CodeRabbit is NOT installed, **When** run_review is called, **Then** an empty result is returned with a warning message (not error)
3. **Given** specific files to review, **When** run_review is called with file list, **Then** only those files are included in the review scope

---

### Edge Cases

- ~~What happens when a command produces extremely large output (>100MB)?~~ → Resolved: Stream-only mode, never buffer in memory
- ~~How does the system handle commands that ignore SIGTERM and require SIGKILL?~~ → Resolved: SIGTERM + 2s grace period + SIGKILL escalation
- ~~What happens when the working directory specified doesn't exist?~~ → Resolved: Fail immediately with WorkingDirectoryError
- ~~How are environment variables handled - inherit from parent or isolated?~~ → Resolved: Merge mode - inherit by default, allow add/override
- ~~What happens when `gh` CLI is installed but not authenticated?~~ → Resolved: Fail-fast on first use, raise GitHubAuthError
- ~~How does validation handle stages with no stdout (silent success)?~~ → Resolved: Empty stdout with returncode 0 = stage passed; StageResult.output will be empty string
- ~~What happens when CodeRabbit produces malformed JSON output?~~ → Resolved: Log warning, return CodeRabbitResult with empty findings list, raw_output preserved for debugging

## Clarifications

### Session 2025-12-18

- Q: How should the system handle commands with extremely large output (>100MB)? → A: Stream-only mode - always stream large output, never buffer entirely in memory
- Q: Should callers be able to pass custom environment variables to commands? → A: Merge mode - inherit parent env by default, allow caller to add/override specific variables
- Q: How should the system handle commands that ignore SIGTERM during timeout? → A: Escalate to SIGKILL - send SIGTERM, wait 2s grace period, then SIGKILL if still running
- Q: When should the system detect and report `gh` CLI authentication issues? → A: Fail-fast on first use - check auth status once when GitHubCLIRunner is first used, raise GitHubAuthError immediately
- Q: How should the system handle a non-existent working directory? → A: Fail immediately - raise WorkingDirectoryError before attempting command execution
- Q: How does validation handle stages with no stdout (silent success)? → A: Empty stdout with returncode 0 indicates success. StageResult.output will be an empty string, and StageResult.passed will be true.
- Q: What happens when CodeRabbit produces malformed JSON output? → A: Graceful degradation - log a warning, return CodeRabbitResult with empty findings list, preserve raw_output for debugging. Do not raise an exception.

## Requirements *(mandatory)*

### Functional Requirements

#### CommandRunner (Base)

- **FR-001**: System MUST execute arbitrary commands passed as a list of strings (no shell interpretation by default)
- **FR-002**: System MUST capture returncode, stdout, stderr, and execution duration for every command
- **FR-003**: System MUST support a configurable timeout with default of 300 seconds
- **FR-004**: System MUST terminate commands that exceed their timeout using graceful escalation: send SIGTERM, wait 2 second grace period, then SIGKILL if process still running; mark results as timed_out
- **FR-005**: System MUST support specifying a working directory for command execution; MUST validate directory exists before execution and raise WorkingDirectoryError if not found
- **FR-006**: System MUST provide async streaming of stdout lines for long-running commands
- **FR-007**: System MUST handle commands with large output (>100MB) via streaming only - never buffer entire output in memory; callers must use streaming API for large-output commands
- **FR-007a**: System MUST inherit parent process environment variables by default and allow callers to add or override specific variables via an optional env parameter

#### ValidationRunner

- **FR-008**: System MUST execute validation stages in sequence, tracking pass/fail status for each
- **FR-009**: System MUST support stages marked as "fixable" with an associated fix_command
- **FR-010**: System MUST automatically attempt fix_command when a fixable stage fails, then re-run the stage
- **FR-011**: System MUST parse Python tracebacks into structured error data (file, line, message)
- **FR-012**: System MUST parse Rust compiler errors into structured error data
- **FR-013**: System MUST parse ESLint JSON output into structured error data
- **FR-014**: System MUST return overall success only when all stages pass

#### GitHubCLIRunner

- **FR-015**: System MUST fetch individual issues by number with all metadata (title, body, labels, state, assignees, url)
- **FR-016**: System MUST list issues with filtering by label, state, and limit
- **FR-017**: System MUST create pull requests with title, body, base branch, head branch, and draft status
- **FR-018**: System MUST fetch individual pull requests with all metadata including mergeable status
- **FR-019**: System MUST fetch PR check statuses (CI results) for a given PR
- **FR-020**: System MUST raise GitHubCLINotFoundError if `gh` command is not available
- **FR-021**: System MUST check `gh` authentication status on first use of GitHubCLIRunner and raise GitHubAuthError immediately if not authenticated (fail-fast pattern)

#### CodeRabbitRunner

- **FR-022**: System MUST run CodeRabbit review and parse findings into structured data
- **FR-023**: System MUST return empty results with warning (not error) if CodeRabbit is not installed
- **FR-024**: System MUST support filtering review to specific files
- **FR-025**: System MUST capture raw output alongside parsed findings for debugging

### Key Entities

- **CommandResult**: Represents the outcome of a command execution - returncode, stdout, stderr, duration_ms, timed_out flag
- **ValidationStage**: Defines a validation step - name, command to run, whether it's fixable, optional fix_command
- **ValidationOutput**: Aggregated validation results - overall success flag, list of individual stage results
- **StageResult**: Single stage outcome - stage name, passed flag, output content, duration_ms
- **ParsedError**: Structured error from parsed output - file path, line number, column, message, severity
- **GitHubIssue**: Issue representation - number, title, body, labels list, state, assignees list, url
- **PullRequest**: PR representation - number, title, body, state, url, head_branch, base_branch, mergeable status
- **CheckStatus**: CI check result - name, status (pending/success/failure), conclusion, url
- **CodeRabbitResult**: Review outcome - findings list, summary text, raw_output
- **CodeRabbitFinding**: Individual finding - file, line, severity, message, suggestion

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Commands execute and return results within 100ms overhead of the actual command duration
- **SC-002**: Streaming output delivers lines within 50ms of the subprocess producing them
- **SC-003**: 100% of validation stage failures include parseable error information when output matches known formats
- **SC-004**: GitHub operations correctly parse 100% of standard `gh` CLI JSON output fields
- **SC-005**: System gracefully handles missing optional tools (CodeRabbit) in 100% of cases without crashing
- **SC-006**: Commands exceeding timeout are terminated within 1 second of timeout expiration
- **SC-007**: Memory usage remains stable (no leaks) when processing commands with >10MB output

## Assumptions

- Commands are passed as argument lists, not shell strings - the caller is responsible for proper argument splitting
- The system inherits environment variables from the parent process by default
- `gh` CLI uses JSON output format (--json flag) for structured data retrieval
- Python 3.10+ asyncio subprocess support is available
- File paths in parsed errors are relative to the working directory where commands are executed
- CodeRabbit CLI outputs findings in a parseable format (JSON or structured text)
- Validation stage fix_commands are idempotent and safe to run automatically
