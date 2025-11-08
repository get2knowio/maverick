# Feature Specification: PR CI Automation

**Feature Branch**: `001-pr-ci-automation`  
**Created**: 2025-11-08  
**Status**: Draft  
**Input**: User description summarizing the need to convert an AI-authored branch into a GitHub Pull Request, monitor GitHub Actions, merge on success, and hand failures back to the workflow for remediation.

## Clarifications

### Session 2025-11-08
- Q: How should the activity respond when no CI checks appear during polling? → A: Continue polling until the max wait duration expires, then return `timeout` without merging.
- Q: What should happen if the existing pull request targets a different base branch than requested? → A: Return an `error` result indicating the base branch mismatch so the workflow can remediate.
- Q: Which integration interface should the activity standardize on for PR and CI operations? → A: Use the authenticated `gh` CLI exclusively for GitHub interactions in this feature.
- Q: How should the activity handle transient GitHub rate limiting or similar errors encountered during polling or merge attempts? → A: Retry with exponential backoff within the polling timeout/retry budget, then surface the terminal status if still failing.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automation merges a healthy PR (Priority: P1)

The Temporal workflow triggers the integration activity to publish a branch of AI-authored changes, watches CI complete successfully, and merges the pull request without manual help.

**Why this priority**: Enables hands-free delivery of AI-produced changes, which is the core value of the integration step.

**Independent Test**: Start the activity with a branch that passes CI; observe it create or reuse a pull request, detect green checks, and merge the work without human intervention.

**Acceptance Scenarios**:

1. **Given** a branch without an open pull request, **When** the activity runs with a success-ready branch, **Then** it creates the pull request with the AI summary, monitors CI to completion, merges into the target branch, and reports success with merge metadata.
2. **Given** a branch that already has a green pull request, **When** the activity starts, **Then** it recognizes the existing state, skips duplicate work, confirms CI is still green, merges safely, and reports success.

---

### User Story 2 - Automation surfaces failing CI for remediation (Priority: P1)

The workflow calls the activity on a branch whose CI fails so that the next workflow phase can repair the issue with full insight into what broke.

**Why this priority**: Without actionable failure detail the remediation loop cannot operate, halting the overall automation.

**Independent Test**: Run the activity on a branch that consistently fails CI; confirm it captures job names, failure statuses, and log links, and returns them without attempting to merge.

**Acceptance Scenarios**:

1. **Given** a branch with a new pull request, **When** CI finishes with failures, **Then** the activity returns a structured payload listing failing jobs and their log URLs, marks the attempt as `ci_failed`, and leaves the PR unmerged for follow-up.
2. **Given** a branch whose CI already failed before the activity starts, **When** the activity polls for status, **Then** it immediately recognizes the failed state, skips further polling, and returns the same structured failure payload.

---

### User Story 3 - Automation safely resumes mid-cycle (Priority: P2)

The workflow re-invokes the activity after a retry or infrastructure hiccup, and the automation resumes from the most recent GitHub state without duplicating actions or corrupting history.

**Why this priority**: Temporal retries and multi-cycle remediation require idempotent behavior to avoid noisy or conflicting pull request operations.

**Independent Test**: Trigger the activity multiple times for the same branch across mixed CI outcomes; confirm each run reuses the existing pull request, honours already-completed CI checks, and produces consistent outputs.

**Acceptance Scenarios**:

1. **Given** a pull request that is already merged, **When** the activity is retried, **Then** it notes the terminal state, returns a success payload without raising errors, and stops further work.
2. **Given** a pull request that is still running CI from a previous attempt, **When** the activity restarts, **Then** it resumes polling using the existing run identifiers and reports the eventual outcome exactly once.

---

### Edge Cases

