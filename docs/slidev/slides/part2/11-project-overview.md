---
layout: section
class: text-center
---

# 11. Project Overview & Philosophy

<div class="text-lg text-secondary mt-4">
Understanding Maverick's design principles
</div>

<div class="mt-8 flex justify-center gap-6 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-teal"></span>
    <span class="text-muted">8 Slides</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-brass"></span>
    <span class="text-muted">Architecture</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-coral"></span>
    <span class="text-muted">Principles</span>
  </div>
</div>

<!--
Section 11 introduces Maverick - what it is, why it exists, and the core
principles that guide its design.

We'll cover:
1. What is Maverick?
2. The problem we solve
3. Architecture overview
4. Separation of concerns
5. Core principles (async-first, dependency injection, fail gracefully)
6. Full ownership standard
7. Project structure tour
8. Key configuration files
-->

---

## layout: two-cols

# 11.1 What is Maverick?

<div class="pr-4">

<div v-click>

## AI-Powered Workflow Orchestration

A Python CLI/TUI application that orchestrates **autonomous AI agents** to automate the development lifecycle.

</div>

<div v-click class="mt-4">

## Key Differentiators

<div class="space-y-2 mt-2">
  <div class="flex items-start gap-2">
    <span class="text-brass mt-1">●</span>
    <div>
      <span class="font-semibold">Autonomous Agents</span>
      <p class="text-sm text-muted">AI makes decisions and recovers from failures</p>
    </div>
  </div>
  <div class="flex items-start gap-2">
    <span class="text-teal mt-1">●</span>
    <div>
      <span class="font-semibold">YAML-Based DSL</span>
      <p class="text-sm text-muted">Declarative, shareable workflow definitions</p>
    </div>
  </div>
  <div class="flex items-start gap-2">
    <span class="text-coral mt-1">●</span>
    <div>
      <span class="font-semibold">Unified Architecture</span>
      <p class="text-sm text-muted">All workflows are discoverable YAML files</p>
    </div>
  </div>
</div>

</div>

</div>

::right::

<div class="pl-4">

<div v-click class="mt-12">

## Built With

```yaml
# Technology Stack
language: Python 3.10+
architecture: Async-First
ai_sdk: claude-agent-sdk
cli: Click
tui: Textual
validation: Pydantic
```

</div>

<div v-click class="mt-6">

## Primary Interface

