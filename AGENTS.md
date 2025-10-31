# maverick Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-10-29

## Active Technologies
- Python 3.11 + Temporal Python SDK, PyYAML (for YAML parsing), uv (dependency management) (001-docker-compose-runner)
- Temporary filesystem (for Docker Compose YAML files) (001-docker-compose-runner)

- Python 3.11 + Temporal Python SDK, gh CLI (runtime tool), uv (dependency manager) (001-workflow-params-repo-check)

## Project Structure

```text
src/
  activities/     # Temporal activities (pure, testable functions)
  workflows/      # Temporal workflows (orchestration logic)
  workers/        # Worker process management
  models/         # Shared data structures
  utils/          # Utility functions
  cli/            # CLI entry points
tests/
  unit/           # Unit tests for activities
  integration/    # Integration tests for workflows
```

## Commands

All commands MUST be run via uv (per Constitution III. UV-Based Development):

```bash
# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov

# Run linter
uv run ruff check .

# Format code
uv run ruff format .

# Run specific test file
uv run pytest tests/unit/test_example.py

# Run Temporal worker (when implemented)
uv run python -m src.workers.main
```

## Code Style

Python 3.11: Follow standard conventions

## Temporal Workflow Best Practices

### Determinism Requirements (NON-NEGOTIABLE)
- **NEVER use `time.time()`** - Use `workflow.now()` instead (returns datetime)
- **NEVER use `datetime.now()`** - Use `workflow.now()` for current workflow time
- **NEVER use `random.random()`** - Use `workflow.random()` for deterministic randomness
- Duration calculation: Use `(workflow.now() - start_time).total_seconds()` for timedelta math

### Common Patterns
```python
# Correct: Deterministic time tracking
start_time = workflow.now()  # Returns datetime
# ... workflow logic ...
end_time = workflow.now()
duration_ms = int((end_time - start_time).total_seconds() * 1000)

# Incorrect: Non-deterministic (will fail)
import time
start_time = time.time()  # ❌ RestrictedWorkflowAccessError
```

### Activity Result Deserialization
- **Always specify `result_type`** when calling activities that return dataclasses
- Without `result_type`, Temporal deserializes to dict instead of dataclass

```python
# Correct: Specify result_type for proper deserialization
result = await workflow.execute_activity(
    "my_activity",
    start_to_close_timeout=timedelta(seconds=30),
    result_type=MyDataClass,  # ✓ Returns MyDataClass instance
)

# Incorrect: Missing result_type
result = await workflow.execute_activity(
    "my_activity",
    start_to_close_timeout=timedelta(seconds=30),
)  # ❌ Returns dict, causes AttributeError on attribute access
```

### Enum Serialization
- **DO NOT use Enums for Temporal data models** - Enums require custom serialization
- **Use `Literal` types with string values** - Works seamlessly with Temporal's JSON converter

```python
# Correct: Literal types for type safety
from typing import Literal

CheckStatus = Literal["pass", "fail"]

@dataclass
class PrereqCheckResult:
    tool: str
    status: CheckStatus  # ✓ Type-safe, serializes naturally
    message: str

# Incorrect: Enum requires custom serializer
class CheckStatus(Enum):  # ❌ Needs custom data converter
    PASS = "pass"
    FAIL = "fail"
```

### Why This Matters
Temporal workflows must be **deterministic** to support replay. Non-deterministic operations like system time calls will cause `RestrictedWorkflowAccessError` and prevent workflow execution. Proper type hints ensure correct deserialization and type safety.

### Workflow Logging (NON-NEGOTIABLE)
- **ALWAYS use `workflow.logger`** - Never use module-level loggers in workflows
- **Pass metadata via `extra` dict** - Use standard Python logging format
- Include workflow context: `workflow.info().workflow_id`, `workflow.info().run_id`

```python
# Correct: Use workflow.logger with extra dict
workflow.logger.info(
    "workflow_started",
    extra={
        "workflow_id": workflow.info().workflow_id,
        "run_id": workflow.info().run_id,
        "param": value
    }
)

# Incorrect: Module-level logger (non-deterministic)
logger = get_structured_logger("my_workflow")  # ❌ Breaks replay
logger.info("workflow_started", param=value)
```

**Why**: Module-level loggers can cause non-deterministic behavior during workflow replay. Only `workflow.logger` is guaranteed to be replay-safe.

