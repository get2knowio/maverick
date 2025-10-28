<!--
Sync Impact Report:
- Version change: 1.0.0 → 1.1.0
- Modified principles: IV. Temporal-First Architecture (expanded with determinism rules)
- Added sections: "Temporal Workflow Best Practices" subsection under Technology Standards
- Removed sections: None
- Templates requiring updates: 
  ✅ .specify/templates/plan-template.md (Constitution Check section aligns)
  ✅ .specify/templates/spec-template.md (requirements alignment confirmed)
  ✅ .specify/templates/tasks-template.md (task categorization aligns)
- Follow-up TODOs: None
- Rationale: MINOR version bump (1.1.0) due to materially expanded guidance on Temporal workflow determinism and type safety, adding non-negotiable rules for workflow correctness.
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

**Critical Determinism Rules (NON-NEGOTIABLE)**:
- Workflows MUST NEVER use `time.time()` - use `workflow.now()` instead (returns datetime)
- Workflows MUST NEVER use `datetime.now()` - use `workflow.now()` for current workflow time
- Workflows MUST NEVER use `random.random()` - use `workflow.random()` for deterministic randomness
- Duration calculation MUST use `(workflow.now() - start_time).total_seconds()` for timedelta math

**Type Safety Requirements**:
- Activity calls MUST specify `result_type` when returning dataclasses to ensure proper deserialization
- Data models MUST use `Literal` types instead of `Enum` for status/state values to avoid custom serialization complexity

**Rationale**: Temporal workflows must be deterministic to support replay. Non-deterministic operations like system time calls will cause `RestrictedWorkflowAccessError` and prevent workflow execution. Proper type hints and serialization ensure correct deserialization and prevent runtime AttributeErrors. These rules are based on production lessons learned during initial feature implementation.

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

#### Temporal Workflow Best Practices

**Determinism Enforcement**:
```python
# ✓ CORRECT: Deterministic time tracking
start_time = workflow.now()  # Returns datetime
# ... workflow logic ...
end_time = workflow.now()
duration_ms = int((end_time - start_time).total_seconds() * 1000)

# ✗ INCORRECT: Non-deterministic (will fail with RestrictedWorkflowAccessError)
import time
start_time = time.time()  # ❌ NEVER use in workflows
```

**Activity Result Deserialization**:
```python
# ✓ CORRECT: Specify result_type for proper deserialization
result = await workflow.execute_activity(
    "my_activity",
    start_to_close_timeout=timedelta(seconds=30),
    result_type=MyDataClass,  # Returns MyDataClass instance
)

# ✗ INCORRECT: Missing result_type returns dict instead of dataclass
result = await workflow.execute_activity(
    "my_activity",
    start_to_close_timeout=timedelta(seconds=30),
)  # Returns dict, causes AttributeError on attribute access
```

**Type Safety with Literals**:
```python
# ✓ CORRECT: Literal types for type safety and seamless serialization
from typing import Literal

CheckStatus = Literal["pass", "fail"]

@dataclass
class PrereqCheckResult:
    tool: str
    status: CheckStatus  # Type-safe, serializes naturally
    message: str

# ✗ INCORRECT: Enum requires custom serializer
class CheckStatus(Enum):  # ❌ Needs custom data converter
    PASS = "pass"
    FAIL = "fail"
```

These patterns are mandatory for all Temporal workflow and activity implementations.

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

**Version**: 1.1.0 | **Ratified**: 2025-10-28 | **Last Amended**: 2025-10-28
