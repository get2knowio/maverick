# Implementation Plan: StepExecutor Protocol

**Branch**: `032-step-executor-protocol` | **Date**: 2026-02-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/032-step-executor-protocol/spec.md`

## Summary

Introduce a `StepExecutor` runtime-checkable Protocol in `maverick.dsl.executor` that
decouples YAML workflow agent step execution from the Claude Agent SDK. Provide a
`ClaudeStepExecutor` concrete implementation wrapping the existing `MaverickAgent.execute()`
flow, integrate it into `execute_agent_step`, and inject it once per workflow run via
`WorkflowContext.step_executor`. Adds typed output validation (`output_schema`), per-step
configuration (`StepExecutorConfig`), and structured observability logging. Zero regressions
in existing agent behavior required (SC-001).

## Technical Context

**Language/Version**: Python 3.10+ with `from __future__ import annotations`
**Primary Dependencies**: Claude Agent SDK (`claude-agent-sdk`), Pydantic, tenacity, structlog
**Storage**: N/A (no persistence changes)
**Testing**: pytest + pytest-asyncio (parallel via xdist)
**Target Platform**: Linux
**Project Type**: Single (CLI)
**Performance Goals**: <5% latency overhead on agent step execution (SC-003)
**Constraints**: Zero regressions in all existing tests (SC-001); protocol module has no
provider-specific imports (SC-004)
**Scale/Scope**: All agent steps in all YAML workflows route through the new abstraction

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Assessment | Notes |
|-----------|-----------|-------|
| **I. Async-First** | ✅ PASS | Protocol is `async def execute()`. ClaudeStepExecutor uses AsyncRetrying. |
| **II. Separation of Concerns** | ✅ PASS | Handler owns context building; executor owns execution mechanics. |
| **III. Dependency Injection** | ✅ PASS | ClaudeStepExecutor receives registry at construction; WorkflowContext injects executor. |
| **IV. Fail Gracefully** | ✅ PASS | Real tenacity retry (not stub). Error propagation preserved. |
| **V. Test-First** | ✅ PASS | Tests for protocol, config, result, claude executor, integration — all required. |
| **VI. Type Safety** | ✅ PASS | `@dataclass(frozen=True, slots=True)` for result/config; `@runtime_checkable Protocol`. |
| **VII. Simplicity / DRY** | ✅ PASS | New executor package moves existing logic (no duplication). |
| **VIII. Relentless Progress** | ✅ PASS | Retry moves to executor (real, not stub). |
| **IX. Hardening** | ✅ PASS | Timeout enforced via config; tenacity retry; specific exception types. |
| **X.1 TUI display-only** | ✅ N/A | No TUI changes. |
| **X.4 Typed contracts** | ✅ PASS | `ExecutorResult` is a frozen dataclass; `to_dict()` for DSL serialization. |
| **X.5 Real resilience** | ✅ PASS | AsyncRetrying applied when retry_policy is set. |
| **X.8 Canonical libraries** | ✅ PASS | structlog, tenacity — existing canonical choices used. |
| **XI. Modularize Early** | ✅ PASS | New `maverick.dsl.executor` package; ~100-150 LOC per module. |
| **XII. Ownership** | ✅ PASS | agent_step.py updated end-to-end; no deferred work. |

**Guardrail violations**: None.

**Complexity tracking**: N/A (no violations).

## Project Structure

### Documentation (this feature)

```text
specs/032-step-executor-protocol/
├── plan.md              # This file
├── research.md          # Phase 0 output ✅
├── data-model.md        # Phase 1 output ✅
├── quickstart.md        # Phase 1 output ✅
├── contracts/
│   └── step_executor_interface.py  # Phase 1 output ✅
└── tasks.md             # Phase 2 output (/speckit.tasks — not yet created)
```

### Source Code (repository root)

```text
# NEW: StepExecutor protocol package
src/maverick/dsl/executor/
├── __init__.py          # Public API: StepExecutor, ExecutorResult, StepExecutorConfig,
│                        #             RetryPolicy, UsageMetadata, ClaudeStepExecutor,
│                        #             DEFAULT_EXECUTOR_CONFIG
├── protocol.py          # StepExecutor @runtime_checkable Protocol (NO provider imports)
├── config.py            # StepExecutorConfig, RetryPolicy frozen dataclasses
├── result.py            # ExecutorResult, UsageMetadata frozen dataclasses
├── errors.py            # ExecutorError, OutputSchemaValidationError
└── claude.py            # ClaudeStepExecutor (wraps MaverickAgent, imports agents/)

