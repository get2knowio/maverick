# Research: Mode-Aware Step Dispatch

**Feature Branch**: `034-step-mode-dispatch`
**Date**: 2026-02-26

## R1: infer_step_mode Relaxation Strategy

### Decision
Modify `infer_step_mode()` in `src/maverick/dsl/executor/config.py` to allow `StepType.PYTHON` steps to have `mode: agent` as an explicit override.

### Rationale
Currently `infer_step_mode()` (line 188-235 of `config.py`) raises `ValueError` when `explicit_mode != inferred`. For `StepType.PYTHON`, the inferred mode is `DETERMINISTIC`. The spec requires PYTHON steps to accept `mode: agent` when explicitly configured.

The fix introduces a set of "mode-overridable" step types:

```python
_MODE_OVERRIDABLE: frozenset[StepType] = frozenset({StepType.PYTHON})
```

For step types in this set, an explicit mode different from the inferred mode is accepted (returned as-is) instead of raising. For all other step types, the existing strict validation is preserved.

### Alternatives Considered
1. **New `StepType.HYBRID`**: Rejected — spec says "no new step types" (A-007).
2. **Handle override downstream**: Rejected — breaks single-source-of-truth for config resolution. The resolved StepConfig would contain a mode that doesn't match the step type, causing confusion in downstream consumers.
3. **Remove all validation**: Rejected — we still want to prevent nonsensical combinations like `StepType.AGENT` + `mode: deterministic` or `StepType.VALIDATE` + `mode: agent`.

### Impact
- `infer_step_mode()` change: ~5 lines
- `validate_agent_only_fields()` in StepConfig: no change needed (it already checks mode, not step type)
- Tests in `test_config.py`: update/add ~4 test cases for PYTHON+AGENT combinations

---

## R2: Dispatch Integration Point

### Decision
Mode-aware dispatch happens at the top of `execute_python_step()` in `src/maverick/dsl/serialization/executor/handlers/python_step.py`. Agent-mode execution is delegated to `dispatch_agent_mode()` in a new sibling module `dispatch.py`.

### Rationale
The python step handler is the natural dispatch point:
1. Already has access to `registry`, `context.step_executor`, `resolved_inputs`, `event_callback`
2. The handler registry maps `StepType.PYTHON → execute_python_step` — no registry change needed
3. Mode dispatch is a python-step concern, not an executor-coordinator concern

The dispatch flow:

```
execute_python_step(step, resolved_inputs, context, registry, ...)
  │
  ├─ resolve_step_config(...)  →  StepConfig with mode, autonomy
  │
  ├─ if force_deterministic from context.inputs: mode = DETERMINISTIC
  │
  ├─ if mode == DETERMINISTIC:
  │     └─ existing handler logic (lookup action, call, return)
  │
  └─ if mode == AGENT:
        └─ dispatch_agent_mode(step, resolved_inputs, context, ...)
              │
              ├─ look up intent description
              ├─ construct prompt (intent + inputs + suffix)
              ├─ try: executor.execute(...)
              │    └─ apply_autonomy_gate(agent_result, ...)
              └─ except: fallback to deterministic handler
```

### Alternatives Considered
1. **Override at executor level (`_execute_step`)**: Rejected — executor shouldn't know about mode semantics. It dispatches by step type, not by mode.
2. **New handler registered separately**: Rejected — no new step types. Would require changes to schema discriminator.

---

## R3: Autonomy Gate Implementation

### Decision
Implement autonomy gates as a single `apply_autonomy_gate()` function in `dispatch.py` with per-level behavior.

### Rationale

| Level | Behavior | Implementation |
|-------|----------|----------------|
| Operator | Warn + fallback to deterministic | Runtime guard. StepConfig validation already rejects `autonomy: operator` on agent mode, but defense-in-depth catches edge cases. |
| Collaborator | Re-execute deterministic, compare structurally | Call deterministic action with same resolved_inputs. Use `_structurally_equivalent()` to compare. Accept agent result if equivalent; else use deterministic result. |
| Consultant | Verify output contract | Check result type matches expected (dict with expected keys, correct types). Log discrepancies. Accept regardless. |
| Approver | Accept directly | No post-processing. Hard failures (exceptions) already caught in the try/except wrapper. |

### Structural Equivalence (`_structurally_equivalent`)

For Collaborator validation, structural equivalence means:
- Same Python type
- For `dict`: same keys, recursively equivalent values
- For `list`/`tuple`: same length, recursively equivalent elements
- For primitives (`str`, `int`, `float`, `bool`, `None`): equality
- For dataclasses: compare via `dataclasses.asdict()`
- For Pydantic models: compare via `.model_dump()`

