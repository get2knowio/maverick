---
layout: section
class: text-center
---

# 12. The Workflow DSL

<div class="text-lg text-secondary mt-4">
Declarative workflow definitions in YAML
</div>

<div class="mt-8 flex justify-center gap-6 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-teal"></span>
    <span class="text-muted">14 Slides</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-brass"></span>
    <span class="text-muted">Step Types</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-coral"></span>
    <span class="text-muted">Expressions</span>
  </div>
</div>

<!--
Section 12 covers Maverick's YAML-based workflow DSL - the declarative system
for defining and sharing AI-powered automation workflows.

We'll cover:
1. Why YAML workflows?
2. File structure (version, name, inputs, steps, outputs)
3. Input declarations
4. Step types overview
5. Python steps
6. Agent steps
7. Validate steps
8. Loop steps (formerly parallel)
9. Branch steps (conditional)
10. Checkpoint steps
11. Subworkflow steps
12. Expression syntax
13. Workflow discovery
14. Hands-on example
-->

---

## layout: two-cols

# 12.1 Why YAML Workflows?

<div class="pr-4">

<div v-click>

## The Python DSL Problem

```python
# Previous approach (deprecated)
@workflow("feature")
async def feature_workflow(ctx):
    # Python knowledge required
    # Hard to share across teams
    # Version control diffs unclear
    await validate_step(ctx, ["lint", "test"])
```

<div class="text-xs text-muted mt-2">
Problems: Requires Python, IDE-specific, merge conflicts
</div>

</div>

<div v-click class="mt-6">

## Benefits of YAML

<div class="space-y-2 mt-2">
  <div class="flex items-start gap-2">
    <span class="text-teal mt-1">✓</span>
    <div>
      <span class="font-semibold">Declarative</span>
      <p class="text-sm text-muted">Describe what, not how</p>
    </div>
  </div>
  <div class="flex items-start gap-2">
    <span class="text-teal mt-1">✓</span>
    <div>
      <span class="font-semibold">Shareable</span>
      <p class="text-sm text-muted">Copy/paste across projects</p>
    </div>
  </div>
  <div class="flex items-start gap-2">
    <span class="text-teal mt-1">✓</span>
    <div>
      <span class="font-semibold">Versionable</span>
      <p class="text-sm text-muted">Clean diffs, easy reviews</p>
    </div>
  </div>
</div>

</div>

</div>

::right::

<div class="pl-4">

<div v-click class="mt-8">

## The YAML Approach ✓

```yaml
version: "1.0"
name: feature
description: Feature development workflow

inputs:
  branch_name:
    type: string
    required: true

steps:
  - name: validate
    type: validate
    stages: [lint, test]
    retry: 3
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Key Insight</strong><br>
  YAML workflows are the <em>only</em> workflow format in Maverick. 
  Built-in and custom workflows use identical infrastructure.
</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">No Python Required</strong><br>
  Teams can customize workflows without touching Python code.
</div>

</div>

<!--
The Python decorator DSL was deprecated in December 2025 in favor of YAML.

Why the change?
1. **Shareable**: YAML workflows can be copied between projects without dependency issues
2. **No Python required**: Product managers and DevOps engineers can modify workflows
3. **Clean version control**: YAML diffs are readable, Python function diffs often aren't
4. **Unified infrastructure**: Built-in workflows (feature, review, validate) use the same system as custom workflows

This democratizes workflow customization - you don't need to be a Python expert.
-->

---

## layout: default

# 12.2 Workflow File Structure

<div class="text-secondary text-sm mb-4">
Anatomy of a Maverick workflow file
</div>

<div class="grid grid-cols-2 gap-6">

<div>

```yaml {all|1|2-3|5-10|12-20|22-23}
version: "1.0"
name: hello-world
description: A simple example workflow

inputs:
  name:
    type: string
    required: true
  greeting:
    type: string
    default: "Hello"

steps:
  - name: format_greeting
    type: python
    action: format_greeting
    args:
      - ${{ inputs.greeting }}
      - ${{ inputs.name }}

outputs:
  message: ${{ steps.format_greeting.output }}
