# Research: Fly Workflow Interface

**Feature**: 009-fly-workflow
**Date**: 2025-12-15

## Research Tasks

### 1. Existing Pattern Analysis: ValidationWorkflow

**Question**: How does the existing ValidationWorkflow implement progress events and state management?

**Findings**:
- `ValidationWorkflow` uses an async generator pattern via `async def run() -> AsyncIterator[ProgressUpdate]`
- Progress events are dataclasses with `@dataclass(slots=True, frozen=True)` for immutability and efficiency
- State is tracked via internal `_result: ValidationWorkflowResult | None` attribute
- Result is accessed via `get_result()` method after workflow completion
- Cancellation is cooperative via `asyncio.Event`

**Decision**: Follow the same async generator pattern for FlyWorkflow progress events. Use frozen dataclasses for progress events.

**Rationale**: Consistency with existing codebase patterns ensures predictable behavior and easier maintenance.

**Alternatives Considered**:
- Callback-based progress: Rejected - more complex, harder to test
- Observable/reactive streams: Rejected - adds dependency, overkill for this use case

---

### 2. Data Model Patterns: Pydantic vs Dataclass

**Question**: When should we use Pydantic BaseModel vs Python dataclasses for the interface types?

**Findings**:
- `ValidationStage`, `ValidationWorkflowResult`, `StageResult` use Pydantic `BaseModel` with `frozen=True`
- `ProgressUpdate`, `CommandResult` use `@dataclass` with `slots=True, frozen=True`
- Pydantic is used when: validation rules needed, serialization required, configuration models
- Dataclasses are used when: simple value objects, progress events, internal types

**Decision**:
- **Pydantic BaseModel**: `FlyInputs`, `FlyConfig`, `WorkflowState`, `FlyResult` (need validation/serialization)
- **Dataclass**: Progress events (`FlyWorkflowStarted`, etc.) (lightweight, immutable events)

**Rationale**: Match the existing pattern where Pydantic handles validated configuration and dataclasses handle lightweight events.

**Alternatives Considered**:
- All Pydantic: Rejected - unnecessary overhead for simple progress events
- All dataclass: Rejected - lose Pydantic validation for inputs/config

---

### 3. Type Integration: AgentUsage vs TokenUsage

**Question**: The spec mentions `TokenUsage` but the codebase has `AgentUsage`. Which should be used?

**Findings**:
- `maverick.agents.result` defines `AgentUsage` with fields: `input_tokens`, `output_tokens`, `total_cost_usd`, `duration_ms`
- The spec FR-010 mentions "TokenUsage" - this appears to be the conceptual name
- `AgentUsage` already has all required fields including `total_cost_usd`

**Decision**: Use existing `AgentUsage` type from `maverick.agents.result`. Update spec reference from `TokenUsage` to `AgentUsage`.

**Rationale**: Reuse existing types to avoid duplication and ensure consistency.

**Alternatives Considered**:
- Create new `TokenUsage` type: Rejected - duplicates `AgentUsage` functionality

---

### 4. WorkflowState Mutability

**Question**: Should `WorkflowState` be mutable or immutable?

**Findings**:
- FR-006 through FR-008 specify WorkflowState fields that accumulate over time (errors list, results)
- `ValidationWorkflowResult` is immutable (created once at completion)
- The spec describes WorkflowState as tracking "current stage" and "accumulated results"

**Decision**: `WorkflowState` should be a **mutable** Pydantic model (no `frozen=True`). The workflow updates state as stages progress. `FlyResult` wraps the final state immutably.

**Rationale**: Tracking ongoing execution requires mutation. Final result (`FlyResult`) captures the frozen snapshot.

**Alternatives Considered**:
- Immutable with copy-on-write: Rejected - excessive object creation for frequent updates
- Plain dict: Rejected - loses type safety

---

### 5. FlyConfig Integration with MaverickConfig

**Question**: How should FlyConfig integrate with the existing MaverickConfig hierarchy?

**Findings**:
- `MaverickConfig` uses Pydantic `BaseSettings` with nested config models
- Existing pattern: `github: GitHubConfig`, `notifications: NotificationConfig`, `validation: ValidationConfig`
- FR-023 specifies: "FlyConfig MUST be integratable into MaverickConfig as fly: FlyConfig field"

**Decision**: Add `fly: FlyConfig` field to `MaverickConfig` following the exact same pattern as other config sections.

**Rationale**: Consistent with existing configuration patterns.

**Alternatives Considered**:
- Separate config file: Rejected - inconsistent with project patterns
- Environment-only config: Rejected - yaml config is primary pattern

---

### 6. Progress Event Naming Convention

**Question**: What naming pattern should progress events follow?

**Findings**:
- Existing: `ProgressUpdate` (generic, single type)
- Spec requires 5 distinct event types: Started, StageStarted, StageCompleted, Completed, Failed
- Pattern should be clear and distinguishable

**Decision**: Use `Fly` prefix for all events: `FlyWorkflowStarted`, `FlyStageStarted`, `FlyStageCompleted`, `FlyWorkflowCompleted`, `FlyWorkflowFailed`

**Rationale**: Follows spec exactly (FR-012 through FR-016) and allows clear identification of event source.

**Alternatives Considered**:
- Generic `WorkflowEvent` with discriminator: Rejected - less type-safe
- Union type without prefix: Rejected - naming collisions with other workflows

---

### 7. WorkflowStage Enum String Representation

**Question**: How should WorkflowStage enum provide string representation (FR-002)?

**Findings**:
- `StageStatus` in validation.py uses `class StageStatus(str, Enum)` pattern
- This allows both `StageStatus.PENDING` and `StageStatus.PENDING.value == "pending"`
- String values are lowercase by convention

**Decision**: Use `class WorkflowStage(str, Enum)` with lowercase string values matching enum name.

**Rationale**: Consistent with existing enum patterns in the codebase.

**Alternatives Considered**:
- Custom `__str__`: Rejected - `str, Enum` pattern is cleaner
- Uppercase values: Rejected - inconsistent with existing patterns

---

## Summary

All research questions have been resolved. Key decisions:

1. **Async generator pattern** for progress events (matches ValidationWorkflow)
2. **Pydantic for config/state**, **dataclass for events** (matches codebase pattern)
3. **Use existing `AgentUsage`** instead of creating new TokenUsage
4. **Mutable `WorkflowState`**, immutable `FlyResult` (practical for ongoing tracking)
5. **`fly: FlyConfig` field** in MaverickConfig (standard pattern)
6. **`Fly*` prefix** for all progress events (clear namespace)
7. **`str, Enum` pattern** for WorkflowStage (consistent with StageStatus)

No unresolved clarifications remain.
