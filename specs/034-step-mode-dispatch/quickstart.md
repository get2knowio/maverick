# Quickstart: Mode-Aware Step Dispatch

**Feature Branch**: `034-step-mode-dispatch`

## Overview

Mode-aware step dispatch enables any Python step in a YAML workflow to execute via an AI agent instead of its deterministic handler. This is controlled by the `mode` and `autonomy` fields in `StepConfig` (Spec 033).

## Basic Usage

### 1. Run a Step in Agent Mode (via maverick.yaml)

```yaml
# maverick.yaml - project-level step configuration
steps:
  git_commit:
    mode: agent
    autonomy: collaborator
    prompt_suffix: "Prefer conventional commit messages with scope."
```

No changes to the workflow YAML are needed. The step configuration is applied at resolution time.

### 2. Run a Step in Agent Mode (via inline step config)

```yaml
# workflow.yaml
steps:
  - name: commit_changes
    type: python
    action: git_commit
    config:
      mode: agent
      autonomy: consultant
    kwargs:
      message: ${{ inputs.commit_message }}
      cwd: ${{ steps.create_workspace.output.workspace_path }}
```

### 3. Force All Steps Deterministic (CLI Flag)

```bash
# Safety valve — ignore all mode: agent configurations
maverick fly --deterministic
```

## Autonomy Levels

| Level | Behavior | Use When |
|-------|----------|----------|
| `operator` | Forces deterministic mode (agent mode rejected) | Production safety default |
| `collaborator` | Agent proposes, deterministic validates | Building confidence in agent mode |
| `consultant` | Agent executes, output contract verified | Agent has proven reliable |
| `approver` | Agent executes with full autonomy | Full trust in agent capability |

### Example: Graduated Adoption

```yaml
# maverick.yaml — start with collaborator, upgrade over time
steps:
  git_commit:
    mode: agent
    autonomy: collaborator  # Phase 1: validate agent results
    # autonomy: consultant  # Phase 2: trust but verify
    # autonomy: approver    # Phase 3: full autonomy
```

## How It Works

### Dispatch Flow

1. `execute_python_step()` resolves the step's `StepConfig` via 4-layer precedence
2. If `--deterministic` flag is set, mode is forced to `DETERMINISTIC`
3. If `mode == DETERMINISTIC`: existing behavior (call action directly)
4. If `mode == AGENT`:
   a. Look up intent description for the action
   b. Construct prompt from intent + resolved inputs + prompt suffix
   c. Execute via `StepExecutor` (Spec 032)
   d. Apply autonomy gate (validate/verify/accept)
   e. On failure: fall back to deterministic handler

### Fallback Guarantee

Agent failures **never** make the system less reliable than deterministic-only:

```
Agent mode attempt
  ├── Success → apply autonomy gate → return result
  └── Failure (exception, timeout, schema violation)
        └── Fallback → run deterministic handler → return result
```

## Observability

All dispatch decisions emit structured log events:

```python
# Example structured log output (structlog)
dispatch.mode_selected    step_name=commit_changes mode=agent autonomy=collaborator action=git_commit
dispatch.agent_completed  step_name=commit_changes action=git_commit duration_ms=2340 accepted=true
dispatch.autonomy_validation step_name=commit_changes autonomy=collaborator outcome=accepted
```

### Fallback Events

```python
dispatch.fallback         step_name=commit_changes action=git_commit reason=timeout
dispatch.deterministic_completed step_name=commit_changes action=git_commit duration_ms=120
```

## Intent Descriptions

Every Python action has a co-located intent description used as the agent's primary prompt:

```python
# src/maverick/library/actions/intents.py
ACTION_INTENTS = {
    "git_commit": "Create a git commit with the specified message in the working directory.",
    "git_push": "Push committed changes from the local branch to the remote repository.",
    "run_preflight_checks": "Verify all prerequisites are available before workflow execution.",
    # ... one entry per registered action
}
```

## Testing

```bash
# Run all dispatch tests
make test PYTEST_ARGS="-k dispatch"

# Run intent completeness test
make test PYTEST_ARGS="-k test_intents"
```
