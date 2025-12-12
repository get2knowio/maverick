# Feature Specification: RefuelWorkflow - Tech Debt and Issue Fixing

**Feature Branch**: `010-refuel-workflow`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Create a spec for the refuel workflow in Maverick - the tech debt and issue fixing workflow"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Basic Issue Processing (Priority: P1)

A developer wants to clear out tech debt issues from their backlog. They run the RefuelWorkflow which automatically fetches issues labeled "tech-debt" from GitHub, creates branches for each, attempts fixes using AI, validates the fixes, and creates PRs. The developer reviews the summary to see what was accomplished.

**Why this priority**: This is the core value proposition - automated batch processing of tech debt issues. Without this, the workflow has no purpose.

**Independent Test**: Can be fully tested by running the workflow against a repository with labeled issues and verifying branches, fixes, and PRs are created.

**Acceptance Scenarios**:

1. **Given** a repository with 5 issues labeled "tech-debt", **When** a developer runs RefuelWorkflow with default settings, **Then** the system fetches all 5 issues, processes each one, and reports results for all 5.
2. **Given** a repository with no issues matching the label, **When** a developer runs RefuelWorkflow, **Then** the system reports "No issues found" and exits gracefully.
3. **Given** a repository with 3 tech-debt issues, **When** the workflow completes, **Then** each successfully fixed issue has a new PR linking back to the original issue.

---

### User Story 2 - Graceful Failure Handling (Priority: P2)

A developer runs RefuelWorkflow on a batch of issues. Two issues fail to fix (complex bugs, missing dependencies, etc.). The workflow continues processing remaining issues, completes all it can, and provides a clear summary showing which issues succeeded, failed, and why.

**Why this priority**: Resilience is critical for batch operations. Users need confidence that one bad issue won't waste an entire run.

**Independent Test**: Can be tested by including known-unfixable issues in the batch and verifying other issues still complete.

**Acceptance Scenarios**:

1. **Given** 5 issues where 2 have unfixable problems, **When** RefuelWorkflow processes them, **Then** 3 PRs are created and the summary shows 3 fixed, 2 failed with failure reasons.
2. **Given** an issue that causes IssueFixerAgent to error, **When** the workflow encounters this issue, **Then** the error is captured, logged, and the workflow continues to the next issue.
3. **Given** a validation failure on one issue, **When** the workflow detects this, **Then** that issue is marked as failed and the workflow proceeds with remaining issues.

---

### User Story 3 - Configurable Processing (Priority: P3)

A developer wants to limit RefuelWorkflow to only process the 3 oldest issues, process them in parallel for speed, and automatically assign issues to themselves while working on them.

**Why this priority**: Configuration options enhance usability but aren't required for core functionality.

**Independent Test**: Can be tested by configuring max_issues, parallel mode, and auto-assign, then verifying behavior matches settings.

**Acceptance Scenarios**:

1. **Given** 10 issues and max_issues set to 3, **When** RefuelWorkflow runs, **Then** only the 3 highest-priority issues are processed.
2. **Given** parallel processing enabled, **When** RefuelWorkflow runs with 4 issues, **Then** issues are processed concurrently (not sequentially).
3. **Given** auto_assign enabled, **When** an issue begins processing, **Then** the issue is assigned to the current user in GitHub.

---

### User Story 4 - Custom Label Filtering (Priority: P4)

A developer wants to process issues with a custom label like "quick-fix" instead of the default "tech-debt" label.

**Why this priority**: Flexibility in label selection extends the workflow's applicability but has reasonable defaults.

**Independent Test**: Can be tested by creating issues with custom label and verifying only those issues are fetched.

**Acceptance Scenarios**:

1. **Given** issues with labels "tech-debt" and "quick-fix", **When** RefuelWorkflow runs with label="quick-fix", **Then** only issues labeled "quick-fix" are processed.

---

### User Story 5 - Result Reporting and Metrics (Priority: P5)

After RefuelWorkflow completes, a developer reviews the RefuelResult summary showing total issues processed, how many fixed vs failed vs skipped, PR URLs for each fix, and resource usage (time, tokens).

**Why this priority**: Reporting is important for user feedback but comes after core processing works.

**Independent Test**: Can be tested by running workflow and verifying the result object contains all expected fields with accurate data.

