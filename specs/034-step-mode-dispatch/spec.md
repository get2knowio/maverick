# Feature Specification: Mode-Aware Step Dispatch

**Feature Branch**: `034-step-mode-dispatch`
**Created**: 2026-02-21
**Status**: Draft
**Input**: User description: "Enable any workflow step to be executed either deterministically (current behavior) or via an AI agent, controlled by per-step configuration."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a Python Step via an AI Agent Instead of Deterministic Code (Priority: P1)

A workflow operator configures a previously deterministic Python step (e.g., `commit_and_push`) to execute in agent mode by setting `mode: agent` in the step's configuration. Instead of executing the hardcoded Python handler, the system constructs a prompt describing the step's intent, passes the step's resolved inputs as context, and delegates execution to a StepExecutor. The step produces equivalent results to its deterministic counterpart, but with the flexibility of an AI agent choosing how to accomplish the goal.

**Why this priority**: This is the core value proposition of progressive autonomy. Without mode-aware dispatch, the `mode` and `autonomy` fields defined in Spec 033 (StepConfig) are inert configuration — they exist but do nothing. This story makes them operational.

**Independent Test**: Can be fully tested by defining a workflow with a single Python step, running it once in deterministic mode and once in agent mode, and verifying both produce a valid result matching the step's output contract.

**Acceptance Scenarios**:

1. **Given** a Python step with `mode: deterministic` (default), **When** the workflow executes, **Then** the step runs through the existing Python handler — identical behavior to before this feature.
2. **Given** a Python step with `mode: agent`, **When** the workflow executes, **Then** the system delegates to a StepExecutor with a prompt describing the step's intent and the step's resolved inputs as context.
3. **Given** a Python step with `mode: agent`, **When** the agent produces a result, **Then** the result is returned to the workflow in the same format as the deterministic handler would produce.

---

### User Story 2 - Autonomy Levels Control Agent Result Handling (Priority: P1)

A workflow operator selects how much trust the system places in an agent's output by setting an autonomy level. At lower autonomy (Collaborator), the agent's proposed result is validated by the deterministic handler before being accepted. At higher autonomy (Consultant, Approver), the agent executes with increasing independence. This gives operators a graduated path from fully deterministic to fully autonomous execution.

**Why this priority**: Autonomy levels are the safety mechanism that makes agent-mode adoption practical. Without graduated trust, operators face an all-or-nothing choice between deterministic and fully autonomous, which inhibits adoption.

**Independent Test**: Can be fully tested by running the same step at each autonomy level (Collaborator, Consultant, Approver) with a mock StepExecutor, verifying the validation/verification/acceptance behavior differs appropriately at each level.

**Acceptance Scenarios**:

1. **Given** a step with `mode: agent` and `autonomy: operator`, **When** the workflow executes, **Then** the system warns that Operator autonomy requires deterministic mode and falls back to the deterministic handler.
2. **Given** a step with `mode: agent` and `autonomy: collaborator`, **When** the agent produces a result, **Then** the deterministic handler validates the result before it is accepted. If validation fails, the deterministic handler runs independently.
3. **Given** a step with `mode: agent` and `autonomy: consultant`, **When** the agent produces a result, **Then** the system verifies the result matches the expected output contract. Discrepancies are logged but the result is accepted.
4. **Given** a step with `mode: agent` and `autonomy: approver`, **When** the agent produces a result, **Then** the system accepts the result directly, only intervening on hard failures (exceptions, schema violations).

---

### User Story 3 - Agent Failures Fall Back to Deterministic Execution (Priority: P1)

When a step running in agent mode fails (exception, timeout, or schema violation), the system automatically falls back to the deterministic Python handler for that step. The fallback is logged for observability. This ensures that enabling agent mode never makes the system less reliable than deterministic-only execution.

**Why this priority**: Fallback safety is a prerequisite for production adoption. Without it, agent-mode failures would crash or stall workflows, making operators reluctant to enable agent execution for any step.

**Independent Test**: Can be fully tested by configuring a step in agent mode with a StepExecutor that raises an exception, verifying the deterministic handler runs as fallback and produces a valid result.

**Acceptance Scenarios**:

1. **Given** a Python step in agent mode, **When** the StepExecutor raises an exception, **Then** the system falls back to the deterministic Python handler and logs the fallback event.
2. **Given** a Python step in agent mode, **When** the StepExecutor times out, **Then** the system falls back to the deterministic Python handler and logs the timeout and fallback.
3. **Given** a Python step in agent mode, **When** the agent's result violates the expected output schema, **Then** the system falls back to the deterministic Python handler and logs the schema violation.
4. **Given** a step type that has no deterministic handler (e.g., a pure agent step), **When** the agent fails, **Then** the error propagates normally (no fallback available).

---

### User Story 4 - Step Intent Descriptions Guide Agent Execution (Priority: P2)

Each Python step handler has a co-located intent description — a brief, plain-language statement of what the step accomplishes. When a step runs in agent mode, this intent description becomes the agent's primary prompt, supplemented by the step's resolved inputs as context. This ensures agents have clear goals without requiring workflow authors to write custom prompts for every step.

**Why this priority**: Intent descriptions are a usability feature that makes agent-mode practical out of the box. Without them, every step running in agent mode would need a custom prompt in the workflow YAML, creating friction for adoption.

**Independent Test**: Can be fully tested by verifying each Python step handler has an associated intent description that is non-empty and descriptive, and that the dispatch system includes it in the agent's prompt when the step runs in agent mode.

**Acceptance Scenarios**:

1. **Given** a Python step handler, **When** its intent description is queried, **Then** it returns a brief, actionable description of what the step accomplishes (not how).
2. **Given** a Python step running in agent mode, **When** the system constructs the agent prompt, **Then** the prompt includes the step's intent description and the step's resolved inputs.
3. **Given** a Python step with a `prompt_suffix` configured (per Spec 033), **When** the step runs in agent mode, **Then** the prompt suffix is appended to the intent description.

---

### User Story 5 - Structured Observability for Mode Dispatch Decisions (Priority: P2)

The system emits structured log events for every dispatch decision: which mode a step executed in, whether autonomy-level checks triggered, and whether a fallback occurred. These events enable operators to compare deterministic vs. agent execution outcomes, identify agent reliability trends, and make informed decisions about increasing autonomy levels over time.

**Why this priority**: Observability is essential for building operator confidence in progressive autonomy. Without it, operators have no data to justify increasing autonomy levels, stalling adoption.

**Independent Test**: Can be fully tested by running steps in various modes and autonomy levels, capturing structured log output, and verifying the expected events are emitted with correct fields.

**Acceptance Scenarios**:

1. **Given** a step executing in deterministic mode, **When** the step completes, **Then** a structured log event is emitted indicating deterministic execution with the step name.
2. **Given** a step executing in agent mode, **When** the step completes, **Then** a structured log event is emitted indicating agent execution with the step name, autonomy level, and execution duration.
3. **Given** a step that falls back from agent to deterministic, **When** the fallback occurs, **Then** a structured log event is emitted with the failure reason, step name, and confirmation that deterministic fallback succeeded.
4. **Given** a Collaborator-level step where validation rejects the agent result, **When** the deterministic handler runs instead, **Then** a structured log event is emitted indicating the validation failure and fallback.

---

### Edge Cases

- What happens when `mode: agent` is set on a `StepType.AGENT` step (which already invokes agents)? The mode setting is ignored — agent-type steps already execute via agents and are not affected by this feature.
- What happens when `mode: agent` is set on a step type that has no intent description (e.g., checkpoint, branch, loop)? The system logs a warning and falls back to deterministic execution, since these control-flow steps have no meaningful intent to delegate to an agent.
- What happens when the deterministic fallback also fails after an agent failure? The error from the deterministic handler propagates normally — the system does not attempt further recovery.
- What happens when `mode: agent` is set but no StepExecutor is configured or available? The system falls back to deterministic execution and logs a warning about the missing executor.
- What happens when the agent produces a result in a different format than the deterministic handler would? At Collaborator level, the deterministic handler's validation catches the format mismatch. At Consultant level, schema verification catches it. At Approver level, the result is accepted as-is (operator has explicitly opted into full agent autonomy).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST dispatch Python steps based on their resolved `StepConfig.mode` — `DETERMINISTIC` routes to the existing Python handler, `AGENT` routes to a StepExecutor with an intent-based prompt.
- **FR-002**: System MUST NOT alter dispatch behavior for `StepType.AGENT`, `StepType.GENERATE`, `StepType.VALIDATE`, or control-flow step types (`BRANCH`, `LOOP`, `CHECKPOINT`, `SUBWORKFLOW`). Mode-aware dispatch applies only to `StepType.PYTHON` steps.
- **FR-003**: System MUST enforce autonomy level semantics when `mode == AGENT`:
  - Operator: warn and fall back to deterministic execution.
  - Collaborator: agent proposes a result; the deterministic handler validates it before acceptance. On validation failure, the deterministic handler runs independently.
  - Consultant: agent executes; the system verifies the result matches the expected output contract. Discrepancies are logged but the result is accepted.
  - Approver: agent executes with full autonomy; the system only intervenes on hard failures (unhandled exceptions, schema violations).