This is intentionally loose — it doesn't compare object identity, ordering of dict keys, or floating-point precision beyond equality.

### Output Contract Verification (Consultant)

For Consultant level, "output contract" verification means:
- If the deterministic action has a return type annotation, check `isinstance(result, annotation)`
- If the result is a dict, check it has the same top-level keys as a reference execution would produce
- If the result is a dataclass/Pydantic model, check it validates against the schema

### Alternatives Considered
1. **Deep equality (`==`)**: Rejected — too strict. Agent may produce semantically equivalent but not byte-identical results.
2. **Custom comparison protocol**: Rejected — over-engineering. The structural comparison covers all current action return types.

---

## R4: Intent Description Coverage

### Decision
Create `src/maverick/library/actions/intents.py` with `ACTION_INTENTS: dict[str, str]` mapping every registered action name to a plain-language intent description.

### Rationale
The spec mandates a central registry dict (FR-004, clarification session). Co-locating with the action registry in `src/maverick/library/actions/` keeps intent descriptions discoverable.

There are ~40 registered actions (counted from `register_all_actions()`). Each needs a 1-2 sentence intent description explaining **what** the step accomplishes (not **how**).

A test (`test_intents.py`) will:
1. Instantiate `ComponentRegistry` and call `register_all_actions()`
2. Assert every registered action name has a corresponding non-empty entry in `ACTION_INTENTS`
3. Assert no orphan entries exist in `ACTION_INTENTS` (keys must match registered actions)

### Action Categories for Intent Authoring

| Category | Actions | Intent Pattern |
|----------|---------|----------------|
| Preflight | `run_preflight_checks` | "Verify all prerequisites (API keys, tools, repository state) are available..." |
| Workspace | `init_workspace`, `create_fly_workspace` | "Initialize/create the development workspace for..." |
| Dependencies | `sync_dependencies` | "Synchronize project dependencies..." |
| Git | `git_add`, `git_commit`, `git_push`, etc. | "Stage/commit/push changes..." |
| jj | `jj_commit_bead`, `jj_describe`, etc. | "Create a jj commit/Set description/..." |
| GitHub | `create_github_pr`, `fetch_github_issues`, etc. | "Create a pull request/Fetch issues..." |
| Review | `gather_pr_context`, `run_review_fix_loop`, etc. | "Collect context for code review/Iterate fix-review cycle..." |
| Validation | `run_fix_retry_loop`, `generate_validation_report` | "Run validation with retry/Generate report..." |
| Beads | `select_next_bead`, `mark_bead_complete`, etc. | "Select the next ready bead/Mark bead as complete..." |
| Cleanup | `process_selected_issues`, `generate_cleanup_summary` | "Process selected issues/Generate summary..." |
| Dry-run | `log_dry_run` | "Log a dry-run message without performing any mutations." |

---

## R5: --deterministic CLI Flag

### Decision
Add `--deterministic` flag to the `fly` command. Pass as workflow input `force_deterministic=true`. The dispatch logic checks `context.inputs.get("force_deterministic")`.

### Rationale
Consistent with how existing flags are passed:
- `dry_run` → `dry_run=true` in input_parts
- `skip_review` → `skip_review=true` in input_parts

The dispatch module checks `context.inputs.get("force_deterministic")` and forces `mode = DETERMINISTIC` when truthy.

### Alternatives Considered
1. **Environment variable**: Could be added later as a supplementary mechanism. Not the primary interface per spec.
2. **MaverickConfig field**: Rejected — this is a runtime override, not persistent configuration.

---

## R6: Prompt Construction for Agent Mode

### Decision
The agent prompt is constructed from three parts:

1. **System instruction**: Intent description + action metadata
2. **User prompt**: Serialized resolved inputs as structured JSON context
3. **Suffix**: `StepConfig.prompt_suffix` or content of `StepConfig.prompt_file`

### Prompt Template

```
You are executing a workflow step. Your goal:

{intent_description}

You have been given the following inputs:
{json.dumps(resolved_inputs, indent=2, default=str)}

{prompt_suffix_content}

Produce output that matches what the deterministic handler would produce.
Output your result as valid JSON.
```

### Rationale
- Intent description provides the "what" (FR-005)
- Resolved inputs provide the "with what" (A-005)
- Prompt suffix provides operator customization (FR-005, per Spec 033)
- The instruction to match deterministic output format helps autonomy gates work

### Alternatives Considered
1. **Separate system prompt and user prompt**: The StepExecutor protocol has both `prompt` and `instructions` parameters. We use `instructions` for the intent+suffix and `prompt` for the resolved inputs.
