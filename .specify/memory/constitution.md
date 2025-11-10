<!--
Sync Impact Report:
- Version change: 1.3.0 → 1.4.0
- Modified principles: Testing Standards (enforce timeout for pytest commands)
- Added sections: None
- Removed sections: None
- Templates requiring updates:
  ✅ .specify/templates/plan-template.md (no pytest guidance; remains aligned)
  ✅ .specify/templates/spec-template.md (no pytest guidance; remains aligned)
  ✅ .specify/templates/tasks-template.md (no pytest guidance; remains aligned)
  ✅ AGENTS.md (timeout guidance added)
  ✅ README.md (timeout guidance added)
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

**Critical Determinism Rules (NON-NEGOTIABLE)**:
- Workflows MUST NEVER use `time.time()` - use `workflow.now()` instead (returns datetime)
- Workflows MUST NEVER use `datetime.now()` - use `workflow.now()` for current workflow time
- Workflows MUST NEVER use `random.random()` - use `workflow.random()` for deterministic randomness
- Duration calculation MUST use `(workflow.now() - start_time).total_seconds()` for timedelta math

**Workflow Logging (NON-NEGOTIABLE)**:
- Workflows MUST ALWAYS use `workflow.logger` - never import module-level loggers
- Metadata MUST be passed via `extra` dict using standard Python logging format
- Must include workflow context: `workflow.info().workflow_id`, `workflow.info().run_id`

**Type Safety Requirements**:
- Activity calls MUST specify `result_type` when returning dataclasses to ensure proper deserialization
- Data models MUST use `Literal` types instead of `Enum` for status/state values to avoid custom serialization complexity

**Worker Architecture Requirements**:
- Single consolidated worker process MUST host ALL workflows and activities
- Unified task queue MUST be used for all workflow types
- Worker processes MUST implement graceful shutdown with signal handlers (SIGTERM, SIGINT)
- Connection management MUST use timeouts and explicit error handling

**Rationale**: Temporal workflows must be deterministic to support replay. Non-deterministic operations like system time calls will cause `RestrictedWorkflowAccessError` and prevent workflow execution. Module-level loggers can cause non-deterministic behavior during replay. Proper type hints and serialization ensure correct deserialization and prevent runtime AttributeErrors. Consolidated worker architecture simplifies operations and resource utilization. These rules are based on production lessons learned during feature implementation.

### V. Observability and Monitoring
All workflows and activities MUST include structured logging, metrics, and tracing. Temporal dashboard integration MUST be maintained. Error handling MUST provide clear context for debugging both during development and in production.

**Logging Architecture (REQUIRED)**:
- Activities & Workers: Structured JSON logging via `src/utils/logging.py` with SafeJSONEncoder
- CLI & User-facing: Traditional formatted logging via `src/common/logging.py`
- Workflows: Exclusively use `workflow.logger` (never import loggers)
- JSON serialization MUST handle datetime, sets, bytes, and custom objects with fallback handling

**Rationale**: Temporal workflows execute across time and failures; comprehensive observability is essential for understanding system behavior and debugging issues. Separate logging architectures ensure proper observability while maintaining deterministic workflow behavior.

### VI. Documentation Standards
Documentation MUST distinguish between ephemeral working documents and durable reference materials. Ephemeral specs (in `specs/` directory) MUST NOT be referenced from durable documentation like README or agent guidance files.

**Durable Documentation Requirements**:
- README.md: User-facing project documentation and quick start guides
- AGENTS.md: Comprehensive AI agent development guidelines  
- Code comments: Inline documentation for maintainability
- Docstrings: API documentation within code

**Ephemeral Specifications**:
- `specs/` directory contains working documents used during active development
- Specs may be moved, renamed, or deleted after feature completion
- Specs MUST NOT be linked from durable documentation
- Completed specs may be archived to `specs-completed/` for historical reference

**Rationale**: Clear separation between temporary planning documents and permanent reference materials prevents broken links and confusion as the project evolves. Specs are valuable during development but should not create maintenance burden in production documentation.

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

### Speckit Workflow Integration (REQUIRED)
- Temporal workflows implementing Speckit specifications MUST treat Speckit-generated `tasks.md` files as the authoritative backlog and re-parse the live document before applying checkpoint-based decisions.
- Activities MUST encapsulate all Speckit CLI calls (`speckit.plan`, `speckit.tasks`, `speckit.implement`, etc.) and MUST capture stdout/stderr using tolerant decoding with `errors='replace'`.
- Workflows MUST preserve determinism by delegating parsing, hashing, and CLI invocation logic to activities; workflow code stores only workflow-safe metadata and checkpoint state.
- Each automated phase MUST emit machine-readable JSON reports capturing status, timestamps, log locations, and remediation guidance to support auditing and follow-up automation.
- Tests MUST cover markdown parsing fixtures, checkpoint drift detection, and resume scenarios for every supported Speckit-driven workflow path.

**Rationale**: The project automates execution of Speckit task plans; codifying these rules keeps automation deterministic, auditable, and aligned with Temporal best practices.

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

