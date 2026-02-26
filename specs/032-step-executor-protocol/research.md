# Research: StepExecutor Protocol

**Branch**: `032-step-executor-protocol` | **Phase**: 0

All technical questions were answered in the spec's Clarifications session (2026-02-22). This
document records the decisions and their rationale for implementation reference.

---

## Decision 1: Module Location

**Decision**: `maverick.dsl.executor` — a new sub-package of `maverick.dsl`

**Rationale**: Keeps the protocol close to its primary consumer (`execute_agent_step`) in the
DSL package while maintaining a clean separation. The name is distinct from the existing
`maverick.dsl.serialization.executor` package (which handles workflow-level execution).

**Alternatives considered**:
- `maverick.executor` (top-level) — rejected: too generic, not co-located with DSL consumers
- `maverick.agents.executor` — rejected: would create dependency from the protocol on the agents
  package, violating SC-004 (no provider-specific deps in the protocol module)

---

## Decision 2: Lifecycle — Per-Workflow-Run

**Decision**: `ClaudeStepExecutor` is created once at workflow start (in
`WorkflowFileExecutor.execute()`) and reused for all agent steps in that run.

**Rationale**: Amortizes any startup cost (agent validation, registry warming). A single
instance ensures consistent configuration (retry policy, model config) across all steps.

**Implementation**: Store the executor on `WorkflowContext.step_executor`. The
`WorkflowFileExecutor.execute()` method creates a `ClaudeStepExecutor(registry=self._registry)`
and sets it on `exec_context.step_executor` immediately after context creation.

