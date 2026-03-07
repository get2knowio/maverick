---
layout: section
class: text-center
---

# 16. The ImplementerAgent

<div class="text-lg text-secondary mt-4">
The primary code-producing agent in the fly workflow
</div>

<div class="mt-8 flex justify-center gap-6 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-teal"></span>
    <span class="text-muted">5 Slides</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-brass"></span>
    <span class="text-muted">Prompt Modes</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-coral"></span>
    <span class="text-muted">Workflow Integration</span>
  </div>
</div>

---
layout: two-cols
---

# 16.1 ImplementerAgent Overview

<div class="pr-4">

The <code>ImplementerAgent</code> is Maverick's primary code-writing agent.

<div class="space-y-2 mt-4 text-sm">
  <div class="flex items-start gap-2"><span class="text-teal mt-1">📝</span><span>reads task context and project conventions</span></div>
  <div class="flex items-start gap-2"><span class="text-teal mt-1">🔧</span><span>writes code and tests through allowed tools</span></div>
  <div class="flex items-start gap-2"><span class="text-teal mt-1">✅</span><span>follows methodical, test-driven guidance</span></div>
  <div class="flex items-start gap-2"><span class="text-teal mt-1">📦</span><span>returns a structured <code>ImplementationResult</code> when needed</span></div>
</div>

</div>

::right::

<div class="pl-4 mt-8 text-sm">

## Responsibility split

| Concern | Owner |
|---------|-------|
| code changes | ImplementerAgent |
| prompt/runtime execution | AcpStepExecutor |
| validation loop | workflow + validation action |
| commit / bead completion | workflow + jj/beads actions |

</div>

---
layout: two-cols
---

# 16.2 ImplementerContext

<div class="pr-4">

```python
class ImplementerContext(BaseModel):
    task_file: Path | None = None
    task_description: str | None = None
    phase_name: str | None = None
    branch: str
    cwd: Path
    skip_validation: bool = False
    dry_run: bool = False
```

</div>

::right::

<div class="pl-4 mt-8 text-sm">

## Supported modes

- <strong>task file</strong> — implement from a <code>tasks.md</code>-style source
- <strong>phase mode</strong> — focus on one named phase
- <strong>single task</strong> — implement from a direct description

</div>

---
layout: two-cols
---

# 16.3 Prompt Construction

<div class="pr-4">

```python
def build_prompt(self, context):
    if context.is_phase_mode:
        return self._build_phase_prompt(...)
    if context.is_single_task:
        return self._build_task_prompt(...)
    return f"Implement tasks from: {context.task_file}"
```

</div>

::right::

<div class="pl-4 mt-8 text-sm">

## Prompt guidance emphasizes

- read <code>CLAUDE.md</code> / repo conventions first
- inspect existing code before changing patterns
- write or update tests
- implement the minimal correct change
- leave validation and commits to the workflow

</div>

---
layout: default
---

# 16.4 Where it fits in FlyBeadsWorkflow

```text
select_bead
  -> implement   (ImplementerAgent via ACP)
  -> sync_deps   (deterministic action)
  -> validate    (deterministic fix/retry loop)
  -> review      (optional reviewer/fixer loop)
  -> commit      (jj + bead bookkeeping)
```

<div class="mt-6 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm text-center">
  The implementer is the creative step in the loop; the rest of the loop is controlled by workflow policy.
</div>

---

# 16.5 Takeaway

<div class="mt-10 p-5 bg-teal/10 border border-teal/30 rounded-xl text-center text-sm">
  The ImplementerAgent is still the workhorse for code generation, but in the current architecture it acts through <strong>typed context + prompt construction</strong>, not a direct embedded SDK client.
</div>
