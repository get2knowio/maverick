# Feature Specification: Core Workflow DSL

**Feature Branch**: `022-workflow-dsl`  
**Created**: 2025-12-14  
**Status**: Draft  
**Input**: User description: "this is spec 022: Create a spec for the core workflow DSL in Maverick, including step types, the workflow decorator, and the execution engine."

## Clarifications

### Session 2025-12-14

- Q: How should `WorkflowResult.final_output` be chosen when a workflow finishes? → A: Use the workflow function’s explicit return value if present; otherwise use the last executed step’s output.
- Q: How should `ValidateStep.stages` be interpreted/resolved when a validate step runs (especially when `stages=None`)? → A: Allow list or config key; `stages=None` uses a configured default stages set.
- Q: When a step raises an exception during execution, what should the workflow engine do? → A: Catch it, mark the step as failed, store a human-readable error string in `StepResult.error`, and stop the workflow.
- Q: What should a context builder callable receive (for AgentStep/GenerateStep contexts)? → A: The full `WorkflowContext` object.
- Q: When a `SubWorkflowStep` runs, how much of the sub-workflow's details should be exposed to the parent workflow run? → A: Parent records the sub-workflow final output, and also makes the full sub-workflow result available.

### Session 2025-12-19

- Q: What happens when a validate step has `retry=0` or `retry=1` and the first validation fails? → A: `retry=0` means no retries (fail immediately, no on-failure step runs); `retry=1` means one retry allowed (on-failure runs once if configured, then re-validate once).
- Q: What happens when a context builder callable fails or returns an invalid context object? → A: Treat as step failure: catch exception, record failed `StepResult` with error, stop workflow (consistent with FR-022).
- Q: What happens when a sub-workflow fails or returns no final output? → A: Sub-workflow failure propagates (parent step fails, parent workflow stops); no explicit return uses last step output per FR-021.
- Q: What happens when a validate step references a stages config key that does not exist? → A: Step failure: validate step fails immediately with clear error about missing config key, workflow stops (fail-fast).

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.
  
  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - Define and run a workflow (Priority: P1)

As a workflow author, I can define a workflow as a sequence of named steps and execute it with inputs so I can automate repeatable tasks and reuse step outputs in later steps.

**Why this priority**: This is the core value: authoring and running workflows with consistent step execution and captured results.

**Independent Test**: Can be fully tested by defining a workflow with 2 Python steps, executing it with inputs, and verifying the final output and per-step results.

**Acceptance Scenarios**:

1. **Given** a decorated workflow with two steps that each produce an output, **When** the workflow is executed with required inputs, **Then** each step runs in order and the workflow returns a result containing both step results and the workflow final output.
2. **Given** a workflow where a later step references a prior step’s output, **When** the workflow is executed, **Then** the later step can access the prior output via the workflow context results.

---

### User Story 2 - Invoke agents with context (Priority: P2)

As a workflow author, I can invoke an agent step or generator step with a provided context (static or computed) so I can perform LLM-assisted tasks and use their outputs in subsequent steps.

**Why this priority**: Agent-driven actions are a key differentiator for Maverick and must integrate cleanly into the step model.

**Independent Test**: Can be fully tested by running a workflow that yields a generate step and verifying the produced text is returned to the workflow and recorded as a step output.

**Acceptance Scenarios**:

1. **Given** an agent step configured with a context builder, **When** the step executes, **Then** the agent receives a context object derived from workflow inputs and prior step results.
2. **Given** a generator step configured with a static context dict, **When** the step executes, **Then** the step returns a generated string and records it as the step output.

---

### User Story 3 - Validate outputs with retry and optional fixes (Priority: P3)

As a workflow author, I can validate prior step outputs and optionally retry validation with a fix step on failure so I can build resilient workflows that self-correct and report clear validation outcomes.

**Why this priority**: Validation and repair loops are central to reliable automation and reduce manual intervention.

**Independent Test**: Can be fully tested by configuring a validate step to fail once, run an on-failure fix step, and then pass on the next attempt.

**Acceptance Scenarios**:

1. **Given** a validate step with a retry limit greater than 1 and an on-failure agent step, **When** validation fails, **Then** the workflow runs the on-failure step and re-runs validation until it passes or attempts are exhausted.
2. **Given** a validate step configured with stages, **When** the step completes, **Then** it returns a structured validation result indicating pass/fail and any failure details.

---

### Edge Cases

- A step raises an exception: the workflow records a failed `StepResult` with a human-readable error string and stops further execution.
- Validate step with `retry=0` and first validation fails: workflow fails immediately without running any on-failure step.
- Validate step with `retry=1` and first validation fails: on-failure step runs once (if configured), then re-validates once; if still failing, workflow fails.
- Context builder callable fails or returns invalid context: treated as step failure with error recorded in `StepResult`, workflow stops (consistent with FR-022).
- Validate step references non-existent stages config key: step fails immediately with clear error, workflow stops (fail-fast).
- Two steps share the same name: workflow fails with a clear error message (per FR-005).
- Sub-workflow fails: parent step fails, parent workflow stops (failure propagates); sub-workflow has no explicit return: uses last step output per FR-021.

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

#### Workflow authoring