## Worker Best Practices

### Graceful Shutdown (REQUIRED)
Every worker MUST implement proper shutdown handling:

- **Add signal handlers** for SIGTERM and SIGINT before starting worker
- **Use asyncio.Event** for shutdown coordination
- **Cancel tasks properly** and await their cancellation
- **Clean up resources** in finally blocks (remove signal handlers)

```python
# Required pattern for worker shutdown
loop = asyncio.get_event_loop()
shutdown_event = asyncio.Event()

def handle_shutdown(sig: int) -> None:
    logger.info("shutdown_signal_received", signal=signal.Signals(sig).name)
    shutdown_event.set()

# Register handlers BEFORE starting worker
loop.add_signal_handler(signal.SIGTERM, lambda: handle_shutdown(signal.SIGTERM))
loop.add_signal_handler(signal.SIGINT, lambda: handle_shutdown(signal.SIGINT))

try:
    worker_task = asyncio.create_task(worker.run())
    shutdown_task = asyncio.create_task(shutdown_event.wait())
    
    done, pending = await asyncio.wait(
        [worker_task, shutdown_task],
        return_when=asyncio.FIRST_COMPLETED
    )
    
    if shutdown_task in done:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
    
    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
finally:
    # MUST clean up handlers
    loop.remove_signal_handler(signal.SIGTERM)
    loop.remove_signal_handler(signal.SIGINT)
```

### Connection Management (REQUIRED)
All Temporal client connections MUST follow this pattern:

- **Use environment variables** for configuration
  - `TEMPORAL_HOST` (default: "localhost:7233")
  - `TEMPORAL_CONNECTION_TIMEOUT` (default: "10.0")
- **Validate configuration** before attempting connection
- **Apply connection timeouts** with `asyncio.wait_for()`
- **Handle exceptions explicitly** (TimeoutError, generic Exception)
- **Log all connection attempts** with target and timeout
- **Exit on failure** with `sys.exit(1)` to prevent silent crashes

```python
# Required pattern for Temporal connection
import asyncio
import os
import sys

temporal_host = os.getenv("TEMPORAL_HOST", "localhost:7233")
connection_timeout = float(os.getenv("TEMPORAL_CONNECTION_TIMEOUT", "10.0"))

# Validate configuration
if not temporal_host or not temporal_host.strip():
    logger.error("temporal_config_invalid", error="TEMPORAL_HOST cannot be empty")
    sys.exit(1)

if connection_timeout <= 0:
    logger.error("temporal_config_invalid", error="timeout must be positive")
    sys.exit(1)

# Connect with timeout
logger.info("temporal_connecting", target_host=temporal_host, timeout_seconds=connection_timeout)

try:
    client = await asyncio.wait_for(
        Client.connect(temporal_host),
        timeout=connection_timeout
    )
    logger.info("temporal_connected", target_host=temporal_host, status="success")
except asyncio.TimeoutError:
    logger.error(
        "temporal_connection_failed",
        error_type="TimeoutError",
        error_message=f"Connection timeout after {connection_timeout}s",
        target_host=temporal_host
    )
    sys.exit(1)
except Exception as e:
    logger.error(
        "temporal_connection_failed",
        error_type=type(e).__name__,
        error_message=str(e),
        target_host=temporal_host
    )
    sys.exit(1)
```

## Code Quality Standards

### Linting Configuration
- **Avoid contradictory rules** - Don't globally ignore rules that have per-file-ignores
- **Use per-file-ignores deliberately** - Allow exceptions only where needed
  - Example: Allow T201 (print) only in `src/cli/*.py`
- **Keep global ignores minimal** - Only ignore rules that apply project-wide

Example from `ruff.toml`:
```toml
# Correct: T201 not in global ignore, only in per-file-ignores
[lint]
ignore = [
    "E501",  # Line too long
]

[lint.per-file-ignores]
"src/cli/*.py" = ["T201"]  # Allow print only in CLI
```

### Data Model Validation (REQUIRED)
All dataclasses with business rules MUST validate in `__post_init__`:

- **Validate invariants immediately** - Fail fast on construction
- **Provide clear error messages** - Include what failed and expected value
- **Document invariants** in docstrings
- **Check both directions** of constraints (if applicable)