- PR already exists but targets a different base branch than expected; activity MUST return an `error` result indicating the mismatch without altering the PR.
- CI providers return no checks or only optional checks for the pull request.
- Polling exceeds the maximum wait window without a terminal CI status.
- GitHub API or CLI calls rate-limit or transiently fail during polling or merge; activity MUST apply exponential backoff retries within its timeout/retry budget before surfacing a terminal status.
- Branch was deleted or force-pushed while the activity waits for CI results.
- Multiple CI runs exist for the same commit (re-runs, matrix jobs) and report mixed statuses.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The activity MUST accept branch name, target branch (defaulting to `main`), AI-generated summary text, and workflow context identifiers as inputs from the Temporal workflow.
- **FR-002**: The activity MUST verify the source branch exists on the remote and resolve (or default) the target branch before attempting pull request operations.
- **FR-003**: The activity MUST detect whether a pull request already exists for the branch using documented `gh pr view` commands, and reuse it when present.
- **FR-004**: When no pull request exists, the activity MUST create one via `gh pr create --base <target>`, using the AI summary as the body plus an attribution note that the description was generated automatically.
- **FR-005**: The activity MUST update an existing pull request body when the AI summary changes, while preserving any prior human comments.
- **FR-006**: The activity MUST initiate or observe GitHub Actions by polling `gh pr checks`, `gh run list`, and/or `gh run view` on a configurable interval until a terminal success, failure, or timeout condition is reached.
- **FR-007**: The polling loop MUST enforce configurable pacing (e.g., 30–60 seconds) and overall timeout (e.g., 45 minutes); when no checks appear, it MUST continue polling until the maximum wait elapses and then return a `timeout` result without merging.
- **FR-008**: On CI success, the activity MUST merge the pull request using `gh pr merge --merge --auto`, confirm the merge commit SHA, and delete the source branch when configured to do so; if branch deletion fails, it MUST report the failure without marking the overall run unsuccessful.
- **FR-009**: On CI failure, the activity MUST collect failing job names, statuses, URLs to logs, and the latest attempt timestamps, returning them to the workflow in a structured payload while leaving the pull request open.
- **FR-010**: The activity MUST produce a deterministic result payload containing status (`merged`, `ci_failed`, `timeout`, `error`), pull request metadata (number, URL, merge commit where applicable), CI evidence, polling duration, and retry guidance for downstream workflow steps.
- **FR-011**: The activity MUST be idempotent across retries by storing and reusing pull request numbers, latest commit SHAs, and CI run identifiers retrieved from GitHub.
- **FR-012**: The activity MUST surface actionable errors (e.g., authentication failures, missing branch) distinctly from CI failures so the workflow can decide between human escalation and automated remediation.

### Non-Functional Requirements

- **NFR-001**: The activity MUST surface terminal CI status to the workflow within two polling intervals (≤2 minutes) after GitHub marks runs complete.
- **NFR-002**: The activity MUST complete pull request merges (including optional branch deletion) within five minutes of CI success in at least 95% of attempts.
- **NFR-003**: The activity MUST emit structured logs and metrics for each polling cycle, including remaining timeout budget and retry counters, to satisfy observability requirements.
- **NFR-004**: The activity MUST gracefully handle network interruptions and GitHub rate limiting by applying exponential backoff without violating the overall timeout budget.
- **NFR-005**: Result payloads MUST remain deterministic across retries and replays, ensuring identical data for identical GitHub states to maintain Temporal workflow determinism.

### Key Entities *(include if feature involves data)*

- **PullRequestAutomationRequest**: Contains branch name, optional target branch, AI summary text, and workflow attempt metadata; drives creation and polling decisions.
- **PullRequestAutomationResult**: Captures final status, pull request URL/number, merge commit SHA, timestamps, and links to CI evidence returned to the workflow.
- **CiFailureDetail**: Represents each failing job with job name, attempt number, status, summary message, and URL to the relevant logs or artifacts.
- **PollingConfiguration**: Defines interval seconds, maximum wait duration, and retry backoff strategy supplied by workflow configuration.

## Assumptions

- `gh` CLI is the sole integration surface and is already authenticated and authorised for the repository before the activity runs.
- Workflow provides or can infer the correct target branch; if omitted, `main` is acceptable for current automation goals.
- GitHub Actions (or configured checks) emit status APIs compatible with `gh pr checks`/`gh run` endpoints.
- Automatic branch deletion after merge is desired unless a workflow flag explicitly opts out.
- Network interruptions will be retried by Temporal according to standard activity retry policies.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of automation attempts either create a new pull request or return the URL of an existing one without manual intervention.
- **SC-002**: For pull requests with CI activity, the automation detects and reports the terminal CI status within two polling intervals (<=2 minutes) of the CI provider marking the run complete.
- **SC-003**: When CI fails, the returned payload includes failing job names and log URLs for all failed jobs in at least 95% of attempts, enabling the remediation step to proceed.
- **SC-004**: When CI succeeds, at least 95% of eligible pull requests are merged and (when configured) branches are deleted within 5 minutes of CI completion.
