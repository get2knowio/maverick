# Feature Specification: Python-Native Workflow Definitions

**Feature Branch**: `035-python-workflow`
**Created**: 2026-02-21
**Status**: Draft
**Input**: User description: "Create Python-native workflow definitions that replace the YAML DSL for Maverick's opinionated workflows, while preserving the YAML DSL as a supported execution path."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Opinionated Workflows Defined in Python (Priority: P1)

A Maverick developer defines the `fly-beads` workflow as a Python class extending `PythonWorkflow`. The class contains an `async execute()` method with native Python control flow (loops, conditionals, try/except), calls to registered actions, and structured event emission. The workflow is testable in isolation with standard pytest patterns — no YAML parsing, expression evaluation, or component registry setup required.

**Why this priority**: This is the core value proposition. Python workflows unlock IDE navigation, refactoring support, type checking, and direct unit testing for the workflows that Maverick ships as its product. Without this, all workflow logic remains encoded in YAML strings with no compile-time safety.

**Independent Test**: Can be fully tested by instantiating a `PythonWorkflow` subclass with a mock `MaverickConfig`, calling `execute()` with test inputs, and asserting the returned `WorkflowResult` contains the expected step results and final output.

**Acceptance Scenarios**:

1. **Given** a `PythonWorkflow` subclass with an `execute()` method, **When** the workflow is instantiated with a `MaverickConfig` and `execute()` is called with valid inputs, **Then** it returns a `WorkflowResult` with success status, step results, and final output.
2. **Given** a `PythonWorkflow` subclass, **When** a developer navigates to a step call within `execute()`, **Then** the IDE resolves the action's type signature, parameters, and docstring — providing the same navigation experience as any other Python code.
3. **Given** a `PythonWorkflow` subclass, **When** a developer writes a unit test, **Then** they can mock individual action calls and assert workflow behavior without any YAML fixtures or registry bootstrapping.

---

### User Story 2 - Step Config Resolution from Python Workflows (Priority: P1)

A Python workflow resolves per-step configuration using `resolve_step_config(step_name)`, which merges the built-in defaults with project-level overrides from `maverick.yaml`. This gives Python workflows the same configuration flexibility as YAML workflows — operators can override model, autonomy, timeout, and other settings per step without modifying the workflow code.

**Why this priority**: Without configuration resolution, Python workflows would hardcode execution parameters, losing the operator-configurability that Spec 033 (StepConfig) established. This story ensures Python workflows are first-class citizens in the configuration hierarchy.

**Independent Test**: Can be fully tested by creating a `MaverickConfig` with `steps` overrides, calling `resolve_step_config("step_name")`, and asserting the returned `StepConfig` reflects the merged values.

**Acceptance Scenarios**:

1. **Given** a `MaverickConfig` with `steps: { review: { mode: agent, autonomy: consultant } }`, **When** the workflow calls `resolve_step_config("review")`, **Then** the returned `StepConfig` has `mode=agent` and `autonomy=consultant`.
2. **Given** a `MaverickConfig` with no step overrides, **When** the workflow calls `resolve_step_config("review")`, **Then** the returned `StepConfig` contains built-in defaults (`mode=deterministic`, `autonomy=operator`).
3. **Given** a `MaverickConfig` with partial overrides (e.g., only `timeout: 600`), **When** the workflow calls `resolve_step_config("step_name")`, **Then** unspecified fields fall back to built-in defaults.

---

### User Story 3 - Progress Events from Python Workflows (Priority: P1)

A Python workflow emits structured progress events (step started, step completed, step failed, workflow completed) as it executes. The CLI layer consumes these events to render live progress — identical to how it consumes events from YAML workflow execution today. The workflow author calls helper methods (e.g., `self.emit_step_started(name)`, `self.emit_step_completed(name, result)`) to emit events at appropriate points.

**Why this priority**: Progress visibility is essential for CLI usability. Without event emission, Python workflows would execute silently with no feedback, degrading the operator experience compared to YAML workflows.

**Independent Test**: Can be fully tested by running a Python workflow and collecting all emitted events, verifying the expected sequence (workflow started, step started/completed pairs, workflow completed).

**Acceptance Scenarios**:

1. **Given** a Python workflow executing a multi-step sequence, **When** each step starts and completes, **Then** the workflow emits `StepStarted` and `StepCompleted` events with the step name and result.
2. **Given** a Python workflow that encounters a step failure, **When** the step raises an exception, **Then** the workflow emits a `StepFailed` event with the step name and error details.
3. **Given** the CLI consuming a Python workflow's events, **When** events are emitted, **Then** the CLI renders them identically to YAML workflow events — same progress indicators, same formatting.

