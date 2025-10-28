<!--
Sync Impact Report:
- Version change: [template] → 1.0.0
- Modified principles: None (initial creation)
- Added sections: All core principles and governance sections
- Removed sections: None
- Templates requiring updates: 
  ✅ .specify/templates/plan-template.md (Constitution Check section aligns)
  ✅ .specify/templates/spec-template.md (requirements alignment confirmed)
  ✅ .specify/templates/tasks-template.md (task categorization aligns)
- Follow-up TODOs: None
-->

# Maverick Constitution

## Core Principles

### I. Simplicity First
Every solution MUST start with the simplest approach that could work. Features and abstractions are only added when demonstrably necessary. YAGNI (You Aren't Gonna Need It) principle is strictly enforced. Complex solutions require explicit justification documenting why simpler alternatives are insufficient.

**Rationale**: Temporal workflows can become complex quickly; maintaining simplicity ensures maintainability and reduces cognitive load for developers working with distributed systems.

### II. Test-Driven Development (NON-NEGOTIABLE)
All code MUST follow the Red-Green-Refactor cycle: Tests written first → Tests fail → Minimal implementation to pass → Refactor. Good, measured test coverage is mandatory, with focus on workflow reliability and temporal activity correctness.

**Rationale**: Temporal workflows involve distributed state and timing; comprehensive testing is essential for confidence in deployment and debugging production issues.

### III. UV-Based Development
All dependency management and script execution MUST use uv (https://docs.astral.sh/uv/). No pip, poetry, or other package managers. Build scripts, test runners, and development workflows MUST be defined in pyproject.toml and executed via uv.

**Rationale**: Standardizing on uv provides fast, deterministic dependency resolution and script execution, critical for temporal workflow reliability.

### IV. Temporal-First Architecture
Code MUST be organized around Temporal workflow concepts: Activities, Workflows, and Workers. Business logic MUST be contained in Activities (testable, deterministic). Workflows MUST orchestrate Activities without side effects. All temporal concerns MUST be explicit and well-documented.

**Rationale**: Proper separation of concerns in Temporal applications prevents common pitfalls like non-deterministic workflows and ensures proper replay behavior.

### V. Observability and Monitoring
All workflows and activities MUST include structured logging, metrics, and tracing. Temporal dashboard integration MUST be maintained. Error handling MUST provide clear context for debugging both during development and in production.

**Rationale**: Temporal workflows execute across time and failures; comprehensive observability is essential for understanding system behavior and debugging issues.

## Technology Standards

### Python Environment
- Python 3.11+ required for type hints and performance
- All dependencies managed through uv with locked versions
- pyproject.toml MUST define all scripts and entry points
- Virtual environments managed exclusively through uv

### Temporal Integration
- Temporal Python SDK as primary workflow engine
- Worker processes MUST be containerizable
- Workflow and Activity definitions MUST be versioned carefully
- Local development MUST use Temporal dev server or Docker Compose

### Testing Standards
- pytest as test framework with temporal testing utilities
- Unit tests for all Activities (pure functions where possible)
- Integration tests for Workflow execution paths
- Contract tests for external service interactions called from Activities
- Minimum 90% code coverage for workflow-critical paths

## Development Workflow

### Code Organization
- Activities in `src/activities/` as pure, testable functions
- Workflows in `src/workflows/` with minimal logic
- Workers in `src/workers/` for process management
- Shared models in `src/models/` for data structures
- Tests mirror source structure in `tests/`

### Quality Gates
- All pull requests MUST pass automated tests
- Code review required for workflow definition changes
- Performance impact assessment for new Activities
- Temporal workflow versioning strategy MUST be documented for changes

### Deployment Requirements
- Workers MUST be deployable as independent services
- Configuration MUST support multiple environments (dev, staging, prod)
- Temporal namespace isolation MUST be maintained per environment

## Governance

This constitution supersedes all other development practices. Changes require explicit amendment with version bump and impact assessment. All features MUST demonstrate compliance with these principles, particularly Simplicity First and Test-Driven Development.

**Amendment Process**: Constitutional changes require documentation of impact on existing workflows, approval from maintainers, and migration plan for existing code.

**Compliance**: All pull requests and code reviews MUST verify adherence to these principles, with particular attention to temporal workflow correctness and test coverage.

**Version**: 1.0.0 | **Ratified**: 2025-10-28 | **Last Amended**: 2025-10-28
