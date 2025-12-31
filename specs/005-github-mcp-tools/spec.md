# Feature Specification: GitHub MCP Tools Integration

**Feature Branch**: `005-github-mcp-tools`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Create custom MCP tools for GitHub integration in Maverick using Claude Agent SDK's in-process MCP server pattern"

## Clarifications

### Session 2025-12-14

- Q: How should the tools handle GitHub API rate limiting? → A: Return error with retry-after info (let caller decide retry strategy)
- Q: How should `github_get_pr_diff` handle very large diffs? → A: Truncate at configurable limit (default 100KB) with warning in response
- Q: When should the system verify `gh` CLI availability? → A: At server creation time (fail fast on `create_github_tools_server()`)
- Q: What format should successful tool responses use? → A: Structured JSON object with typed fields (e.g., `{"pr_number": 123, "url": "..."}`)
- Q: How should tools handle missing git repository context? → A: Fail at server creation with clear error (same as missing `gh` CLI)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create Pull Request via Agent (Priority: P1)

An agent working on implementing a feature needs to create a pull request to submit their work. The agent uses the `github_create_pr` tool to create a PR with a title, description body, base branch, head branch, and optionally as a draft.

**Why this priority**: Creating PRs is the primary output mechanism for the FlyWorkflow and is essential for any code changes to be reviewed and merged.

**Independent Test**: Can be fully tested by having an agent invoke the tool with valid parameters on a test branch and verifying a PR is created in the repository.

**Acceptance Scenarios**:

1. **Given** a feature branch with commits ahead of main, **When** agent calls `github_create_pr` with title, body, base="main", head="feature-branch", **Then** a PR is created and the tool returns the PR URL and number
2. **Given** valid parameters including draft=true, **When** agent calls `github_create_pr`, **Then** a draft PR is created that is not ready for review
3. **Given** the head branch does not exist, **When** agent calls `github_create_pr`, **Then** tool returns an error response with isError=true and helpful message

---

### User Story 2 - List and Retrieve Issues for RefuelWorkflow (Priority: P1)

The RefuelWorkflow needs to discover open issues with specific labels to select work items. An agent uses `github_list_issues` to find issues and `github_get_issue` to get detailed information about specific issues.

**Why this priority**: Issue discovery is the entry point for RefuelWorkflow and is required before any issue-fixing work can begin.

**Independent Test**: Can be fully tested by calling `github_list_issues` with label and state filters, then calling `github_get_issue` on returned issue numbers.

**Acceptance Scenarios**:

1. **Given** a repository with issues labeled "tech-debt", **When** agent calls `github_list_issues` with label="tech-debt" and state="open", **Then** tool returns JSON array of matching issues with number, title, and labels
2. **Given** a valid issue number, **When** agent calls `github_get_issue` with that number, **Then** tool returns full issue details including body, comments count, assignees, and labels
3. **Given** a non-existent issue number, **When** agent calls `github_get_issue`, **Then** tool returns an error response with isError=true

---

### User Story 3 - Check PR Status for Merge Readiness (Priority: P2)

Before merging or finalizing a PR, agents need to verify the PR status including CI check results, review status, and mergeability. The `github_pr_status` tool provides this consolidated view.

**Why this priority**: PR status checking is needed for workflow completion but only after PR creation and review activities.

**Independent Test**: Can be fully tested by creating a test PR and calling `github_pr_status` to verify it returns check statuses, review counts, and mergeable state.

**Acceptance Scenarios**:

1. **Given** a PR with passing checks and approving reviews, **When** agent calls `github_pr_status`, **Then** tool returns status showing checks passed, reviews approved, and mergeable=true
2. **Given** a PR with failing checks, **When** agent calls `github_pr_status`, **Then** tool returns status showing which checks failed with their names
3. **Given** a PR with merge conflicts, **When** agent calls `github_pr_status`, **Then** tool returns mergeable=false with conflict indication

---

### User Story 4 - Get PR Diff for Code Review (Priority: P2)

During code review workflows, agents need to retrieve the diff for a pull request to analyze changes. The `github_get_pr_diff` tool provides the complete diff.

**Why this priority**: Diff retrieval supports code review functionality which occurs after implementation but before merge.

**Independent Test**: Can be fully tested by calling `github_get_pr_diff` on a known PR and verifying the diff content is returned.

**Acceptance Scenarios**:

1. **Given** a valid PR number, **When** agent calls `github_get_pr_diff`, **Then** tool returns the complete diff showing all file changes
2. **Given** a non-existent PR number, **When** agent calls `github_get_pr_diff`, **Then** tool returns an error response with isError=true

---

### User Story 5 - Manage Issue Labels (Priority: P3)

Workflows need to add labels to issues and PRs for tracking status (e.g., "in-progress", "needs-review"). The `github_add_labels` tool enables this.

**Why this priority**: Label management is supplementary organization that enhances but doesn't block core workflows.

**Independent Test**: Can be fully tested by calling `github_add_labels` on a test issue and verifying labels are added.

**Acceptance Scenarios**:

