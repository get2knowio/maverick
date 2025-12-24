# Feature Specification: Preflight Validation System

**Feature Branch**: `027-preflight-validation`  
**Created**: 2024-12-24  
**Status**: Draft  
**Input**: User description: "Design and implement a Preflight Validation system for Maverick workflows to prevent mid-execution failures due to missing tools or configuration"

## User Scenarios & Testing _(mandatory)_

### User Story 1 - Clear Failure Before Work Begins (Priority: P1)

As a developer running the `maverick fly` or `maverick refuel` command, I want the system to validate all required tools and configurations **before** creating any branches or modifying any state, so that I receive clear, actionable error messages when something is missing rather than discovering failures mid-workflow.

**Why this priority**: This is the core value proposition—preventing wasted time and corrupted state from mid-execution failures. A developer who runs a workflow and gets immediate feedback about missing `gh` CLI or misconfigured git saves significant debugging time.

**Independent Test**: Can be fully tested by running a workflow with a deliberately missing tool (e.g., renamed `gh` binary) and verifying the workflow fails immediately with a clear message before any git operations occur.

**Acceptance Scenarios**:

1. **Given** the `gh` CLI is not installed, **When** a user runs `maverick fly`, **Then** the workflow fails immediately with a clear message "GitHub CLI (gh) not found" before any branch is created.

2. **Given** git is not configured with user credentials, **When** a user runs `maverick refuel`, **Then** the workflow fails with a message explaining git user configuration is missing before any issue processing begins.

3. **Given** the user's GitHub token lacks required scopes (e.g., `repo`), **When** running `maverick fly`, **Then** the workflow fails with a message listing the missing permission scopes.

4. **Given** all tools are properly installed and configured, **When** a user runs any workflow, **Then** the preflight phase completes silently (or with minimal success indication) and the workflow proceeds normally.

---

### User Story 2 - Aggregated Error Reporting (Priority: P1)

As a developer setting up a new environment, I want the preflight validation to report **all** missing requirements at once rather than failing on the first error, so that I can fix everything in one pass instead of playing "whack-a-mole" with errors.

**Why this priority**: Equally critical to P1-1. A single aggregated error report dramatically improves the developer experience when multiple things are wrong, reducing fix-retry cycles from N to 1.

**Independent Test**: Can be tested by removing multiple tools (git, gh, pytest) simultaneously and verifying all are reported in a single error message.

**Acceptance Scenarios**:

1. **Given** both `gh` CLI and `pytest` are missing, **When** a user runs `maverick fly`, **Then** the error output lists both missing tools in a single summary.

2. **Given** `git` is installed but the directory is not a repository AND `gh` is not authenticated, **When** a user runs `maverick refuel`, **Then** both issues are reported together with clear remediation steps for each.

3. **Given** three validation tools (`ruff`, `mypy`, `pytest`) are configured but only `ruff` is installed, **When** preflight runs, **Then** the error message lists `mypy` and `pytest` as missing with their expected installation commands.

---

### User Story 3 - Validation in Dry-Run Mode (Priority: P2)

As a developer who wants to test a workflow without making changes, I want preflight validation to run even in `dry_run` mode, so that I can verify my environment is correctly configured before committing to a real run.

**Why this priority**: Supports the common pattern of "test before you run" and ensures dry-run gives accurate previews of what would happen.

**Independent Test**: Can be tested by running `maverick fly --dry-run` with a missing tool and verifying the validation error appears.

**Acceptance Scenarios**:

1. **Given** `gh` CLI is missing, **When** a user runs `maverick fly --dry-run`, **Then** the preflight validation still fails with the missing tool message.

2. **Given** all tools are present, **When** a user runs `maverick fly --dry-run`, **Then** preflight passes and the dry-run proceeds to show what would be done.

---

### User Story 4 - Fast Parallel Validation (Priority: P2)

As a developer, I want preflight validation to complete quickly so that it doesn't add noticeable latency to workflow startup.

**Why this priority**: User experience optimization—validation should feel instant, not like a separate lengthy phase.

**Independent Test**: Can be tested by measuring preflight completion time with all tools present, targeting completion in under 2 seconds on typical hardware.

**Acceptance Scenarios**:

1. **Given** all required tools are installed, **When** preflight validation runs, **Then** all validation checks complete in parallel rather than sequentially.

2. **Given** a slow network connection, **When** validating GitHub authentication, **Then** the validation timeout is reasonable (configurable, default ~5 seconds) and doesn't block indefinitely.

---

### User Story 5 - Extensible Validation for Custom Tools (Priority: P3)

As a project maintainer, I want to be able to add custom validation checks for project-specific tools without modifying Maverick core code, so that I can ensure project-specific requirements are validated.

**Why this priority**: Future extensibility; core functionality works without this but it enables advanced use cases.

**Independent Test**: Can be tested by configuring a custom validation tool in project config and verifying it's included in preflight checks.

**Acceptance Scenarios**:

1. **Given** a project's `maverick.toml` specifies custom validation tools (tool name and optional version check command), **When** preflight runs, **Then** those tools are validated alongside built-in requirements.

---

### Edge Cases

- What happens when a tool exists but returns unexpected exit codes? The system should interpret non-zero exit codes as validation failure with the actual error output captured.
- How does the system handle tools that are present but corrupted/broken? The system validates tool executability by running version/health check commands, not just checking file existence.
- What happens when validation itself times out? A per-check timeout (default: 5 seconds) prevents any single check from blocking; timeout is treated as failure with clear message.
- How does the system handle partial authentication (e.g., gh logged in but token expired)? The validation should perform an active check (e.g., `gh auth status`) rather than just checking for token file existence.
- What happens when the current directory is deleted mid-validation? The system should catch filesystem errors and report them as environment validation failures.

