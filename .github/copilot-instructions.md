# maverick Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-10-28

## Active Technologies
- Python 3.11 + Temporal Python SDK, uv toolchain, OpenCode CLI (`speckit.implement`); Temporal workflow state (no new external stores) (001-automate-phase-tasks)
- Python 3.11, Rust toolchain (cargo), Temporal Python SDK, uv tooling, CodeRabbit CLI, OpenCode CLI; Temporal workflow state and downstream artifact persistence (001-automate-review-fix)
- Python 3.11 + Temporal Python SDK; uv for dependency management; pytest (tests) (001-cli-prereq-check)
- Python 3.11 + Temporal Python SDK, GitHub CLI (`gh`), uv toolchain (001-pr-ci-automation)
- N/A (stateful data returned via Temporal workflow payloads) (001-pr-ci-automation)
- Python 3.11 (existing project standard) + Temporal Python SDK (existing), uv for dependency management (existing) (001-multi-task-orchestration)
- N/A (all state stored in Temporal workflow state as per FR-017, FR-019) (001-multi-task-orchestration)
- Python 3.11 + Temporal Python SDK, git CLI (via subprocess), uv toolchain, structured logging utilities (001-task-branch-switch)
- N/A (Temporal workflow state only) (001-task-branch-switch)
- Python 3.11 (project standard) + Temporal Python SDK (already), `click` (CLI ergonomics) or built-in `argparse` (DECISION PENDING), existing project logging modules (`src/common/logging.py`). (001-maverick-cli)
- N/A (read-only repo + Temporal state) (001-maverick-cli)
- Python 3.11 + Click (CLI), Temporal Python SDK, uv (tooling). Optional: Rich for styled output. Future TUI candidate: Textual (research below). (001-maverick-cli)
- N/A (no new stores; state remains in Temporal workflow state) (001-maverick-cli)
- Python 3.11 + Click (CLI), temporalio (Temporal Python SDK client), uv (tooling), Git CLI (runtime), project logging modules (`src/common/logging.py`) (001-maverick-cli)
- N/A (no new stores; uses Temporal service and repo filesystem) (001-maverick-cli)

## Project Structure

```text
src/
tests/
```

## Commands

All test commands MUST include a timeout wrapper while we investigate hanging pytest runs.

```bash
# Run tests (wrap with timeout to prevent hangs)
timeout 600 uv run pytest

# Run tests with coverage
timeout 600 uv run pytest --cov

# Run linter
uv run ruff check .

# Format code
uv run ruff format .

# Run specific test file
timeout 600 uv run pytest tests/unit/test_example.py
```

Allocate 10 minutes by default because the current suite averages ~8 minutes. Adjust the timeout window when suites need longer to finish, but every pytest invocation MUST include a `timeout` wrapper until the hanging test issue is resolved.

## Code Style

Python 3.11: Follow standard conventions

## Temporal Workflow Best Practices

### Determinism Requirements
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

### Workflow Logging
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

# Incorrect: Module-level logger
logger = get_structured_logger("my_workflow")  # ❌ Non-deterministic
logger.info("workflow_started", param=value)
```

## Worker Best Practices

### Graceful Shutdown
- **Add signal handlers** for SIGTERM and SIGINT
- **Use asyncio.Event** for shutdown coordination
- **Cancel tasks properly** on shutdown
- **Clean up resources** in finally blocks

```python
# Set up shutdown handling
loop = asyncio.get_event_loop()
shutdown_event = asyncio.Event()

def handle_shutdown(sig: int) -> None:
    logger.info("shutdown_signal_received", signal=signal.Signals(sig).name)
    shutdown_event.set()

loop.add_signal_handler(signal.SIGTERM, lambda: handle_shutdown(signal.SIGTERM))
loop.add_signal_handler(signal.SIGINT, lambda: handle_shutdown(signal.SIGINT))

try:
    # Run worker...
finally:
    loop.remove_signal_handler(signal.SIGTERM)
    loop.remove_signal_handler(signal.SIGINT)
```

### Connection Management
- **Use environment variables** for configuration (TEMPORAL_HOST, TEMPORAL_CONNECTION_TIMEOUT)
- **Validate configuration** before use (non-empty, positive values)
- **Apply connection timeouts** with `asyncio.wait_for()`
- **Handle specific exceptions** (TimeoutError, generic Exception)
- **Log connection attempts** with target and timeout
- **Exit explicitly on failure** with `sys.exit(1)` to prevent silent crashes

```python
# Correct: Configurable connection with timeout
temporal_host = os.getenv("TEMPORAL_HOST", "localhost:7233")
connection_timeout = float(os.getenv("TEMPORAL_CONNECTION_TIMEOUT", "10.0"))

# Validate
if not temporal_host or not temporal_host.strip():
    logger.error("temporal_config_invalid", error="TEMPORAL_HOST cannot be empty")
    sys.exit(1)

try:
    client = await asyncio.wait_for(
        Client.connect(temporal_host),
        timeout=connection_timeout
    )
