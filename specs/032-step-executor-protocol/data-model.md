# Data Model: StepExecutor Protocol

**Branch**: `032-step-executor-protocol` | **Phase**: 1

---

## Entity Overview

| Entity | Type | Module | Description |
|--------|------|--------|-------------|
| `StepExecutor` | `@runtime_checkable Protocol` | `maverick.dsl.executor.protocol` | Provider-agnostic execution interface |
| `ExecutorResult` | `@dataclass(frozen=True, slots=True)` | `maverick.dsl.executor.result` | Typed return value from execute() |
| `StepExecutorConfig` | `@dataclass(frozen=True, slots=True)` | `maverick.dsl.executor.config` | Per-step execution settings |
| `RetryPolicy` | `@dataclass(frozen=True, slots=True)` | `maverick.dsl.executor.config` | Tenacity retry parameters |
| `UsageMetadata` | `@dataclass(frozen=True, slots=True)` | `maverick.dsl.executor.result` | Token/cost metadata from execution |
| `ClaudeStepExecutor` | class | `maverick.dsl.executor.claude` | Claude adapter implementing StepExecutor |
| `OutputSchemaValidationError` | Exception | `maverick.dsl.executor.errors` | Raised when output_schema validation fails |

---

## StepExecutor Protocol

```python
# maverick/dsl/executor/protocol.py
from __future__ import annotations
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from pydantic import BaseModel

@runtime_checkable
class StepExecutor(Protocol):
    """Provider-agnostic protocol for executing agent steps.

    A StepExecutor decouples workflow step execution from any specific AI
    provider. Implementors receive a prompt (the agent context) plus
    execution configuration and return a typed ExecutorResult.

    The protocol is async-only and has no dependencies on provider-specific
    packages. Alternative provider adapters (OpenAI, local models, etc.) can
    implement this protocol without importing maverick.agents or claude-agent-sdk.

    Lifecycle (for concrete implementations):
        Created once per workflow run, reused for all agent steps in that run.
    """

    async def execute(
        self,
        *,
        step_name: str,
        agent_name: str,
        prompt: Any,
        instructions: str | None = None,
        allowed_tools: list[str] | None = None,
        cwd: Path | None = None,
        output_schema: type[BaseModel] | None = None,
        config: StepExecutorConfig | None = None,
        event_callback: EventCallback | None = None,
    ) -> ExecutorResult: ...
```

**Constraints**:
- `maverick.dsl.executor.protocol` has **no imports** from `maverick.agents` or `claude-agent-sdk`
- Protocol is `@runtime_checkable` — supports `isinstance()` checks for adapter validation

---

## ExecutorResult

```python
# maverick/dsl/executor/result.py
@dataclass(frozen=True, slots=True)
class UsageMetadata:
    """Token and cost metadata from a model invocation."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_cost_usd: float | None = None

    def to_dict(self) -> dict[str, Any]: ...

@dataclass(frozen=True, slots=True)
class ExecutorResult:
    """Typed result from a StepExecutor.execute() call.

    Attributes:
        output: The agent's result. When output_schema was provided and
            validation succeeded, this is a validated Pydantic model instance.
            Otherwise, it is the raw result from agent.execute().
        success: True if execution completed without errors.
        usage: Token/cost metadata, or None if unavailable from the provider.
        events: AgentStreamChunk events collected during streaming execution.
            Also forwarded in real-time via event_callback when provided.
    """
    output: Any
    success: bool
    usage: UsageMetadata | None
    events: tuple[AgentStreamChunk, ...]  # immutable, frozen-safe

    def to_dict(self) -> dict[str, Any]: ...
```

**Notes**:
- `events` uses `tuple` (not list) for frozen dataclass compatibility
- `output` is `Any` since it may be a rich domain object (ImplementerContext result,
  ReviewResult, etc.) or a validated Pydantic instance

---

## StepExecutorConfig

```python
# maverick/dsl/executor/config.py
@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Tenacity retry parameters for executor-level retry.

    Maps to: stop_after_attempt(max_attempts) + wait_exponential(min=wait_min, max=wait_max)
    """
    max_attempts: int = 3
    wait_min: float = 1.0
    wait_max: float = 10.0

    def to_dict(self) -> dict[str, Any]: ...

@dataclass(frozen=True, slots=True)
class StepExecutorConfig:
    """Per-step execution configuration for StepExecutor.

    All fields are optional (None = use provider default / inherit from agent config).
    When config is not provided to execute(), the executor uses built-in defaults.

    Attributes:
        timeout: Execution timeout in seconds. Default 300.
        retry_policy: Tenacity retry configuration. When provided, the executor
            applies retry at the outermost scope. Default: None (no executor retry).
        model: Model identifier override. Default: None (inherit from agent).
        temperature: Temperature override. Default: None (inherit from agent).
        max_tokens: Max tokens override. Default: None (inherit from agent).
    """
    timeout: int | None = None
    retry_policy: RetryPolicy | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None

    def to_dict(self) -> dict[str, Any]: ...

# Module-level default config (timeout=300, no retry override, no model override)
DEFAULT_EXECUTOR_CONFIG = StepExecutorConfig(timeout=300)
```

---

## ClaudeStepExecutor