```

</div>

<div>

<div v-click="1" class="p-3 bg-raised rounded-lg border border-border mb-3">
  <div class="text-xs font-mono text-teal">version (required)</div>
  <div class="text-sm mt-1">Schema version - currently <code>"1.0"</code></div>
</div>

<div v-click="2" class="p-3 bg-raised rounded-lg border border-border mb-3">
  <div class="text-xs font-mono text-brass">name & description</div>
  <div class="text-sm mt-1">Workflow identifier and documentation</div>
</div>

<div v-click="3" class="p-3 bg-raised rounded-lg border border-border mb-3">
  <div class="text-xs font-mono text-coral">inputs</div>
  <div class="text-sm mt-1">Parameter declarations with types and defaults</div>
</div>

<div v-click="4" class="p-3 bg-raised rounded-lg border border-border mb-3">
  <div class="text-xs font-mono text-teal">steps</div>
  <div class="text-sm mt-1">Ordered list of workflow operations</div>
</div>

<div v-click="5" class="p-3 bg-raised rounded-lg border border-border">
  <div class="text-xs font-mono text-brass">outputs</div>
  <div class="text-sm mt-1">Named results exposed to callers</div>
</div>

</div>

</div>

<!--
Every workflow file has the same five sections:

1. **version**: Currently "1.0" - this allows future schema evolution without breaking existing workflows

2. **name & description**: The name is used for `maverick fly <name>` and must be unique. Description appears in `maverick workflow list`

3. **inputs**: Declare parameters the workflow accepts. Each input has a type, required flag, and optional default

4. **steps**: The heart of the workflow - an ordered list of operations. Steps can reference inputs and outputs of previous steps

5. **outputs**: Named results that callers can access. Useful when composing workflows via subworkflow steps
-->

---

## layout: default

# 12.3 Input Declarations

<div class="text-secondary text-sm mb-4">
Type-safe parameter definitions
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Supported Types

```yaml
inputs:
  # String input
  branch_name:
    type: string
    required: true
    description: Feature branch name

  # Boolean with default
  dry_run:
    type: boolean
    default: false

  # Integer with constraints
  max_retries:
    type: integer
    default: 3

  # Float for thresholds
  coverage_threshold:
    type: float
    default: 0.8
```

</div>

</div>

<div>

<div v-click>

### All Input Types

| Type      | Python Equivalent | Example        |
| --------- | ----------------- | -------------- |
| `string`  | `str`             | `"main"`       |
| `integer` | `int`             | `42`           |
| `boolean` | `bool`            | `true`         |
| `float`   | `float`           | `0.85`         |
| `object`  | `dict[str, Any]`  | `{key: value}` |
| `array`   | `list[Any]`       | `[1, 2, 3]`    |

</div>

<div v-click class="mt-6">

### Validation Rules

<div class="space-y-2 text-sm">

<div class="p-2 bg-coral/10 border border-coral/30 rounded">
  <strong class="text-coral">Required + Default</strong>
  <div class="text-muted">Cannot combine required=true with a default value</div>
</div>

<div class="p-2 bg-teal/10 border border-teal/30 rounded">
  <strong class="text-teal">Type Coercion</strong>
  <div class="text-muted">Pydantic validates and coerces input values</div>
</div>

</div>

</div>

</div>

</div>

<!--
Input declarations are enforced by Pydantic at workflow load time.

**Six types**: string, integer, boolean, float, object, array
- object maps to Python dict
- array maps to Python list

**Validation rules**:
1. Required inputs MUST be provided - no defaults allowed
2. Optional inputs can have defaults
3. Type coercion is automatic (e.g., "42" → 42 for integer)

**CLI usage**:
```bash
maverick fly feature -i branch_name=my-feature -i dry_run=true
```

Inputs are passed via `-i key=value` pairs and are type-validated before workflow execution.
-->

---

## layout: default

# 12.4 Step Types Overview

<div class="text-secondary text-sm mb-4">
Eight step types for different operations
</div>

<div class="grid grid-cols-4 gap-3">

<div v-click class="p-3 bg-teal/10 border border-teal/30 rounded-lg">
  <div class="text-lg mb-1">🐍</div>
  <div class="font-semibold text-sm">python</div>
  <div class="text-xs text-muted mt-1">Call registered functions</div>
</div>

<div v-click class="p-3 bg-brass/10 border border-brass/30 rounded-lg">
  <div class="text-lg mb-1">🤖</div>
  <div class="font-semibold text-sm">agent</div>
  <div class="text-xs text-muted mt-1">Invoke AI agents</div>
</div>

<div v-click class="p-3 bg-coral/10 border border-coral/30 rounded-lg">
  <div class="text-lg mb-1">✍️</div>
  <div class="font-semibold text-sm">generate</div>
  <div class="text-xs text-muted mt-1">Text generation</div>
</div>

<div v-click class="p-3 bg-teal/10 border border-teal/30 rounded-lg">
  <div class="text-lg mb-1">✅</div>
  <div class="font-semibold text-sm">validate</div>
  <div class="text-xs text-muted mt-1">Run checks with retry</div>
</div>

<div v-click class="p-3 bg-brass/10 border border-brass/30 rounded-lg">
  <div class="text-lg mb-1">🔁</div>
  <div class="font-semibold text-sm">loop</div>
  <div class="text-xs text-muted mt-1">Iterate with concurrency</div>
</div>

<div v-click class="p-3 bg-coral/10 border border-coral/30 rounded-lg">
  <div class="text-lg mb-1">🌿</div>
  <div class="font-semibold text-sm">branch</div>
  <div class="text-xs text-muted mt-1">Conditional execution</div>
</div>

<div v-click class="p-3 bg-teal/10 border border-teal/30 rounded-lg">
  <div class="text-lg mb-1">💾</div>
  <div class="font-semibold text-sm">checkpoint</div>
  <div class="text-xs text-muted mt-1">Resume points</div>
</div>

<div v-click class="p-3 bg-brass/10 border border-brass/30 rounded-lg">
  <div class="text-lg mb-1">📦</div>
  <div class="font-semibold text-sm">subworkflow</div>
  <div class="text-xs text-muted mt-1">Nested workflows</div>
</div>

</div>

<div v-click class="mt-6">

### Common Step Fields

```yaml
- name: step_name # Required: Unique identifier
  type: python # Required: Step type
  when: ${{ condition }} # Optional: Skip if false
  metadata: # Optional: Progress tracking
    progress:
      stage: "validation"
      weight: 10