except asyncio.TimeoutError:
    logger.error("temporal_connection_failed", error_type="TimeoutError", ...)
    sys.exit(1)
except Exception as e:
    logger.error("temporal_connection_failed", error_type=type(e).__name__, ...)
    sys.exit(1)
```

## Code Quality Standards

### Linting Configuration
- **Avoid contradictory rules** - Don't globally ignore rules that have per-file-ignores
- **Use per-file-ignores deliberately** - Allow exceptions only where needed (e.g., T201 for CLI)
- **Keep global ignores minimal** - Only ignore rules that apply project-wide

### Data Model Validation
- **Validate invariants in `__post_init__`** - Use dataclass post-init for business rules
- **Provide clear error messages** - Include what failed and why
- **Document invariants** in docstrings

```python
@dataclass
class WorkflowState:
    """State tracking.
    
    Invariants:
        - state="pending" requires verification=None
        - state="verified" requires verification with status="pass"
    """
    state: WorkflowStateType
    verification: VerificationResult | None = None
    
    def __post_init__(self) -> None:
        if self.state == "pending" and self.verification is not None:
            raise ValueError("state=pending requires verification=None")
```

### Input Validation
- **Validate early** - Check inputs before processing
- **Call validation functions** in the correct order
- **Let exceptions propagate** - Don't swallow validation errors

```python
# Correct: Validate host before using it
host = https_match.group(1).lower()
validate_github_host(host)  # ✓ Validates before proceeding
owner = https_match.group(2)
# ... continue processing
```

## Error Handling & Resilience

### Subprocess Output Decoding
- **Always use `errors='replace'`** with `.decode()` to prevent UnicodeDecodeError
- **Never use bare `.decode()`** - can crash on non-UTF-8 bytes from external tools

```python
# Correct: Tolerant decoding
stderr_text = stderr.decode('utf-8', errors='replace')
error_output = stderr.decode('utf-8', errors='replace').lower()

# Incorrect: Can crash
stderr_text = stderr.decode()  # ❌ Crashes on invalid UTF-8
```

### JSON Serialization Safety
- **Use SafeJSONEncoder** for structured logging
- **Implement fallback handling** - never let serialization errors propagate
- SafeJSONEncoder should handle: datetime, sets, bytes, custom objects

```python
# Safe serialization with fallback
try:
    json_output = json.dumps(log_entry, cls=SafeJSONEncoder)
except Exception as e:
    fallback_entry = {"logger": name, "event": event, "serialization_error": str(e)}
    json_output = json.dumps(fallback_entry)
```

### CLI Tool Integration
- **Validate tool flags** - check documentation for supported options
- **Use documented APIs** - prefer environment variables or URL formats
- **Example**: Use `HOST/OWNER/REPO` format for gh CLI, not invalid flags

```python
# Correct: Use documented format
repo_with_host = f"{host}/{repo_slug}"
cmd = ["gh", "repo", "view", repo_with_host]
```

## Logging Architecture

### Module Separation
- **`src/utils/logging.py`** - Structured JSON logging for Activities & Workers
- **`src/common/logging.py`** - Traditional logging for CLI & user-facing code
- **Workflows** - ALWAYS use `workflow.logger` (never import loggers)

```python
# Activities: Structured logging
from src.utils.logging import get_structured_logger
logger = get_structured_logger("activity.my_activity")

# Workflows: Use workflow.logger ONLY
workflow.logger.info("event", extra={"workflow_id": workflow.info().workflow_id})
```

## Worker Architecture

### Consolidation Pattern
- **Single worker** in `src/workers/main.py` hosts ALL workflows and activities
- **Unified task queue** - All workflows use same queue
- **Benefits** - Simplified operations, better resource utilization, easier deployment

## Recent Changes
- 001-maverick-cli: Added Python 3.11 + Click (CLI), temporalio (Temporal Python SDK client), uv (tooling), Git CLI (runtime), project logging modules (`src/common/logging.py`)
- 001-maverick-cli: Added Python 3.11 + Click (CLI), Temporal Python SDK, uv (tooling). Optional: Rich for styled output. Future TUI candidate: Textual (research below).
- 001-maverick-cli: Added [if applicable, e.g., PostgreSQL, CoreData, files or N/A]


## Documentation Standards

### Ephemeral Specs
- **`specs/` directory**: Contains ephemeral feature specifications used during development
- **DO NOT reference** specs in durable documentation (README, AGENTS.md, etc.)
- **DO NOT link** to specs from user-facing documentation
- Specs are working documents that may be moved, renamed, or deleted after feature completion

### Durable Documentation
- **README.md**: User-facing project documentation
- **AGENTS.md**: AI agent development guidelines
- **Code comments**: Inline documentation for maintainability

## MCP Server Usage

When assistance is needed beyond local codebase context:

- **context7 MCP server**: Use for retrieving up-to-date library documentation and code examples (e.g., Temporal SDK usage, Python standard library)
- **github MCP server**: Use for GitHub operations like creating issues, PRs, managing branches, and searching repositories

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
