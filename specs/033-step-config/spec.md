# Feature Specification: Step Configuration Model

**Feature Branch**: `033-step-config`
**Created**: 2026-02-21
**Status**: Draft
**Input**: User description: "Expand Maverick's configuration model to support rich per-step configuration, unifying the provider selection from ADR-001 with the execution mode and autonomy levels from ADR-002."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure Step Execution Mode Per Workflow Step (Priority: P1)

A workflow author defines a workflow in YAML where some steps run deterministically (linting, formatting) and others run via an AI agent (code review, implementation). Each step declares its execution mode and autonomy level directly in the workflow definition, eliminating the need for implicit conventions about which steps use AI and which do not.

**Why this priority**: This is the core value proposition. Without per-step mode and autonomy configuration, workflows cannot express the fundamental distinction between deterministic and agent-driven steps, nor control how much autonomy an agent receives.

**Independent Test**: Can be fully tested by defining a workflow with mixed step modes (deterministic + agent) and verifying each step respects its configured mode. Delivers the ability to express execution intent per step.

**Acceptance Scenarios**:

1. **Given** a workflow YAML with a step configured as `mode: deterministic`, **When** the workflow is loaded and validated, **Then** the step's configuration reflects deterministic mode with operator-level autonomy by default.
2. **Given** a workflow YAML with a step configured as `mode: agent` and `autonomy: consultant`, **When** the workflow is loaded, **Then** the step's configuration reflects agent mode with consultant-level autonomy.
3. **Given** a workflow YAML with a step that omits `mode` and `autonomy`, **When** the workflow is loaded, **Then** the step defaults to deterministic mode with operator-level autonomy.

---

### User Story 2 - Override Model and Provider Settings Per Step (Priority: P1)

A workflow author configures individual steps to use different providers or model settings. For example, a code review step uses a high-capability model with low temperature, while a brainstorming step uses a creative model with higher temperature. These overrides layer on top of the global `ModelConfig` defaults.

**Why this priority**: Provider and model flexibility per step is essential for cost optimization and task-appropriate model selection. Without this, all agent steps share the same model configuration regardless of task complexity.

**Independent Test**: Can be fully tested by defining a workflow with steps specifying different `provider`, `model_id`, and `temperature` values, then verifying each step's resolved configuration matches its overrides (falling back to global defaults for unspecified fields).

**Acceptance Scenarios**:

1. **Given** a step with `model_id: claude-opus-4-5-20250918` and `temperature: 0.7`, **When** the step configuration is resolved, **Then** those values override the global `ModelConfig` defaults.
2. **Given** a step with no model overrides, **When** the step configuration is resolved, **Then** the step inherits `model_id`, `temperature`, and `max_tokens` from the global `ModelConfig`.
3. **Given** a step with `provider: claude` and `model_id` set, **When** the step configuration is resolved, **Then** the provider and model are paired correctly for executor selection.

---

### User Story 3 - Configure Operational Limits Per Step (Priority: P2)

A workflow author sets per-step operational limits such as timeout, max retries, allowed tools, and max tokens. Long-running implementation steps get generous timeouts and retries, while quick validation steps get tight limits. This prevents runaway steps from blocking the entire workflow.

**Why this priority**: Operational limits are important for production reliability but secondary to the core mode/autonomy and model configuration. Workflows function without per-step limits (using global defaults), but explicit limits improve robustness.

**Independent Test**: Can be fully tested by defining steps with explicit `timeout`, `max_retries`, and `allowed_tools` values, then verifying the resolved configuration reflects those limits.

**Acceptance Scenarios**:

1. **Given** a step with `timeout: 600` and `max_retries: 3`, **When** the step configuration is resolved, **Then** those operational limits are available to the step executor.
2. **Given** a step with `allowed_tools: ["Read", "Glob", "Grep"]`, **When** the step configuration is resolved, **Then** only those tools are permitted for that step.
3. **Given** a step with no operational limits specified, **When** the step configuration is resolved, **Then** reasonable defaults are used (no timeout override, no retry override, all tools allowed).

---

### User Story 4 - Extend Agent Prompts Per Step (Priority: P2)

A workflow author augments the agent's instructions for a specific step by providing a prompt suffix inline or referencing an external prompt file. This allows step-level customization of agent behavior without modifying the agent's base instructions.

**Why this priority**: Prompt customization enables workflow authors to tailor agent behavior for specific contexts (e.g., "focus on security concerns" for a security review step). This is valuable but not required for basic step configuration to function.

**Independent Test**: Can be fully tested by defining a step with `prompt_suffix` or `prompt_file`, then verifying the resolved configuration includes the additional prompt content.

**Acceptance Scenarios**:

1. **Given** a step with `prompt_suffix: "Focus on performance implications"`, **When** the step configuration is resolved, **Then** the suffix is available for the executor to append to agent instructions.
2. **Given** a step with `prompt_file: "./prompts/security-review.md"`, **When** the step configuration is resolved, **Then** the file path is validated and the content is accessible.
3. **Given** a step with both `prompt_suffix` and `prompt_file`, **When** the step configuration is resolved, **Then** validation rejects the configuration as mutually exclusive.

---

### User Story 5 - Configure Steps in maverick.yaml (Priority: P3)

A project maintainer defines default step configurations in `maverick.yaml` under a `steps` key, keyed by step name. These project-level defaults are overridden by inline step configuration in the workflow YAML. This enables organization-wide policies (e.g., "all agent steps default to collaborator autonomy") without modifying individual workflows.

