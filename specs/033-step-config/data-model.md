# Data Model: Step Configuration Model

**Feature**: 033-step-config | **Date**: 2026-02-25

## Entities

### StepMode (Enum)

**Location**: `src/maverick/dsl/types.py`

| Value | Description |
|-------|-------------|
| `deterministic` | Code-only step (python, validate). No AI provider involved. |
| `agent` | AI-powered step (agent, generate). Uses StepExecutor for execution. |

**Type**: `str, Enum` (matches `StepType` convention for YAML serialization).

### AutonomyLevel (Enum)

**Location**: `src/maverick/dsl/types.py`

| Value | Order | Description |
|-------|-------|-------------|
| `operator` | 0 | Deterministic only. Step follows exact instructions. |
| `collaborator` | 1 | Agent proposes, code validates before applying. |
| `consultant` | 2 | Agent executes, code verifies after completion. |
| `approver` | 3 | Agent autonomous, escalates only on exceptions. |

**Type**: `str, Enum`. Order is informational (enforcement is the executor's responsibility per A-002).

### StepConfig (Pydantic BaseModel)

**Location**: `src/maverick/dsl/executor/config.py`

Replaces and extends `StepExecutorConfig`. Central per-step configuration model.

| Field | Type | Default | Description | Validation |
|-------|------|---------|-------------|------------|
| `mode` | `StepMode \| None` | `None` | Execution strategy. Inferred from step type when None. | Enum member |
| `autonomy` | `AutonomyLevel \| None` | `None` | Agent independence level. Defaults to `operator` when resolved. | Enum member; rejected when mode=deterministic (except operator) |
| `provider` | `Literal["claude"] \| None` | `None` | AI provider. Future-proofing placeholder. | Only "claude" accepted |
| `model_id` | `str \| None` | `None` | Model identifier override. | Non-empty string |
| `temperature` | `float \| None` | `None` | Sampling temperature override. | 0.0 <= v <= 1.0 |
| `max_tokens` | `int \| None` | `None` | Max output tokens override. | > 0, <= 200000 |
| `timeout` | `int \| None` | `None` | Timeout in seconds. | > 0 |
| `max_retries` | `int \| None` | `None` | Maximum retry attempts. | >= 0 |
| `allowed_tools` | `list[str] \| None` | `None` | Tool whitelist. None=all, []=none. | List of non-empty strings; rejected when mode=deterministic |
| `prompt_suffix` | `str \| None` | `None` | Inline prompt extension. | Rejected when mode=deterministic |
| `prompt_file` | `str \| None` | `None` | Path to prompt file (relative to workflow). | Rejected when mode=deterministic; mutually exclusive with prompt_suffix |
| `retry_policy` | `RetryPolicy \| None` | `None` | Deprecated. Use `max_retries` instead. Preserved for backward compat with `StepExecutorConfig`. | |

**Cross-field validators**:
1. `validate_agent_only_fields`: If mode=deterministic, reject autonomy (above operator), allowed_tools, prompt_suffix, prompt_file.
2. `validate_prompt_exclusivity`: prompt_suffix and prompt_file are mutually exclusive.
3. `validate_retry_migration`: If both `max_retries` and `retry_policy` are set, raise error.

**Serialization**: `model_dump(exclude_none=True)` for YAML output. `model_validate()` for YAML input.

**Backward compatibility**: `StepExecutorConfig` becomes a type alias for `StepConfig`.

### RetryPolicy (frozen dataclass — unchanged)

**Location**: `src/maverick/dsl/executor/config.py`

Preserved as-is. Fields: `max_attempts`, `wait_min`, `wait_max`.

### MaverickConfig.steps (new field)

**Location**: `src/maverick/config.py`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `steps` | `dict[str, StepConfig]` | `{}` | Project-level step config defaults keyed by step name. |

Participates in config hierarchy: env vars > project YAML > user YAML > defaults.

## Relationships

```
MaverickConfig
├── model: ModelConfig          ← Layer 4: global model defaults
├── agents: dict[str, AgentConfig]  ← Layer 3: per-agent model overrides
└── steps: dict[str, StepConfig]    ← Layer 2: project-level step defaults

WorkflowFile
└── steps: list[StepRecordUnion]
    └── StepRecord.config: dict | None  ← Layer 1: inline step config (highest priority)

Resolution: Layer 1 > Layer 2 > Layer 3 > Layer 4
```

## State Transitions

StepConfig is immutable after resolution. No state transitions.

Configuration lifecycle:
1. **Parse**: Raw YAML dict loaded into `StepRecord.config`
2. **Resolve**: `resolve_step_config()` merges 4 layers into a fully-resolved `StepConfig`
3. **Infer**: Mode inferred from step type if not explicit; autonomy defaults to operator
4. **Validate**: Cross-field constraints checked (mode/autonomy compat, prompt exclusivity)
5. **Consume**: Executor receives resolved `StepConfig` and applies settings