```

</div>

<!--
Maverick supports eight step types, each for a specific purpose:

**Deterministic steps** (always produce the same output):
- `python`: Call registered Python functions
- `validate`: Run validation with retry logic
- `checkpoint`: Mark resume points

**AI-powered steps** (use Claude agents):
- `agent`: Full agent invocation with tools
- `generate`: Text generation without tools

**Control flow steps**:
- `loop`: Iteration with optional concurrency
- `branch`: Conditional execution
- `subworkflow`: Composition via nested workflows

All steps share common fields: `name`, `type`, optional `when` condition, and `metadata` for progress tracking.
-->

---

## layout: two-cols

# 12.5 Python Steps

<div class="pr-4">

<div v-click>

### Basic Syntax

```yaml
- name: preflight
  type: python
  action: run_preflight_checks
  kwargs:
    check_api: true
    check_git: true
```

</div>

<div v-click class="mt-4">

### With Arguments

```yaml
- name: format_message
  type: python
  action: format_greeting
  args:
    - "Hello"
    - ${{ inputs.name }}
  kwargs:
    uppercase: false
```

</div>

<div v-click class="mt-4">

### With Rollback

```yaml
- name: create_branch
  type: python
  action: git.create_branch
  kwargs:
    branch: ${{ inputs.branch_name }}
  rollback: git.delete_branch
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

### PythonStepRecord Schema

```python
class PythonStepRecord(StepRecord):
    type: Literal[StepType.PYTHON]

    # Registered function name
    action: str

    # Positional arguments
    args: list[Any] = []

    # Keyword arguments
    kwargs: dict[str, Any] = {}

    # Compensation on failure
    rollback: str | None = None
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Action Registration</strong><br>
  Actions must be registered in the <code>ComponentRegistry</code> 
  before workflow execution.
</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Expression Support</strong><br>
  Both <code>args</code> and <code>kwargs</code> can contain 
  <code>${{ }}</code> expressions.
</div>

</div>

<!--
Python steps invoke registered Python functions.

**action**: The function name registered in ComponentRegistry
- Can be a simple name like "run_preflight_checks"
- Or a dotted path like "git.create_branch"

**args vs kwargs**:
- `args` are positional arguments passed in order
- `kwargs` are keyword arguments passed by name

**rollback**: Optional compensation action
- Called if the workflow fails AFTER this step succeeds
- Used for cleanup (e.g., delete branch if later steps fail)

All argument values can use expressions to reference inputs or previous step outputs.
-->

---

## layout: two-cols

# 12.6 Agent Steps

<div class="pr-4">

<div v-click>

### Invoke AI Agents

```yaml
- name: implement_feature
  type: agent
  agent: implementer
  context:
    task_file: ${{ inputs.task_file }}
    branch_name: ${{ inputs.branch_name }}
    phase: ${{ item }}
