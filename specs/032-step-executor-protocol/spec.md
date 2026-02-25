# Feature Specification: StepExecutor Protocol

**Feature Branch**: `032-step-executor-protocol`
**Created**: 2026-02-21
**Status**: Draft
**Input**: User description: "Introduce a StepExecutor protocol that decouples workflow step execution from the Claude Agent SDK, enabling future provider flexibility."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Workflow Authors Use Provider-Agnostic Steps (Priority: P1)

A workflow author defines agent steps in YAML that execute against the currently configured provider without any provider-specific knowledge. The DSL executor routes each agent step through a StepExecutor, which handles prompt submission, tool orchestration, and result extraction behind a uniform interface.

**Why this priority**: This is the core decoupling — without it, every agent step is hardwired to the Claude Agent SDK. Achieving this unlocks all downstream flexibility.

**Independent Test**: Can be fully tested by running an existing YAML workflow end-to-end with the new StepExecutor layer in place, verifying identical behavior to the current direct-SDK path.

**Acceptance Scenarios**:

1. **Given** a YAML workflow with an agent step, **When** the workflow executor processes the step, **Then** it delegates execution to the registered StepExecutor implementation rather than directly instantiating an agent class.
2. **Given** a StepExecutor configured with the Claude provider adapter, **When** an agent step executes, **Then** the result is identical to what the current direct-SDK path produces (same output structure, same streaming events).
3. **Given** an agent step with `allowed_tools`, `cwd`, and `instructions` context, **When** executed via the StepExecutor, **Then** all parameters are faithfully forwarded to the underlying provider.

---

### User Story 2 - Existing Agent Behavior Preserved Under New Abstraction (Priority: P1)

Existing MaverickAgent subclasses (ImplementerAgent, CodeReviewerAgent, CuratorAgent, etc.) continue to function without modification. The Claude-backed StepExecutor adapter wraps the existing `MaverickAgent.query()` flow, preserving streaming, circuit-breaker protection, tool validation, and error wrapping.

**Why this priority**: Zero regressions in existing functionality is a prerequisite for adoption. This must ship alongside the protocol definition.

**Independent Test**: Run the full existing test suite (unit + integration) with the new adapter wired in; all tests pass without modification.

**Acceptance Scenarios**:

1. **Given** an ImplementerAgent registered in the AgentRegistry, **When** an agent step invokes it through the StepExecutor, **Then** the agent receives the same context object and produces the same result as the direct path.
2. **Given** an agent step that streams output, **When** executed via the StepExecutor, **Then** `AgentStreamChunk` events are emitted with identical content and timing characteristics.
3. **Given** an agent step that fails, **When** the underlying agent raises an error, **Then** the StepExecutor propagates the error with the same exception type and context as the current path.

---

### User Story 3 - Typed Output Contracts Through the Executor (Priority: P2)

A workflow author specifies an `output_schema` (Pydantic BaseModel subclass) for an agent step. The StepExecutor validates the agent's output against this schema and returns a typed `ExecutorResult` containing the validated data.

**Why this priority**: Typed outputs are a natural extension of the executor pattern and improve reliability of multi-step workflows where downstream steps depend on structured data from upstream agent results.

**Independent Test**: Define a workflow step with an output schema, run it, and verify the result is validated against the schema — both for valid output and for schema-violating output.

**Acceptance Scenarios**:

1. **Given** an agent step with an `output_schema` of type `T`, **When** the agent produces conforming output, **Then** the `ExecutorResult.output` contains a validated instance of `T`.
2. **Given** an agent step with an `output_schema`, **When** the agent produces non-conforming output, **Then** the StepExecutor raises a validation error with details about the schema mismatch.
3. **Given** an agent step without an `output_schema`, **When** it executes, **Then** the `ExecutorResult.output` contains the raw agent result (backward compatible).

---

### User Story 4 - StepExecutor Configuration via Workflow Context (Priority: P3)

A workflow author or operator configures executor behavior (timeouts, retry policies, model selection) through a `StepExecutorConfig` object passed per-step or inherited from workflow-level defaults. The executor applies these settings without requiring changes to the agent implementation.

**Why this priority**: Configuration flexibility is valuable but not critical for the initial decoupling. It builds on the protocol once established.

**Independent Test**: Define two identical agent steps with different `StepExecutorConfig` values (e.g., different timeouts), run both, and verify the executor respects each step's configuration independently.

**Acceptance Scenarios**:

1. **Given** a `StepExecutorConfig` with a custom timeout, **When** an agent step runs, **Then** the executor enforces the specified timeout rather than any provider default.
2. **Given** no explicit `StepExecutorConfig`, **When** an agent step runs, **Then** the executor uses defaults matching current behavior: `timeout=300s`, `retry_policy=stop_after_attempt(3)` with `wait_exponential(min=1, max=10)`, no model or temperature override (inherited from agent/workflow config).

---

### Edge Cases

- What happens when the StepExecutor receives an unknown agent name? It raises a clear error before attempting execution.
- What happens when the StepExecutor's provider adapter is unavailable (e.g., API key missing)? It raises a configuration error at executor initialization, not mid-step.
- What happens when `output_schema` validation fails on partial/streaming output? Validation applies only to the final result, not intermediate stream chunks.
- How does the executor handle agent steps that use MCP tool servers? MCP server references are passed through to the provider adapter; the executor itself is tool-agnostic.

## Clarifications

### Session 2026-02-22

