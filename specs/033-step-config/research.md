# Research: Step Configuration Model

**Feature**: 033-step-config | **Date**: 2026-02-25

## Research Tasks

### R1: Replace frozen dataclass with Pydantic BaseModel for StepConfig

**Decision**: Replace `StepExecutorConfig` (frozen dataclass) with `StepConfig` (Pydantic BaseModel).

**Rationale**:
- The existing `StepExecutorConfig` is a frozen dataclass with 5 fields and manual `to_dict()`. It works but cannot express cross-field validation (e.g., "autonomy only valid when mode=agent").
- Pydantic `BaseModel` provides `@model_validator`, `@field_validator`, `model_dump()`, and native YAML/JSON serialization — all required by the spec's validation rules (FR-005, FR-006).
- The `StepExecutor` protocol references `StepExecutorConfig` by name. We'll rename the protocol parameter type to `StepConfig` and keep `StepExecutorConfig` as a deprecated alias for one release cycle.
- `RetryPolicy` remains a frozen dataclass (no cross-field validation needed; frozen semantics are appropriate).

**Alternatives considered**:
- Keep dataclass + manual validation: Rejected — cross-field validators would be hand-rolled and inconsistent with the rest of the codebase (Pydantic everywhere).
- Create `StepConfig` as a separate new class: Rejected — two config types for the same purpose violates DRY. Replacement with backward-compat alias is cleaner.

### R2: Enum placement for StepMode and AutonomyLevel

**Decision**: Add `StepMode` and `AutonomyLevel` to `src/maverick/dsl/types.py`.

**Rationale**:
- `dsl/types.py` already contains `StepType` enum (line 17). Grouping DSL enums here follows existing convention.
- Both enums are `str, Enum` subclasses (like `StepType`) for YAML serialization compatibility.
- `AutonomyLevel` uses ordered integer-backed values for potential future comparison, but is a `str, Enum` for serialization.

**Alternatives considered**:
- Place in `config.py`: Rejected — these are DSL concepts, not general config.
- Place in `dsl/executor/config.py`: Acceptable but `types.py` is the established enum home.

### R3: StepConfig field on step records — base vs. per-type

**Decision**: Add `config: dict[str, Any] | None` to the `StepRecord` base class.

**Rationale**:
- The spec says "DSL step records (agent, generate, validate, python) MUST accept an optional `config` field" (FR-008). All four main types plus subworkflow benefit from config.
- Adding to base avoids repeating the field in 5+ subclasses.
- Loop, branch, and checkpoint steps inherit the field but it's ignored (harmless).
- The YAML field is `config` (not `executor_config`). For backward compat, `AgentStepRecord` continues to accept `executor_config` via a model validator that maps it to `config` with a deprecation warning.

**Alternatives considered**:
- Add only to agent/generate/validate/python records: Rejected — more code duplication, and subworkflows also benefit from step config (they can pass it through to their internal steps).
- Use `StepConfig` Pydantic type directly on the schema field: Rejected — the schema field is `dict[str, Any] | None` (raw YAML), deserialized to `StepConfig` at handler time. This matches the existing pattern for `executor_config`.

### R4: Four-layer configuration resolution strategy

**Decision**: Implement a `resolve_step_config()` function in `dsl/executor/config.py`.

**Rationale**:
- Resolution order: step inline `config` > project-level `steps[name]` > agent-level `agents[agent_name]` > global `model` defaults.
- The function takes all four layers and merges them field-by-field: for each field in `StepConfig`, use the first non-None value found in precedence order.
- `mode` and `autonomy` do not participate in agent-level or global-level resolution (they are step-specific concepts). Only `model_id`, `temperature`, `max_tokens`, and `timeout` inherit from agent/global config.
- Returns a fully-resolved `StepConfig` with no None values for model fields.

**Alternatives considered**:
- Pydantic model inheritance with `model_copy(update=...)`: Works for simple merging but doesn't express the 4-layer precedence cleanly.
- Separate resolver class: Over-engineered for a pure function.

### R5: Backward compatibility for executor_config field

**Decision**: Accept `executor_config` as a deprecated alias on `AgentStepRecord`, mapped to `config` via `@model_validator`.

**Rationale**:
- Existing workflows use `executor_config` on agent steps. Breaking them violates FR-012.
- A model validator on `AgentStepRecord` checks for `executor_config` in the raw data, moves it to `config`, and emits a deprecation warning via `structlog`.
- If both `executor_config` and `config` are provided, raise `ConfigError` (ambiguous).
- The `StepExecutor` protocol parameter is renamed from `config: StepExecutorConfig` to `config: StepConfig`. A type alias `StepExecutorConfig = StepConfig` preserves backward compat for any external code referencing the old name.

**Alternatives considered**:
- Keep `executor_config` as the canonical name: Rejected — spec explicitly renames to `config`.
- Silent migration without warning: Rejected — users should know to update their YAML.

### R6: Mode inference from step type

**Decision**: Implement mode inference in the step handler layer, not in the schema validator.

**Rationale**:
- The spec says mode is inferred from step type when omitted: `type: agent/generate` → `mode: agent`; `type: python/validate` → `mode: deterministic` (FR-008).
- This inference happens during `_resolve_executor_config()` (or its replacement), not during Pydantic schema validation, because the schema layer only sees raw YAML dicts.
- If `mode` is explicitly set in the YAML and contradicts the step type, validation rejects it with a clear error message.

**Alternatives considered**:
- Infer at schema level: Rejected — `StepRecord.config` is `dict | None` (raw YAML); the step type discriminator and config dict are separate fields. Cross-field validation across the discriminated union is complex and fragile in Pydantic.
- Infer at `StepConfig` construction time: Requires passing step type into StepConfig, coupling config to schema. Better to keep StepConfig as a pure config model and infer externally.

### R7: provider field — forward compatibility only

**Decision**: `provider` field on `StepConfig` defaults to `"claude"` and validates to accept only `"claude"`.

**Rationale**:
- Spec says: "Future-proofing placeholder. Validated to accept only `"claude"`" (A-001).
- Uses `Literal["claude"]` type with default `"claude"`. This is the simplest validation.
- Does not influence executor selection in this feature (executor routing remains in 032).

**Alternatives considered**:
- Open string with warning for unknown providers: Rejected — spec is explicit about only accepting "claude".
- Enum-based provider: Over-engineered for a single value. Convert to enum when a second provider is added.
