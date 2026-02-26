# Implementation Plan: Mode-Aware Step Dispatch

**Branch**: `034-step-mode-dispatch` | **Date**: 2026-02-26 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/034-step-mode-dispatch/spec.md`

## Summary

Enable any `StepType.PYTHON` workflow step to execute either deterministically (current behavior) or via an AI agent, controlled by the `StepConfig.mode` field from Spec 033. The dispatch decision happens inside the Python step handler, routing to the existing action callable or to a `StepExecutor`-based agent path with intent-guided prompting. Autonomy levels (Operator through Approver) control validation/verification gates on agent results, and agent failures automatically fall back to deterministic execution.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Claude Agent SDK (`claude-agent-sdk`), Pydantic, structlog, tenacity
**Storage**: N/A (no persistence changes)
**Testing**: pytest + pytest-asyncio (parallel via xdist)
**Target Platform**: Linux (CLI application)
**Project Type**: Single project (existing `src/maverick/` layout)
**Performance Goals**: N/A — dispatch overhead must be negligible (microseconds for mode check)
**Constraints**: Zero behavioral regression for existing workflows; StepConfig.timeout governs agent execution
**Scale/Scope**: ~61 registered Python actions need intent descriptions

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | PASS | All new dispatch paths are async. Agent execution uses existing async `StepExecutor.execute()`. No blocking calls. |
| II. Separation of Concerns | PASS | Dispatch logic stays in the handler layer (workflows/execution). Agents provide judgment via StepExecutor. Deterministic validation stays in the handler. |
| III. Dependency Injection | PASS | StepExecutor is already injected via `WorkflowContext.step_executor`. No new global state. |
| IV. Fail Gracefully | PASS | Agent failures fall back to deterministic execution (FR-006). Fallback is a real execution, not a stub. |
| V. Test-First | PASS | Tests for each autonomy level, fallback scenarios, and intent registry completeness. |
| VI. Type Safety | PASS | New type `DispatchResult` is a frozen dataclass. Autonomy gate is a function, not a type. Intent registry is `dict[str, str]` with validation. |
| VII. Simplicity & DRY | PASS | Dispatch logic is a single function in the existing handler module. No new abstractions beyond what the spec requires. |
| VIII. Relentless Progress | PASS | Fallback-to-deterministic ensures forward progress even when agent mode fails. |
| IX. Hardening by Default | PASS | Agent timeout via StepConfig.timeout. Fallback on exception, timeout, or schema violation. |
| X. Architectural Guardrails | See below | |
| — Guardrail #3 (deterministic ops in workflows) | PASS | Validation of agent results happens in the handler, not in the agent. |
| — Guardrail #4 (typed contracts) | PASS | `DispatchResult` frozen dataclass for dispatch outcomes. |
| — Guardrail #8 (canonical libraries) | PASS | Uses structlog for logging, existing StepExecutor for agent execution. |
| — Guardrail #11 (workspace cwd) | PASS | cwd is threaded through existing resolved_inputs; no change needed. |
| — Guardrail #12 (DSL expression coercion) | PASS | No new DSL expressions introduced. |
| XI. Modularize Early | PASS | New dispatch module ~200 LOC. Intent registry ~150 LOC. Well under soft limit. |
| XII. Ownership | PASS | Full coverage of all actions with intent descriptions. |

## Project Structure

### Documentation (this feature)

```text
specs/034-step-mode-dispatch/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── contracts/           # Phase 1 output
```

### Source Code (repository root)

```text
src/maverick/
├── dsl/
│   ├── executor/
│   │   └── config.py                         # MODIFY: relax infer_step_mode() for PYTHON+AGENT
│   └── serialization/
│       └── executor/
│           └── handlers/
│               ├── python_step.py            # MODIFY: add mode-aware dispatch logic
│               └── dispatch.py               # NEW: mode dispatch, autonomy gates, fallback
├── library/
│   └── actions/
│       └── intents.py                        # NEW: intent registry mapping action names → descriptions
├── cli/
│   └── commands/
│       └── fly/
│           └── _group.py                     # MODIFY: add --deterministic flag

tests/
├── unit/
│   └── dsl/
│       ├── executor/
│       │   └── test_config.py                # MODIFY: update infer_step_mode tests
│       └── serialization/
│           └── executor/
│               └── handlers/
│                   ├── test_dispatch.py       # NEW: dispatch logic tests
│                   └── test_python_step_dispatch.py  # NEW: integration tests for mode-aware python step
└── unit/
    └── library/
        └── actions/
            └── test_intents.py               # NEW: intent registry completeness tests
