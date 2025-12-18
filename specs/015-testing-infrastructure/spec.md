# Feature Specification: Testing Infrastructure

**Feature Branch**: `015-testing-infrastructure`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Create testing infrastructure for Maverick including unit tests, integration tests, and CI configuration"

## Clarifications

### Session 2025-12-17

- Q: How should Claude Agent SDK responses be mocked in tests? → A: Predefined response sequences - fixtures return canned responses in order
- Q: What should be explicitly out of scope? → A: Performance/load testing, mutation testing, visual regression testing
- Q: How should CI test results be reported on PRs? → A: GitHub check annotations only (inline failure comments in PR diff)
- Q: What should be the default timeout for async tests? → A: 30 seconds - balanced for most async operations

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run Unit Tests Locally (Priority: P1)

As a developer working on Maverick, I want to run unit tests locally to verify my changes don't break existing functionality before committing.

**Why this priority**: Unit tests are the foundation of the testing pyramid. Developers need fast feedback on their changes to maintain code quality and catch regressions early.

**Independent Test**: Can be fully tested by running `pytest tests/unit/` and verifying tests execute successfully with meaningful coverage output.

**Acceptance Scenarios**:

1. **Given** I have made changes to an agent class, **When** I run unit tests for that agent, **Then** tests execute and report pass/fail status within 30 seconds
2. **Given** I am writing a new tool, **When** I use provided test fixtures, **Then** I can mock Claude Agent SDK responses without making real API calls
3. **Given** tests are running, **When** an assertion fails, **Then** the failure message clearly indicates what was expected vs actual

---

### User Story 2 - Run Integration Tests (Priority: P2)

As a developer, I want to run integration tests to verify that workflows, TUI components, and CLI commands work correctly when components are combined.

**Why this priority**: Integration tests validate that components work together correctly. They catch issues that unit tests miss but are slower to run.

**Independent Test**: Can be fully tested by running `pytest tests/integration/` and `pytest tests/tui/` and verifying workflows execute end-to-end with mocked agents.

**Acceptance Scenarios**:

1. **Given** I have modified a workflow, **When** I run integration tests, **Then** the workflow executes with mocked agents and validates expected state transitions
2. **Given** I have changed a TUI screen, **When** I run TUI tests, **Then** Textual's pilot framework validates screen rendering and user interactions
3. **Given** I have modified CLI commands, **When** I run CLI tests, **Then** Click's testing utilities validate command parsing and execution

---

### User Story 3 - Continuous Integration Validation (Priority: P3)

As a maintainer, I want CI to automatically validate code quality on every PR to ensure only quality code is merged.

**Why this priority**: CI automates quality gates, ensuring consistent standards across all contributions without manual intervention.

**Independent Test**: Can be fully tested by pushing a branch or opening a PR and observing the GitHub Actions workflow execution and results.

**Acceptance Scenarios**:

1. **Given** I open a PR, **When** CI runs, **Then** linting (ruff), type checking (mypy), and tests (pytest) execute automatically
2. **Given** CI runs tests, **When** coverage is below 80%, **Then** the CI job fails with a clear message about coverage shortfall
3. **Given** CI passes on a PR, **When** I view the results, **Then** I can see coverage reports and test results for Python 3.10, 3.11, and 3.12

---

### User Story 4 - Write Tests Using Fixtures (Priority: P2)

As a developer adding new functionality, I want reusable test fixtures so I can quickly write comprehensive tests without boilerplate.

**Why this priority**: Well-designed fixtures reduce test writing time and ensure consistency across the test suite.

**Independent Test**: Can be fully tested by creating a new test file that imports fixtures and verifies they provide expected mock objects and utilities.

**Acceptance Scenarios**:

1. **Given** I need to test an agent, **When** I use the mock Claude SDK client fixture, **Then** I can simulate agent responses without API calls
2. **Given** I need to test GitHub integration, **When** I use the mock GitHub CLI fixture, **Then** I can simulate `gh` command responses
3. **Given** I need to test async generators, **When** I use the async generator capture utility, **Then** I can collect and assert on all yielded values

---

### Edge Cases

- What happens when a test fixture fails to initialize? Tests using that fixture should fail with a clear fixture error message.
- How does the system handle flaky async tests? Tests should use proper async utilities with a default 30-second timeout to avoid intermittent failures.
- What happens when CI times out? Workflow should have appropriate timeout limits and fail gracefully with partial results.
- How are tests that require external services handled? Such tests should be marked for skip unless the service is available.