```

</div>

<div v-click class="mt-4">

### Context Types

```yaml
# Static context dict
context:
  key: value
  nested:
    data: here

# Or reference a context builder
context: build_implementation_context
```

</div>

<div v-click class="mt-4">

### With Rollback

```yaml
- name: code_review
  type: agent
  agent: reviewer
  context: build_review_context
  rollback: cleanup_review_artifacts
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

### AgentStepRecord Schema

```python
class AgentStepRecord(StepRecord):
    type: Literal[StepType.AGENT]

    # Registered agent name
    agent: str

    # Static dict or builder name
    context: dict[str, Any] | str = {}

    # Compensation on failure
    rollback: str | None = None
```

</div>

<div v-click class="mt-4 space-y-3">

<div class="p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Agent vs Generate</strong><br>
  Agent steps have access to MCP tools. Generate steps 
  are for pure text generation without tool use.
</div>

<div class="p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Streaming Output</strong><br>
  Agent steps stream <code>AgentStreamChunk</code> events 
  to the TUI in real-time.
</div>

</div>

</div>

<!--
Agent steps invoke registered MaverickAgent instances.

**agent**: Name of the registered agent
- Built-in: "implementer", "reviewer", "spec_reviewer", "technical_reviewer"
- Custom agents can be registered in the ComponentRegistry

**context**: Data passed to the agent
- Can be a static dictionary with expressions
- Or a string referencing a registered context builder function

Context builders are useful when you need complex logic to assemble the context - they keep the YAML clean while allowing Python logic where needed.

Agent steps emit streaming events, so the TUI shows real-time progress as Claude thinks and acts.
-->

---

## layout: two-cols

# 12.7 Validate Steps

<div class="pr-4">

<div v-click>

### Validation with Retry

```yaml
- name: run_validation
  type: validate
  stages:
    - format
    - lint
    - typecheck
    - test
  retry: 3
```

</div>

<div v-click class="mt-4">

### With On-Failure Handler

```yaml
- name: validate_code
  type: validate
  stages: [lint, test]
  retry: 3
  on_failure:
    name: fix_issues
    type: agent
    agent: fixer
    context:
      errors: ${{ steps.validate_code.errors }}
```

</div>

<div v-click class="mt-4">

### Stage Reference

```yaml
# Reference config key instead of inline
- name: validate
  type: validate
  stages: default_validation_stages
  retry: 2
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

### ValidateStepRecord Schema

```python
class ValidateStepRecord(StepRecord):
    type: Literal[StepType.VALIDATE]

    # Stage list or config key
    stages: list[str] | str

    # Max retry attempts (0 = no retry)
    retry: int = 3  # default

    # Step to run before each retry
    on_failure: StepRecordUnion | None
```

</div>

<div v-click class="mt-4">

### Validation Flow

```
┌─────────────┐
│ Run Stages  │
└──────┬──────┘
       │
   ┌───▼───┐     ┌─────────────┐
   │ Pass? ├─No──► on_failure  │
   └───┬───┘     └──────┬──────┘
       │                │
      Yes          ┌────▼────┐
       │           │ retry > 0│
       ▼           └────┬────┘
    Complete            │
                  Yes───┴───No
                   │        │
              Loop Back   Fail
```

</div>

</div>

<!--
Validate steps run validation stages with automatic retry.

**stages**: List of validation stages to run
- Built-in: "format", "lint", "typecheck", "test"
- Or a config key referencing predefined stages

**retry**: Number of fix attempts
- Default is 3 (from DEFAULTS.DEFAULT_RETRY_ATTEMPTS)
- Set to 0 to disable retry entirely

**on_failure**: Step to run before each retry
- Typically an agent step that tries to fix the issues
- Has access to the validation errors via expressions

This pattern implements "fail-fix-retry" loops that are central to Maverick's autonomous recovery philosophy.
-->

---

## layout: two-cols

# 12.8 Loop Steps

<div class="pr-4">

<div v-click>

### Sequential Iteration

```yaml
- name: process_phases
  type: loop
  for_each: ${{ steps.get_phases.output }}
  steps:
    - name: implement
      type: agent
      agent: implementer
      context:
        phase: ${{ item }}
        index: ${{ index }}
