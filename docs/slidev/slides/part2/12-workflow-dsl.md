---
layout: section
class: text-center
---

# 12. Python Workflow Engine

<div class="text-lg text-secondary mt-4">
The current orchestration model built around <code>PythonWorkflow</code>
</div>

<div class="mt-8 flex justify-center gap-6 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-teal"></span>
    <span class="text-muted">6 Slides</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-brass"></span>
    <span class="text-muted">Lifecycle</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-coral"></span>
    <span class="text-muted">Rollbacks & Checkpoints</span>
  </div>
</div>

---
layout: two-cols
---

# 12.1 From YAML DSL to Python Classes

<div class="pr-4">

## Retired Model

```text
workflow.yaml
  -> parse schema
  -> resolve expressions
  -> instantiate step definitions
```

<div v-click class="mt-6">

## Current Model

```python
class FlyBeadsWorkflow(PythonWorkflow):
    async def _run(self, inputs: dict[str, Any]) -> Any:
        ...
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Source of truth</strong><br>
  All live workflows now inherit from <code>src/maverick/workflows/base.py</code>.
</div>

</div>

::right::

<div class="pl-4 mt-8">

## Why Python Workflows?

<div class="space-y-2 text-sm mt-3">
  <div class="flex items-start gap-2"><span class="text-brass mt-1">✓</span><span>One implementation path for orchestration logic</span></div>
  <div class="flex items-start gap-2"><span class="text-brass mt-1">✓</span><span>Direct access to typed config, results, and registry objects</span></div>
  <div class="flex items-start gap-2"><span class="text-brass mt-1">✓</span><span>Simpler debugging than a parallel YAML runtime</span></div>
  <div class="flex items-start gap-2"><span class="text-brass mt-1">✓</span><span>Clear ownership of retries, rollbacks, and checkpoints</span></div>
</div>

</div>

---
layout: two-cols
---

# 12.2 PythonWorkflow Base Class

<div class="pr-4">

```python
class PythonWorkflow(ABC):
    def __init__(
        self,
        *,
        config,
        registry,
        checkpoint_store,
        step_executor,
        workflow_name,
    ):
        ...

    async def execute(self, inputs):
        ...

    @abstractmethod
    async def _run(self, inputs):
        ...
```

</div>

::right::

<div class="pl-4 mt-6">

## What the base class provides

- event emission helpers
- step result tracking
- rollback registration + reverse-order execution
- checkpoint save/load delegation
- per-step config resolution
- final <code>WorkflowResult</code> aggregation

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Template Method</strong><br>
  <code>execute()</code> manages the lifecycle; subclasses implement domain logic in <code>_run()</code>.
</div>

</div>

---
layout: default
---

# 12.3 Execution Flow

```mermaid {scale: 0.72}
flowchart TD
    A[PythonWorkflow.execute(inputs)] --> B[emit WorkflowStarted]
    B --> C[spawn _run_with_cleanup]
    C --> D[self._run(inputs)]
    D --> E[emit StepStarted / StepOutput / StepCompleted]
    E --> F{error?}
    F -->|no| G[aggregate WorkflowResult]
    F -->|yes| H[emit failure + run rollbacks]
    G --> I[emit WorkflowCompleted]
    H --> I
```

<div class="mt-6 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm text-center">
  The workflow streams progress events while work runs in the background; callers consume the event queue in real time.
</div>

---
layout: two-cols
---

# 12.4 Primary Workflows

<div class="pr-4">

| Workflow | Purpose |
|----------|---------|
| `FlyBeadsWorkflow` | bead-driven implementation loop |
| `RefuelSpeckitWorkflow` | create beads from `tasks.md` |
| `RefuelMaverickWorkflow` | create beads from flight plans |
| `GenerateFlightPlanWorkflow` | generate plans from PRDs |

</div>

::right::

<div class="pl-4 mt-8">

## The Fly bead loop

```text
preflight
  -> create_workspace
  -> select_bead
  -> implement
  -> sync_deps
  -> validate
  -> review
  -> commit
  -> checkpoint
```

<div v-click class="mt-4 text-sm text-muted">
  The loop repeats until no ready beads remain or <code>max_beads</code> is reached.
</div>

</div>

---
layout: two-cols
---

# 12.5 Config Resolution, Rollbacks, Checkpoints

<div class="pr-4">

## Per-step config resolution

```python
config = workflow.resolve_step_config(
    "implement",
    StepType.AGENT,
)
```

<div v-click class="mt-4 text-sm text-muted">
  Project config, defaults, and step overrides are merged before execution.
</div>

</div>

::right::

<div class="pl-4 mt-6">

## Recovery primitives

- <code>register_rollback(name, action)</code>
- <code>save_checkpoint(data)</code>
- <code>load_checkpoint()</code>

<div v-click class="mt-4 p-3 bg-coral/10 border border-coral/30 rounded-lg text-sm">
  <strong class="text-coral">Ownership boundary</strong><br>
  Workflows own recovery policy. Agents do not decide when to retry, checkpoint, or roll back.
</div>

</div>

---

# 12.6 Takeaway

<div class="mt-10 grid grid-cols-3 gap-4">
  <div class="p-4 bg-raised rounded-lg border border-border text-sm">
    <div class="font-semibold text-teal">Python-native orchestration</div>
    <div class="text-muted mt-2">Workflow logic now lives in normal Python classes, not a parallel YAML runtime.</div>
  </div>
  <div class="p-4 bg-raised rounded-lg border border-border text-sm">
    <div class="font-semibold text-brass">Typed dependencies</div>
    <div class="text-muted mt-2">Config, registry, checkpoint stores, and executors are injected directly.</div>
  </div>
  <div class="p-4 bg-raised rounded-lg border border-border text-sm">
    <div class="font-semibold text-coral">Recovery built in</div>
    <div class="text-muted mt-2">Events, rollbacks, and checkpoints are first-class workflow features.</div>
  </div>
</div>
