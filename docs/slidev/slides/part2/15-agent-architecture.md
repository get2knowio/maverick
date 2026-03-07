---
layout: section
class: text-center
---

# 15. Agent Architecture

<div class="text-lg text-secondary mt-4">
AI agents as prompt builders with typed contracts and explicit tool policy
</div>

<div class="mt-8 flex justify-center gap-6 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-teal"></span>
    <span class="text-muted">6 Slides</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-brass"></span>
    <span class="text-muted">Generic Types</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-coral"></span>
    <span class="text-muted">ACP Prompting</span>
  </div>
</div>

---
## layout: two-cols

# 15.1 What is a Maverick Agent?

<div class="pr-4">

## Agents Provide Judgment

Agents know <strong>how</strong> to approach a task.

<div class="space-y-2 mt-3 text-sm">
  <div class="flex items-start gap-2"><span class="text-teal mt-1">✓</span><span>shape prompts from typed context</span></div>
  <div class="flex items-start gap-2"><span class="text-teal mt-1">✓</span><span>declare instructions and allowed tools</span></div>
  <div class="flex items-start gap-2"><span class="text-teal mt-1">✓</span><span>return structured output contracts when needed</span></div>
</div>

<div v-click class="mt-4 p-3 bg-coral/10 border border-coral/30 rounded-lg text-sm">
  <strong class="text-coral">Key principle</strong><br>
  Agents no longer own the live provider conversation. The executor does.
</div>

</div>

::right::

<div class="pl-4 mt-8">

## Current mental model

```mermaid {scale: 0.62}
flowchart TD
    A[Workflow] --> B[Agent class]
    B --> C[build_prompt(context)]
    C --> D[AcpStepExecutor]
    D --> E[ACP subprocess]
    E --> F[ExecutorResult]
```

</div>

---
## layout: two-cols

# 15.2 MaverickAgent Base Class

<div class="pr-4">

```python
class MaverickAgent(ABC, Generic[TContext, TResult]):
    def __init__(
        self,
        name: str,
        instructions: str,
        allowed_tools: list[str],
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        output_model: type[BaseModel] | None = None,
    ) -> None:
        ...
```

</div>

::right::

<div class="pl-4 mt-8">

```python
@abstractmethod
def build_prompt(self, context: TContext) -> str:
    ...
```

<div v-click class="mt-4 text-sm">
  The agent defines role, tool budget, optional output schema, and prompt construction.
</div>

</div>

---
## layout: two-cols

# 15.3 Tool Policy

<div class="pr-4 text-sm">

## Built-in tools include

- <code>Read</code>, <code>Write</code>, <code>Edit</code>
- <code>Bash</code>, <code>Glob</code>, <code>Grep</code>
- <code>WebFetch</code>, <code>WebSearch</code>
- <code>Task</code>, <code>TodoWrite</code>

</div>

::right::

<div class="pl-4 mt-8 text-sm">

## Least privilege still applies

- agents declare their allowed tools up front
- MCP tools are namespaced as <code>mcp__server__tool</code>
- permission mode can further restrict runtime execution

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Validation happens at construction</strong><br>
  Unknown tools are rejected when the agent instance is created.
</div>

</div>

---
## layout: default

# 15.4 Registered Agents

<div class="grid grid-cols-2 gap-4 mt-4 text-sm">
  <div class="p-4 bg-raised rounded-lg border border-border">
    <div><strong>implementer</strong> — implement tasks</div>
    <div><strong>code_reviewer</strong> — general code review</div>
    <div><strong>unified_reviewer</strong> — spec + technical review</div>
    <div><strong>simple_fixer</strong> — fix review findings</div>
  </div>
  <div class="p-4 bg-raised rounded-lg border border-border">
    <div><strong>issue_fixer</strong> — resolve GitHub issues</div>
    <div><strong>validation_fixer</strong> — address validation failures</div>
    <div><strong>decomposer</strong> — split plans into work units</div>
    <div><strong>curator</strong> — reorganize history for <code>land</code></div>
  </div>
</div>

---
## layout: default

# 15.5 Takeaway

<div class="mt-10 p-5 bg-teal/10 border border-teal/30 rounded-xl text-center text-sm">
  In the current architecture, a Maverick agent is primarily a <strong>typed prompt builder</strong> with an explicit tool budget.
  The <strong>AcpStepExecutor</strong> owns the actual execution session.
</div>