```

</div>

<div v-click class="mt-4">

### Parallel Execution

```yaml
- name: run_reviews
  type: loop
  for_each: ${{ ['spec', 'technical'] }}
  max_concurrency: 2 # Run both in parallel
  steps:
    - name: review
      type: agent
      agent: ${{ item }}_reviewer
```

</div>

<div v-click class="mt-4">

### Unlimited Concurrency

```yaml
- name: process_files
  type: loop
  for_each: ${{ steps.get_files.output }}
  max_concurrency: 0 # Fully parallel
  steps: [...]
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

### LoopStepRecord Schema

```python
class LoopStepRecord(StepRecord):
    type: Literal[StepType.LOOP]

    # Steps for each iteration
    steps: list[StepRecordUnion]

    # List expression to iterate
    for_each: str | None = None

    # Concurrency control
    max_concurrency: int = 1
    # 1 = sequential (default)
    # N = up to N concurrent
    # 0 = unlimited parallel
```

</div>

<div v-click class="mt-4">

### Loop Context Variables

| Variable       | Description                |
| -------------- | -------------------------- |
| `${{ item }}`  | Current iteration value    |
| `${{ index }}` | Zero-based iteration index |

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Note</strong><br>
  Loop steps replaced the old "parallel" step type with 
  clearer semantics and explicit concurrency control.
</div>

</div>

<!--
Loop steps iterate over collections with configurable concurrency.

**for_each**: Expression that evaluates to a list
- Each item becomes available as `${{ item }}`
- The index is available as `${{ index }}`

**max_concurrency**: Controls parallel execution
- `1` (default): Sequential, one at a time
- `N > 1`: Up to N concurrent iterations
- `0`: Fully parallel (all at once)

The loop step replaced the previous "parallel" step type because:
1. "loop" clearly indicates iteration
2. Concurrency is explicit via max_concurrency
3. Sequential iteration (the common case) is the default

Use `max_concurrency: 0` sparingly - it can overwhelm APIs with rate limits.
-->

---

## layout: two-cols

# 12.9 Branch Steps

<div class="pr-4">

<div v-click>

### Conditional Execution

```yaml
- name: decide_action
  type: branch
  options:
    - when: ${{ inputs.dry_run }}
      step:
        name: preview_only
        type: python
        action: show_preview

    - when: ${{ not inputs.skip_review }}
      step:
        name: run_review
        type: agent
        agent: reviewer

    - when: "true" # Default case
      step:
        name: skip_message
        type: python
        action: log_skipped
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

### BranchStepRecord Schema

```python
class BranchStepRecord(StepRecord):
    type: Literal[StepType.BRANCH]

    # Ordered condition → step pairs
    options: list[BranchOptionRecord]

class BranchOptionRecord(BaseModel):
    # Condition expression
    when: str

    # Step to execute if true
    step: StepRecordUnion
```

</div>

<div v-click class="mt-4">

### Evaluation Order

<div class="space-y-2 text-sm">

1. Conditions evaluated **in order**
2. **First** matching condition wins
3. Use `"true"` as catch-all default
4. If no match → step skipped

</div>

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">vs. `when` Field</strong><br>
  Use <code>when</code> on any step for simple skip logic.
  Use <code>branch</code> for multi-way decisions.
</div>

</div>

<!--
Branch steps provide multi-way conditional execution.

**options**: Ordered list of condition → step pairs
- Conditions are evaluated in order
- First true condition's step is executed
- Remaining options are skipped

**Default case**: Use `when: "true"` as the last option for a catch-all

**vs. simple `when` field**:
- Every step can have a `when` field for simple skip conditions
- Branch is for "if/elif/else" style multi-way decisions

Example use cases:
- Different handling for dry_run vs real execution
- Feature flags controlling behavior
- Environment-specific steps (dev vs prod)
-->

---

## layout: two-cols

# 12.10 Checkpoint Steps

<div class="pr-4">

<div v-click>

### Basic Checkpoint

```yaml
- name: after_implementation
  type: checkpoint
