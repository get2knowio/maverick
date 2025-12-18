# Research: Subprocess Execution Module

**Feature**: 017-subprocess-runners
**Date**: 2025-12-18

## Overview

Research findings for implementing a subprocess execution module in Maverick. This document captures technology decisions, best practices, and patterns discovered during the planning phase.

---

## 1. Async Subprocess Execution in Python

### Decision: Use `asyncio.create_subprocess_exec()`

**Rationale**: This is the standard async subprocess API in Python 3.10+ and is already used throughout the Maverick codebase (see `maverick.tools.git`, `maverick.tools.github`, `maverick.workflows.validation`).

**Alternatives Considered**:
- `subprocess.run()` with threading: Rejected - violates Constitution I (Async-First)
- `trio` subprocess: Rejected - introduces new dependency, not compatible with existing asyncio codebase
- Third-party `aiosubprocess`: Rejected - unnecessary dependency when stdlib works well

**Key Patterns from Codebase**:
```python
process = await asyncio.create_subprocess_exec(
    *cmd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    cwd=cwd,
)
stdout_bytes, stderr_bytes = await asyncio.wait_for(
    process.communicate(), timeout=timeout
)
```

---

## 2. Timeout Handling with Graceful Termination

### Decision: SIGTERM + 2s Grace Period + SIGKILL Escalation

**Rationale**: This pattern aligns with spec FR-004 and industry best practices for graceful process termination. The 2-second grace period allows processes to clean up resources before forced termination.

**Alternatives Considered**:
- Immediate SIGKILL: Rejected - doesn't allow process cleanup, can leave orphaned resources
- Longer grace period (5s+): Rejected - spec requires "terminated within 1 second of timeout expiration" (SC-006)
- SIGINT then SIGTERM then SIGKILL: Rejected - overly complex, SIGTERM is sufficient

**Implementation Pattern**:
```python
try:
    stdout, stderr = await asyncio.wait_for(
        process.communicate(), timeout=timeout
    )
except asyncio.TimeoutError:
    # SIGTERM
    process.terminate()
    try:
        # 2-second grace period
        await asyncio.wait_for(process.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        # SIGKILL escalation
        process.kill()
        await process.wait()
    raise TimeoutError(...)
```

---

## 3. Streaming Output for Large Commands

### Decision: Async Line Iterator with `readline()`

**Rationale**: Streaming via `readline()` provides natural line-by-line output, avoids buffering entire output in memory (FR-007), and delivers lines within 50ms of subprocess producing them (SC-002).

**Alternatives Considered**:
- Chunk-based streaming: Rejected - loses line boundaries, harder for callers to process
- Callback-based streaming: Rejected - less Pythonic than async generators
- Third-party streaming libraries: Rejected - unnecessary dependency

**Implementation Pattern**:
```python
async def stream_output(
    process: asyncio.subprocess.Process,
) -> AsyncIterator[str]:
    """Stream stdout lines as they become available."""
    assert process.stdout is not None
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        yield line.decode("utf-8", errors="replace").rstrip("\n")
```

---

## 4. Environment Variable Handling

### Decision: Merge Mode (Inherit + Override)

**Rationale**: Spec FR-007a requires inheriting parent environment by default with ability to add/override. This matches typical use cases where tools need PATH and other system variables but may need custom settings.

**Alternatives Considered**:
- Clean slate (explicit env only): Rejected - breaks most commands that need PATH
- Full copy without merge: Rejected - doesn't allow custom variables
- No env parameter: Rejected - spec requires caller override capability

**Implementation Pattern**:
```python
def _build_env(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    """Build environment by merging parent env with overrides."""
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return env
```

---

## 5. Working Directory Validation

### Decision: Fail-Fast with `WorkingDirectoryError`

**Rationale**: Spec FR-005 requires validating directory exists before execution and raising `WorkingDirectoryError` if not found. Early validation provides clear error messages.

**Alternatives Considered**:
- Let subprocess fail naturally: Rejected - error messages less clear
- Auto-create missing directories: Rejected - could hide bugs, unexpected side effects

**Implementation Pattern**:
```python
def _validate_cwd(cwd: Path | None) -> None:
    if cwd is not None and not cwd.is_dir():
        raise WorkingDirectoryError(f"Working directory does not exist: {cwd}")
```

---

## 6. Output Parsing Architecture

### Decision: Pluggable Parser Registry

**Rationale**: Different tools (ruff, mypy, rustc, eslint) have different output formats. A registry of parsers allows adding new formats without modifying core code.

**Alternatives Considered**:
- Single universal parser: Rejected - output formats too different
- Hardcoded parsers in runner: Rejected - violates separation of concerns
- No parsing (raw output only): Rejected - spec requires structured error data (FR-011 to FR-013)

**Implementation Pattern**:
```python
class OutputParser(Protocol):
    """Protocol for output parsers."""
    def can_parse(self, output: str) -> bool: ...
    def parse(self, output: str) -> list[ParsedError]: ...

PARSERS: dict[str, OutputParser] = {
    "python": PythonTracebackParser(),
    "rust": RustCompilerParser(),
    "eslint": ESLintJSONParser(),
}
```

