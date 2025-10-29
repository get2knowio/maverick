# Feature Specification: Parameterized Workflow with Repo Verification

**Feature Branch**: `001-workflow-params-repo-check`  
**Created**: 2025-10-28  
**Status**: Draft  
**Input**: User description: "Our workflow should take parameters and make those parameters available to the individual steps/activities along the way. Lets build an MVP version of this by having the workflow take a github repo URL.  Then well add a new verification step (using the gh cli) to make sure the github repo exists."

## Clarifications

### Session 2025-10-29

- Q: Should verification require pre-checking `gh` authentication for the target host before calling `gh repo view`? → A: Require `gh auth status` first; if unauthenticated, fail with guidance; otherwise run `gh repo view`.

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.
  
  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - Provide Repo URL and Verify (Priority: P1)

A workflow runner initiates a workflow and provides a GitHub repository URL as an input parameter. Before any dependent steps execute, the workflow verifies that the repository exists. If it does not exist or is inaccessible, the workflow stops and returns a clear error.

**Why this priority**: Prevents wasted runs and downstream failures by catching invalid inputs early.

**Independent Test**: Start the workflow with a repository URL and observe a pass/fail verification result without running any other steps.

**Acceptance Scenarios**:

1. **Given** a valid, accessible repository URL, **When** the workflow starts, **Then** the verification passes and the workflow proceeds to subsequent steps.
2. **Given** a non-existent repository URL, **When** the workflow starts, **Then** verification fails and the workflow halts with a clear error message identifying the invalid repository.
3. **Given** a malformed URL string, **When** the workflow starts, **Then** the input is rejected with a validation error before attempting verification.
4. **Given** a private repository that the environment has access to, **When** the workflow starts, **Then** verification passes and the workflow proceeds (supports GitHub.com and/or GitHub Enterprise when accessible via the environment's configured GitHub context).

---

### User Story 2 - Parameters Available to Steps (Priority: P2)

All workflow steps can access named parameters provided at workflow start (e.g., `github_repo_url`) in a consistent manner.

**Why this priority**: Ensures reusability and modularity of steps that depend on shared inputs.

**Independent Test**: Execute any single step in isolation and confirm it can read the `github_repo_url` parameter by key.

**Acceptance Scenarios**:

1. **Given** a workflow started with `github_repo_url`, **When** a step runs, **Then** the step can read the exact value provided without additional configuration.
2. **Given** multiple parameters (future), **When** a step runs, **Then** it can access only the keys it requests and receive clear errors for missing keys.

---

### User Story 3 - Clear Failure Handling (Priority: P3)

If verification fails, the workflow cleanly halts before running any dependent steps and surfaces actionable guidance to the user (e.g., "Repository not found" or "Access denied").

**Why this priority**: Reduces confusion and support burden by making failures self-explanatory.

**Independent Test**: Provide an invalid or unauthorized repository and confirm the run stops with a clear error without executing later steps.

**Acceptance Scenarios**:

1. **Given** a non-existent repository, **When** the workflow starts, **Then** the run status is set to failed with a message that the repository cannot be found.
2. **Given** an inaccessible private repository, **When** the workflow starts, **Then** the run status is failed with guidance about missing access. The system retries once on transient errors (e.g., timeouts or rate limits) and halts if verification still fails; no manual override is provided.

---

[Add more user stories as needed, each with an assigned priority]

### Edge Cases

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right edge cases.
-->

- URLs with/without `.git` suffix (e.g., `https://github.com/org/repo` vs `git@github.com:org/repo.git`).
- Unsupported formats or hosts (e.g., non-GitHub URLs) are rejected with a validation error.
- Repository redirects or renames should be treated as existing if resolvable.
- Network unavailable or rate-limited: verification auto-retries once and, if still failing, surfaces a transient error with guidance to retry later.
- Private repositories without sufficient permissions: fail with access guidance (do not leak details).

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

- **FR-001**: The workflow MUST accept an input parameter named `github_repo_url` when a run is initiated.
- **FR-002**: The system MUST validate `github_repo_url` format before verification (accept HTTPS and SSH GitHub repository notations; limit hosts to those supported by the environment's configured GitHub context[s]).
- **FR-003**: The workflow MUST perform a repository existence check before executing any dependent steps.
- **FR-004**: If the repository check fails (not found, invalid, or inaccessible), the workflow MUST halt and return a clear, actionable error message.
- **FR-005**: Parameters provided at workflow start MUST be available to all steps via a consistent access mechanism using the parameter key.
- **FR-006**: The workflow MUST record the verification outcome (success/failure and reason) in run logs.
- **FR-007**: The repository existence check MUST complete within 5 seconds for 95% of attempts under normal network conditions.
- **FR-008**: The system MUST support repositories (public or private) that are accessible in the current environment via configured GitHub contexts (GitHub.com and/or GitHub Enterprise). If access is not configured, verification fails with access guidance.
- **FR-009**: On transient verification errors (e.g., timeouts, 5xx, or rate limits), the system MUST automatically retry once before halting; if the second attempt fails, the workflow stops with a transient error message (no manual override).
- **FR-010**: Prior to verification, the system MUST check that `gh` is installed and authenticated for the target host using `gh auth status` (or `gh auth status -h <host>`). If unauthenticated, the workflow MUST halt with guidance to authenticate (e.g., `gh auth login`).

#### Dependencies & Constraints

- Requires connectivity to GitHub at run time; verification cannot succeed offline.
- Access to private repositories depends on valid credentials being available to the runtime environment; otherwise, verification should fail with an access error (no sensitive data leaked).
- Requires GitHub CLI (`gh`) to be installed and authenticated for the target host prior to verification; otherwise, the workflow halts with authentication guidance.

### Key Entities *(include if feature involves data)*

- **Workflow Parameter**: A named input provided at run start (e.g., key `github_repo_url`, value string).
- **Workflow Step**: An activity that can read one or more named parameters.
- **Verification Result**: Outcome of the repository existence check (status: pass/fail, message: reason).
- **Repository**: A target GitHub repository identified by organization/user and name.

### Assumptions

- The runtime environment has authenticated access to GitHub as configured (public and/or private repositories on GitHub.com and/or GitHub Enterprise) when applicable.
- Verification tooling and connectivity are available at run time; if not, transient error handling (single retry) applies.

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: 100% of valid repository URLs proceed to downstream steps after passing verification.
- **SC-002**: 100% of malformed or non-GitHub URLs are rejected before verification with a clear validation error.
- **SC-003**: For public repositories, 95% of verifications complete within 5 seconds under normal network conditions.
- **SC-004**: 0% of runs proceed to dependent steps when verification fails.