```

</div>

<div v-click class="mt-4">

### With Explicit ID

```yaml
- name: checkpoint_phase_1
  type: checkpoint
  checkpoint_id: implementation_complete
```

</div>

<div v-click class="mt-4">

### Workflow with Checkpoints

```yaml
steps:
  - name: init
    type: python
    action: init_workspace

  - name: cp_init
    type: checkpoint

  - name: implement
    type: agent
    agent: implementer

  - name: cp_impl
    type: checkpoint

  - name: validate
    type: validate
    stages: [lint, test]
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

### CheckpointStepRecord Schema

```python
class CheckpointStepRecord(StepRecord):
    type: Literal[StepType.CHECKPOINT]

    # Optional explicit ID
    # Defaults to step name
    checkpoint_id: str | None = None
```

</div>

<div v-click class="mt-4">

### What Gets Saved

<div class="space-y-2 text-sm">

- ✓ Workflow inputs
- ✓ Completed step names
- ✓ Step outputs
- ✓ Current iteration context
- ✗ In-progress agent state

</div>

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Resume Capability</strong><br>
  <code>maverick fly --resume</code> loads the last checkpoint 
  and skips completed steps.
</div>

<div v-click class="mt-3 p-3 bg-coral/10 border border-coral/30 rounded-lg text-sm">
  <strong class="text-coral">Place After Expensive Steps</strong><br>
  Put checkpoints after long-running operations to avoid 
  re-running them on resume.
</div>

</div>

<!--
Checkpoint steps mark workflow state boundaries for resumability.

**When a checkpoint step succeeds**:
1. Workflow state is serialized (inputs, completed steps, outputs)
2. State is saved to the checkpoint store
3. Execution continues

**On resume** (`maverick fly --resume`):
1. Load the most recent checkpoint
2. Skip already-completed steps
3. Continue from where we left off

**checkpoint_id**: Optional explicit identifier
- Defaults to the step name if not provided
- Useful when you have multiple checkpoints with similar names

**Best practice**: Place checkpoints after expensive operations (agent steps, validation loops) to avoid repeating them on failure.
-->

---

## layout: two-cols

# 12.11 Subworkflow Steps

<div class="pr-4">

<div v-click>

### Invoke Another Workflow

```yaml
- name: run_validation
  type: subworkflow
  workflow: validate
  inputs:
    fix: true
    max_attempts: 3
```

</div>

<div v-click class="mt-4">

### Pass Dynamic Inputs

```yaml
- name: review_pr
  type: subworkflow
  workflow: review
  inputs:
    pr_number: ${{ steps.create_pr.output.number }}
    base_branch: ${{ inputs.base_branch }}
```

</div>

<div v-click class="mt-4">

### Access Subworkflow Outputs

```yaml
- name: check_result
  type: branch
  options:
    - when: ${{ steps.review_pr.output.approved }}
      step:
        name: merge
        type: python
        action: merge_pr
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

### SubWorkflowStepRecord Schema

```python
class SubWorkflowStepRecord(StepRecord):
    type: Literal[StepType.SUBWORKFLOW]

    # Workflow name or file path
    workflow: str

    # Input values (may have expressions)
    inputs: dict[str, Any] = {}
```

</div>

<div v-click class="mt-4">

### Resolution Order

1. Project: `.maverick/workflows/`
2. User: `~/.config/maverick/workflows/`
3. Built-in: Packaged with Maverick

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Composition Pattern</strong><br>
  Build complex workflows from smaller, reusable pieces.
  The <code>feature</code> workflow internally uses 
  <code>validate</code> subworkflows.
</div>

</div>

<!--
Subworkflow steps enable workflow composition.

**workflow**: Name of the workflow to invoke
- Resolved using the standard discovery order
- Can be a built-in workflow name or custom workflow

**inputs**: Values passed to the subworkflow
- Must satisfy the subworkflow's input declarations
- Can contain expressions referencing parent workflow context

**Outputs**: The subworkflow's outputs are available as step outputs
- Access via `${{ steps.step_name.output.field }}`

**Use cases**:
- Reusing the validate workflow in multiple parent workflows
- Breaking large workflows into manageable pieces
- Sharing common patterns across projects
-->

---

## layout: default

# 12.12 Expression Syntax

<div class="text-secondary text-sm mb-4">
Dynamic values with <code>${{ }}</code> expressions
</div>

<div class="grid grid-cols-2 gap-6">

<div>

<div v-click>

### Input References

```yaml
# Simple input
${{ inputs.branch_name }}