#### Worker Best Practices (REQUIRED)

**Graceful Shutdown**:
Every worker MUST implement proper shutdown handling before starting:
- Add signal handlers for SIGTERM and SIGINT
- Use asyncio.Event for shutdown coordination
- Cancel tasks properly and await their cancellation
- Clean up resources in finally blocks (remove signal handlers)

**Connection Management**:
All Temporal client connections MUST follow this pattern:
- Use environment variables for configuration (TEMPORAL_HOST, TEMPORAL_CONNECTION_TIMEOUT)
- Validate configuration before attempting connection (non-empty, positive values)
- Apply connection timeouts with `asyncio.wait_for()`
- Handle exceptions explicitly (TimeoutError, generic Exception)
- Log all connection attempts with target and timeout
- Exit on failure with `sys.exit(1)` to prevent silent crashes

**Rationale**: Proper shutdown handling prevents data loss and ensures clean termination. Connection management with timeouts and validation prevents hanging workers and provides clear error messages for debugging connection issues.

### Code Quality Standards (REQUIRED)

**Linting Configuration**:
- Avoid contradictory rules (don't globally ignore rules that have per-file-ignores)
- Use per-file-ignores deliberately (e.g., allow T201/print only in `src/cli/*.py`)
- Keep global ignores minimal (only rules that apply project-wide)

**Data Model Validation**:
All dataclasses with business rules MUST validate in `__post_init__`:
- Validate invariants immediately (fail fast on construction)
- Provide clear error messages (include what failed and expected value)
- Document invariants in docstrings
- Check both directions of constraints (if applicable)

**Input Validation**:
All input parsing and validation MUST follow this pattern:
- Validate early (check inputs immediately after extraction)
- Call validation in correct order (e.g., host before slug)
- Apply validation consistently (same validation for all input formats)
- Let exceptions propagate (don't swallow validation errors)

**Rationale**: Consistent code quality standards prevent subtle bugs and make code more maintainable. Early validation with clear error messages helps developers identify issues quickly.

### Error Handling & Resilience (CRITICAL)

**Subprocess Output Decoding (REQUIRED)**:
All subprocess stderr/stdout decoding MUST use tolerant error handling:
- Always use `errors='replace'` with `.decode()` to prevent UnicodeDecodeError
- Never use bare `.decode()` which can crash on non-UTF-8 bytes
- Call `.lower()` after decoding for safe case-insensitive matching

**JSON Serialization Safety (REQUIRED)**:
All structured logging MUST use safe JSON serialization:
- Use SafeJSONEncoder to handle datetime, sets, bytes, custom objects
- Implement fallback handling (never let serialization errors propagate)
- Provide minimal fallback with event name and error details

**CLI Tool Integration (REQUIRED)**:
When integrating with external CLI tools (gh, git, etc.):
- Validate tool flags against documentation for supported options
- Use documented APIs (prefer environment variables or URL formats)
- Handle tool-specific formats properly (e.g., `HOST/OWNER/REPO` for gh CLI)
- Research tool options with `--help` or official documentation before use

**Rationale**: External tools may output non-UTF-8 bytes; tolerant decoding ensures activities never crash due to encoding issues. Safe JSON serialization with fallbacks ensures logging never fails silently. Proper CLI tool integration prevents errors from invalid flags or formats.

### Testing Standards
- pytest as test framework with temporal testing utilities
- Unit tests for all Activities (pure functions where possible)
- Integration tests for Workflow execution paths
- Contract tests for external service interactions called from Activities
- Minimum 90% code coverage for workflow-critical paths
- All `uv run pytest` executions MUST be wrapped in a `timeout` command (e.g., `timeout 15 uv run pytest tests/...`) to mitigate hanging test processes; select durations that balance reliability and runaway termination.

**Rationale**: Enforcing timeouts prevents CI and local runs from hanging indefinitely when pytest fixtures stall, ensuring faster feedback loops and predictable automation pipelines.

## Development Workflow

### Code Organization
- Activities in `src/activities/` as pure, testable functions
- Workflows in `src/workflows/` with minimal logic
- Workers in `src/workers/` for process management
- Shared models in `src/models/` for data structures
- Utilities in `src/utils/` for structured logging and helpers
- Common code in `src/common/` for CLI and user-facing utilities
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

This constitution supersedes all other development practices. Changes require explicit amendment with version bump and impact assessment. All features MUST demonstrate compliance with these principles, particularly Simplicity First, Test-Driven Development, and the Temporal-specific operational patterns.

**Amendment Process**: Constitutional changes require documentation of impact on existing workflows, approval from maintainers, and migration plan for existing code.

**Compliance**: All pull requests and code reviews MUST verify adherence to these principles, with particular attention to temporal workflow correctness, operational patterns (worker shutdown, connection management, error handling), and test coverage.

**Version**: 1.4.0 | **Ratified**: 2025-10-28 | **Last Amended**: 2025-11-10