```

**Structure Decision**: All new code fits within the existing `src/maverick/` single-project layout. The dispatch module is co-located with the python step handler. The intent registry is co-located with the action registry.

## Complexity Tracking

No constitution violations to justify.

---

## Phase 0: Research

### Research Task 1: infer_step_mode Relaxation Strategy

**Decision**: Modify `infer_step_mode()` in `src/maverick/dsl/executor/config.py` to allow `StepType.PYTHON` steps to have `mode: agent` as an explicit override.

**Rationale**: Currently `infer_step_mode()` raises `ValueError` if `explicit_mode != inferred`. The spec requires PYTHON steps to accept `mode: agent`. The fix is to define a set of "mode-overridable" step types (`{StepType.PYTHON}`) and only reject overrides for types that truly cannot support them (AGENT, GENERATE, VALIDATE, BRANCH, LOOP, CHECKPOINT).

**Alternatives considered**:
- Add a completely new step type `StepType.HYBRID`: Rejected — the spec explicitly says "no new step types" (A-007).
- Keep validation strict, handle mode override downstream: Rejected — breaks the single-source-of-truth for step config resolution.

### Research Task 2: Dispatch Integration Point

**Decision**: The dispatch decision happens at the **top of `execute_python_step()`** in `python_step.py`. When `StepConfig.mode == AGENT`, execution is delegated to a new `dispatch_agent_mode()` function in a sibling `dispatch.py` module.

**Rationale**: The python step handler is the natural dispatch point because:
1. It already has access to `registry`, `context` (with `step_executor`), `resolved_inputs`, and `event_callback`.
2. The handler registry (`STEP_HANDLERS`) maps `StepType.PYTHON → execute_python_step`. No change to the handler registry is needed.
3. Mode dispatch is a concern of the python step handler, not the executor coordinator.

**Alternatives considered**:
- Override at the executor level (`_execute_step`): Rejected — would require the executor to know about mode semantics, violating separation of concerns.
- Create a new handler and register under a different key: Rejected — the spec requires no new step types.

### Research Task 3: Autonomy Gate Implementation

**Decision**: Autonomy gates are implemented as a single `apply_autonomy_gate()` function in `dispatch.py` that takes the agent result, the autonomy level, the deterministic action, and resolved inputs, and returns a `DispatchResult`.

**Rationale**: Each autonomy level has distinct validation behavior:
- **Operator**: Should not reach agent mode (warn + fallback to deterministic). This is already handled by StepConfig validation which rejects `autonomy: operator` on agent-mode steps, but we add a runtime guard as defense-in-depth.
- **Collaborator**: Re-execute deterministic handler, structurally compare outputs. Accept agent result only if equivalent; otherwise use deterministic result.
- **Consultant**: Validate agent result against output contract (type check, key presence). Log discrepancies but accept.
- **Approver**: Accept agent result directly. Only intervene on hard failures (exceptions already caught upstream).

**Structural comparison** for Collaborator: Compare using a `_structurally_equivalent()` helper that checks:
1. Same type
2. For dicts: same keys, recursively equivalent values
3. For lists: same length, recursively equivalent elements
4. For primitives: equality
5. For dataclasses: convert to dict and compare

**Alternatives considered**:
- Deep equality (`==`): Rejected — too strict; agent may produce semantically equivalent but not identical results (e.g., different string formatting).
- Hash comparison: Rejected — not meaningful for complex nested structures.

### Research Task 4: Intent Description Coverage

**Decision**: Create `src/maverick/library/actions/intents.py` containing `ACTION_INTENTS: dict[str, str]` mapping every registered action name to a plain-language intent description.

**Rationale**: The spec mandates a central registry dict (FR-004, clarification session). Co-locating with the action registry (`src/maverick/library/actions/`) keeps intent descriptions discoverable. A test verifies every registered action has an intent entry (SC-006).

### Research Task 5: --deterministic CLI Flag

**Decision**: Add `--deterministic` flag to the `fly` command in `_group.py`. Pass it as a workflow input (`force_deterministic=true`). The dispatch logic in `dispatch.py` checks this flag via `WorkflowContext.inputs.get("force_deterministic")`.

**Rationale**: The flag is an operational safety valve (FR-011, A-009). It overrides all per-step mode settings at runtime.

**Alternatives considered**:
- Environment variable (`MAVERICK_FORCE_DETERMINISTIC`): Could be added later, but the CLI flag is the primary interface per the spec.
- Global config field: Rejected — this is a runtime override, not a persistent configuration.

### Research Task 6: Prompt Construction

**Decision**: The agent prompt is constructed from three parts (FR-005):
1. **Intent description** from `ACTION_INTENTS[step.action]`
2. **Resolved inputs** serialized as structured context (JSON or key-value)
3. **Prompt suffix/file** from `StepConfig.prompt_suffix` or `StepConfig.prompt_file`

The prompt is passed to `StepExecutor.execute()` as the `prompt` parameter, with a system-level instruction combining intent and constraints.

---

## Phase 1: Design

### Data Model

See [data-model.md](data-model.md) for entity definitions.

### Key Types

#### DispatchResult (frozen dataclass)

```python
@dataclass(frozen=True, slots=True)
class DispatchResult:
    """Result of mode-aware step dispatch."""
    output: Any                           # Step result
    mode_used: StepMode                   # Actual mode executed (may differ from config)
    fallback_used: bool                   # True if agent failed and deterministic ran
    autonomy_level: AutonomyLevel         # Autonomy level applied
    agent_result_accepted: bool | None    # None if deterministic, True/False for agent
    validation_details: str | None        # Details about validation/verification outcome

    def to_dict(self) -> dict[str, Any]: ...