---

### User Story 4 - YAML Workflows Remain Functional (Priority: P2)

Existing YAML workflows (both built-in and user-defined in `.maverick/workflows/`) continue to function without modification. The `WorkflowFileExecutor` remains the execution engine for YAML-defined workflows. User-authored YAML workflows in `.maverick/workflows/` and `~/.config/maverick/workflows/` are discovered and executed as before.

**Why this priority**: YAML backward compatibility is critical for existing users and for user-authored workflows. However, it is secondary to making the opinionated Python workflows functional since the YAML execution path already works and requires no changes.

**Independent Test**: Can be fully tested by running an existing YAML workflow through `WorkflowFileExecutor` after the Python workflow infrastructure is added, verifying identical behavior.

**Acceptance Scenarios**:

1. **Given** an existing YAML workflow in `.maverick/workflows/`, **When** it is discovered and executed, **Then** it runs through `WorkflowFileExecutor` with identical behavior to before this feature.
2. **Given** a user who has not adopted Python workflows, **When** they run `maverick fly`, **Then** the system uses the Python-native `FlyBeadsWorkflow` — YAML equivalents are no longer the primary path for opinionated workflows.
3. **Given** a user-authored YAML workflow in `.maverick/workflows/`, **When** it is discovered, **Then** it executes through `WorkflowFileExecutor` as before — user-authored YAML workflows are unaffected.

---

### User Story 5 - CLI Commands Route to Python Workflows (Priority: P2)

The CLI commands (`maverick fly`, `maverick refuel speckit`) instantiate and execute the corresponding Python workflow class directly, rather than discovering and loading a YAML file. This simplifies the execution path — the CLI creates the workflow, passes configuration and inputs, and consumes the resulting event stream.

**Why this priority**: Direct instantiation from CLI commands eliminates the discovery/registry indirection for opinionated workflows, making the execution path easier to understand, debug, and test. It builds on the P1 Python workflow infrastructure.

**Independent Test**: Can be fully tested by invoking the CLI command with test arguments and verifying the correct Python workflow class is instantiated and executed.

**Acceptance Scenarios**:

1. **Given** a user running `maverick fly`, **When** the CLI processes the command, **Then** it instantiates `FlyBeadsWorkflow` with the resolved `MaverickConfig` and calls `execute()`.
2. **Given** a user running `maverick refuel speckit`, **When** the CLI processes the command, **Then** it instantiates `RefuelSpeckitWorkflow` and calls `execute()`.
3. **Given** a Python workflow's `execute()` returning an async iterator of events, **When** the CLI consumes the iterator, **Then** it renders progress using the same Rich-based display as YAML workflow events.

---

### Edge Cases

- What happens when a Python workflow raises an unhandled exception mid-execution? The workflow emits a `WorkflowFailed` event and the `execute()` method propagates the exception after recording it in the `WorkflowResult`.
- What happens when `resolve_step_config()` is called for a step name not defined in `maverick.yaml`? It returns the built-in defaults — no error, since project-level step config is optional.
- What happens when a Python workflow and a YAML workflow have the same name? Python workflows take precedence for opinionated (built-in) workflows. User-authored YAML workflows in `.maverick/workflows/` are a separate namespace and are not affected.
- What happens when a Python workflow needs to invoke a sub-workflow defined in YAML? The Python workflow can use a helper method to load and execute a YAML workflow via `WorkflowFileExecutor`, maintaining interoperability.
- What happens when a Python workflow's `execute()` is cancelled (e.g., Ctrl+C)? Cancellation propagates as `asyncio.CancelledError`, and any registered rollback actions execute before the workflow terminates.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a `PythonWorkflow` abstract base class with an `async execute(inputs: dict[str, Any]) -> AsyncIterator[ProgressEvent]` method that subclasses implement to define workflow logic.
- **FR-002**: `PythonWorkflow` MUST accept a `MaverickConfig` at construction time and use it for configuration resolution throughout execution.
- **FR-003**: `PythonWorkflow` MUST provide a `resolve_step_config(step_name: str) -> StepConfig` method that merges built-in defaults with project-level overrides from `MaverickConfig.steps`.
- **FR-004**: `PythonWorkflow` MUST provide helper methods for emitting progress events: `emit_step_started(name)`, `emit_step_completed(name, result)`, `emit_step_failed(name, error)`, `emit_workflow_completed(result)`.
- **FR-005**: `PythonWorkflow` MUST track step results and produce a `WorkflowResult` upon completion, with the same structure as YAML workflow results.
- **FR-006**: `PythonWorkflow` MUST provide access to registered actions, agents, and other components through a `ComponentRegistry` passed at construction or resolved from configuration.
- **FR-007**: System MUST provide concrete Python workflow implementations for `fly-beads` and `refuel-speckit` that replicate the behavior of their YAML counterparts.
- **FR-008**: CLI commands (`maverick fly`, `maverick refuel speckit`) MUST instantiate and execute the corresponding Python workflow class directly.
- **FR-009**: Existing YAML workflows (user-authored and built-in discovery paths) MUST continue to function without modification via `WorkflowFileExecutor`.
- **FR-010**: `PythonWorkflow` subclasses MUST be directly testable with standard pytest patterns — no YAML parsing, expression evaluation, or workflow discovery infrastructure required.
- **FR-011**: `PythonWorkflow` MUST support rollback registration, allowing steps to register compensating actions that execute on workflow failure or cancellation.
- **FR-012**: `PythonWorkflow` MUST support checkpointing, allowing workflows to persist state and resume from the last successful step after a failure.
- **FR-013**: Progress events emitted by Python workflows MUST be compatible with the existing `ProgressEvent` types defined in `maverick.dsl.events`, ensuring the CLI renders them identically.

