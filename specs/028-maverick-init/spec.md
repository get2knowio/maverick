# Feature Specification: Unified Maverick Init with Claude-Powered Detection

**Feature Branch**: `028-maverick-init`
**Created**: 2025-12-29
**Status**: Draft
**Input**: User description: "Replace maverick config init with a comprehensive maverick init command that validates all prerequisites, uses Claude to analyze the project and derive configuration values, prints all findings, and adds Anthropic API validation to workflow preflight checks."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - First-Time Project Initialization (Priority: P1)

A developer new to Maverick runs `maverick init` in their project directory to set up Maverick for the first time. The command automatically validates all prerequisites (git, gh CLI, GitHub authentication, Anthropic API key), analyzes the project structure using Claude to detect the project type and appropriate validation commands, and generates a complete `maverick.yaml` configuration file.

**Why this priority**: This is the primary entry point for all new Maverick users. Without a working init command, users cannot use any other Maverick features.

**Independent Test**: Can be tested by running `maverick init` in a fresh project directory with valid prerequisites. Delivers immediate value by generating a working configuration file.

**Acceptance Scenarios**:

1. **Given** a git repository with valid prerequisites (git, gh, ANTHROPIC_API_KEY), **When** user runs `maverick init`, **Then** the system validates all prerequisites, analyzes the project, and generates a complete `maverick.yaml` file
2. **Given** a Python project with pyproject.toml and pytest configured, **When** user runs `maverick init`, **Then** the system detects "Python" project type and populates format/lint/typecheck/test commands appropriately
3. **Given** an Ansible Collection with galaxy.yml, **When** user runs `maverick init`, **Then** the system detects "Ansible Collection" project type and configures yamllint/ansible-lint/molecule commands

---

### User Story 2 - Preflight API Validation Before Workflow Execution (Priority: P2)

A developer runs `maverick fly` or `maverick refuel` to start a workflow. Before the workflow begins, the system performs preflight checks including validating that the Anthropic API is accessible. If validation fails, the workflow is blocked with a clear error message.

**Why this priority**: Prevents workflows from starting and failing mid-execution due to API access issues, saving developer time and avoiding wasted compute.

**Independent Test**: Can be tested by running `maverick fly` with valid/invalid API credentials and observing the preflight check output.

**Acceptance Scenarios**:

1. **Given** valid Anthropic API credentials, **When** user runs `maverick fly`, **Then** preflight shows "Anthropic API accessible" with checkmark and workflow proceeds
2. **Given** invalid Anthropic API key, **When** user runs `maverick fly`, **Then** preflight shows API validation failure and workflow is blocked with actionable error message
3. **Given** ANTHROPIC_API_KEY environment variable is not set, **When** user runs `maverick fly`, **Then** system displays error suggesting the export command

---

### User Story 3 - Override Auto-Detection with Manual Configuration (Priority: P3)

A developer working on an unconventional project or a project with ambiguous markers uses command-line flags to override the automatic detection behavior.

**Why this priority**: Provides escape hatch for edge cases where automatic detection may be incorrect or unnecessary.

**Independent Test**: Can be tested by running `maverick init --type python` in any project and verifying Python defaults are applied regardless of project structure.

**Acceptance Scenarios**:

1. **Given** any project, **When** user runs `maverick init --type python`, **Then** system skips Claude detection and applies Python project defaults
2. **Given** any project, **When** user runs `maverick init --no-detect`, **Then** system uses marker-based heuristics instead of Claude for detection
3. **Given** an existing maverick.yaml file, **When** user runs `maverick init`, **Then** system displays error unless `--force` flag is provided

---

### User Story 4 - Deprecation Path for Legacy Command (Priority: P4)

A developer who previously used `maverick config init` runs that command and receives a deprecation warning directing them to the new `maverick init` command.

**Why this priority**: Ensures smooth migration path for existing users while maintaining backward compatibility temporarily.

**Independent Test**: Can be tested by running `maverick config init` and verifying deprecation warning is displayed.

**Acceptance Scenarios**:

1. **Given** user runs `maverick config init`, **When** command executes, **Then** system displays deprecation warning recommending `maverick init` instead

---

### Edge Cases