**Acceptance Scenarios**:

1. **Given** a completed workflow run, **When** the developer examines RefuelResult, **Then** they see counts for processed/fixed/failed/skipped issues.
2. **Given** 3 successfully created PRs, **When** examining per-issue results, **Then** each includes the PR URL.
3. **Given** a workflow run, **When** examining RefuelResult, **Then** total_time_seconds and token_usage are populated with accurate values.

---

### Edge Cases

- What happens when GitHub API rate limit is exceeded during fetching?
  - The workflow should fail gracefully with a clear error message indicating rate limiting.
- What happens when a branch name conflicts with an existing branch?
  - The workflow should generate a unique branch name variant or skip the issue with an appropriate error.
- What happens when the user lacks permission to create branches/PRs?
  - The workflow should detect permission errors early and report them clearly.
- What happens when an issue has no description or insufficient context?
  - IssueFixerAgent attempts its best fix; if it cannot proceed, the issue is marked as skipped with reason "insufficient context."
- What happens when ValidationWorkflow fails repeatedly on a fix?
  - After a configurable number of retries (default: 2), the issue is marked as failed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a RefuelWorkflow class that orchestrates batch issue processing
- **FR-002**: System MUST fetch issues from GitHub using a configurable label filter (default: "tech-debt")
- **FR-003**: System MUST allow filtering and prioritization of issues by age (oldest first), complexity estimate, and assignee status
- **FR-004**: System MUST support both sequential and parallel processing modes for issues
- **FR-005**: System MUST create a feature branch for each issue being processed
- **FR-006**: System MUST invoke IssueFixerAgent to attempt fixing each issue
- **FR-007**: System MUST run ValidationWorkflow on each attempted fix before PR creation
- **FR-008**: System MUST create a PR linking back to the original issue upon successful fix and validation
- **FR-009**: System MUST continue processing remaining issues when one issue fails
- **FR-010**: System MUST capture and report errors with context for failed issues
- **FR-011**: System MUST return a RefuelResult containing counts of processed, fixed, failed, and skipped issues
- **FR-012**: System MUST include per-issue results with PR URLs (where applicable) in RefuelResult
- **FR-013**: System MUST track and report total execution time in RefuelResult
- **FR-014**: System MUST track and report token usage in RefuelResult
- **FR-015**: System MUST allow configuration of maximum issues to process per run
- **FR-016**: System MUST allow enabling/disabling parallel processing via configuration
- **FR-017**: System MUST allow enabling auto-assignment of issues being worked on
- **FR-018**: System MUST yield progress updates as async generator for TUI consumption (per Maverick architecture)
- **FR-019**: System MUST follow async-first patterns using asyncio (per Maverick core principles)

### Key Entities

- **RefuelWorkflow**: The main orchestrator class that manages the batch issue processing lifecycle
- **RefuelConfig**: Configuration dataclass holding label filter, max issues, parallel mode, auto-assign, and close-on-merge settings
- **RefuelResult**: Result dataclass containing aggregate statistics and per-issue outcomes
- **IssueResult**: Per-issue result containing issue reference, status (fixed/failed/skipped), PR URL, error message, time, and tokens
- **GitHubIssue**: Representation of a GitHub issue with number, title, body, labels, assignees, and created date

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Workflow can process a batch of 10 issues and complete within 30 minutes (assuming average issue complexity)
- **SC-002**: 95% of simple tech-debt issues (formatting, typos, simple refactors) are successfully fixed and pass validation
- **SC-003**: Zero unhandled exceptions cause workflow termination - all errors are captured and reported
- **SC-004**: Users can review workflow results and understand what happened for each issue within 1 minute of examining RefuelResult
- **SC-005**: Parallel processing mode reduces total execution time by at least 40% compared to sequential mode when processing 5+ independent issues
- **SC-006**: All created PRs correctly link back to their source issues and include AI-generated descriptions

## Assumptions

- GitHub CLI (`gh`) is installed and authenticated with appropriate repository permissions
- IssueFixerAgent and ValidationWorkflow are existing components that RefuelWorkflow will integrate with
- Issues labeled for tech debt contain sufficient context in their title/body for AI-assisted fixing
- Repository follows standard Git branching model (main/master as base branch)
- Rate limits are not expected during typical batch sizes (≤20 issues)
