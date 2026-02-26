# Quickstart: Step Configuration Model

**Feature**: 033-step-config | **Date**: 2026-02-25

## Basic Usage

### Configure step mode and autonomy in YAML

```yaml
version: "1.0"
name: example-workflow
steps:
  - name: lint_code
    type: python
    action: run_linter
    config:
      mode: deterministic      # Explicit (also inferred from type: python)
      timeout: 60

  - name: implement_feature
    type: agent
    agent: implementer
    config:
      mode: agent              # Explicit (also inferred from type: agent)
      autonomy: consultant     # Agent executes, code verifies
      model_id: claude-opus-4-6
      temperature: 0.3
      timeout: 600
      max_retries: 2

  - name: review_code
    type: agent
    agent: reviewer
    config:
      autonomy: collaborator   # Agent proposes, code validates
      allowed_tools: ["Read", "Glob", "Grep"]
      prompt_suffix: "Focus on security implications"
```

### Configure project-level step defaults in maverick.yaml

```yaml
# maverick.yaml
model:
  model_id: claude-sonnet-4-5-20250929
  temperature: 0.0

agents:
  reviewer:
    model_id: claude-opus-4-6

steps:
  review_code:
    autonomy: consultant
    timeout: 300
  implement_feature:
    autonomy: approver
    max_retries: 3
```

### Resolution precedence

For a step named `review_code` using agent `reviewer`:

1. **Inline config** (workflow YAML `config:` block) — highest priority
2. **Project steps** (`maverick.yaml` → `steps.review_code`)
3. **Agent config** (`maverick.yaml` → `agents.reviewer`)
4. **Global defaults** (`maverick.yaml` → `model`) — lowest priority

Example: If inline sets `temperature: 0.7` but project steps sets `temperature: 0.3`, the resolved value is `0.7`.

## Mode Inference

When `mode` is omitted from `config`, it is inferred from the step's `type`:

| Step Type | Inferred Mode |
|-----------|---------------|
| `python` | `deterministic` |
| `validate` | `deterministic` |
| `agent` | `agent` |
| `generate` | `agent` |

If `mode` is explicitly set and contradicts the step type, validation rejects the configuration.

## Backward Compatibility

Existing workflows using `executor_config` continue to work:

```yaml
# Old style (deprecated, still accepted)
steps:
  - name: implement
    type: agent
    agent: implementer
    executor_config:
      timeout: 600
      model: claude-opus-4-6

# New style (preferred)
steps:
  - name: implement
    type: agent
    agent: implementer
    config:
      timeout: 600
      model_id: claude-opus-4-6
      autonomy: consultant
```

A deprecation warning is emitted when `executor_config` is used.

## Validation Rules

- `autonomy` above `operator` requires `mode: agent`
- `allowed_tools`, `prompt_suffix`, `prompt_file` require `mode: agent`
- `prompt_suffix` and `prompt_file` are mutually exclusive
- `temperature` must be between 0.0 and 1.0
- `provider` only accepts `"claude"` (future-proofing)
- Mode must be consistent with step type when explicitly set

## Python API

```python
from maverick.dsl.executor.config import StepConfig, resolve_step_config
from maverick.dsl.types import StepMode, AutonomyLevel

# Create directly
config = StepConfig(
    mode=StepMode.AGENT,
    autonomy=AutonomyLevel.CONSULTANT,
    model_id="claude-opus-4-6",
    temperature=0.3,
)

# Resolve with 4-layer merge
resolved = resolve_step_config(
    inline_config={"timeout": 600},
    project_step_config=StepConfig(autonomy=AutonomyLevel.COLLABORATOR),
    agent_config=AgentConfig(model_id="claude-opus-4-6"),
    global_model=ModelConfig(),
    step_type=StepType.AGENT,
    step_name="review_code",
)
```
