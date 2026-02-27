# Data Model: Mode-Aware Step Dispatch

**Feature Branch**: `034-step-mode-dispatch`
**Date**: 2026-02-26

## Entities

### 1. DispatchResult

**Location**: `src/maverick/dsl/serialization/executor/handlers/dispatch.py`

A frozen dataclass capturing the outcome of a mode-aware dispatch decision.

| Field | Type | Description |
|-------|------|-------------|
| `output` | `Any` | The step result (from agent or deterministic handler) |
| `mode_used` | `StepMode` | Actual execution mode (may differ from configured if fallback occurred) |
| `fallback_used` | `bool` | `True` if agent mode failed and deterministic handler ran |
| `autonomy_level` | `AutonomyLevel` | The autonomy level applied during dispatch |
| `agent_result_accepted` | `bool \| None` | `None` for deterministic, `True` if agent result used, `False` if rejected by gate |
| `validation_details` | `str \| None` | Human-readable details about validation/verification outcome |

**Validation Rules**:
- If `mode_used == DETERMINISTIC` and `fallback_used == False`, then `agent_result_accepted` must be `None`
- If `fallback_used == True`, then `mode_used` must be `DETERMINISTIC` and `agent_result_accepted` must be `False`

**State Transitions**: N/A — immutable value object created once per dispatch.

**Relationships**: Returned by `dispatch_agent_mode()`, consumed by `execute_python_step()`.

### 2. ACTION_INTENTS Registry

**Location**: `src/maverick/library/actions/intents.py`

A module-level constant `dict[str, str]` mapping action names to intent descriptions.

| Field | Type | Description |
|-------|------|-------------|
| key | `str` | Registered action name (e.g., `"git_commit"`) |
| value | `str` | Plain-language intent description (1-2 sentences) |

**Validation Rules**:
- Every key must correspond to a registered action in `ComponentRegistry.actions`
- Every value must be a non-empty string
- No orphan keys (keys without registered actions)
- Enforced by `test_intents.py`

**Relationships**: Read by `dispatch_agent_mode()` to construct agent prompts.

### 3. StepConfig (Modified — Spec 033)

**Location**: `src/maverick/dsl/executor/config.py`

No new fields. Existing fields `mode` and `autonomy` become operational for `StepType.PYTHON` steps.

**Behavioral Change**:
- `infer_step_mode(StepType.PYTHON, StepMode.AGENT)` now returns `StepMode.AGENT` instead of raising `ValueError`
- `validate_agent_only_fields()` already permits agent-only fields when `mode == AGENT`, regardless of step type

### 4. WorkflowContext.inputs (Modified)

**Location**: `src/maverick/dsl/context.py`

No schema change. New conventional key:

| Key | Type | Description |
|-----|------|-------------|
| `force_deterministic` | `str` (`"true"` / `"false"`) | When `"true"`, forces all PYTHON steps to deterministic mode |

**Set by**: `fly` CLI command when `--deterministic` flag is passed.
**Read by**: `execute_python_step()` dispatch logic.

## Existing Entities (No Changes)

### StepMode (Spec 033)
- `DETERMINISTIC` / `AGENT` — no changes

### AutonomyLevel (Spec 033)
- `OPERATOR` / `COLLABORATOR` / `CONSULTANT` / `APPROVER` — no changes

### StepExecutor Protocol (Spec 032)
- Used as-is for agent-mode execution

### ExecutorResult (Spec 032)
- Used as-is to receive agent execution results

### PythonStepRecord
- No schema changes — `config` field already supports per-step overrides

## Entity Relationship Diagram

```
PythonStepRecord
  ├── .action → ActionRegistry.get(name) → callable
  ├── .config → resolve_step_config() → StepConfig
  │                                        ├── .mode → StepMode
  │                                        └── .autonomy → AutonomyLevel
  │
  └── execute_python_step()
        │
        ├── mode == DETERMINISTIC → action(**resolved_inputs) → result
        │
        └── mode == AGENT → dispatch_agent_mode()
              │
              ├── ACTION_INTENTS[action] → intent string
              ├── StepExecutor.execute() → ExecutorResult
              ├── apply_autonomy_gate() → DispatchResult
              └── on failure → fallback to action(**resolved_inputs)
```