## Requirements _(mandatory)_

### Functional Requirements

- **FR-001**: System MUST provide a `ValidatableRunner` interface (protocol) that requires an async `validate()` method returning a structured result.

- **FR-002**: The `validate()` method MUST return a result object containing: success status (boolean), a list of error messages (if failed), and optional warning messages.

- **FR-003**: `GitRunner` MUST implement `ValidatableRunner` to verify:

  - `git` executable is available on PATH
  - Current working directory is inside a git repository
  - Repository is in a healthy state (not in middle of rebase/merge conflict)
  - User identity is configured (user.name and user.email)

- **FR-004**: `GitHubCLIRunner` MUST implement `ValidatableRunner` to verify:

  - `gh` CLI executable is available on PATH
  - User is authenticated (`gh auth status` succeeds)
  - Token has required scopes (minimally: `repo`, `read:org`)

- **FR-005**: `ValidationRunner` MUST implement `ValidatableRunner` to verify that all configured validation tool executables (from config, e.g., `ruff`, `mypy`, `pytest`) are available on PATH.

- **FR-006**: `CodeRabbitRunner` MUST implement `ValidatableRunner` to verify the `coderabbit` CLI is available IF the runner is enabled in configuration.

- **FR-007**: `FlyWorkflow` and `RefuelWorkflow` MUST execute a preflight validation phase BEFORE any state-changing operations (branch creation, file modifications).

- **FR-008**: The preflight phase MUST execute even when `dry_run` mode is enabled.

- **FR-009**: Multiple validation checks SHOULD run concurrently (in parallel) to minimize startup time.

- **FR-010**: If any critical validation fails, the workflow MUST terminate immediately without proceeding to any subsequent stages.

- **FR-011**: When multiple validations fail, the system MUST aggregate all failures into a single error report rather than failing on the first error.

- **FR-012**: Error messages MUST be actionable, including:

  - What is missing or misconfigured
  - How to fix the issue (e.g., "Run `brew install gh` or visit https://cli.github.com")
  - Output MUST use rich terminal formatting (colors, icons) consistent with existing Maverick console output patterns for human readability.

- **FR-013**: The preflight phase MUST have configurable timeout per check (default: 5 seconds).

- **FR-014**: Validation results MUST distinguish between critical failures (that block workflow) and warnings (that allow workflow to proceed with degraded functionality). All tool presence/requirement failures are critical. Only non-blocking configuration suggestions (e.g., "consider setting `git config pull.rebase true`") are warnings.

- **FR-015**: The `WorkflowDSLMixin` SHOULD provide a shared preflight validation method that both `FlyWorkflow` and `RefuelWorkflow` can use.

- **FR-016**: The preflight system MUST dynamically discover which runners to validate based on runners actually used/configured for the current workflow, rather than validating a hardcoded list.

### Key Entities

- **ValidationResult**: Represents the outcome of a single validation check, containing success status, error messages, warning messages, and the name of the validated component.

- **PreflightResult**: Aggregates multiple `ValidationResult` objects and provides overall pass/fail status with combined error reporting.

- **ValidatableRunner**: A protocol (interface) that runner classes implement to provide environment validation capabilities.

## Success Criteria _(mandatory)_

### Measurable Outcomes

- **SC-001**: Workflows fail within 5 seconds of startup when critical tools are missing, rather than failing minutes later mid-execution.

- **SC-002**: When 3+ validation errors exist, all errors are reported in a single output with remediation hints for each.

- **SC-003**: Preflight validation completes in under 2 seconds when all tools are present and properly configured.

- **SC-004**: Zero state-changing operations (branch creation, commits, PRs) occur when preflight validation fails.

- **SC-005**: Developers can identify and resolve all missing requirements in a single fix-retry cycle when errors are aggregated.

- **SC-006**: The validation system supports all 4 core runners (Git, GitHub CLI, Validation, CodeRabbit) with consistent interface.

## Assumptions

- Git and GitHub CLI (`gh`) are the primary external dependencies; other tools (ruff, mypy, pytest) are project-specific and configured via Maverick config.
- Network connectivity is available for GitHub authentication checks; offline scenarios will fail the `gh` validation.
- The project uses async/await patterns throughout; validation follows this convention.
- Validation tool availability is checked via `shutil.which()` for PATH lookup and simple command execution for health checks.
- Default timeout of 5 seconds per check is sufficient for typical environments; slow CI environments may need configuration.

## Clarifications

### Session 2024-12-24

- Q: What validation failures should be warnings vs. critical? → A: All tool/requirement failures are critical; only configuration suggestions (e.g., "consider setting git pull.rebase") are warnings.
- Q: What output format for preflight validation results? → A: Rich terminal output with colors/icons, matching existing Maverick console patterns.
- Q: Should validation results be persisted for debugging/auditing? → A: Terminal output only; no persistence (validation is transient, re-run on each invocation).
- Q: How does preflight discover which runners to validate? → A: Dynamic discovery based on runners actually used/configured for the current workflow.
- Q: How should custom validators be configured? → A: Configuration in `maverick.toml` specifying tool names and optional version check commands.

## Out of Scope

- Automatic installation of missing tools (the system reports what's missing but doesn't auto-install).
- Validation of specific tool versions (e.g., "pytest >= 7.0"); only presence/executability is checked.
- Network connectivity validation beyond what's needed for GitHub authentication.
- Validation of Maverick's own installation or Python environment.