# MODIFIED: DSL context — add step_executor field
src/maverick/dsl/context.py

# MODIFIED: Agent step handler — integrate StepExecutor
src/maverick/dsl/serialization/executor/handlers/agent_step.py

# MODIFIED: Workflow executor — create+inject ClaudeStepExecutor once per run
src/maverick/dsl/serialization/executor/executor.py

# MODIFIED: AgentStepRecord — add output_schema field
src/maverick/dsl/serialization/schema.py

# NEW: Tests
tests/unit/dsl/executor/
├── __init__.py
├── test_protocol.py      # Protocol contract: isinstance checks, method signature
├── test_config.py        # StepExecutorConfig + RetryPolicy
├── test_result.py        # ExecutorResult + UsageMetadata
├── test_errors.py        # OutputSchemaValidationError
└── test_claude.py        # ClaudeStepExecutor unit tests (mocked MaverickAgent)

tests/integration/dsl/
└── test_step_executor_integration.py  # End-to-end: workflow + mock executor
```

**Structure Decision**: Single project layout (existing pattern). New `executor` package
sits alongside `serialization`, `expressions`, etc. in `maverick.dsl`. This keeps the
protocol close to its primary consumer (`execute_agent_step`) while maintaining clean
separation from the Claude-specific adapter.

---

## Implementation Phases

### Phase 1: Protocol Package (P1 — Core Decoupling)

**Deliverable**: `maverick.dsl.executor` package with protocol, types, and errors.
All new code is provider-agnostic (SC-004). No existing code changes.

#### Task 1.1 — Create `src/maverick/dsl/executor/config.py`

```python
"""StepExecutorConfig and RetryPolicy frozen dataclasses."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    wait_min: float = 1.0
    wait_max: float = 10.0
    def to_dict(self) -> dict[str, Any]: ...

@dataclass(frozen=True, slots=True)
class StepExecutorConfig:
    timeout: int | None = None
    retry_policy: RetryPolicy | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    def to_dict(self) -> dict[str, Any]: ...

DEFAULT_EXECUTOR_CONFIG = StepExecutorConfig(timeout=300)
```

#### Task 1.2 — Create `src/maverick/dsl/executor/result.py`

```python
"""ExecutorResult and UsageMetadata frozen dataclasses."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maverick.dsl.events import AgentStreamChunk

@dataclass(frozen=True, slots=True)
class UsageMetadata:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_cost_usd: float | None = None
    def to_dict(self) -> dict[str, Any]: ...

@dataclass(frozen=True, slots=True)
class ExecutorResult:
    output: Any
    success: bool
    usage: UsageMetadata | None
    events: tuple[AgentStreamChunk, ...]
    def to_dict(self) -> dict[str, Any]: ...
```

#### Task 1.3 — Create `src/maverick/dsl/executor/errors.py`

```python
"""StepExecutor error hierarchy."""
from __future__ import annotations
from pydantic import ValidationError
from pydantic import BaseModel
from maverick.exceptions import MaverickError

class ExecutorError(MaverickError):
    """Base class for StepExecutor errors."""

class OutputSchemaValidationError(ExecutorError):
    def __init__(self, step_name: str, schema_type: type[BaseModel],
                 validation_errors: ValidationError) -> None: ...