```bash
# Execute a workflow
maverick fly feature -i branch_name=my-feature

# List available workflows
maverick workflow list

# Interactive TUI mode
maverick fly feature --tui
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg">
  <div class="text-xs font-mono text-teal">Tagline</div>
  <div class="text-sm mt-1 italic">"Autonomous Agents for the Modern Developer"</div>
</div>

</div>

<!--
Maverick is an AI-powered development workflow orchestration system.

What makes it unique:
1. **Autonomous agents** - Unlike scripted automation, AI agents make decisions, handle edge cases, and recover from failures independently.

2. **YAML-based DSL** - Workflows are defined declaratively in YAML, making them:
   - Shareable across teams
   - Version-controllable
   - Customizable without Python knowledge

3. **Unified architecture** - Everything is a workflow. Built-in workflows and custom workflows use the same infrastructure.

The primary interface is the `maverick fly` command which executes workflows.
-->

---

## layout: default

# 11.2 The Problem We Solve

<div class="grid grid-cols-2 gap-6 mt-6">

<div v-click>

## ❌ Traditional Automation

<div class="mt-4 space-y-3">

<div class="p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
  <div class="font-semibold text-red-400">Brittle Scripts</div>
  <p class="text-sm text-muted mt-1">Break on unexpected input, no recovery</p>
</div>

<div class="p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
  <div class="font-semibold text-red-400">Manual Intervention</div>
  <p class="text-sm text-muted mt-1">Humans fix errors, run next step</p>
</div>

<div class="p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
  <div class="font-semibold text-red-400">Hard-Coded Logic</div>
  <p class="text-sm text-muted mt-1">Can't handle novel situations</p>
</div>

<div class="p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
  <div class="font-semibold text-red-400">Inconsistent Quality</div>
  <p class="text-sm text-muted mt-1">Results vary by developer experience</p>
</div>

</div>

</div>

<div v-click>

## ✅ Maverick's Approach

<div class="mt-4 space-y-3">

<div class="p-3 bg-teal/10 border border-teal/30 rounded-lg">
  <div class="font-semibold text-teal">Autonomous Recovery</div>
  <p class="text-sm text-muted mt-1">AI agents retry, adapt, and fix issues</p>
</div>

<div class="p-3 bg-teal/10 border border-teal/30 rounded-lg">
  <div class="font-semibold text-teal">End-to-End Automation</div>
  <p class="text-sm text-muted mt-1">Task → Code → Review → PR, hands-free</p>
</div>

<div class="p-3 bg-teal/10 border border-teal/30 rounded-lg">
  <div class="font-semibold text-teal">Intelligent Judgment</div>
  <p class="text-sm text-muted mt-1">Claude reasons about unforeseen problems</p>
</div>

<div class="p-3 bg-teal/10 border border-teal/30 rounded-lg">
  <div class="font-semibold text-teal">Consistent Standards</div>
  <p class="text-sm text-muted mt-1">Same quality every time, enforced by agents</p>
</div>

</div>

</div>

</div>

<div v-click class="mt-6 p-4 bg-brass/10 border border-brass/30 rounded-lg">
  <div class="text-center">
    <span class="text-brass font-semibold">The Vision:</span> 
    <span class="text-muted">From task definition to merged PR with minimal human intervention</span>
  </div>
</div>

<!--
Traditional automation tools have fundamental limitations:

1. **Brittle Scripts**: Shell scripts and CI/CD pipelines break when they encounter unexpected input. No recovery mechanism.

2. **Manual Intervention**: When something fails, a human has to debug, fix, and restart. Overnight runs become morning headaches.

3. **Hard-Coded Logic**: Traditional automation can't handle situations the author didn't anticipate.

4. **Inconsistent Quality**: Code review quality varies by reviewer. Junior devs miss things seniors would catch.

Maverick's approach uses AI agents that:
- Automatically retry and recover from failures
- Run the entire development lifecycle end-to-end
- Apply judgment to novel situations
- Enforce consistent quality standards every time
-->

---

## layout: default

# 11.3 Architecture Overview

<div class="mt-4">

```
┌──────────────────────────────────────────────────────────────────────────┐
│  CLI Layer (Click)                                                        │
│  maverick fly │ workflow │ config │ status │ review                       │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     ↓
┌──────────────────────────────────────────────────────────────────────────┐
│  Workflow DSL Layer                                                       │
│  YAML parsing │ Step execution │ Checkpointing │ Expression evaluation    │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     ↓
┌──────────────────────────────────────────────────────────────────────────┐
│  Agent Layer (Claude Agent SDK)                                           │
│  ImplementerAgent │ CodeReviewerAgent │ FixerAgent │ Generators           │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     ↓
┌──────────────────────────────────────────────────────────────────────────┐
│  Tool Layer (MCP)                                                         │
│  Git operations │ GitHub API │ Validation runners │ Notifications         │
└──────────────────────────────────────────────────────────────────────────┘
```

</div>

<div class="grid grid-cols-4 gap-3 mt-6">
  <div v-click class="p-3 rounded-lg bg-indigo-500/20 border border-indigo-500/50 text-center">
    <div class="text-2xl">🖥️</div>
    <div class="text-xs font-semibold mt-1">CLI</div>
    <div class="text-xs text-muted">User Interface</div>
  </div>
  <div v-click class="p-3 rounded-lg bg-purple-500/20 border border-purple-500/50 text-center">
    <div class="text-2xl">📝</div>
    <div class="text-xs font-semibold mt-1">Workflows</div>
    <div class="text-xs text-muted">Orchestration</div>
  </div>
  <div v-click class="p-3 rounded-lg bg-teal/20 border border-teal/50 text-center">
    <div class="text-2xl">🤖</div>
    <div class="text-xs font-semibold mt-1">Agents</div>
    <div class="text-xs text-muted">AI Judgment</div>
  </div>
  <div v-click class="p-3 rounded-lg bg-brass/20 border border-brass/50 text-center">
    <div class="text-2xl">🔧</div>
    <div class="text-xs font-semibold mt-1">Tools</div>
    <div class="text-xs text-muted">Side Effects</div>
  </div>
</div>

<!--
Maverick's architecture is organized into four distinct layers:

1. **CLI Layer (Click)**: User-facing commands. `maverick fly` executes workflows, `maverick workflow` manages them, `maverick config` handles configuration.

2. **Workflow DSL Layer**: The orchestration engine. Parses YAML workflow definitions, executes steps in sequence or parallel, handles checkpointing for resumption.

3. **Agent Layer (Claude Agent SDK)**: The AI brains. Each agent has a specific role - ImplementerAgent writes code, CodeReviewerAgent reviews it, FixerAgent corrects issues.

4. **Tool Layer (MCP)**: External integrations. Git operations, GitHub API calls, validation command execution. This is where side effects happen.

Information flows DOWN through these layers. The CLI invokes workflows, workflows invoke agents, agents use tools.
-->

---

## layout: two-cols

# 11.4 Separation of Concerns

<div class="pr-4">

Each layer has a **single responsibility**:

<div v-click class="mt-4">

## Agents: **HOW**

<div class="p-3 bg-teal/10 border border-teal/30 rounded-lg mt-2">

- System prompts define behavior
- Tool selection based on task
- Claude SDK interaction
- **Provide judgment only**
- No deterministic side effects!

```python
# Agent returns what to do, not does it
result = await agent.execute(task)
# result.recommendation, not result.commit()
```

</div>

</div>

<div v-click class="mt-4">

## Workflows: **WHAT & WHEN**

<div class="p-3 bg-purple-500/10 border border-purple-500/30 rounded-lg mt-2">

- Orchestration and sequencing
- State management
- Error recovery policies
- **Own all side effects**

```yaml
# Workflow owns the commit action
- name: commit_changes
  type: python
  action: git.commit
  args: [${{ steps.implement.output }}]