1. **Given** a valid issue number and label names, **When** agent calls `github_add_labels`, **Then** labels are added to the issue and tool returns confirmation
2. **Given** a label that doesn't exist in the repository, **When** agent calls `github_add_labels`, **Then** the label is created and added (default GitHub behavior)

---

### User Story 6 - Close Issues After Resolution (Priority: P3)

After fixing an issue, RefuelWorkflow needs to close it with an optional comment explaining the resolution. The `github_close_issue` tool provides this capability.

**Why this priority**: Issue closure is the final step of issue-fixing workflows but can be done manually if needed.

**Independent Test**: Can be fully tested by calling `github_close_issue` on a test issue and verifying it is closed with the comment.

**Acceptance Scenarios**:

1. **Given** a valid open issue number, **When** agent calls `github_close_issue` with a comment, **Then** the issue is closed and the comment is added
2. **Given** a valid open issue number, **When** agent calls `github_close_issue` without a comment, **Then** the issue is closed without adding a comment
3. **Given** an already closed issue, **When** agent calls `github_close_issue`, **Then** tool returns success (idempotent operation)

---

### Edge Cases

- **Missing gh CLI**: `create_github_tools_server()` raises exception immediately if `gh` is not installed or not authenticated (fail-fast)
- **Rate Limiting**: Tools return error with `isError: true` and include retry-after information when rate limited; caller decides retry strategy
- **Missing Repo Context**: `create_github_tools_server()` raises exception if not in a git repository with configured remote (fail-fast)
- **Large Diffs**: `github_get_pr_diff` truncates output at configurable limit (default 100KB) and includes warning when truncated
- **Network Errors**: Tools surface underlying `gh` CLI network errors via `isError: true` with original message (no special handling beyond FR-005)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a `create_github_tools_server()` factory function that returns a configured MCP server with all GitHub tools
- **FR-002**: All tools MUST use the Claude Agent SDK's `@tool` decorator pattern
- **FR-003**: All tools MUST wrap GitHub CLI (`gh`) commands for reliability and consistency
- **FR-004**: Each tool MUST return MCP-formatted responses with content array containing structured JSON (typed fields, not free-form text)
- **FR-005**: Each tool MUST handle errors gracefully and return `isError: true` with helpful error messages
- **FR-006**: Each tool MUST log operations for debugging using the standard logging module
- **FR-007**: `github_create_pr` MUST accept parameters: title (required), body (required), base (required), head (required), draft (optional, default false)
- **FR-008**: `github_list_issues` MUST accept parameters: label (optional), state (optional, default "open"), limit (optional, default 30)
- **FR-009**: `github_get_issue` MUST accept parameter: issue_number (required)
- **FR-010**: `github_get_pr_diff` MUST accept parameters: pr_number (required), max_size (optional, default 100KB); truncate with warning if exceeded
- **FR-011**: `github_add_labels` MUST accept parameters: issue_number (required), labels (required, list of strings)
- **FR-012**: `github_close_issue` MUST accept parameters: issue_number (required), comment (optional)
- **FR-013**: `github_pr_status` MUST accept parameter: pr_number (required) and return checks status, review status, and mergeable state
- **FR-014**: All tools MUST have clear input schemas with type hints for all parameters
- **FR-015**: `create_github_tools_server()` MUST verify at creation time: (a) `gh` CLI installed and authenticated, (b) running in git repo with remote; raise `GitHubToolsError` if not
- **FR-016**: When rate limited, tools MUST return `isError: true` with retry-after duration extracted from GitHub response; no automatic retry

### Key Entities

- **MCPServer**: The configured server instance returned by the factory function, containing all registered tools
- **ToolResponse**: MCP-formatted response object with `content` array containing structured JSON (typed fields like `pr_number`, `url`, `state`), and optional `isError` flag
- **GitHubTool**: Individual tool functions decorated with `@tool`, each wrapping specific `gh` CLI commands
- **PullRequest**: Represents a GitHub PR with properties: number, title, body, state, checks, reviews, mergeable
- **Issue**: Represents a GitHub issue with properties: number, title, body, state, labels, assignees, comments

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 7 specified tools are implemented and pass unit tests with 100% coverage of success and error paths
- **SC-002**: Tools execute within 5 seconds for typical operations (list issues, get PR status)
- **SC-003**: Error messages are clear enough that users can diagnose and fix issues without additional support in 90% of cases
- **SC-004**: The factory function can be instantiated and tools registered without errors
- **SC-005**: FlyWorkflow can successfully create PRs using the `github_create_pr` tool
- **SC-006**: RefuelWorkflow can successfully list, get, and close issues using the respective tools
- **SC-007**: Tools correctly surface GitHub CLI errors with original error messages preserved

## Assumptions

- GitHub CLI (`gh`) is installed and authenticated in the execution environment
- Commands are executed within a git repository context with a configured remote
- Standard GitHub API rate limits apply (authenticated: 5000 requests/hour)
- The Claude Agent SDK's `@tool` decorator and `create_sdk_mcp_server()` function are available from the `claude-agent-sdk` package
- Tool responses follow MCP (Model Context Protocol) format conventions