# With default fallback
${{ inputs.task_file or steps.init.output.path }}
```

</div>

<div v-click class="mt-4">

### Step Output References

```yaml
# Direct output
${{ steps.validate.output }}

# Nested field
${{ steps.gather.output.pr_metadata.title }}

# Array access
${{ steps.get_files.output[0] }}
```

</div>

<div v-click class="mt-4">

### Loop Context

```yaml
# Current item in for_each loop
${{ item }}

# Nested item access
${{ item.filename }}

# Current index (0-based)
${{ index }}
```

</div>

</div>

<div>

<div v-click>

### Boolean Operations

```yaml
# Negation
${{ not inputs.dry_run }}

# Conjunction
${{ inputs.fix and steps.validate.output.failed }}

# Disjunction
${{ inputs.skip_review or inputs.dry_run }}
```

</div>

<div v-click class="mt-4">

### Ternary Expressions

```yaml
# value_if_true if condition else value_if_false
${{ "prod" if inputs.production else "dev" }}

# Complex conditions
${{ steps.review.output if not inputs.skip_review else null }}
```

</div>

<div v-click class="mt-4">

### Template Strings

```yaml
# Mix literals and expressions
description: "Feature branch: ${{ inputs.branch_name }}"

# Multiple expressions
path: "specs/${{ inputs.branch }}/tasks.md"
```

</div>

</div>

</div>

<!--
Expressions are evaluated at runtime using the Lark parser from Section 9.

**Reference types**:
- `inputs.*` - Workflow input parameters
- `steps.*` - Previous step outputs
- `item` / `index` - Loop iteration context

**Access patterns**:
- Dot notation: `inputs.name`, `output.field`
- Bracket notation: `output[0]`, `output["key"]`

**Boolean operators**:
- `not` - Negation
- `and` - Logical AND
- `or` - Logical OR

**Ternary**: `value_if_true if condition else value_if_false`

**Template strings**: Mix literal text with expressions for string building.

The grammar is in `src/maverick/dsl/expressions/grammar.lark`.
-->

---

## layout: two-cols

# 12.13 Workflow Discovery

<div class="pr-4">

<div v-click>

### Three Locations

```
┌─────────────────────────────────┐
│  1. Project (highest priority)  │
│  .maverick/workflows/           │
└───────────────┬─────────────────┘
                │ overrides
┌───────────────▼─────────────────┐
│  2. User                        │
│  ~/.config/maverick/workflows/  │
└───────────────┬─────────────────┘
                │ overrides
┌───────────────▼─────────────────┐
│  3. Built-in (lowest priority)  │
│  maverick/library/workflows/    │
└─────────────────────────────────┘
```

</div>

<div v-click class="mt-4">

### Override Example

```bash
# Copy built-in to customize
cp ~/.local/lib/python3.10/site-packages/\
maverick/library/workflows/feature.yaml \
.maverick/workflows/feature.yaml

# Edit your copy
vim .maverick/workflows/feature.yaml
```

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

### Listing Workflows

```bash
$ maverick workflow list

Built-in workflows:
  feature   - Speckit-based feature development
  review    - Dual-agent code review
  validate  - Validation with optional fixes
  cleanup   - Project cleanup workflow

Project workflows (.maverick/workflows/):
  feature   - Custom feature workflow (overrides)
  deploy    - Project-specific deployment
```

</div>

<div v-click class="mt-4">

### Discovery API

```python
from maverick.dsl.discovery import create_discovery

discovery = create_discovery()
result = discovery.discover()

for wf in result.workflows:
    print(f"{wf.name}: {wf.source}")
    # feature: WorkflowSource.PROJECT
    # review: WorkflowSource.BUILTIN