**Why this priority**: Project-level step configuration is a convenience layer. The core value is delivered by inline workflow-level step configuration (P1/P2). Project-level defaults add polish for teams managing multiple workflows.

**Independent Test**: Can be fully tested by setting step defaults in `maverick.yaml`, defining a workflow with a matching step name, and verifying the merge precedence (workflow inline > project config > built-in defaults).

**Acceptance Scenarios**:

1. **Given** `maverick.yaml` with `steps: { review: { autonomy: consultant } }` and a workflow step named "review" with no autonomy override, **When** the step configuration is resolved, **Then** the step uses consultant autonomy from the project config.
2. **Given** `maverick.yaml` with step defaults and a workflow step with explicit overrides, **When** the step configuration is resolved, **Then** the workflow-level values take precedence.
3. **Given** no `steps` key in `maverick.yaml`, **When** step configuration is resolved, **Then** built-in defaults apply.

---

### Edge Cases

- What happens when `mode: deterministic` is paired with agent-only fields like `autonomy: approver` or `allowed_tools`? Validation rejects the incompatible combination.
- What happens when `prompt_file` references a non-existent path? Validation fails with a clear error message identifying the missing file.
- What happens when `temperature` is set outside the valid range (e.g., negative or > 1.0)? Pydantic validation rejects the value with a descriptive error.
- What happens when a step name in `maverick.yaml` does not match any workflow step? The configuration is silently ignored (no error for unused defaults).
- What happens when `autonomy` is set without `mode: agent`? Validation rejects the configuration since autonomy levels only apply to agent-mode steps.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a `StepMode` enumeration with values `deterministic` and `agent` to classify each step's execution strategy.
- **FR-002**: System MUST provide an `AutonomyLevel` enumeration with four ordered levels: `operator` (deterministic only), `collaborator` (agent proposes, code validates), `consultant` (agent executes, code verifies), and `approver` (agent autonomous, escalates exceptions).
- **FR-003**: System MUST provide a `StepConfig` model that consolidates all per-step tunables: `mode`, `autonomy`, `provider`, `model_id`, `allowed_tools`, `prompt_suffix`, `prompt_file`, `timeout`, `max_retries`, `temperature`, and `max_tokens`.
- **FR-004**: `StepConfig` MUST default to `mode: deterministic` and `autonomy: operator` when no values are specified, ensuring safe-by-default behavior.
- **FR-005**: `StepConfig` MUST validate that agent-specific fields (`autonomy` above operator, `allowed_tools`, `prompt_suffix`, `prompt_file`) are only set when `mode` is `agent`.
- **FR-006**: `StepConfig` MUST validate that `prompt_suffix` and `prompt_file` are mutually exclusive.
- **FR-007**: `StepConfig` MUST inherit unset model fields (`model_id`, `temperature`, `max_tokens`) from the global `ModelConfig` at resolution time, not at definition time.
- **FR-008**: DSL step records (agent, generate, validate, python) MUST accept an optional `config` field of type `StepConfig`.
- **FR-009**: `MaverickConfig` MUST support a `steps: dict[str, StepConfig]` field for project-level step configuration defaults.
- **FR-010**: Step configuration resolution MUST follow precedence: workflow inline config > project-level `steps` config > built-in defaults.
- **FR-011**: `StepConfig` MUST be serializable to and from YAML/JSON for workflow file compatibility.
- **FR-012**: All existing workflows MUST continue to function without modification (backward compatibility).

### Key Entities

- **StepMode**: Enumeration distinguishing deterministic (code-only) steps from agent-driven (AI-powered) steps. Determines the execution path.
- **AutonomyLevel**: Four-tier enumeration defining how much independence an agent has within a step, ranging from fully human-controlled to fully autonomous with exception escalation.
- **StepConfig**: Central configuration model for per-step tunables. Combines execution mode, autonomy level, provider/model settings, operational limits, and prompt customization into a single validated unit.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All existing workflows execute identically before and after the change — zero behavioral regressions.
- **SC-002**: A workflow author can configure mode, autonomy, provider, and operational limits for any step using a single, consistent configuration model.
- **SC-003**: Invalid step configurations (e.g., agent-only fields on deterministic steps, mutually exclusive prompts) are rejected at load time with clear error messages before any step executes.
- **SC-004**: Per-step model overrides correctly layer on top of global defaults — a step with `temperature: 0.7` inherits all other model settings from the global configuration.
- **SC-005**: Project-level step defaults in `maverick.yaml` are correctly merged with workflow-level overrides following the documented precedence order.

## Assumptions

- **A-001**: The `provider` field defaults to `"claude"` as the only currently supported provider. The field exists to support future provider adapters (per the 032 Step Executor Protocol spec) without configuration model changes.
- **A-002**: `AutonomyLevel` ordering (operator < collaborator < consultant < approver) is informational for this spec. Enforcement of autonomy semantics (what each level permits) is the responsibility of the step executor, not the configuration model.
- **A-003**: `timeout` is specified in seconds as an integer. Sub-second precision is not required for step-level timeouts.
- **A-004**: `prompt_file` paths are resolved relative to the workflow file's directory, consistent with existing DSL path resolution patterns.
- **A-005**: The `steps` key in `maverick.yaml` uses step names as keys. Step names are unique within a workflow but may collide across workflows; project-level defaults apply to all steps with matching names.
