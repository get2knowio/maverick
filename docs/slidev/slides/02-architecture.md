---
layout: section
class: text-center
---

# Part 2: Architecture Overview

Understanding Maverick's Layered Design

<!--
This section covers Maverick's four-layer architecture, project structure, and core constitutional principles. Understanding this architecture is essential for extending Maverick and reasoning about how components interact.
-->

---
layout: default
---

# Four-Layer Architecture

<div class="mt-8">

```mermaid
graph TD
    CLI[CLI/TUI Layer<br/>Click + Textual<br/><small>User interaction & display</small>]
    WF[Workflow Layer<br/>Orchestration<br/><small>FlyWorkflow, RefuelWorkflow, DSL Engine</small>]
    AG[Agent Layer<br/>Claude Agent SDK<br/><small>CodeReviewer, Implementer, Fixer, Generators</small>]
    TL[Tool Layer<br/>MCP Tools<br/><small>GitHub, git, validation, notifications</small>]

    CLI --> WF
    WF --> AG
    AG --> TL

    style CLI fill:#6366f1,stroke:#4f46e5,color:#fff
    style WF fill:#8b5cf6,stroke:#7c3aed,color:#fff
    style AG fill:#06b6d4,stroke:#0891b2,color:#fff
    style TL fill:#10b981,stroke:#059669,color:#fff
```

</div>

<div class="grid grid-cols-4 gap-4 mt-8" v-click>
  <ArchitectureLayer
    title="CLI/TUI"
    description="User interaction and visual feedback"
    color="indigo"
    icon="🖥️"
  />
  <ArchitectureLayer
    title="Workflows"
    description="Task orchestration and sequencing"
    color="purple"
    icon="🔄"
  />
  <ArchitectureLayer
    title="Agents"
    description="AI-powered task execution"
    color="cyan"
    icon="🤖"
  />
  <ArchitectureLayer
    title="Tools"
    description="External system integration"
    color="emerald"
    icon="🛠️"
  />
</div>

<!--
Maverick's architecture follows a strict layered design with clear separation of concerns:

1. CLI/TUI Layer: Handles all user interaction via Click commands and Textual-based UI. No business logic here - only display and input capture.

2. Workflow Layer: Orchestrates multi-step processes. Workflows know WHAT to do and WHEN, coordinating agents and managing state. This layer includes both the legacy FlyWorkflow/RefuelWorkflow and the new DSL-based workflow engine.

3. Agent Layer: Implements HOW tasks are done. Agents interact with Claude via the SDK, using specialized system prompts and tool permissions. Each agent has a specific purpose (code review, implementation, fixing issues, etc.).

4. Tool Layer: Wraps external systems using the MCP protocol. Tools provide a safe, structured interface to GitHub CLI, git operations, validation commands, and notifications.

This separation enables independent testing, parallel development, and clear reasoning about system behavior.
-->

---
layout: default
---

# Project Structure

<div class="grid grid-cols-2 gap-8 mt-4">

<div>

### Core Modules

<div class="space-y-2 mt-4">
  <div v-click class="flex items-start gap-2">
    <code class="text-purple-400">agents/</code>
    <span class="text-sm text-slate-400">Agent implementations</span>
  </div>
  <div v-click class="flex items-start gap-2">
    <code class="text-purple-400">workflows/</code>
    <span class="text-sm text-slate-400">Legacy workflow orchestration</span>
  </div>
  <div v-click class="flex items-start gap-2">
    <code class="text-purple-400">dsl/</code>
    <span class="text-sm text-slate-400">Workflow DSL engine</span>
  </div>
  <div v-click class="flex items-start gap-2">
    <code class="text-purple-400">tools/</code>
    <span class="text-sm text-slate-400">MCP tool definitions</span>
  </div>
  <div v-click class="flex items-start gap-2">
    <code class="text-purple-400">tui/</code>
    <span class="text-sm text-slate-400">Textual application</span>
  </div>
  <div v-click class="flex items-start gap-2">
    <code class="text-purple-400">library/</code>
    <span class="text-sm text-slate-400">Built-in components</span>
  </div>
</div>

</div>

<div>

### Supporting Infrastructure

<div class="space-y-2 mt-4">
  <div v-click class="flex items-start gap-2">
    <code class="text-cyan-400">hooks/</code>
    <span class="text-sm text-slate-400">Safety & logging hooks</span>
  </div>
  <div v-click class="flex items-start gap-2">
    <code class="text-cyan-400">runners/</code>
    <span class="text-sm text-slate-400">External command execution</span>
  </div>
  <div v-click class="flex items-start gap-2">
    <code class="text-cyan-400">models/</code>
    <span class="text-sm text-slate-400">Pydantic data models</span>
  </div>
  <div v-click class="flex items-start gap-2">
    <code class="text-cyan-400">utils/</code>
    <span class="text-sm text-slate-400">Shared utilities</span>
  </div>
  <div v-click class="flex items-start gap-2">
    <code class="text-cyan-400">cli/</code>
    <span class="text-sm text-slate-400">CLI helpers & validators</span>
  </div>