- **FR-004**: System MUST provide an intent description for each existing Python step handler, co-located with the handler, describing what the step accomplishes in plain language.
- **FR-005**: System MUST construct the agent prompt from the step's intent description, the step's resolved inputs, and any configured `prompt_suffix` or `prompt_file` content (per Spec 033).
- **FR-006**: System MUST fall back to the deterministic Python handler when agent-mode execution fails due to exceptions, timeouts, or schema violations, provided a deterministic handler exists for that step.
- **FR-007**: System MUST emit structured log events (via structlog) for: mode selection (deterministic vs. agent), autonomy-level checks (validation, verification, acceptance), and fallback occurrences (agent-to-deterministic).
- **FR-008**: System MUST preserve identical default behavior for all existing workflows — steps without explicit `mode` configuration default to `DETERMINISTIC` with `OPERATOR` autonomy, producing no behavioral change.
- **FR-009**: System MUST NOT require modifications to existing YAML workflow files — mode and autonomy are supplied via `StepConfig` (per Spec 033), not changes to step definitions.
- **FR-010**: System MUST integrate with the StepExecutor protocol defined in Spec 032 for agent-mode execution, not bypass it with direct agent instantiation.

### Key Entities

- **Step Dispatcher**: The decision point in the workflow executor that examines a step's `StepConfig.mode` and routes execution to the deterministic handler or to a StepExecutor-based agent path.
- **Intent Description**: A plain-language statement co-located with each Python step handler, describing what the step accomplishes. Serves as the agent's primary prompt when the step runs in agent mode.
- **Autonomy Gate**: The per-level logic that determines how an agent's result is validated, verified, or accepted based on the configured `AutonomyLevel`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All existing workflows execute identically before and after this change — zero behavioral regressions when no `mode` or `autonomy` overrides are configured.
- **SC-002**: A workflow operator can switch any Python step from deterministic to agent execution by setting a single configuration field (`mode: agent`), without modifying the workflow YAML.
- **SC-003**: Agent-mode failures never produce worse outcomes than deterministic-only execution — every agent failure triggers a logged fallback to the deterministic handler.
- **SC-004**: Each autonomy level produces observably different behavior: Collaborator validates before accepting, Consultant verifies after execution, Approver accepts directly.
- **SC-005**: Structured log events are emitted for every dispatch decision, enabling operators to compare agent vs. deterministic outcomes across workflow runs.
- **SC-006**: Every Python step handler has a non-empty intent description that can serve as an effective agent prompt.

## Assumptions

- **A-001**: Specs 032 (StepExecutor Protocol) and 033 (StepConfig) are implemented before this feature. This spec depends on `StepExecutor`, `StepConfig`, `StepMode`, and `AutonomyLevel` being available.
- **A-002**: "Validation" at Collaborator level means invoking the deterministic handler to check whether the agent's proposed result is acceptable. The deterministic handler acts as a validator, not a separate validation step.
- **A-003**: "Verification" at Consultant level means checking the agent's result against the step's output contract (schema or structural checks). It does not re-execute the step deterministically.
- **A-004**: Intent descriptions are static, human-authored strings. They are not generated at runtime.
- **A-005**: The prompt constructed for agent-mode execution includes resolved inputs (after expression evaluation), not raw `${{ }}` expressions.
- **A-006**: Fallback from agent to deterministic is a one-shot attempt. If the deterministic handler also fails, the error propagates normally — there is no retry cascade between modes.
- **A-007**: This feature does not introduce new step types. It adds an alternative execution path for existing `StepType.PYTHON` steps.

## Dependencies

- **Spec 032 - StepExecutor Protocol**: Provides the `StepExecutor` interface and `ClaudeStepExecutor` implementation used for agent-mode execution.
- **Spec 033 - Step Configuration Model**: Provides `StepConfig`, `StepMode`, and `AutonomyLevel` — the configuration surface this feature dispatches on.