```

</div>

</div>

</div>

::right::

<div class="pl-4 mt-8">

<div v-click>

## TUI: **Display Only**

<div class="p-3 bg-coral/10 border border-coral/30 rounded-lg mt-2">

- Present state to user
- Capture user input
- **No business logic**
- No subprocess execution!

```python
# TUI renders what workflows report
self.update_status(event.message)
# Never: subprocess.run(...)
```

</div>

</div>

<div v-click class="mt-4">

## Tools: **External Systems**

<div class="p-3 bg-brass/10 border border-brass/30 rounded-lg mt-2">

- Wrap external APIs
- Delegate to runners
- **Stateless operations**

```python
@tool
async def git_commit(message: str) -> str:
    """Commit staged changes."""
    return await runner.execute(
        ["git", "commit", "-m", message]
    )
```

</div>

</div>

</div>

<!--
The separation of concerns is critical to Maverick's maintainability:

**Agents (HOW)**: Know how to perform a task. They contain system prompts, tool selection logic, and Claude SDK interaction. Critically, agents provide JUDGMENT ONLY - they recommend actions but don't execute them directly.

**Workflows (WHAT & WHEN)**: Know what needs to be done and when. They orchestrate the sequence of operations, manage state, handle checkpointing, and OWN all deterministic side effects like git commits and file writes.

**TUI (Display Only)**: The terminal UI is PURELY for display. It renders state and captures input, but contains NO business logic. It never runs subprocesses or makes API calls.

**Tools (External Systems)**: Wrappers around external systems (git, GitHub, validation commands). They delegate actual execution to runners and remain stateless.

This separation ensures each component can be tested, modified, and debugged independently.
-->

---

## layout: default

# 11.5 Core Principles

<div class="grid grid-cols-2 gap-4 mt-4">

<div v-click>
<PrincipleCard number="1" title="Async-First" color="teal">

All agent interactions and workflows MUST be async.

```python
# ✅ Correct
async def execute_step(step: Step) -> Result:
    return await agent.run(step.prompt)