---

## 7. GitHub CLI Integration

### Decision: Wrap `gh` CLI with JSON Output

**Rationale**: The `gh` CLI already provides comprehensive GitHub API access with authentication handled. Using `--json` flag gives structured output that's easy to parse. This pattern is already established in `maverick.tools.github`.

**Alternatives Considered**:
- Direct GitHub API via `httpx`: Rejected - requires managing OAuth tokens, rate limiting
- `PyGitHub` library: Rejected - adds dependency, `gh` CLI already required
- GraphQL API directly: Rejected - more complex, `gh` abstracts this well

**Key Patterns**:
```python
stdout, stderr, rc = await _run_gh_command(
    "issue", "list", "--label", label, "--json", "number,title,labels,state,url"
)
issues = json.loads(stdout)
```

---

## 8. CodeRabbit Integration

### Decision: Optional Tool with Graceful Degradation

**Rationale**: Spec FR-023 requires returning empty results with warning (not error) if CodeRabbit is not installed. This aligns with Constitution VIII (Relentless Progress) - workflows continue without optional tools.

**Alternatives Considered**:
- Require CodeRabbit: Rejected - spec says optional
- Fail silently: Rejected - users should know tool is missing

**Implementation Pattern**:
```python
async def run_review(self, files: list[Path]) -> CodeRabbitResult:
    if not await self._is_coderabbit_installed():
        logger.warning("CodeRabbit not installed, skipping review")
        return CodeRabbitResult(findings=[], warnings=["CodeRabbit not installed"])
    # ... run review
```

---

## 9. Error Handling Strategy

### Decision: Exception Hierarchy under `MaverickError`

**Rationale**: Constitution requires structured error types from exception hierarchy. New runner exceptions extend existing patterns.

**New Exception Classes**:
```python
class RunnerError(MaverickError):
    """Base exception for runner failures."""

class WorkingDirectoryError(RunnerError):
    """Working directory does not exist or is not accessible."""

class CommandTimeoutError(RunnerError):
    """Command execution exceeded timeout."""

class CommandNotFoundError(RunnerError):
    """Executable not found in PATH."""

class GitHubCLINotFoundError(RunnerError):
    """GitHub CLI (gh) is not installed."""

class GitHubAuthError(RunnerError):
    """GitHub CLI is not authenticated."""
```

---

## 10. Data Model Strategy

### Decision: Frozen Dataclasses with `slots=True`

**Rationale**: Following existing patterns in `maverick.agents.result` and `maverick.models`. Frozen dataclasses provide immutability, slots provide memory efficiency for frequently-instantiated result objects.

**Alternatives Considered**:
- Pydantic BaseModel: Considered for validation, but overkill for simple result objects
- Named tuples: Rejected - less readable, no type validation in `__post_init__`
- Regular dataclasses: Rejected - mutability can cause bugs

**Pattern**:
```python
@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
```

---

## 11. Validation Stage Orchestration

### Decision: Extend Existing `ValidationWorkflow` Patterns

**Rationale**: `maverick.workflows.validation` already implements stage orchestration with fix attempts. `ValidationRunner` can reuse these patterns or wrap them.

**Key Insight**: The existing `ValidationWorkflow` class handles:
- Sequential stage execution
- Fix agent invocation
- Timeout handling
- Progress updates

**Recommendation**: `ValidationRunner` should be a thin wrapper that delegates to the existing workflow or extracts common utilities.

---

## 12. Testing Strategy

### Decision: Comprehensive Mocking with Real Integration Tests

**Rationale**: Unit tests mock subprocess creation to test logic. Integration tests (marked with `pytest.mark.integration`) run actual commands.

**Mock Pattern** (from existing tests):
```python
@pytest.fixture
def mock_subprocess():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"output", b""))
    mock_proc.wait = AsyncMock()
    mock_proc.terminate = MagicMock()
    mock_proc.kill = MagicMock()
    return mock_proc
```

---

## Summary of Decisions

| Area | Decision | Key Pattern |
|------|----------|-------------|
| Subprocess API | `asyncio.create_subprocess_exec()` | No shell=True |
| Timeout | SIGTERM + 2s + SIGKILL | Graceful escalation |
| Streaming | `readline()` async iterator | Line-by-line |
| Environment | Merge mode | Inherit + override |
| Working Dir | Fail-fast validation | `WorkingDirectoryError` |
| Parsing | Pluggable registry | Protocol-based |
| GitHub | Wrap `gh` CLI | JSON output |
| CodeRabbit | Optional + graceful | Warning not error |
| Errors | Exception hierarchy | `RunnerError` base |
| Data Models | Frozen dataclasses | slots=True |
| Validation | Extend workflow patterns | Reuse existing |
| Testing | Mock + integration | pytest-asyncio |

All NEEDS CLARIFICATION items from Technical Context have been resolved through this research.