</div>

</div>

</div>

<div class="mt-8" v-click>

### Entry Points

```python
src/maverick/
├── main.py              # CLI entry point (Click commands)
├── config.py            # Pydantic configuration models
└── exceptions.py        # Custom exception hierarchy (MaverickError base)
```

</div>

<!--
The project structure reflects the architectural layers:

agents/ contains all agent implementations:
- base.py: MaverickAgent abstract base class
- Concrete agents: code_reviewer, implementer, fixer, issue_fixer
- generators/: Template generators for PR bodies, commit messages, etc.
- Shared utilities for context building and result extraction

workflows/ contains legacy workflow implementations:
- base.py: Base workflow class
- fly.py: Full spec-based development workflow
- refuel.py: Tech-debt resolution workflow
- validation.py: Validation-only workflow

dsl/ is the new workflow DSL engine:
- engine.py: Core execution engine
- steps/: Step types (agent, generate, parallel, conditional, etc.)
- checkpoint/: State persistence for resumption
- serialization/: YAML workflow loading
- visualization/: Workflow graph rendering

tools/ contains MCP tool wrappers:
- github.py: PR and issue management
- git.py: Branch, commit, and sync operations
- validation.py: Format, lint, build, test
- notification.py: Push notifications via ntfy

tui/ contains the Textual application:
- app.py: Main app and router
- screens/: All screen implementations
- widgets/: Reusable UI components

library/ contains built-in reusable components:
- workflows/: Pre-built workflow templates
- agents/: Configurable agent templates
- actions/: Reusable workflow actions
- fragments/: Composable workflow fragments

The separation enables parallel development, clear dependencies, and easy testing.
-->

---
layout: center
class: text-center
---

# The Constitution

8 Core Principles Governing Maverick Development

<div class="text-slate-400 text-sm mt-2">
Source: <code>.specify/memory/constitution.md</code>
</div>

<!--
Maverick is governed by a formal constitution that defines core principles, technology choices, and code conventions. These principles are non-negotiable and supersede all other practices. Let's examine each principle.
-->

---
layout: default
---

# Core Principles (1/2)

<div class="grid grid-cols-2 gap-4 mt-6">

<div class="space-y-4">
  <PrincipleCard
    number="1"
    title="Async-First"
    description="All agent interactions and workflows MUST be async. No threading for I/O operations."
    color="indigo"
    v-click
  >
    <div class="mt-2 text-xs text-slate-500">
      <code>asyncio</code> patterns • Async generators for progress • Responsive TUI
    </div>
  </PrincipleCard>

  <PrincipleCard
    number="2"
    title="Separation of Concerns"
    description="Components have distinct, non-overlapping responsibilities."
    color="purple"
    v-click
  >
    <div class="mt-2 text-xs text-slate-500">
      Agents: HOW • Workflows: WHAT/WHEN • TUI: Display • Tools: External systems
    </div>
  </PrincipleCard>

  <PrincipleCard
    number="3"
    title="Dependency Injection"
    description="Agents and workflows receive configuration and dependencies, not global state."
    color="cyan"
    v-click
  >
    <div class="mt-2 text-xs text-slate-500">
      No module-level mutable state • Inject tool servers • Testable with mocks
    </div>
  </PrincipleCard>

  <PrincipleCard
    number="4"
    title="Fail Gracefully, Recover Aggressively"
    description="One agent/issue failing MUST NOT crash the entire workflow."
    color="emerald"
    v-click
  >
    <div class="mt-2 text-xs text-slate-500">
      Retry with backoff • Aggregate partial results • Forward progress prioritized
    </div>
  </PrincipleCard>
</div>

<div class="space-y-4">
  <PrincipleCard
    number="5"
    title="Test-First"
    description="Every public class and function MUST have tests. TDD is mandatory."
    color="amber"
    v-click
  >
    <div class="mt-2 text-xs text-slate-500">
      pytest + pytest-asyncio • Mock external deps • Red-Green-Refactor
    </div>
  </PrincipleCard>

  <PrincipleCard
    number="6"
    title="Type Safety"
    description="Complete type hints required. Use Pydantic BaseModel or @dataclass."
    color="rose"
    v-click
  >
    <div class="mt-2 text-xs text-slate-500">
      All public functions typed • Protocol for interfaces • frozen/slots dataclasses
    </div>
  </PrincipleCard>

  <PrincipleCard
    number="7"
    title="Simplicity"
    description="No over-engineering. Start simple, add complexity only when justified."
    color="blue"
    v-click
  >
    <div class="mt-2 text-xs text-slate-500">
      No global state • No god-classes • No premature abstraction • YAGNI
    </div>
  </PrincipleCard>

  <PrincipleCard
    number="8"
    title="Relentless Progress"
    description="Forward progress at all costs during unattended operation."
    color="teal"
    v-click
  >
    <div class="mt-2 text-xs text-slate-500">
      Checkpoint state • Exhaust recovery options • Never give up silently
    </div>
  </PrincipleCard>
