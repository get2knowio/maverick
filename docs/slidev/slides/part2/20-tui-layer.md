---
layout: section
class: text-center
---

# 20. The TUI Layer

<div class="text-lg text-secondary mt-4">
Display-only terminal interface for the unified workflow event stream
</div>

<div class="mt-8 flex justify-center gap-6 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-teal"></span>
    <span class="text-muted">5 Slides</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-brass"></span>
    <span class="text-muted">Display-Only</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-coral"></span>
    <span class="text-muted">Streaming-First</span>
  </div>
</div>

---
layout: two-cols
---

# 20.1 TUI Design Philosophy

<div class="pr-4 text-sm">

## Core Principle: Display Only

- render workflow state and progress
- capture user input and navigation
- delegate all work to workflows, executors, and services
- never execute subprocesses or make network calls directly

</div>

::right::

<div class="pl-4 mt-8">

<div class="p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Architectural guardrail</strong><br>
  <code>src/maverick/tui/**</code> must remain free of business logic and side effects.
</div>

</div>

---
layout: two-cols
---

# 20.2 Unified Event Stream

<div class="pr-4">

```text
WorkflowStarted
StepStarted
StepOutput
AgentStreamChunk
StepCompleted
WorkflowCompleted
```

</div>

::right::

<div class="pl-4 mt-8 text-sm">

All step types feed the same stream:

- agent steps stream <code>AgentStreamChunk</code>
- deterministic steps stream <code>StepOutput</code>
- lifecycle events wrap both with started/completed markers

</div>

---
layout: default
---

# 20.3 Streaming-First UX

```
┌────────────────────────────────┐
│ Header / context              │
├────────────────────────────────┤
│ Unified workflow event stream │
│  ▸ step started               │
│  ▸ agent thinking             │
│  ▸ tool activity              │
│  ▸ validation output          │
│  ▸ step completed             │
├────────────────────────────────┤
│ Footer / shortcuts            │
└
```

<div class="mt-6 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm text-center">
  The goal is minimal chrome and maximum visibility into what the workflow is doing right now.
</div>

---
layout: default
---

# 20.4 Operational Notes

<div class="grid grid-cols-3 gap-4 mt-4 text-sm">
  <div class="p-4 bg-raised rounded-lg border border-border">
    <div class="font-semibold text-teal">Common event contract</div>
    <div class="text-muted mt-2">CLI and TUI can both consume the same workflow progress events.</div>
  </div>
  <div class="p-4 bg-raised rounded-lg border border-border">
    <div class="font-semibold text-brass">Buffer discipline</div>
    <div class="text-muted mt-2">The streaming UI uses bounded buffering to avoid unbounded memory growth.</div>
  </div>
  <div class="p-4 bg-raised rounded-lg border border-border">
    <div class="font-semibold text-coral">Debounced rendering</div>
    <div class="text-muted mt-2">Rapid event bursts are coalesced so the UI stays readable and responsive.</div>
  </div>
</div>
