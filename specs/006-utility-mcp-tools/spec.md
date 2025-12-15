# Feature Specification: Utility MCP Tools

**Feature Branch**: `006-utility-mcp-tools`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Create custom MCP tools for notifications, git utilities, and validation in Maverick using Claude Agent SDK's in-process MCP server pattern"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Receive Workflow Progress Notifications (Priority: P1)

During long-running workflows like FlyWorkflow or RefuelWorkflow, users need to receive push notifications about workflow progress without watching the terminal. An agent uses `send_workflow_update` to notify users when major workflow stages complete (implementation done, code review started, validation passed, etc.).

**Why this priority**: Workflows can run for extended periods. Notifications enable users to context-switch to other work while staying informed of progress, directly improving user experience.

**Independent Test**: Can be fully tested by invoking `send_workflow_update` with a workflow stage and message, then verifying the notification is delivered to the configured ntfy.sh topic.

**Acceptance Scenarios**:

1. **Given** ntfy.sh is configured with a topic, **When** agent calls `send_workflow_update` with stage="implementation" and message="Task 3 of 5 completed", **Then** a notification is sent with appropriate formatting and the tool returns success
2. **Given** ntfy.sh is configured, **When** agent calls `send_workflow_update` with stage="error" and message="Validation failed", **Then** a high-priority notification is sent with error-appropriate styling
3. **Given** ntfy.sh is NOT configured, **When** agent calls `send_workflow_update`, **Then** tool returns success with a message indicating notifications are disabled (graceful degradation)

---

### User Story 2 - Commit Changes with Conventional Commits (Priority: P1)

After an agent makes code changes, it needs to commit those changes following the project's conventional commit format. The agent uses `git_commit` to create properly formatted commits with type, scope, and description.

**Why this priority**: Every workflow that modifies code requires the ability to commit changes. This is a fundamental operation for all implementation workflows.

**Independent Test**: Can be fully tested by making a file change, calling `git_commit` with type="feat", scope="tools", and message="add notification support", then verifying a properly formatted commit is created.

**Acceptance Scenarios**:

1. **Given** staged changes exist, **When** agent calls `git_commit` with type="feat", scope="api", message="add new endpoint", **Then** a commit is created with message "feat(api): add new endpoint"
2. **Given** staged changes exist, **When** agent calls `git_commit` with type="fix" and message="correct validation" (no scope), **Then** a commit is created with message "fix: correct validation"
3. **Given** no staged changes exist, **When** agent calls `git_commit`, **Then** tool returns an error indicating nothing to commit
4. **Given** staged changes exist and breaking=true, **When** agent calls `git_commit`, **Then** commit message includes "!" after type/scope (e.g., "feat(api)!: breaking change")

---

### User Story 3 - Run Project Validation Suite (Priority: P1)

Before creating a PR or finalizing changes, agents need to run the project's validation commands (format, lint, build, test) and understand which validations passed or failed. The agent uses `run_validation` to execute validations and `parse_validation_output` to interpret results.

**Why this priority**: Validation is a mandatory step in both FlyWorkflow and RefuelWorkflow before PR submission. Automated validation with structured output enables iterative fixing.

**Independent Test**: Can be fully tested by introducing a linting error, calling `run_validation` with type="lint", then verifying the tool returns failure with parseable output.

**Acceptance Scenarios**:

1. **Given** code with no issues, **When** agent calls `run_validation` with types=["format", "lint", "test"], **Then** tool returns success with individual results for each validation type
2. **Given** code with lint errors, **When** agent calls `run_validation` with types=["lint"], **Then** tool returns failure with the raw lint output
3. **Given** validation output from a failed lint run, **When** agent calls `parse_validation_output` with output and type="lint", **Then** tool returns structured list of errors with file, line, and message
4. **Given** validation commands are not configured, **When** agent calls `run_validation`, **Then** tool returns an error indicating missing configuration

---

### User Story 4 - Push Changes to Remote (Priority: P2)

After committing changes, agents need to push the current branch to the remote repository. The agent uses `git_push` to push commits, optionally setting up upstream tracking.

**Why this priority**: Pushing is required to share changes and create PRs, but only after commits are created. It's a dependent step in the workflow.

**Independent Test**: Can be fully tested by creating a commit on a test branch, calling `git_push`, and verifying the remote branch is updated.

**Acceptance Scenarios**:

1. **Given** a branch with unpushed commits, **When** agent calls `git_push`, **Then** commits are pushed and tool returns success with pushed commit count
2. **Given** a new branch with no upstream, **When** agent calls `git_push` with set_upstream=true, **Then** branch is pushed and upstream is configured
3. **Given** the remote is unreachable, **When** agent calls `git_push`, **Then** tool returns an error with the network failure message

---

### User Story 5 - Get Branch and Diff Information (Priority: P2)

Agents need to understand the current git state before making decisions about commits and PRs. The `git_current_branch` and `git_diff_stats` tools provide this context.