</div>

</div>

<!--
These eight principles form the foundation of Maverick's design:

Principle 1 - Async-First: Everything is async to maintain TUI responsiveness during long-running agent operations. Workflows yield progress updates as async generators, enabling real-time display without blocking the event loop.

Principle 2 - Separation of Concerns: Clear boundaries between layers. Agents know HOW (system prompts, tools, SDK usage), Workflows know WHAT and WHEN (orchestration, sequencing), TUI handles display only, and Tools wrap external systems. No business logic in the TUI. Agents don't orchestrate themselves.

Principle 3 - Dependency Injection: All dependencies are explicit and injected at construction time. MCP tool servers, configuration objects, and external service clients are passed in, not created internally. This enables testing with mocks and makes dependencies visible.

Principle 4 - Fail Gracefully, Recover Aggressively: Parallel agent execution means partial success is valuable. Retry operations with exponential backoff. Continue processing remaining work when some items fail. Aggregate partial results rather than discarding successful work. The enhanced version adds "Recover Aggressively" to emphasize forward progress.

Principle 5 - Test-First: TDD is mandatory, not optional. Write tests before implementation (Red-Green-Refactor). Use pytest fixtures for common setup. Mock external dependencies. TUI tests use Textual's pilot fixture. All async tests marked with pytest.mark.asyncio.

Principle 6 - Type Safety: Complete type annotations on all public functions. Use TypeAlias for complex types. Prefer @dataclass or Pydantic BaseModel over plain dicts. Use Protocol for duck-typed interfaces. Use frozen=True for immutable value objects and slots=True for frequently instantiated objects.

Principle 7 - Simplicity: YAGNI - You Aren't Gonna Need It. No global mutable state. No god-classes; prefer composition. No hardcoded paths; use pathlib and config. No premature abstractions; three similar lines are better than a bad abstraction. Simple code is easier to understand, test, and maintain.

Principle 8 - Relentless Progress: NEW in v1.1.0. The paramount principle for autonomous operation. Never give up silently - exhaust all recovery options. Checkpoint state after significant operations for resumption. Degrade gracefully to slower but reliable alternatives. Isolate failures so one task doesn't block others. Preserve partial work by committing before risky operations. This principle enables Maverick to operate unattended for extended periods without human intervention.
-->

---
layout: default
---

# Relentless Progress in Action

<div class="mt-6">

The recovery hierarchy for autonomous operation:

<FlowDiagram
  direction="vertical"
  :steps="[
    { name: '1. Retry with backoff', class: 'bg-emerald-600 text-white' },
    { name: '2. Try alternative approach', class: 'bg-cyan-600 text-white' },
    { name: '3. Skip & continue remaining work', class: 'bg-amber-600 text-white' },
    { name: '4. Checkpoint & surface error', class: 'bg-rose-600 text-white' }
  ]"
/>

</div>

<div class="mt-8 grid grid-cols-2 gap-6">

<div v-click>

### Checkpoint Examples

```python
# After each task completion
workflow.checkpoint({
  "completed": ["task-1", "task-2"],
  "in_progress": "task-3",
  "remaining": ["task-4", "task-5"]
})
```

</div>

<div v-click>

### Recovery Examples

```python
# Retry with exponential backoff
for attempt in range(3):
    try:
        return await operation()
    except TransientError:
        await asyncio.sleep(2 ** attempt)

# Fall back to alternative
try:
    return await fast_path()
except FastPathError:
    return await reliable_fallback()
```

</div>

</div>

<!--
Principle 8 - Relentless Progress - is the newest and most critical principle for autonomous operation.

The recovery hierarchy defines the order of preference when operations fail:

1. Retry the exact operation with exponential backoff (default: 3 attempts). This handles transient failures like network issues or API rate limits.

2. Try an alternative approach to achieve the same goal. For example, if the CodeRabbit CLI fails, fall back to architectural review only.

3. Skip the failing component and continue with remaining work. Isolate failures so one task doesn't block others. Aggregate partial results.

4. Checkpoint state and surface an actionable error for user intervention. This is the last resort when all recovery options are exhausted.

Checkpoints are critical for resumption. After each significant operation, persist enough state to allow manual or automatic retry. This includes completed tasks, in-progress work, and remaining items.

Examples show practical implementation:
- Checkpoint after each task with structured state
- Retry with exponential backoff for transient errors
- Fallback from fast path to reliable alternative

This principle enables Maverick to operate unattended for hours or days, recovering from transient failures without human intervention. It's the key to autonomous agent orchestration.
-->