```python
@dataclass
class WorkflowState:
    """State tracking.
    
    Invariants:
        - state="pending" requires verification=None
        - state="verified" requires verification with status="pass"
        - state="failed" requires verification with status="fail"
    """
    state: WorkflowStateType
    verification: VerificationResult | None = None
    
    def __post_init__(self) -> None:
        """Validate state transitions."""
        # Validate pending state
        if self.state == "pending" and self.verification is not None:
            raise ValueError("state=pending requires verification=None")
        
        # Validate verification presence
        if self.verification is not None and self.state == "pending":
            raise ValueError("verification present requires state!=pending")
        
        # Validate verified/failed states
        if self.state == "verified" and self.verification is None:
            raise ValueError("state=verified requires verification result")
        # ... more validations
```

### Input Validation (REQUIRED)
All input parsing and validation MUST follow this pattern:

- **Validate early** - Check inputs immediately after extraction
- **Call validation in correct order** - Host before slug, etc.
- **Apply validation consistently** - Same validation for all input formats
- **Let exceptions propagate** - Don't swallow validation errors

```python
# Correct: Validate host immediately after extraction
if https_match:
    host = https_match.group(1).lower()
    validate_github_host(host)  # ✓ Validates before continuing
    owner = https_match.group(2)
    repo = https_match.group(3)
    repo_slug = f"{owner}/{repo}"
    _validate_repo_slug(repo_slug)  # ✓ Second validation
    return NormalizedRepo(host=host, repo_slug=repo_slug)

# Incorrect: Missing validation
if https_match:
    host = https_match.group(1).lower()  # ❌ Not validated
    repo_slug = f"{owner}/{repo}"
    return NormalizedRepo(host=host, repo_slug=repo_slug)  # ❌ Invalid host accepted
```

## Error Handling & Resilience (CRITICAL)

### Subprocess Output Decoding (REQUIRED)
All subprocess stderr/stdout decoding MUST use tolerant error handling:

- **Always use `errors='replace'`** with `.decode()` - Prevents UnicodeDecodeError
- **Never use bare `.decode()`** - Can crash on non-UTF-8 bytes
- **Call `.lower()` after decoding** - For safe case-insensitive matching

```python
# Correct: Tolerant decoding prevents crashes
stderr_text = stderr.decode('utf-8', errors='replace')
error_output = stderr.decode('utf-8', errors='replace').lower()

# Incorrect: Can raise UnicodeDecodeError
stderr_text = stderr.decode()  # ❌ Crashes on invalid UTF-8
```

**Why**: External tools (gh CLI, git, etc.) may output non-UTF-8 bytes. Tolerant decoding ensures activities never crash due to encoding issues.

### JSON Serialization Safety (REQUIRED)
All structured logging MUST use safe JSON serialization:

- **Use SafeJSONEncoder** - Handles datetime, sets, bytes, custom objects
- **Implement fallback handling** - Never let serialization errors propagate
- **Provide minimal fallback** - Include event name and error details

```python
# Correct: Safe serialization with fallback
try:
    json_output = json.dumps(log_entry, cls=SafeJSONEncoder)
except Exception as e:
    # Fallback: emit minimal log with error
    fallback_entry = {
        "logger": self.name,
        "event": event,
        "timestamp": log_entry.get("timestamp", datetime.now(UTC).isoformat()),
        "serialization_error": str(e)
    }
    try:
        json_output = json.dumps(fallback_entry)
    except Exception:
        # Last resort: hardcoded string
        json_output = f'{{"logger":"{self.name}","event":"{event}","error":"serialization_failed"}}'

# Incorrect: No error handling
json_output = json.dumps(log_entry)  # ❌ Can raise TypeError
```

**SafeJSONEncoder should handle**:
- `datetime` → ISO format string
- `set`/`frozenset` → list
- `bytes` → UTF-8 string with `errors='replace'`
- Other objects → `str()` representation

### CLI Tool Integration (REQUIRED)
When integrating with external CLI tools (gh, git, etc.):

- **Validate tool flags** - Check documentation for supported options
- **Use documented APIs** - Prefer environment variables or URL formats over undocumented flags
- **Handle tool-specific formats** - Use proper argument formats (e.g., `HOST/OWNER/REPO` for gh)

```python
# Correct: Use documented HOST/OWNER/REPO format for gh CLI
repo_with_host = f"{host}/{repo_slug}"
cmd = ["gh", "repo", "view", repo_with_host]

# Incorrect: Using invalid -h flag with gh repo view
cmd = ["gh", "repo", "view", repo_slug, "-h", host]  # ❌ -h not supported
```