```

#### Intent Registry

```python
# src/maverick/library/actions/intents.py
ACTION_INTENTS: dict[str, str] = {
    "git_commit": "Create a git commit with the specified message in the working directory.",
    "git_push": "Push local commits to the remote repository.",
    # ... one entry per registered action
}

def get_intent(action_name: str) -> str | None:
    """Look up the intent description for an action."""
    return ACTION_INTENTS.get(action_name)
```

### Contracts

#### dispatch_agent_mode()

```python
async def dispatch_agent_mode(
    *,
    step: PythonStepRecord,
    resolved_inputs: dict[str, Any],
    context: WorkflowContext,
    registry: ComponentRegistry,
    step_config: StepConfig,
    event_callback: EventCallback | None = None,
) -> DispatchResult:
    """Execute a Python step via agent mode with autonomy gates."""
```

#### apply_autonomy_gate()

```python
async def apply_autonomy_gate(
    *,
    agent_result: Any,
    autonomy_level: AutonomyLevel,
    deterministic_action: Callable[..., Any],
    resolved_inputs: dict[str, Any],
    step_name: str,
) -> DispatchResult:
    """Apply autonomy-level validation/verification to agent result."""
```

#### Modified execute_python_step()

```python
async def execute_python_step(
    step: PythonStepRecord,
    resolved_inputs: dict[str, Any],
    context: WorkflowContext,
    registry: ComponentRegistry,
    config: Any = None,
    event_callback: EventCallback | None = None,
) -> Any:
    """Execute a Python step — mode-aware dispatch.

    When StepConfig.mode == AGENT, delegates to dispatch_agent_mode().
    When StepConfig.mode == DETERMINISTIC (default), runs existing handler.
    """
```

### Structured Log Events (FR-007)

| Event | Fields | When |
|-------|--------|------|
| `dispatch.mode_selected` | `step_name`, `mode`, `autonomy`, `action` | Before execution |
| `dispatch.agent_completed` | `step_name`, `action`, `autonomy`, `duration_ms`, `accepted` | After agent produces result |
| `dispatch.autonomy_validation` | `step_name`, `autonomy`, `outcome` (`accepted`/`rejected`/`verified`) | After autonomy gate |
| `dispatch.fallback` | `step_name`, `action`, `reason` (`exception`/`timeout`/`schema_violation`/`validation_failure`) | When falling back to deterministic |
| `dispatch.deterministic_completed` | `step_name`, `action`, `duration_ms` | After deterministic execution |

### Quickstart

See [quickstart.md](quickstart.md) for usage examples.

---

## Key Design Decisions

1. **Dispatch lives in the handler layer**: The `execute_python_step()` function gains mode awareness. A new `dispatch.py` sibling module contains the agent dispatch and autonomy gate logic, keeping the handler focused and under the LOC soft limit.

2. **StepConfig resolution happens once**: `resolve_step_config()` is called once at the top of `execute_python_step()`. The resolved config is passed to all downstream functions. No duplicate resolution.

3. **infer_step_mode() becomes permissive for PYTHON**: Instead of rejecting `mode: agent` for PYTHON steps, it allows this combination. The set of "flexible" step types is explicit: only `{StepType.PYTHON}`.

4. **Fallback reuses resolved inputs**: Per spec clarification, fallback execution reuses the same `resolved_inputs` dict — no re-resolution of DSL expressions (A-008).

5. **Intent descriptions are static strings**: No runtime generation. One dict, one test to verify completeness against the action registry.

6. **--deterministic flag flows via workflow inputs**: Simple, consistent with how other CLI flags (dry_run, skip_review) are passed. No new plumbing needed.