```

#### Task 1.4 — Create `src/maverick/dsl/executor/protocol.py`

```python
"""StepExecutor @runtime_checkable Protocol — no provider-specific imports."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Protocol, TYPE_CHECKING, runtime_checkable
from pydantic import BaseModel
from maverick.dsl.executor.config import StepExecutorConfig
from maverick.dsl.executor.result import ExecutorResult
from maverick.dsl.serialization.executor.handlers.base import EventCallback

@runtime_checkable
class StepExecutor(Protocol):
    async def execute(
        self, *, step_name: str, agent_name: str, prompt: Any,
        instructions: str | None = None, allowed_tools: list[str] | None = None,
        cwd: Path | None = None, output_schema: type[BaseModel] | None = None,
        config: StepExecutorConfig | None = None,
        event_callback: EventCallback | None = None,
    ) -> ExecutorResult: ...
```

**Circular import guard**: `protocol.py` imports `EventCallback` from
`maverick.dsl.serialization.executor.handlers.base`. If this creates a circular dep,
redefine `EventCallback` locally in `protocol.py` and use `TYPE_CHECKING` import.
Prefer the re-use from `handlers.base` to avoid duplication.

#### Task 1.5 — Create `src/maverick/dsl/executor/__init__.py`

Export the stable public API:
```python
from maverick.dsl.executor.config import DEFAULT_EXECUTOR_CONFIG, RetryPolicy, StepExecutorConfig
from maverick.dsl.executor.result import ExecutorResult, UsageMetadata
from maverick.dsl.executor.protocol import StepExecutor
from maverick.dsl.executor.claude import ClaudeStepExecutor

__all__ = [
    "StepExecutor", "ExecutorResult", "StepExecutorConfig",
    "RetryPolicy", "UsageMetadata", "ClaudeStepExecutor",
    "DEFAULT_EXECUTOR_CONFIG",
]
```

**Note**: `ClaudeStepExecutor` is exported from `__init__.py` but NOT from `protocol.py`.
This preserves the zero-provider-dep guarantee for `protocol.py` itself.

---

### Phase 2: ClaudeStepExecutor (P1 — Claude Adapter)

**Deliverable**: `ClaudeStepExecutor` in `maverick.dsl.executor.claude` that replicates
all current `execute_agent_step` execution mechanics (streaming, retry, error wrapping).

#### Task 2.1 — Create `src/maverick/dsl/executor/claude.py`

Key implementation details:

**Constructor**:
```python
class ClaudeStepExecutor:
    def __init__(self, registry: ComponentRegistry) -> None:
        self._registry = registry
        self._logger = get_logger(__name__)
```

**execute() method outline**:
```python
async def execute(self, *, step_name, agent_name, prompt, ...) -> ExecutorResult:
    effective_config = config or DEFAULT_EXECUTOR_CONFIG
    self._logger.info("executor.step_start", step_name=step_name,
                      agent_name=agent_name, config=effective_config.to_dict())
    start_time = time.monotonic()
    emitted_events: list[AgentStreamChunk] = []
    attempt_number = 0

    # --- Agent instantiation ---
    agent_class = self._registry.agents.get(agent_name)
    agent_kwargs = self._build_agent_kwargs(agent_name)
    agent = agent_class(**agent_kwargs)

    # --- Stream callback injection ---
    if event_callback and hasattr(agent, "stream_callback"):
        agent.stream_callback = self._make_stream_callback(
            step_name, agent_name, event_callback, emitted_events
        )

    # --- Thinking indicator (T028 preservation) ---
    thinking_event = AgentStreamChunk(
        step_name=step_name, agent_name=agent_name,
        text="Agent is working...", chunk_type="thinking",
    )
    if event_callback:
        await event_callback(thinking_event)
    emitted_events.append(thinking_event)

    # --- Execution with optional retry ---
    try:
        result = await self._execute_with_retry(
            agent, prompt, effective_config, step_name, agent_name
        )
    except Exception as e:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        self._logger.error("executor.step_error", step_name=step_name,
                           error_type=type(e).__name__, attempt_number=attempt_number)
        raise

    # --- Output schema validation (FR-007) ---
    if output_schema is not None:
        try:
            result = output_schema.model_validate(result)
        except ValidationError as e:
            raise OutputSchemaValidationError(step_name, output_schema, e) from e

    # --- Usage extraction ---
    usage = self._extract_usage(result)

    duration_ms = int((time.monotonic() - start_time) * 1000)
    self._logger.info("executor.step_complete", step_name=step_name,
                      duration_ms=duration_ms,
                      usage=usage.to_dict() if usage else None, success=True)

    return ExecutorResult(
        output=result, success=True, usage=usage,
        events=tuple(emitted_events),
    )
```

**_execute_with_retry()**:
```python
async def _execute_with_retry(self, agent, prompt, config, step_name, agent_name):
    if config.retry_policy:
        rp = config.retry_policy
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(rp.max_attempts),
            wait=wait_exponential(multiplier=1, min=rp.wait_min, max=rp.wait_max),
        ):
            with attempt:
                return await _call_execute(agent, prompt)
    else:
        return await _call_execute(agent, prompt)
```

**_build_agent_kwargs()**:
- For `"implementer"` agent: inject `validation_commands` from `maverick.config`
- All others: return `{}`
- This matches the existing logic in `execute_agent_step`

**_extract_usage()**:
- Duck-type check for `result.usage` attribute (MaverickAgent results may expose usage)
- Return `UsageMetadata(...)` if found; `None` otherwise

**_make_stream_callback()**:
- Returns an async `stream_text_callback` that:
  1. Detects tool calls vs text (same logic as current handler lines 199-219)
  2. Creates `AgentStreamChunk` events
  3. Calls `event_callback()` if available
  4. Appends to `emitted_events` list

**Timeout enforcement**:
- Wrap `_execute_with_retry` in `asyncio.wait_for(coro, timeout=config.timeout)` when
  `config.timeout` is not None

---

### Phase 3: Integration (P1 — Wire Into Handler + Context)

**Deliverable**: Agent step execution routes through `StepExecutor`. All existing tests pass.

#### Task 3.1 — Modify `src/maverick/dsl/context.py`

Add `step_executor` field:
```python
if TYPE_CHECKING:
    from maverick.dsl.executor.protocol import StepExecutor

@dataclass
class WorkflowContext:
    ...
    step_executor: StepExecutor | None = None  # injected at workflow start (FR-008)
```

**Circular import note**: Use `TYPE_CHECKING` guard. At runtime, `step_executor` is typed
as `Any | None` — the Protocol check happens in `execute_agent_step` if needed.

#### Task 3.2 — Modify `src/maverick/dsl/serialization/executor/executor.py`

After `exec_context = context.create_execution_context(workflow.name, inputs)` (line 356),
inject the ClaudeStepExecutor:

```python
from maverick.dsl.executor import ClaudeStepExecutor

# Line ~357 — inject executor once per workflow run (FR-008)
exec_context.step_executor = ClaudeStepExecutor(registry=self._registry)
```

This satisfies FR-008 (workflow-level executor selection) and the lifecycle requirement
(created once per workflow run).

#### Task 3.3 — Modify `src/maverick/dsl/serialization/executor/handlers/agent_step.py`

**Replace** the core execution logic (lines 118-293) with a thin delegation to the executor:

```python
# 1. Registry validation (keep for fast fail before context building)
if not registry.agents.has(step.agent):
    raise ReferenceResolutionError(...)

# 2. Context building (keep — context build logic stays in handler)
agent_context = await resolve_context_builder(...)
if step.agent == "implementer" and isinstance(agent_context, dict):
    agent_context = _convert_to_implementer_context(agent_context)

# 3. Get executor from context or create default
executor = context.step_executor
if executor is None:
    from maverick.dsl.executor import ClaudeStepExecutor
    executor = ClaudeStepExecutor(registry=registry)

# 4. Resolve output_schema if provided (FR-007)
output_schema = _resolve_output_schema(step)

# 5. Delegate to StepExecutor
executor_result = await executor.execute(
    step_name=step.name,
    agent_name=step.agent,
    prompt=agent_context,
    output_schema=output_schema,
    config=None,  # defaults applied inside executor; step-level config added in P3
    event_callback=event_callback,
)

# 6. Rollback registration (unchanged)
if step.rollback: ...

# 7. Return HandlerOutput
return HandlerOutput(result=executor_result.output, events=list(executor_result.events))
```

**_convert_to_implementer_context()**: Extract the existing inline conversion block
(lines 81-116) into a private helper function for readability.

**_resolve_output_schema(step)**:
```python
def _resolve_output_schema(step: AgentStepRecord) -> type[BaseModel] | None:
    schema_path = getattr(step, "output_schema", None)
    if not schema_path:
        return None
    try:
        module_path, class_name = schema_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    except (ImportError, AttributeError, ValueError) as e:
        raise ConfigError(f"Cannot resolve output_schema '{schema_path}': {e}") from e
```

#### Task 3.4 — Modify `src/maverick/dsl/serialization/schema.py`

Add `output_schema` field to `AgentStepRecord`:
```python
class AgentStepRecord(StepRecord):
    ...
    output_schema: str | None = Field(
        None,
        description=(
            "Dotted Python path to a Pydantic BaseModel subclass for output validation."
        ),
    )
```

---

### Phase 4: Testing (P1 + P2 — Mandatory Test Coverage)

**Deliverable**: Comprehensive tests. All existing tests must continue to pass (SC-001).

#### Task 4.1 — Unit tests for protocol package

**`tests/unit/dsl/executor/test_config.py`**:
- `RetryPolicy` default values, field constraints, `to_dict()` roundtrip
- `StepExecutorConfig` all-None defaults, partial config, `to_dict()` roundtrip
- `DEFAULT_EXECUTOR_CONFIG` has `timeout=300` and no retry/model override

**`tests/unit/dsl/executor/test_result.py`**:
- `UsageMetadata` default values, `to_dict()` roundtrip
- `ExecutorResult` construction with all fields, `to_dict()`, immutability

**`tests/unit/dsl/executor/test_errors.py`**:
- `OutputSchemaValidationError` carries correct step_name, schema_type, validation_errors
- Inherits from `MaverickError`

**`tests/unit/dsl/executor/test_protocol.py`**:
- `StepExecutor` isinstance check works for mock implementation
- `ClaudeStepExecutor` satisfies `isinstance(executor, StepExecutor)`
- Protocol rejects non-conforming objects

#### Task 4.2 — Unit tests for ClaudeStepExecutor

**`tests/unit/dsl/executor/test_claude.py`**:
- **Happy path**: mock agent returns result → `ExecutorResult(success=True, ...)`
- **Streaming**: mock agent calls `stream_callback` → AgentStreamChunk in `events`
- **Retry policy**: mock agent raises once, succeeds on retry → `max_attempts` respected
- **Timeout**: mock agent sleeps → `asyncio.TimeoutError` on timeout
- **Output schema valid**: mock result passes validation → `ExecutorResult.output` is validated instance
- **Output schema invalid**: mock result fails validation → `OutputSchemaValidationError` raised
- **Unknown agent**: `registry.agents.has()` returns False → `ReferenceResolutionError` raised
- **Agent raises error**: error propagated with ERROR chunk emitted
- **Observability**: `executor.step_start`, `executor.step_complete`, `executor.step_error` logged
- **event_callback forwarding**: events forwarded in real-time + collected in `ExecutorResult.events`

#### Task 4.3 — Integration test for execute_agent_step with StepExecutor

**`tests/integration/dsl/test_step_executor_integration.py`**:
- Run `execute_agent_step` with a mock `StepExecutor` injected via `context.step_executor`
- Verify the mock's `execute()` is called with correct params
- Verify `HandlerOutput.result` equals `ExecutorResult.output`
- Verify `HandlerOutput.events` contains events from `ExecutorResult.events`
- **Existing behavior test**: run with `ClaudeStepExecutor` and mock `MaverickAgent` —
  verify identical output to current direct-execution path

#### Task 4.4 — Regression: ensure existing test suite passes

Run `make test` after integration. All tests in:
- `tests/unit/dsl/serialization/executor/handlers/test_agent_step_streaming.py`
- `tests/unit/dsl/serialization/test_executor.py`
- `tests/unit/dsl/serialization/test_executor_steps.py`
- `tests/integration/test_executor_step_paths.py`

...must pass without modification.

---

### Phase 5: P2 — Typed Output Contracts (User Story 3)

**Deliverable**: `output_schema` field functional end-to-end in YAML + Python.

Covered by:
- Task 3.3: `_resolve_output_schema()` helper in `agent_step.py`
- Task 3.4: `output_schema: str | None` in `AgentStepRecord`
- Task 4.2: Output schema tests in `test_claude.py`

No additional tasks — P2 is fully integrated into the above.

---

### Phase 6: P3 — StepExecutorConfig per step (User Story 4)

**Deliverable**: Step-level `executor_config` YAML field wired to `StepExecutorConfig`.

This is the lowest-priority item. Deferred to a follow-up task if not needed for MVP.

If included: add `executor_config: dict[str, Any] | None` to `AgentStepRecord` and
deserialize it to `StepExecutorConfig` in the handler.

---

## File-by-File Summary

### New Files

| File | LOC est. | Purpose |
|------|----------|---------|
| `src/maverick/dsl/executor/__init__.py` | ~25 | Public API exports |
| `src/maverick/dsl/executor/protocol.py` | ~60 | StepExecutor Protocol |
| `src/maverick/dsl/executor/config.py` | ~80 | StepExecutorConfig, RetryPolicy |
| `src/maverick/dsl/executor/result.py` | ~80 | ExecutorResult, UsageMetadata |
| `src/maverick/dsl/executor/errors.py` | ~40 | OutputSchemaValidationError |
| `src/maverick/dsl/executor/claude.py` | ~250 | ClaudeStepExecutor |
| `tests/unit/dsl/executor/__init__.py` | ~1 | Package marker |
| `tests/unit/dsl/executor/test_config.py` | ~80 | Config unit tests |
| `tests/unit/dsl/executor/test_result.py` | ~60 | Result unit tests |
| `tests/unit/dsl/executor/test_errors.py` | ~40 | Error unit tests |
| `tests/unit/dsl/executor/test_protocol.py` | ~60 | Protocol contract tests |
| `tests/unit/dsl/executor/test_claude.py` | ~300 | ClaudeStepExecutor unit tests |
| `tests/integration/dsl/test_step_executor_integration.py` | ~150 | End-to-end integration |

### Modified Files

| File | Change | Risk |
|------|--------|------|
| `src/maverick/dsl/context.py` | Add `step_executor: StepExecutor \| None = None` field | Low — additive only |
| `src/maverick/dsl/serialization/executor/executor.py` | Inject `ClaudeStepExecutor` after context creation | Low — 3-line addition |
| `src/maverick/dsl/serialization/executor/handlers/agent_step.py` | Replace execution block with executor delegation | Medium — core logic change |
| `src/maverick/dsl/serialization/schema.py` | Add `output_schema: str \| None` to `AgentStepRecord` | Low — additive, optional field |

---

## Dependency Import Map

```
maverick.dsl.executor.config    →  dataclasses, typing (stdlib only)
maverick.dsl.executor.result    →  maverick.dsl.events.AgentStreamChunk, dataclasses, typing
maverick.dsl.executor.errors    →  maverick.exceptions, pydantic
maverick.dsl.executor.protocol  →  maverick.dsl.executor.{config,result}, maverick.dsl.events,
                                   maverick.dsl.serialization.executor.handlers.base (EventCallback),
                                   pydantic, pathlib, typing.Protocol
                                   ✗ NO maverick.agents
                                   ✗ NO claude-agent-sdk
maverick.dsl.executor.claude    →  ALL of above + maverick.dsl.serialization.registry,
                                   maverick.agents.base (for type hints only),
                                   maverick.logging, tenacity, asyncio
maverick.dsl.executor.__init__  →  ALL sub-modules (re-exports)
```

## Constitution Check (Post-Design Re-evaluation)

All checks pass:

1. **Async-First**: Protocol method is `async def execute()`. `ClaudeStepExecutor` uses
   `asyncio.wait_for` for timeout and `AsyncRetrying` for retry.

2. **Typed Contracts**: `ExecutorResult`, `StepExecutorConfig`, `RetryPolicy`, `UsageMetadata`
   are all `@dataclass(frozen=True, slots=True)` with `to_dict()` methods.

3. **Real Resilience**: Retry via tenacity `AsyncRetrying` with `stop_after_attempt` +
   `wait_exponential` — not a stub.

4. **Canonical Libraries**: structlog (`get_logger`), tenacity (`AsyncRetrying`) — no
   alternatives introduced.

5. **Modularize Early**: New package is ~535 LOC total across 5 files (well under 500/file).
   Existing `agent_step.py` shrinks from 431 lines as execution block moves to executor.

6. **SC-004 Preserved**: `protocol.py`, `config.py`, `result.py` — zero provider imports.
   Only `claude.py` imports from `maverick.agents`.