- What happens when git remote is not configured? Owner/repo are left as null with a warning printed
- What happens when project type cannot be determined with high confidence? System uses Python defaults and prints a warning
- What happens when GitHub authentication fails? Clear error message is displayed with remediation steps
- What happens when Anthropic API model is inaccessible due to permission/plan limits? Error message suggests checking plan/permissions
- What happens when Claude API call for detection fails (timeout, rate limit, error)? Init command fails with error message (workflows require working Claude API)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST validate that git is installed and accessible
- **FR-002**: System MUST validate that gh CLI is installed and accessible
- **FR-003**: System MUST validate that user is authenticated with GitHub via gh CLI
- **FR-004**: System MUST validate that ANTHROPIC_API_KEY environment variable is set
- **FR-005**: System MUST validate Anthropic API access by sending a minimal completion request (e.g., "Hi" with max_tokens=1)
- **FR-006**: System MUST derive GitHub owner/repo from git remote URL (supporting both SSH and HTTPS formats)
- **FR-007**: System MUST use Claude (claude-3-5-haiku) to analyze project structure and determine project type, providing directory tree and content of key marker files (pyproject.toml, package.json, galaxy.yml, go.mod, Cargo.toml)
- **FR-008**: System MUST generate appropriate validation commands (format, lint, typecheck, test) based on detected project type
- **FR-009**: System MUST generate a complete maverick.yaml configuration file with all detected settings
- **FR-010**: System MUST print all findings used to populate the configuration before generating the file
- **FR-011**: System MUST NOT prompt user interactively; all values are derived automatically
- **FR-012**: System MUST support `--type` flag to override automatic project type detection
- **FR-013**: System MUST support `--no-detect` flag to use marker-based heuristics instead of Claude
- **FR-014**: System MUST support `--force` flag to overwrite existing maverick.yaml
- **FR-015**: System MUST refuse to overwrite existing maverick.yaml without `--force` flag
- **FR-016**: System MUST add Anthropic API validation to fly workflow preflight checks
- **FR-017**: System MUST add Anthropic API validation to refuel workflow preflight checks
- **FR-018**: System MUST block workflow execution if preflight checks fail
- **FR-019**: System MUST display deprecation warning when `maverick config init` is invoked
- **FR-020**: System MUST redact API key in output display (show only prefix and last 4 characters)

### Key Entities

- **ProjectType**: Enumeration of supported project types (Python, Ansible Collection, Ansible Playbook, Node.js, Go, Rust, unknown)
- **PreflightResult**: Outcome of a preflight check including status (pass/fail), message, and optional remediation advice
- **ProjectDetectionResult**: Claude's analysis output including detected project types (may be multiple in monorepos), primary type recommendation, confidence level, findings list, and recommended validation commands
- **MaverickConfig**: The complete configuration structure written to maverick.yaml

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can complete project initialization in under 30 seconds for typical projects
- **SC-002**: 95% of standard project types (Python, Node.js, Go, Rust, Ansible) are correctly detected without manual override. Measured via integration test suite with 20+ sample projects (4+ per type) verifying Claude detection matches expected ProjectType.
- **SC-003**: Users receive clear, actionable error messages for all failure scenarios within 5 seconds
- **SC-004**: Zero workflows fail mid-execution due to API access issues that could have been caught by preflight checks
- **SC-005**: Users can override automatic detection using a single command-line flag without documentation lookup
- **SC-006**: Generated configuration files are valid and immediately usable with `maverick fly` or `maverick refuel`

## Clarifications

### Session 2025-12-29

- Q: What should happen when a repository contains markers for multiple project types (e.g., monorepo)? → A: Detect multiple types but ask Claude to recommend a single "primary" type
- Q: What validation method should be used for Anthropic API access check? → A: Send a minimal completion request (e.g., "Hi" with max_tokens=1)
- Q: What should happen if Claude API call for project detection fails? → A: Fail the init command with an error message (workflows require Claude anyway)
- Q: Which Claude model should be used for project type detection? → A: claude-3-5-haiku (fast, cheap, sufficient for detection)
- Q: What project information should be sent to Claude for detection? → A: File names plus content of key marker files (pyproject.toml, package.json, galaxy.yml, go.mod, Cargo.toml, etc.)

## Assumptions

- Users have git installed and the current directory is a git repository
- Users have gh CLI installed for GitHub operations
- The Anthropic API supports a minimal "echo" style validation call
- Project type detection can be accomplished by analyzing directory structure and key marker files (pyproject.toml, package.json, galaxy.yml, go.mod, Cargo.toml)
- The Claude model specified in configuration is accessible to the user's API key
- Standard validation tool availability (ruff, pytest, eslint, etc.) is the user's responsibility to ensure