- **FR-001**: System MUST provide a workflow authoring API that supports defining an ordered sequence of named steps and executing that sequence with runtime inputs.
- **FR-002**: System MUST provide a `@workflow(name, description="")` decorator that captures workflow metadata and produces an executable workflow object.
- **FR-003**: The workflow decorator MUST inspect the decorated function’s signature to derive the workflow’s input parameters, including parameter names, declared types (when provided), and default values.
- **FR-004**: System MUST provide a step builder function `step(step_name)` that creates a step definition with the provided name.
- **FR-005**: System MUST require step names to be unique within a workflow execution; duplicate step names MUST fail the workflow with a clear error message.

#### Step types

- **FR-006**: System MUST support a Python step type that executes a provided callable action with configured positional and keyword arguments and returns the callable’s return value as the step output.
- **FR-007**: System MUST support an agent step type that invokes an agent (provided as an instance or a class) using a context provided as either (a) a dict or (b) a callable context builder; when a callable context builder is provided, the system MUST call it with the full `WorkflowContext` and use the returned value as the step context; the step returns an `AgentResult` as the step output.
- **FR-008**: System MUST support a generate step type that invokes a generator agent (provided as an instance) using a context provided as either (a) a dict or (b) a callable context builder; when a callable context builder is provided, the system MUST call it with the full `WorkflowContext` and use the returned value as the step context; the step returns a generated string as the step output.
- **FR-009**: System MUST support a validate step type that runs one or more validation stages defined by either (a) an explicit list of stages or (b) a reference to a configured stages set; when stages are not provided, the validate step MUST use a configured default stages set.
- **FR-010**: Validate steps MUST support an optional on-failure step; when configured and validation fails on an attempt where retries remain, the on-failure step MUST run before the next validation attempt begins.
- **FR-011**: System MUST support a sub-workflow step type that executes another workflow (provided as a workflow object or a decorated workflow function) and returns a sub-workflow invocation result that includes both the sub-workflow’s final output and the full sub-workflow result.

#### Base step and results

- **FR-012**: All step types MUST be represented as step definition objects that include a `name` and a `step_type` and can execute against a workflow context to produce a step result.
- **FR-013**: System MUST produce a `StepResult` for every executed step containing: step name, step type, success boolean, output value, duration in milliseconds, and an optional error string on failure.
- **FR-014**: Step definitions MUST support serialization to a dictionary representation for logging, display, or persistence; serialized output MUST include the step name, step type, and step configuration, and MUST NOT require non-serializable runtime objects to be present.

#### Workflow context

- **FR-015**: System MUST create a `WorkflowContext` for each workflow execution that includes: workflow inputs, completed step results keyed by step name, and shared services/configuration needed by steps.
- **FR-016**: Workflow context MUST allow step execution to access prior step outputs via `results[step_name].output`.

#### Execution engine

- **FR-017**: Workflow execution MUST iterate through the workflow definition, execute each yielded step, store each `StepResult` in the workflow context, and provide the step output back to the workflow authoring function for subsequent logic.
- **FR-018**: If a step fails (produces an unsuccessful result), the workflow execution MUST stop further step execution and return an unsuccessful workflow result.
- **FR-019**: Workflow execution MUST emit progress events suitable for a TUI, at minimum: step started and step completed (including success/failure and duration).
- **FR-020**: Workflow execution MUST return a `WorkflowResult` containing: workflow name, overall success boolean, an ordered list of all step results, total duration in milliseconds, and the workflow’s final output.
- **FR-021**: Workflow execution MUST set `WorkflowResult.final_output` to the workflow function’s explicit return value when provided; otherwise it MUST set `final_output` to the last executed step’s output.
- **FR-022**: If step execution raises an exception, workflow execution MUST catch it, record a failed `StepResult` for that step, populate `StepResult.error` with a human-readable error string, and stop further step execution.

### Assumptions

- Workflow authors are developers using Maverick as a developer tool; workflow definitions are expected to run in-process and may call internal Maverick services.
- `AgentResult`, `GeneratorAgent`, `ValidationStage`, and `ValidationResult` are existing domain types; this feature standardizes how they participate in workflow steps and results.
- The workflow final output uses the workflow function’s explicit return value when provided; otherwise it uses the last executed step’s output.

### Key Entities *(include if feature involves data)*

- **Workflow**: An executable definition with metadata (name, description), declared inputs, and an ordered sequence of yielded steps.
- **WorkflowContext**: Per-execution runtime context containing inputs, completed step results, and shared services/configuration needed by steps.
- **StepDefinition**: A named unit of work with a specific step type and configuration; it executes using a workflow context and produces a step result.
- **StepType**: A categorization for step behavior (Python, Agent, Generate, Validate, Sub-workflow) used for reporting and serialization.
- **StepResult**: A per-step execution record including success/failure, output, duration, and error details (when applicable).
- **WorkflowResult**: A per-workflow execution record including overall success, ordered step results, total duration, and final output.
- **SubWorkflowInvocationResult**: The output of a sub-workflow step, including the sub-workflow’s final output and the full sub-workflow result.

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: A workflow author can define and execute a workflow with at least 5 step types (Python, Agent, Generate, Validate, Sub-workflow) and receive a structured workflow result without manual wiring between steps.
- **SC-002**: For a successful workflow run, 100% of executed steps have a recorded step result including step name, step type, success flag, output, and duration.
- **SC-003**: When a step fails, the workflow run stops within one additional step boundary (no further steps execute) and returns an unsuccessful workflow result that includes a human-readable error string for the failing step.
- **SC-004**: Workflow execution emits progress events that allow a user to see step-by-step status updates in a UI during a run, including start and completion for each step.