```python
# maverick/dsl/executor/claude.py
class ClaudeStepExecutor:
    """Claude Agent SDK adapter for StepExecutor protocol.

    Wraps MaverickAgent subclasses, preserving streaming, circuit-breaker
    protection, and error wrapping. Agent classes are looked up from the
    ComponentRegistry provided at construction time.

    Lifecycle:
        Created once per workflow run. Reused for all agent steps.

    Retry behavior:
        When config.retry_policy is provided, executor applies tenacity
        AsyncRetrying at the outermost scope. No internal agent retries
        are applied additionally.

    Args:
        registry: Component registry for agent class lookup.
    """

    def __init__(self, registry: ComponentRegistry) -> None: ...

    async def execute(
        self,
        *,
        step_name: str,
        agent_name: str,
        prompt: Any,
        instructions: str | None = None,
        allowed_tools: list[str] | None = None,
        cwd: Path | None = None,
        output_schema: type[BaseModel] | None = None,
        config: StepExecutorConfig | None = None,
        event_callback: EventCallback | None = None,
    ) -> ExecutorResult: ...
```

**Internal flow** (in `execute()`):
1. Log `executor.step_start`
2. Lookup agent class: `self._registry.agents.get(agent_name)`
3. Instantiate: `agent = agent_class(**kwargs)` (kwargs include e.g. `validation_commands`)
4. Inject stream callback: `agent.stream_callback = _make_stream_callback(event_callback, ...)`
5. Build effective config: merge `config` with `DEFAULT_EXECUTOR_CONFIG`
6. If `config.retry_policy`: wrap in `AsyncRetrying`; else: direct call
7. `result = await agent.execute(prompt)`
8. If `output_schema`: validate via `output_schema.model_validate(result)` or raise `OutputSchemaValidationError`
9. Extract usage from result
10. Log `executor.step_complete`
11. Return `ExecutorResult(output=result, success=True, usage=..., events=...)`

---

## OutputSchemaValidationError

```python
# maverick/dsl/executor/errors.py
from maverick.exceptions import MaverickError

class ExecutorError(MaverickError):
    """Base class for StepExecutor errors."""
    ...

class OutputSchemaValidationError(ExecutorError):
    """Raised when agent output fails output_schema validation.

    Attributes:
        step_name: Name of the step that produced invalid output.
        schema_type: The Pydantic model class used for validation.
        validation_errors: Pydantic ValidationError details.
    """
    def __init__(
        self,
        step_name: str,
        schema_type: type[BaseModel],
        validation_errors: ValidationError,
    ) -> None: ...
```

---

## Modified Entities

### WorkflowContext (modified)

**File**: `src/maverick/dsl/context.py`

Add optional `step_executor` field:

```python
# TYPE_CHECKING import to avoid circular dep at runtime
if TYPE_CHECKING:
    from maverick.dsl.executor.protocol import StepExecutor

@dataclass
class WorkflowContext:
    ...
    # New field (FR-008): executor for agent steps. When None, execute_agent_step
    # creates a default ClaudeStepExecutor per call.
    step_executor: StepExecutor | None = None
```

**Note**: Uses string annotation (`"StepExecutor"`) or `TYPE_CHECKING` guard to avoid
circular imports at runtime. `StepExecutor` is a Protocol, so `isinstance()` checks
deferred to runtime only.

### AgentStepRecord (modified)

**File**: `src/maverick/dsl/serialization/schema.py`

Add `output_schema` field:

```python
class AgentStepRecord(StepRecord):
    ...
    output_schema: str | None = Field(
        None,
        description=(
            "Dotted Python path to a Pydantic BaseModel subclass for output validation. "
            "E.g. 'maverick.agents.reviewer.ReviewResult'. "
            "When provided, agent output is validated and ExecutorResult.output "
            "contains a validated model instance."
        ),
    )
```

---

## State Transitions (StepExecutor lifecycle)

```
WorkflowFileExecutor.execute() called
    │
    ├─► create_execution_context()  →  WorkflowContext
    │
    ├─► ClaudeStepExecutor(registry)  →  set exec_context.step_executor
    │
    ▼  for each step in workflow.steps:
         if step.type == AGENT:
             execute_agent_step()
                 │
                 ├─► context.step_executor.execute(...)
                 │       │
                 │       ├─► executor.step_start logged
                 │       ├─► agent instantiated + stream_callback injected
                 │       ├─► [retry loop if config.retry_policy]
                 │       │       └─► agent.execute(prompt)
                 │       ├─► output_schema validation (if provided)
                 │       ├─► executor.step_complete logged
                 │       └─► return ExecutorResult
                 │
                 └─► HandlerOutput(result=result.output, events=list(result.events))
    │
WorkflowFileExecutor.execute() completes / discards step_executor
```

---

## Dependency Graph (new `maverick.dsl.executor` package)

```
maverick.dsl.executor
├── protocol.py     → imports: maverick.dsl.executor.{result,config}, maverick.dsl.events
│                            pydantic.BaseModel, pathlib.Path, typing.Protocol
│                            (NO maverick.agents, NO claude-agent-sdk)
├── config.py       → imports: dataclasses, typing (NO maverick imports)
├── result.py       → imports: maverick.dsl.events.AgentStreamChunk, dataclasses, typing
├── errors.py       → imports: maverick.exceptions.MaverickError, pydantic.ValidationError
└── claude.py       → imports: maverick.dsl.executor.{protocol,config,result,errors}
                               maverick.dsl.serialization.registry.ComponentRegistry
                               maverick.dsl.events.AgentStreamChunk
                               maverick.logging.get_logger
                               tenacity
                               (CAN import maverick.agents, claude-agent-sdk)
```