**Why this priority**: Branch and diff awareness is necessary context for workflow decisions but is supplementary to the core modification operations.

**Independent Test**: Can be fully tested by checking out a known branch, making changes, and verifying `git_current_branch` returns the branch name and `git_diff_stats` returns accurate statistics.

**Acceptance Scenarios**:

1. **Given** the current branch is "feature-x", **When** agent calls `git_current_branch`, **Then** tool returns "feature-x"
2. **Given** changes exist in 3 files with 50 insertions and 20 deletions, **When** agent calls `git_diff_stats`, **Then** tool returns { files_changed: 3, insertions: 50, deletions: 20 }
3. **Given** no changes exist, **When** agent calls `git_diff_stats`, **Then** tool returns { files_changed: 0, insertions: 0, deletions: 0 }
4. **Given** not in a git repository, **When** agent calls `git_current_branch`, **Then** tool returns an error indicating not a git repository

---

### User Story 6 - Create Feature Branches (Priority: P2)

When starting work on a new issue or feature, agents need to create and checkout a new branch from a specified base. The `git_create_branch` tool provides this capability.

**Why this priority**: Branch creation initiates new work but is only needed at workflow start. Many workflows operate on existing branches.

**Independent Test**: Can be fully tested by calling `git_create_branch` with a branch name, then verifying the branch exists and is checked out.

**Acceptance Scenarios**:

1. **Given** on main branch, **When** agent calls `git_create_branch` with name="feature-123", **Then** branch "feature-123" is created from main and checked out
2. **Given** on main branch, **When** agent calls `git_create_branch` with name="fix-456" and base="develop", **Then** branch is created from develop and checked out
3. **Given** a branch with that name already exists, **When** agent calls `git_create_branch`, **Then** tool returns an error indicating branch exists

---

### User Story 7 - Send Custom Notifications (Priority: P3)

Agents may need to send arbitrary notifications beyond workflow updates (e.g., alerting about security issues, notifying about manual intervention needed). The `send_notification` tool provides full control over notification parameters.

**Why this priority**: Custom notifications are useful for edge cases but most notification needs are covered by `send_workflow_update`.

**Independent Test**: Can be fully tested by calling `send_notification` with custom title, message, priority, and tags, then verifying the notification is delivered with all parameters.

**Acceptance Scenarios**:

1. **Given** ntfy.sh is configured, **When** agent calls `send_notification` with title="Security Alert", message="Credential detected in code", priority="urgent", tags=["warning", "security"], **Then** notification is sent with all specified parameters
2. **Given** ntfy.sh is configured, **When** agent calls `send_notification` with only message="Quick update", **Then** notification is sent with defaults (priority="default", no tags)
3. **Given** ntfy.sh is NOT configured, **When** agent calls `send_notification`, **Then** tool returns success indicating notifications disabled

---

### Edge Cases

- **ntfy.sh server unreachable**: Return success with warning message after brief retry (1-2 attempts with 2s timeout); log warning for debugging; never block workflow
- **Detached HEAD state**: `git_current_branch` returns "(detached)"; commits allowed; `git_push` returns warning that push requires a branch
- **Validation timeout**: Kill process after configured timeout, return error with "timeout" status and any partial output captured
- **Large validation output**: Truncate to first 50 errors with summary count (e.g., "Showing 50 of 1,247 errors"); configurable limit
- **Git credentials missing/expired**: Detect authentication failure patterns, return structured error with "authentication_required" status and remediation hint (e.g., "Run 'gh auth login' or configure git credentials")
- **Outside git repository**: Git tools return clear error with "not_a_repository" status (covered by FR-019)

## Requirements *(mandatory)*

### Functional Requirements

#### Factory Functions

- **FR-001**: System MUST provide a `create_notification_tools_server()` factory function that returns a configured MCP server with notification tools
- **FR-002**: System MUST provide a `create_git_tools_server()` factory function that returns a configured MCP server with git utility tools
- **FR-003**: System MUST provide a `create_validation_tools_server()` factory function that returns a configured MCP server with validation tools
- **FR-004**: Each factory function MUST accept optional configuration parameters for customization

#### Tool Implementation

- **FR-005**: All tools MUST use the Claude Agent SDK's `@tool` decorator pattern
- **FR-006**: All tools MUST return MCP-formatted responses with content array containing text blocks
- **FR-007**: All tools MUST handle errors gracefully and return `isError: true` with helpful error messages
- **FR-008**: All tools MUST log operations using the standard logging module
- **FR-009**: All tools MUST have clear input schemas with type hints for all parameters

#### Notification Tools

- **FR-010**: `send_notification` MUST accept parameters: message (required), title (optional), priority (optional, one of: min, low, default, high, urgent), tags (optional, list of strings)
- **FR-011**: `send_workflow_update` MUST accept parameters: stage (required), message (required), workflow_name (optional)
- **FR-012**: Notification tools MUST gracefully handle missing ntfy.sh configuration by returning success with "notifications disabled" message
- **FR-013**: Notification tools MUST support configurable ntfy.sh server URL and topic via configuration
- **FR-013a**: Notification tools MUST gracefully handle network failures with brief retry (1-2 attempts, 2s timeout per attempt), returning success with warning message and logging the failure