# ❌ Never do this
subprocess.run(["git", "push"])  # Blocks!
```

Use `asyncio.to_thread()` for blocking operations.

</PrincipleCard>
</div>

<div v-click>
<PrincipleCard number="2" title="Dependency Injection" color="purple">

No global state. Pass dependencies explicitly.

```python
# ✅ Correct - injected
class Workflow:
    def __init__(self, config: Config, repo: GitRepo):
        self.config = config
        self.repo = repo

# ❌ Never - global state
from maverick import GLOBAL_CONFIG  # Bad!
```

</PrincipleCard>
</div>

<div v-click>
<PrincipleCard number="3" title="Fail Gracefully" color="coral">

One failure MUST NOT crash the whole workflow.

```python
for issue in issues:
    try:
        await process_issue(issue)
    except IssueError as e:
        logger.error("issue_failed", issue=issue.id)
        continue  # Don't stop!
```

Retry with exponential backoff (default: 3 attempts).

</PrincipleCard>
</div>

<div v-click>
<PrincipleCard number="4" title="Type Safety" color="amber">

Complete type hints required everywhere.

```python
# ✅ Typed contracts
@dataclass(frozen=True)
class StepResult:
    output: str
    context: WorkflowContext
    duration_ms: int
```

No `dict[str, Any]` blobs in public APIs.

</PrincipleCard>
</div>

</div>

<!--
Maverick is built on four non-negotiable principles:

1. **Async-First**: Every agent interaction, every workflow step, every I/O operation must be async. Never call `subprocess.run()` from an async function - use `asyncio.to_thread()` or async runners.

2. **Dependency Injection**: No global state. Configuration, repositories, clients - everything is passed explicitly at construction time. This makes testing trivial and behavior predictable.

3. **Fail Gracefully, Recover Aggressively**: A single failing issue must not crash a batch job. Capture errors with context, retry with exponential backoff, continue processing other items.

4. **Type Safety**: Complete type hints on all public functions. Use frozen dataclasses or Pydantic models, never ad-hoc dictionaries. This enables IDE support and catches bugs at development time.
-->

---

## layout: default

# 11.6 Full Ownership Standard

<div class="text-secondary text-sm mb-4">
The default stance is <span class="text-brass font-semibold">complete ownership</span> of repository state
</div>

<div class="grid grid-cols-2 gap-6">

<div v-click>

## The Rules

<div class="space-y-3 mt-4">

<div class="p-3 bg-teal/10 border-l-4 border-teal rounded">
  <div class="font-semibold">Do what you're asked, then keep going</div>
  <p class="text-sm text-muted mt-1">Complete changes end-to-end, fix collateral issues you find along the way</p>
</div>

<div class="p-3 bg-teal/10 border-l-4 border-teal rounded">
  <div class="font-semibold">Fix what you find</div>
  <p class="text-sm text-muted mt-1">Broken tests, lint errors, flaky behavior - fix them even if they predate your changes</p>
</div>

<div class="p-3 bg-teal/10 border-l-4 border-teal rounded">
  <div class="font-semibold">Keep the tree green</div>
  <p class="text-sm text-muted mt-1">"Not my problem" is not acceptable. If the repo is failing, the task is not done</p>
</div>

<div class="p-3 bg-teal/10 border-l-4 border-teal rounded">
  <div class="font-semibold">No artificial scope minimization</div>
  <p class="text-sm text-muted mt-1">We prefer complete solutions over narrow patches</p>
</div>

</div>

</div>

<div v-click>

## Anti-Patterns

<div class="space-y-3 mt-4">

<div class="p-3 bg-red-500/10 border-l-4 border-red-500 rounded">
  <div class="font-semibold text-red-400">❌ "That's not related to my change"</div>
  <p class="text-sm text-muted mt-1">If you touched it, you own it</p>
</div>

<div class="p-3 bg-red-500/10 border-l-4 border-red-500 rounded">
  <div class="font-semibold text-red-400">❌ "The test was already failing"</div>
  <p class="text-sm text-muted mt-1">Fix it anyway</p>
</div>

<div class="p-3 bg-red-500/10 border-l-4 border-red-500 rounded">
  <div class="font-semibold text-red-400">❌ "That's too hard to fix right now"</div>
  <p class="text-sm text-muted mt-1">Break it down and make progress</p>
</div>

<div class="p-3 bg-red-500/10 border-l-4 border-red-500 rounded">
  <div class="font-semibold text-red-400">❌ "I'll create an issue for later"</div>
  <p class="text-sm text-muted mt-1">Only defer when truly blocked</p>
</div>

</div>

</div>

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-center">
  <span class="text-brass font-semibold">Philosophy:</span>
  <span class="text-muted">Leave the codebase better than you found it</span>
</div>

<!--
The "Full Ownership Standard" is Maverick's operating philosophy - it applies to both the AI agents AND human contributors.

Key principles:
1. **Complete the task, then keep going**: Don't stop at the minimum. Fix related issues you encounter.

2. **Fix what you find**: Pre-existing bugs, flaky tests, lint warnings - if you see them, fix them.

3. **Keep the tree green**: Never leave the repository in a broken state. If tests fail, your task isn't done.

4. **No artificial minimization**: "Out of scope" is usually an excuse. Break large problems into smaller ones and make real progress.

Anti-patterns to avoid:
- Blaming pre-existing issues
- Deferring everything to "tech debt"
- Stopping at narrow patches when a complete solution is achievable

This philosophy ensures code quality improves over time, not degrades.
-->

---

## layout: default

# 11.7 Project Structure Tour

<div class="grid grid-cols-2 gap-6 mt-4">

<div>

```
src/maverick/
├── cli/                 # Click CLI layer
│   └── commands/        # fly, workflow, config...
├── dsl/                 # Workflow DSL engine
│   ├── serialization/   # YAML parsing, schema
│   ├── discovery/       # Workflow discovery
│   ├── steps/           # Step implementations
│   └── expressions/     # Expression parser
├── agents/              # AI agent implementations
│   ├── code_reviewer.py
│   ├── implementer.py
│   ├── fixer.py
│   └── generators/      # Text generators
├── library/             # Built-in content
│   ├── workflows/       # YAML definitions
│   ├── actions/         # Python actions
│   └── fragments/       # Reusable pieces
├── tools/               # MCP tools
│   ├── github/
│   └── git/
├── tui/                 # Textual TUI
│   ├── screens/
│   └── widgets/
└── runners/             # Subprocess execution
```

</div>

<div>

<div v-click class="mb-4">

### cli/ - Command Line Interface

<div class="text-sm text-muted">
Click-based commands. Thin layer that validates input and delegates to workflows.
</div>

</div>

<div v-click class="mb-4">

### dsl/ - Domain Specific Language

<div class="text-sm text-muted">
The workflow engine. Parses YAML, evaluates expressions, executes steps, manages checkpoints.
</div>

</div>

<div v-click class="mb-4">

### agents/ - AI Agents

<div class="text-sm text-muted">
Agent implementations with system prompts and tool configurations. Each agent has a specific role.
</div>

</div>

<div v-click class="mb-4">

### library/ - Built-in Workflows

<div class="text-sm text-muted">
Packaged workflows like `feature`, `cleanup`, `review`. Discoverable and overridable.
</div>

</div>

<div v-click class="mb-4">

### tools/ - MCP Tools

<div class="text-sm text-muted">
Tool definitions for Claude SDK. Git operations, GitHub API, validation commands.
</div>

</div>

<div v-click>

### tui/ - Terminal UI

<div class="text-sm text-muted">
Textual application for real-time workflow monitoring. Display only - no business logic.
</div>

</div>

</div>

</div>

<!--
Let's walk through Maverick's project structure:

**cli/** - The Click-based command line interface. Commands like `fly`, `workflow`, `config`. This layer is intentionally thin - it validates input and delegates to workflows.

**dsl/** - The workflow domain-specific language engine. This is the heart of Maverick:
- `serialization/` - YAML parsing and schema validation
- `discovery/` - Finding workflows from project/user/built-in locations
- `steps/` - Step type implementations (python, agent, validate, parallel)
- `expressions/` - The `${{ inputs.x }}` expression parser and evaluator

**agents/** - AI agent implementations. Each agent has:
- A system prompt defining its role
- Tool permissions (what it can do)
- The `execute()` method

**library/** - Built-in workflows and actions. These are shipped with Maverick and can be overridden.

**tools/** - MCP tool definitions for the Claude SDK. Git operations, GitHub API wrappers.

**tui/** - The Textual terminal user interface. Screens, widgets, real-time updates.
-->

---

## layout: two-cols

# 11.8 Key Configuration Files

<div class="pr-4">

<div v-click>

## pyproject.toml

```toml
[project]
name = "maverick"
version = "0.1.0"
requires-python = ">=3.10"