- Q: What is the instantiation lifecycle of `ClaudeStepExecutor`? → A: Per-workflow run — created once at workflow start, reused for all steps in that run.
- Q: How does `StepExecutorConfig.retry_policy` relate to MaverickAgent's internal tenacity retries? → A: Executor retry is authoritative — the executor applies the retry policy at the outermost scope; ClaudeStepExecutor bypasses internal agent-level retries when a retry policy is provided.
- Q: Where in the module hierarchy should `StepExecutor`, `ExecutorResult`, and `StepExecutorConfig` be defined? → A: `maverick.dsl.executor` — a module within the DSL package, keeping the protocol close to its primary consumer (`execute_agent_step`) with no provider-specific dependencies.
- Q: What structured log events should the executor emit for observability? → A: Three events via `get_logger()`: `executor.step_start` (step name, agent, config), `executor.step_complete` (duration, token usage, success), `executor.step_error` (error type, attempt number).
- Q: What are the default values for `StepExecutorConfig` when none is provided? → A: `timeout=300` (seconds), `retry_policy=stop_after_attempt(3)` with `wait_exponential(min=1, max=10)`, no model/temperature override (inherit from agent/workflow config).

## Requirements *(mandatory)*

### Non-Functional Requirements

- **NFR-001**: The executor MUST emit structured log events via `maverick.logging.get_logger()` at three instrumentation points:
  - `executor.step_start` — fields: `step_name`, `agent_name`, `config` (serialized StepExecutorConfig)
  - `executor.step_complete` — fields: `step_name`, `duration_ms`, `usage` (token/cost metadata), `success`
  - `executor.step_error` — fields: `step_name`, `error_type`, `attempt_number`

### Functional Requirements

- **FR-001**: System MUST define a `StepExecutor` runtime-checkable protocol with an `execute()` method accepting prompt, instructions, allowed_tools, cwd, output_schema, and config parameters.
- **FR-002**: System MUST provide an `ExecutorResult` value object containing the execution output, success status, usage metadata, and any streaming events collected during execution.
- **FR-003**: System MUST provide a `StepExecutorConfig` value object for per-step configuration (timeout, model, temperature, max_tokens, retry policy).
- **FR-004**: System MUST provide a `ClaudeStepExecutor` implementation that wraps the existing `MaverickAgent.query()` and agent lifecycle, preserving streaming, circuit-breaker, and error-wrapping behavior. When `StepExecutorConfig.retry_policy` is provided, the executor applies it at the outermost scope and bypasses any internal agent-level tenacity retries to prevent double-retrying.
- **FR-005**: System MUST integrate the StepExecutor into the DSL agent step handler (`execute_agent_step`) so all agent steps route through the executor.
- **FR-006**: System MUST preserve all existing agent step behavior (streaming events, error propagation, context resolution) when using the ClaudeStepExecutor adapter.
- **FR-007**: System MUST validate agent output against `output_schema` when provided, raising a typed validation error on mismatch.
- **FR-008**: System MUST allow the StepExecutor implementation to be selected or configured at the workflow level, defaulting to the Claude adapter.
- **FR-009**: System MUST expose the StepExecutor protocol as a stable public interface (at `maverick.dsl.executor`) that alternative provider adapters can implement without depending on Maverick internals or provider-specific packages.

### Key Entities

- **StepExecutor**: Protocol defining the provider-agnostic execution interface. Single method: `execute()`.
- **ExecutorResult**: Frozen dataclass containing `output` (the agent's result), `success` (bool), `usage` (token/cost metadata), and `events` (streaming events emitted during execution).
- **StepExecutorConfig**: Frozen dataclass for per-step execution settings — timeout, model override, temperature, max_tokens, retry policy. Defaults: `timeout=300s`, `retry_policy=stop_after_attempt(3)` with `wait_exponential(min=1, max=10)`, no model/temperature override.
- **ClaudeStepExecutor**: Concrete implementation wrapping MaverickAgent and Claude Agent SDK. Handles agent instantiation, prompt dispatch, streaming, and result extraction. **Lifecycle**: created once per workflow run and reused across all agent steps in that run; a new instance is constructed at workflow start and discarded at workflow completion.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All existing workflow tests pass without modification after the StepExecutor integration, confirming zero regressions.
- **SC-002**: A new provider adapter can be implemented by satisfying the StepExecutor protocol alone — no imports from `maverick.agents` or `claude-agent-sdk` required.
- **SC-003**: Agent step execution latency does not increase by more than 5% compared to the current direct path (the abstraction layer adds negligible overhead).
- **SC-004**: The StepExecutor protocol and its supporting types are defined in `maverick.dsl.executor` with no dependencies on provider-specific packages (e.g., `claude-agent-sdk`).

## Assumptions

- The existing `MaverickAgent` class hierarchy and `AgentRegistry` will continue to exist and be used by the Claude adapter. The StepExecutor does not replace agents — it wraps their invocation.
- The initial implementation provides only the Claude adapter. Alternative provider adapters (e.g., OpenAI, local models) are future work enabled by this protocol but not part of this feature.
- Output schema validation uses Pydantic's `model_validate()` on the raw agent result. Agents that return free-text will continue to work by omitting the `output_schema` parameter.
- The StepExecutor protocol is async-only, consistent with Maverick's async-first principle.
- Streaming behavior is preserved by collecting `AgentStreamChunk` events during execution and including them in `ExecutorResult.events`, while also forwarding them in real-time via the existing event callback mechanism.