**Alternatives considered**:
- Per-step creation — rejected: unnecessary overhead and spec explicitly says per-workflow
- Module-level singleton — rejected: not test-friendly (can't inject mock executor)

---

## Decision 3: Retry Policy Ownership

**Decision**: `StepExecutorConfig.retry_policy` is authoritative. When provided, the executor
applies it at the outermost scope using tenacity `AsyncRetrying`. The executor does NOT call
the internal agent-level retry mechanism.

**Rationale**: Prevents double-retry behavior when both the executor and the agent have retry
logic. Makes retry policy visible and configurable at the DSL level rather than hidden inside
agent implementations.

**Implementation**: `ClaudeStepExecutor.execute()` wraps `agent.execute(context)` in an
`AsyncRetrying` block when `config.retry_policy` is present.

**Alternatives considered**:
- Agent-level retry preserved and executor retry added on top — rejected: spec explicitly says
  "executor retry is authoritative, bypasses internal retries"

---

## Decision 4: Protocol Parameter Design

**Decision**: `StepExecutor.execute()` signature:
```python
async def execute(
    self,
    *,
    step_name: str,        # for observability logs
    agent_name: str,       # for executor to look up or log agent identity
    prompt: Any,           # the agent context object (rich type for Claude)
    instructions: str | None = None,    # override agent instructions
    allowed_tools: list[str] | None = None,  # override agent tool list
    cwd: Path | None = None,
    output_schema: type[BaseModel] | None = None,
    config: StepExecutorConfig | None = None,
    event_callback: EventCallback | None = None,
) -> ExecutorResult:
```

**Rationale**: The spec says `execute()` accepts `prompt, instructions, allowed_tools, cwd,
output_schema, config`. We add `step_name` and `agent_name` to satisfy NFR-001 structured
logging. Using `Any` for `prompt` allows rich Python objects (ImplementerContext, etc.) for
the Claude adapter while permitting plain strings for future providers.

**Alternatives considered**:
- Only protocol params from spec (no step_name/agent_name) — rejected: NFR-001 requires
  structured log events with step_name and agent_name at all three instrumentation points
- Passing pre-instantiated agent object — rejected: breaks provider abstraction
- Using a separate "AgentSpec" object instead of individual params — rejected: more complex
  without clear benefit at this stage

---

## Decision 5: ClaudeStepExecutor + Registry

**Decision**: `ClaudeStepExecutor` is initialized with a `ComponentRegistry` reference.
It uses `registry.agents.get(agent_name)` to look up agent classes and instantiates them
on each `execute()` call.

**Rationale**: The executor is a thin adaptor — agent instantiation is cheap. Storing the
registry at construction ensures the executor has everything it needs to dispatch to any
registered agent without violating the `execute()` parameter contract.

**Alternatives considered**:
- Pass agent class directly in `execute()` — rejected: makes the protocol Claude-specific
  (leaks implementation detail into the protocol signature)
- Pre-instantiate agents and cache them — rejected: agents may have per-call state, and
  the current model creates fresh instances per invocation

---

## Decision 6: Output Schema Representation in YAML

**Decision**: `AgentStepRecord.output_schema: str | None` — a Python dotted path string
(e.g., `"maverick.agents.reviewer.ReviewResult"`). Resolved at execution time via
`importlib.import_module` + `getattr`. Validation error → `OutputSchemaValidationError`.

**Rationale**: YAML cannot express type references. String paths are the standard Python
pattern for deferred type resolution. Only resolved when the step actually executes.

**Alternatives considered**:
- Pass a type directly (only possible from Python code, not YAML) — retained as an option
  for programmatic workflow construction but not the primary path
- Store schema JSON (OpenAPI style) — rejected: too complex for this use case

---

## Decision 7: Default StepExecutorConfig Values

Per spec clarification:

| Field | Default |
|-------|---------|
| `timeout` | `300` seconds |
| `retry_policy` | `RetryPolicy(max_attempts=3, wait_min=1.0, wait_max=10.0)` |
| `model` | `None` (inherit from agent/workflow config) |
| `temperature` | `None` (inherit) |
| `max_tokens` | `None` (inherit) |

A `None` `retry_policy` means no executor-level retry (agent internal retries apply as-is).
Default `StepExecutorConfig()` sets all fields to `None` — no enforcement. The executor
only applies timeout/retry when explicitly configured.

---

## Decision 8: Streaming Event Forwarding

**Decision**: `ClaudeStepExecutor` injects `stream_callback` on the agent instance (same
pattern as the current `execute_agent_step` handler) and collects `AgentStreamChunk` events
in an internal list. These are returned as `ExecutorResult.events` and then incorporated
into `HandlerOutput.events` by the handler.

**Real-time forwarding**: When `event_callback` is provided, chunks are forwarded
immediately via `event_callback()` (for TUI). They are also appended to `ExecutorResult.events`
so downstream code that processes `HandlerOutput.events` still receives them.

**Rationale**: Preserves exact streaming behavior; no regressions. Decouples the callback
machinery from the handler, moving it entirely into the executor.

---

## Key Codebase Findings

### Current Agent Step Handler

- **File**: `src/maverick/dsl/serialization/executor/handlers/agent_step.py` (431 lines)
- **Entry point**: `async def execute_agent_step(step, resolved_inputs, context, registry, config=None, event_callback=None) -> Any`
- **Current flow**: registry lookup → context build → agent instantiate → stream callback → `agent.execute(context)` → HandlerOutput

### WorkflowContext Creation Point

- **File**: `src/maverick/dsl/serialization/executor/executor.py`, line 356
- `exec_context = context.create_execution_context(workflow.name, inputs)` — inject executor here

### Existing HandlerOutput Contract

- **File**: `src/maverick/dsl/serialization/executor/handlers/models.py`
- `HandlerOutput(result: Any, events: list[Any])` — agent_step returns this

### AgentStepRecord Schema

- **File**: `src/maverick/dsl/serialization/schema.py`, line 145
- Fields: `type`, `agent`, `context`, `rollback` — add `output_schema: str | None`

### No Existing `executor` Package Under `maverick.dsl`

- `src/maverick/dsl/` contains: config, context, events, errors, protocols, results, types,
  plus sub-packages (expressions, prerequisites, serialization, steps, etc.)
- No `executor` package exists — safe to create `src/maverick/dsl/executor/`
- Note: `src/maverick/dsl/serialization/executor/` is a different, existing package (workflow
  file executor); the new `maverick.dsl.executor` is the step executor protocol package