### Key Entities

- **PythonWorkflow**: Abstract base class that all Python-native workflows extend. Provides configuration resolution, event emission, step tracking, rollback registration, and result aggregation. Replaces YAML workflow definitions for Maverick's opinionated workflows.
- **FlyBeadsWorkflow**: Concrete Python workflow implementing the bead-driven development loop (preflight, workspace creation, bead selection, implementation, validation, review, commit).
- **RefuelSpeckitWorkflow**: Concrete Python workflow implementing the spec-to-beads pipeline (parse tasks.md, create epic bead, create work beads, wire dependencies).
- **WorkflowResult**: Existing result type (from `maverick.dsl.results`) reused by Python workflows to report execution outcomes.
- **StepConfig**: Existing configuration model (from Spec 033) resolved per-step within Python workflows via `resolve_step_config()`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Both `fly-beads` and `refuel-speckit` workflows can be executed end-to-end as Python workflow classes, producing equivalent results to their YAML counterparts.
- **SC-002**: Python workflow tests achieve the same coverage as the workflows they replace, using standard pytest patterns without YAML fixtures or registry bootstrapping.
- **SC-003**: All existing CLI commands (`maverick fly`, `maverick refuel speckit`) produce identical user-visible behavior after switching from YAML to Python workflow execution.
- **SC-004**: User-authored YAML workflows in `.maverick/workflows/` and `~/.config/maverick/workflows/` continue to be discovered and executed without any changes.
- **SC-005**: A new Python workflow can be created by a developer in under 15 minutes by subclassing `PythonWorkflow` and implementing `execute()`, with full IDE support (autocompletion, type checking, navigation).
- **SC-006**: Per-step configuration overrides from `maverick.yaml` are correctly applied to Python workflow steps via `resolve_step_config()`.

## Assumptions

- **A-001**: Specs 032 (StepExecutor Protocol), 033 (StepConfig), and 034 (Mode-Aware Dispatch) are implemented before this feature. Python workflows use `StepConfig` for configuration resolution and may use `StepExecutor` for agent-mode step dispatch.
- **A-002**: The `ComponentRegistry` (actions, agents, generators, context builders) remains the canonical way to access registered components. Python workflows receive the registry at construction time rather than importing actions directly, preserving testability via mock registries.
- **A-003**: The built-in YAML workflow files (`fly-beads.yaml`, `refuel-speckit.yaml`) will be retained in the repository for reference and for users who have extended them, but they will no longer be the primary execution path for the CLI commands.
- **A-004**: Python workflows emit the same `ProgressEvent` types as YAML workflows. No new event types are required — the existing event vocabulary is sufficient.
- **A-005**: Rollback and checkpointing in Python workflows use the same mechanisms as YAML workflows (rollback registration via context, checkpoint persistence via `CheckpointStore`), adapted for direct Python invocation.
- **A-006**: Python workflow classes are located in `src/maverick/workflows/` (one package per workflow), consistent with the architecture guidelines for workflow organization.
