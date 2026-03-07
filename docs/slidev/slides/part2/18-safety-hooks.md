---
layout: section
class: text-center
---

# 18. Runtime Safety Controls

<div class="text-lg text-secondary mt-4">
Defense in depth in the ACP executor and agent runtime
</div>

<div class="mt-8 flex justify-center gap-6 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-coral"></span>
    <span class="text-muted">5 Slides</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-brass"></span>
    <span class="text-muted">Permission Modes</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-teal"></span>
    <span class="text-muted">Circuit Breaking</span>
  </div>
</div>

---
layout: two-cols
---

# 18.1 Defense in Depth

<div class="pr-4 text-sm">

Maverick protects agent execution with multiple layers:

1. agent instructions
2. explicit <code>allowed_tools</code>
3. ACP permission handling
4. circuit breaker limits
5. cwd scoping and structured output validation

</div>

::right::

<div class="pl-4 mt-8">

<div class="p-3 bg-coral/10 border border-coral/30 rounded-lg text-sm">
  <strong class="text-coral">Current architecture note</strong><br>
  Safety is no longer taught as direct Claude SDK hooks inside agents.
  It lives primarily in the ACP client/executor boundary.
</div>

</div>

---
layout: two-cols
---

# 18.2 Permission Modes

<div class="pr-4">

| Mode | Meaning |
|------|---------|
| `auto_approve` | accept tool requests |
| `deny_dangerous` | deny dangerous built-in tools |
| `interactive` | reserved for future support |

</div>

::right::

<div class="pl-4 mt-8 text-sm">

In <code>deny_dangerous</code> mode, Maverick denies:

- <code>Bash</code>
- <code>Write</code>
- <code>Edit</code>
- <code>NotebookEdit</code>

Safe read/search tools remain allowed by default.

</div>

---
layout: two-cols
---

# 18.3 Circuit Breaker

<div class="pr-4">

```python
MAX_SAME_TOOL_CALLS = 15
```

If an ACP session calls the same tool 15 or more times, Maverick aborts the session.

</div>

::right::

<div class="pl-4 mt-8 text-sm">

## Why it matters

- catches stuck tool loops early
- limits wasted tokens and time
- surfaces a clear failure for workflow recovery logic

</div>

---
layout: default
---

# 18.4 Additional Runtime Protections

<div class="grid grid-cols-3 gap-4 mt-4 text-sm">
  <div class="p-4 bg-raised rounded-lg border border-border">
    <div class="font-semibold text-teal">Retry + reconnect</div>
    <div class="text-muted mt-2">Transient ACP failures can reconnect through the executor retry policy.</div>
  </div>
  <div class="p-4 bg-raised rounded-lg border border-border">
    <div class="font-semibold text-brass">Explicit cwd</div>
    <div class="text-muted mt-2">Workflow steps should pass workspace cwd so tools operate in the hidden workspace, not the user repo.</div>
  </div>
  <div class="p-4 bg-raised rounded-lg border border-border">
    <div class="font-semibold text-coral">Output schemas</div>
    <div class="text-muted mt-2">Structured outputs can be validated against Pydantic models before the workflow trusts them.</div>
  </div>
</div>