#### Git Utility Tools

- **FR-014**: `git_current_branch` MUST return the current branch name or error if not in a git repository
- **FR-015**: `git_create_branch` MUST accept parameters: name (required), base (optional, defaults to current branch)
- **FR-016**: `git_commit` MUST accept parameters: message (required), type (optional, for conventional commits), scope (optional), breaking (optional, boolean)
- **FR-017**: `git_push` MUST accept parameters: set_upstream (optional, boolean, default false)
- **FR-018**: `git_diff_stats` MUST return structured data: files_changed (int), insertions (int), deletions (int)
- **FR-019**: Git tools MUST handle non-git-repository context gracefully with clear error messages
- **FR-019a**: `git_current_branch` MUST return "(detached)" when in detached HEAD state
- **FR-019b**: `git_push` MUST return an error with helpful message when in detached HEAD state, suggesting branch creation
- **FR-019c**: `git_push` MUST detect authentication failures and return structured error with "authentication_required" status and remediation hint

#### Validation Tools

- **FR-020**: `run_validation` MUST accept parameters: types (required, list of validation types: format, lint, build, test)
- **FR-021**: `run_validation` MUST execute configured validation commands for each requested type
- **FR-022**: `run_validation` MUST return per-type results indicating success/failure and raw output
- **FR-023**: `parse_validation_output` MUST accept parameters: output (required, string), type (required, validation type)
- **FR-024**: `parse_validation_output` MUST return structured errors with file, line, column (if available), and message
- **FR-025**: Validation commands MUST be configurable via project configuration (e.g., pyproject.toml, maverick.yaml)
- **FR-026**: `run_validation` MUST support timeout configuration with sensible defaults (5 minutes)
- **FR-026a**: `run_validation` MUST kill timed-out processes and return error with "timeout" status, including any partial output captured before timeout
- **FR-027**: `parse_validation_output` MUST truncate results to configurable limit (default 50 errors) and include total error count in response

### Key Entities

- **MCPServer**: The configured server instance returned by each factory function, containing registered tools
- **ToolResponse**: MCP-formatted response object with `content` array containing `TextContent` blocks, and optional `isError` flag
- **NotificationConfig**: Configuration for ntfy.sh integration: server_url, topic, default_priority
- **GitState**: Represents current git state: branch, has_changes, staged_files, unstaged_files
- **ValidationConfig**: Configuration for validation commands: format_cmd, lint_cmd, build_cmd, test_cmd, timeout
- **ValidationResult**: Result of a validation run: type, success, output, errors (if parsed)
- **ParsedError**: Structured error from validation output: file, line, column, message, severity

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 9 specified tools are implemented and pass unit tests with 100% coverage of success and error paths
- **SC-002**: Tools execute within 2 seconds for simple operations (git_current_branch, send_notification)
- **SC-003**: Validation tools support timeout up to 10 minutes for long-running test suites
- **SC-004**: All three factory functions can be instantiated and tools registered without errors
- **SC-005**: Notification tools successfully degrade to no-op when ntfy.sh is not configured
- **SC-006**: Git tools work correctly in any valid git repository context
- **SC-007**: Validation output parsing correctly extracts errors from common linter output formats (ruff, mypy)
- **SC-008**: Error messages are clear enough that users can diagnose and fix issues without additional support in 90% of cases
- **SC-009**: FlyWorkflow and RefuelWorkflow can successfully use these tools for their respective operations

## Clarifications

### Session 2025-12-15

- Q: When ntfy.sh server is configured but unreachable, how should notification tools behave? → A: Return success with warning message after brief retry (graceful degradation)
- Q: When validation tools produce very large output (thousands of errors), how should it be handled? → A: Truncate to first N errors (e.g., 50) with summary count of remaining
- Q: How should git tools behave in detached HEAD state? → A: Return "(detached)" for git_current_branch; allow commits but warn on push
- Q: When a validation command times out, what should happen? → A: Kill process after timeout, return error with "timeout" status and partial output
- Q: When git credentials are missing or expired during push, how should the tool respond? → A: Detect auth failure, return structured error with "authentication_required" status and remediation hint

## Assumptions

- ntfy.sh is an optional dependency; workflows function without it
- Git is installed and available in the execution environment
- Commands are executed within a git repository context (for git tools)
- Validation commands are standard Python tooling (ruff, mypy, pytest) unless configured otherwise
- The Claude Agent SDK's `@tool` decorator and `create_sdk_mcp_server()` function are available from the `claude-agent-sdk` package
- Tool responses follow MCP (Model Context Protocol) format conventions
- Network access is available for ntfy.sh notifications (when configured)