[project.scripts]
maverick = "maverick.main:cli"

[tool.ruff]
line-length = 88
target-version = "py310"

[tool.mypy]
python_version = "3.10"
strict = true
```

<div class="text-xs text-muted mt-2">Build config, dependencies, tool settings</div>

</div>

<div v-click class="mt-4">

## maverick.yaml

```yaml
# Project configuration
github:
  owner: get2knowio
  repo: maverick
  default_branch: main

validation:
  format_cmd: ["ruff", "format", "."]
  lint_cmd: ["ruff", "check", "--fix", "."]
  typecheck_cmd: ["mypy", "."]
  test_cmd: ["pytest", "-x", "--tb=short"]
```

</div>

</div>

::right::

<div class="pl-4 mt-4">

<div v-click>

## CLAUDE.md / copilot-instructions.md

<div class="p-3 bg-teal/10 border border-teal/30 rounded-lg">

AI assistant context files:

- Project overview
- Coding standards
- Architecture rules
- Tool guidance

```markdown
# Maverick

## Core Principles

1. Async-First
2. Dependency Injection
3. Fail Gracefully
4. Type Safety

## Architectural Guardrails

- TUI is display-only
- Agents provide judgment only
- Workflows own side effects
```

</div>

</div>

<div v-click class="mt-4">

## Config Priority

<div class="space-y-2 mt-2">
  <div class="flex items-center gap-2 text-sm">
    <span class="px-2 py-0.5 rounded bg-teal/20 text-teal font-mono text-xs">1</span>
    <span>CLI --config flag</span>
    <span class="text-muted text-xs">(highest)</span>
  </div>
  <div class="flex items-center gap-2 text-sm">
    <span class="px-2 py-0.5 rounded bg-purple-500/20 text-purple-400 font-mono text-xs">2</span>
    <span>.maverick/config.yaml</span>
    <span class="text-muted text-xs">(project)</span>
  </div>
  <div class="flex items-center gap-2 text-sm">
    <span class="px-2 py-0.5 rounded bg-brass/20 text-brass font-mono text-xs">3</span>
    <span>~/.config/maverick/config.yaml</span>
    <span class="text-muted text-xs">(user)</span>
  </div>
  <div class="flex items-center gap-2 text-sm">
    <span class="px-2 py-0.5 rounded bg-slate-500/20 text-slate-400 font-mono text-xs">4</span>
    <span>Built-in defaults</span>
    <span class="text-muted text-xs">(lowest)</span>
  </div>
</div>

</div>

</div>

<!--
Key configuration files in a Maverick project:

**pyproject.toml**: The standard Python project file. Defines:
- Project metadata and version
- Entry points (`maverick` command)
- Tool configuration (ruff, mypy)
- Dependencies

**maverick.yaml**: Project-specific Maverick configuration:
- GitHub repository settings
- Validation command customization
- Notification settings
- Model preferences

**CLAUDE.md / .github/copilot-instructions.md**: AI assistant context files. These are critical - they teach AI agents about:
- Project architecture
- Coding standards
- What NOT to do
- How to make decisions

**Configuration Priority**: Settings are merged from multiple sources:
1. CLI flags (highest priority)
2. Project config (.maverick/)
3. User config (~/.config/maverick/)
4. Built-in defaults (lowest)

This layering lets users customize at any level while maintaining sensible defaults.
-->