```

</div>

</div>

<!--
Workflow discovery follows a layered override pattern.

**Priority order** (highest to lowest):
1. **Project**: `.maverick/workflows/` in your repo
2. **User**: `~/.config/maverick/workflows/` for personal workflows
3. **Built-in**: Packaged with Maverick

**Override mechanism**:
- A project workflow with the same name as a built-in workflow takes precedence
- This lets you customize built-in workflows per-project

**Discovery result includes**:
- All discovered workflows with their sources
- Conflicts (same name at same priority level)
- Skipped files (invalid YAML, parse errors)

Use `maverick workflow list` to see what's available and which workflows override others.
-->

---

## layout: default

# 12.14 Putting It Together

<div class="text-secondary text-sm mb-4">
A complete workflow example
</div>

```yaml {all|1-3|5-16|18-25|27-41|43-44}
version: "1.0"
name: quick-fix
description: Fast fix workflow - validate, fix issues, commit

inputs:
  message:
    type: string
    required: false
    default: "fix: resolve validation issues"
    description: Commit message for fixes

  stages:
    type: array
    required: false
    default: [format, lint]
    description: Validation stages to run

steps:
  - name: validate_and_fix
    type: validate
    stages: ${{ inputs.stages }}
    retry: 3
    on_failure:
      name: auto_fix
      type: agent
      agent: fixer
      context:
        errors: ${{ steps.validate_and_fix.errors }}

  - name: commit_fixes
    type: branch
    options:
      - when: ${{ steps.validate_and_fix.output.changes_made }}
        step:
          name: do_commit
          type: python
          action: git.commit
          kwargs:
            message: ${{ inputs.message }}
      - when: "true"
        step:
          name: no_changes
          type: python
          action: log_info
          args: ["No changes needed"]

outputs:
  fixed: ${{ steps.validate_and_fix.output.passed }}
```

<div v-click class="mt-2 text-sm text-muted">
Run with: <code>maverick fly quick-fix -i stages='["format", "lint", "typecheck"]'</code>
</div>

<!--
This workflow demonstrates multiple concepts working together:

1. **Inputs with defaults**: `message` and `stages` both have sensible defaults
2. **Validate step with on_failure**: Automatic fix-retry loop using an AI agent
3. **Branch step**: Conditional commit only if changes were made
4. **Outputs**: Expose the final pass/fail status to callers

**Execution flow**:
1. Run validation stages (format, lint by default)
2. If validation fails, invoke the fixer agent
3. Retry validation (up to 3 times)
4. If changes were made and validation passes, commit
5. If no changes needed, just log and exit

This pattern is reusable across any project!
-->

---

layout: center
class: text-center

---

# Section 12 Complete 🎉

<div class="text-lg text-secondary mt-4">
You've learned Maverick's YAML-based workflow DSL
</div>

<div class="mt-8 grid grid-cols-4 gap-4 max-w-3xl mx-auto text-sm">
  <div class="p-3 bg-teal/10 border border-teal/30 rounded-lg">
    <div class="text-2xl mb-2">📝</div>
    <div class="font-semibold">YAML Structure</div>
    <div class="text-xs text-muted">inputs, steps, outputs</div>
  </div>
  <div class="p-3 bg-brass/10 border border-brass/30 rounded-lg">
    <div class="text-2xl mb-2">🔧</div>
    <div class="font-semibold">8 Step Types</div>
    <div class="text-xs text-muted">python, agent, loop...</div>
  </div>
  <div class="p-3 bg-coral/10 border border-coral/30 rounded-lg">
    <div class="text-2xl mb-2">💫</div>
    <div class="font-semibold">Expressions</div>
    <div class="text-xs text-muted">${{ inputs.x }}</div>
  </div>
  <div class="p-3 bg-teal/10 border border-teal/30 rounded-lg">
    <div class="text-2xl mb-2">🔍</div>
    <div class="font-semibold">Discovery</div>
    <div class="text-xs text-muted">project → user → built-in</div>
  </div>
</div>

<div class="mt-8 text-sm text-muted">
  Next up: <strong>Section 13 - Expression Evaluation Engine</strong>
</div>

<!--
Section 12 recap:

1. **Why YAML**: Declarative, shareable, no Python required
2. **File structure**: version, name, inputs, steps, outputs
3. **Input declarations**: Type-safe parameters with validation
4. **Step types**: python, agent, generate, validate, loop, branch, checkpoint, subworkflow
5. **Expressions**: ${{ inputs.x }}, ${{ steps.y.output }}, ternary, boolean ops
6. **Discovery**: Three-level override system (project → user → built-in)

Next section will dive deep into how expressions are parsed and evaluated using Lark.
-->