**Research First**: Always verify CLI tool options with `--help` or official documentation before using flags.

## Logging Architecture (REQUIRED)

### Module Separation
The project maintains TWO logging modules with distinct purposes:

**`src/utils/logging.py`** - Structured JSON logging for Temporal components:
- Used by: Activities, Workers
- Features: SafeJSONEncoder, multi-level fallbacks, Temporal-safe timestamps
- Format: JSON with structured fields

**`src/common/logging.py`** - Traditional logging for user-facing components:
- Used by: CLI tools, non-Temporal code
- Features: Standard Python logging, human-readable format
- Format: Plain text with timestamps

```python
# Activities: Use structured logging
from src.utils.logging import get_structured_logger
logger = get_structured_logger("activity.my_activity")
logger.info("operation_started", param=value)

# CLI: Use traditional logging
from src.common.logging import get_logger
logger = get_logger(__name__)
logger.info("User-friendly message")

# Workflows: ALWAYS use workflow.logger (never import loggers)
workflow.logger.info("workflow_event", extra={"workflow_id": workflow.info().workflow_id})
```

**Important**: Never import logging modules in workflows - use `workflow.logger` exclusively.

## Worker Architecture (REQUIRED)

### Consolidation Pattern
Maintain a SINGLE worker process that registers ALL workflows and activities:

- **Single worker file** - `src/workers/main.py` hosts everything
- **Unified task queue** - All workflows use same queue (e.g., `maverick-task-queue`)
- **Single entry point** - One CLI command to start worker
- **Register everything** - All workflows and activities in one Worker instance

```python
# Correct: Consolidated worker
worker = Worker(
    client,
    task_queue="maverick-task-queue",
    workflows=[ReadinessWorkflow, RepoVerificationWorkflow, ...],
    activities=[check_gh_status, verify_repository, ...]
)

# Incorrect: Multiple separate workers
# ❌ Don't create separate workers for different workflow types
```

**Benefits**: Simplified operations, better resource utilization, easier deployment, unified monitoring.

## Development Principles

### Constitution Compliance
All code MUST follow the Maverick Constitution:
- **Simplicity First**: Start with simplest approach; justify complexity
- **Test-Driven Development**: Red-Green-Refactor cycle (NON-NEGOTIABLE)
- **UV-Based Development**: All dependency management via uv (NON-NEGOTIABLE)
- **Temporal-First Architecture**: Code organized around Temporal concepts
- **Observability**: Structured logging, metrics, tracing required

### Quality Standards
- Minimum 90% code coverage for workflow-critical paths
- All Activities MUST be pure, testable functions
- Workflows MUST orchestrate Activities without side effects
- Error handling MUST provide clear context for debugging

## Recent Changes
- 001-docker-compose-runner: Added Python 3.11 + Temporal Python SDK, PyYAML (for YAML parsing), uv (dependency management)
- 001-docker-compose-runner: Added Python 3.11 + Temporal Python SDK, PyYAML (for YAML parsing), uv (dependency management)

- 001-workflow-params-repo-check: Added Python 3.11 + Temporal Python SDK, gh CLI (runtime tool), uv (dependency manager)

## Documentation Standards

### Ephemeral Specs
- **`specs/` directory**: Contains ephemeral feature specifications used during development
- **DO NOT reference** specs in durable documentation (README, AGENTS.md, etc.)
- **DO NOT link** to specs from user-facing documentation
- Specs are working documents that may be moved, renamed, or deleted after feature completion
- Specs may be moved to `specs-completed/` or archived after implementation

### Durable Documentation
- **README.md**: User-facing project documentation and quick start guides
- **AGENTS.md**: Comprehensive AI agent development guidelines
- **Code comments**: Inline documentation for maintainability
- **Docstrings**: API documentation within code

**Rule**: Only reference permanent, maintained documentation in user-facing materials. Specs are for development planning only.

## MCP Server Usage

When assistance is needed beyond local codebase context:

- **context7 MCP server**: Use for retrieving up-to-date library documentation and code examples (e.g., Temporal SDK usage, Python standard library)
- **github MCP server**: Use for GitHub operations like creating issues, PRs, managing branches, and searching repositories

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