## Requirements *(mandatory)*

### Functional Requirements

#### Test Fixtures

- **FR-001**: System MUST provide a mock Claude Agent SDK client fixture that simulates agent responses using predefined response sequences (canned responses returned in order) without making real API calls
- **FR-002**: System MUST provide sample configuration object fixtures matching `MaverickConfig` schema
- **FR-003**: System MUST provide mock GitHub CLI response fixtures for common operations (PR creation, issue listing, status checks)
- **FR-004**: System MUST provide sample agent response/message fixtures representing typical agent outputs

#### Test Utilities

- **FR-005**: System MUST provide a utility to capture and collect all items from async generators for assertion
- **FR-006**: System MUST provide utilities to assert on `AgentResult` contents including status, messages, and errors
- **FR-007**: System MUST provide utilities to validate MCP tool responses against expected schemas
- **FR-026**: System MUST configure pytest-asyncio with a default 30-second timeout for async tests

#### Test Organization

- **FR-008**: Unit tests MUST be organized at `tests/unit/agents/` for agent class tests
- **FR-009**: Unit tests MUST be organized at `tests/unit/tools/` for MCP tool tests
- **FR-010**: Unit tests MUST be organized at `tests/unit/workflows/` for workflow logic tests
- **FR-011**: Unit tests MUST be organized at `tests/unit/config/` for configuration tests
- **FR-012**: Integration tests MUST be organized at `tests/integration/` for end-to-end workflow tests
- **FR-013**: TUI tests MUST be organized at `tests/tui/` for Textual screen and widget tests

#### Integration Testing

- **FR-014**: System MUST support testing workflows with fully mocked agents
- **FR-015**: System MUST support testing TUI screens using Textual's pilot framework
- **FR-016**: System MUST support testing CLI commands using Click's testing utilities (CliRunner)

#### CI Configuration

- **FR-017**: CI workflow MUST run on PR creation and push to main branch
- **FR-018**: CI workflow MUST test against Python 3.10, 3.11, and 3.12 in a matrix configuration
- **FR-019**: CI workflow MUST run ruff for linting as a required step
- **FR-020**: CI workflow MUST run mypy for type checking as a required step
- **FR-021**: CI workflow MUST run pytest with coverage reporting as a required step
- **FR-022**: CI workflow MUST fail if code coverage falls below 80%
- **FR-023**: CI workflow MUST be defined in `.github/workflows/test.yml`
- **FR-025**: CI workflow MUST report test failures via GitHub check annotations (inline in PR diff)

#### Example Tests

- **FR-024**: System MUST include example test cases demonstrating testing patterns for each major component type (agent, tool, workflow, config, TUI, CLI)

### Key Entities

- **Test Fixture**: A reusable test setup component that provides mock objects, sample data, or test utilities. Attributes include scope (function, class, module, session) and dependencies on other fixtures.
- **Mock Client**: A simulated Claude Agent SDK client that returns predefined response sequences in order. Attributes include ordered response queue, call tracking for verification, and optional per-method response configuration.
- **Test Suite**: A collection of related tests organized by component type. Attributes include path location and test markers.
- **CI Workflow**: A GitHub Actions workflow definition. Attributes include triggers, job matrix, and steps.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Developers can run the full unit test suite in under 60 seconds on standard development hardware
- **SC-002**: Test coverage reaches minimum 80% of source code lines
- **SC-003**: All major components (agents, tools, workflows, config, TUI, CLI) have at least one example test demonstrating the testing pattern
- **SC-004**: CI pipeline completes within 10 minutes for a typical PR
- **SC-005**: Developers can write a new agent test using fixtures with less than 20 lines of boilerplate code
- **SC-006**: Zero test failures due to real API calls or external service dependencies in the standard test suite

## Assumptions

- pytest and pytest-asyncio are the chosen testing frameworks (per CLAUDE.md)
- Textual's pilot testing framework is available and compatible with the project's Textual version
- Click's CliRunner is available for CLI testing
- GitHub Actions is the CI/CD platform (repository is on GitHub)
- The Claude Agent SDK provides mockable interfaces or can be effectively mocked
- Ruff and mypy are already configured or will be configured as part of this work

## Out of Scope

- **Performance/load testing**: Stress testing, benchmarking, and load testing infrastructure
- **Mutation testing**: Tools like mutmut for testing test quality
- **Visual regression testing**: Screenshot comparison or visual diff testing
