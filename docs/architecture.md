# Maverick Architecture Guide

> Post-042 ACP Integration — March 2026

This document describes the current architecture of Maverick after the removal of the
YAML DSL infrastructure (041) and the migration to the Agent Client Protocol (042).

---

## Table of Contents

1. [High-Level Overview](#high-level-overview)
2. [Python Workflow Engine](#python-workflow-engine)
3. [ACP Integration Layer](#acp-integration-layer)
4. [Agent System](#agent-system)
5. [Component Registry](#component-registry)
6. [Configuration System](#configuration-system)
7. [CLI Commands Reference](#cli-commands-reference)
8. [VCS & Workspace Layer](#vcs--workspace-layer)
9. [Library: Actions, Agents, Generators](#library-actions-agents-generators)
10. [Event & Result Model](#event--result-model)

---

## 1. High-Level Overview

Maverick is a CLI tool that automates AI-powered development workflows. The core
execution model is:

```
CLI Command
  -> PythonWorkflow (orchestration)
    -> Actions (deterministic steps: git, validation, beads)
    -> AcpStepExecutor (AI agent steps)
      -> ACP subprocess (claude-agent-acp)
        -> Claude API
```

### Key Architectural Boundaries

| Layer | Responsibility | Examples |
|-------|---------------|----------|
| **CLI** (`maverick.cli`) | User interface, option parsing, output rendering | `fly`, `land`, `refuel` |
| **Workflows** (`maverick.workflows`) | Orchestration — WHAT to do and WHEN | `FlyBeadsWorkflow`, `RefuelSpeckitWorkflow` |
| **Agents** (`maverick.agents`) | Judgment — HOW to do a task (prompts, tool selection) | `ImplementerAgent`, `CuratorAgent` |
| **Executor** (`maverick.executor`) | Provider-agnostic step execution protocol | `AcpStepExecutor`, `StepExecutor` protocol |
| **Actions** (`maverick.library.actions`) | Deterministic operations (git, jj, validation, beads) | `jj_commit_bead()`, `run_preflight_checks()` |
| **Registry** (`maverick.registry`) | Component discovery and dispatch | `ComponentRegistry` facade |
| **Config** (`maverick.config`) | Pydantic-validated settings from YAML/env | `MaverickConfig` |

### What Changed (041 + 042)

- **041**: Removed the YAML DSL engine (`dsl/`, `fragments/`, YAML workflow definitions). All workflows are now pure Python classes inheriting from `PythonWorkflow`.
- **042**: Replaced direct `claude-agent-sdk` usage with the Agent Client Protocol (ACP). Agents no longer call the SDK directly; instead, `AcpStepExecutor` spawns an ACP-compatible subprocess and communicates over stdio.

---

## 2. Python Workflow Engine

### Base Class: `PythonWorkflow`

**Location**: `src/maverick/workflows/base.py`

All workflows inherit from `PythonWorkflow`, which provides:

- **Template method**: `execute(inputs)` -> `AsyncGenerator[ProgressEvent, None]`
- **Configuration resolution**: `resolve_step_config(step_name)` merges defaults with per-step overrides
- **Event emission**: `emit_step_started()`, `emit_step_completed()`, `emit_step_failed()`, `emit_output()`
- **Rollback registration**: `register_rollback(name, action)` — LIFO execution on failure
- **Checkpointing**: `save_checkpoint(data)`, `load_checkpoint()` for resume support
- **Result aggregation**: Collects `StepResult` instances into a `WorkflowResult`

```python
class PythonWorkflow(ABC):
    def __init__(self, *, config, registry, checkpoint_store, step_executor, workflow_name):
        ...

    async def execute(self, inputs: dict[str, Any]) -> AsyncGenerator[ProgressEvent, None]:
        # 1. Emit WorkflowStarted
        # 2. Run _run() in background task
        # 3. Yield events from internal queue
        # 4. Emit WorkflowCompleted
        ...

    @abstractmethod
    async def _run(self, inputs: dict[str, Any]) -> Any:
        """Subclasses implement workflow logic here."""
        ...
```

### Execution Flow

```
PythonWorkflow.execute(inputs)
  |
  +-- emits WorkflowStarted
  +-- spawns background task: _run_with_cleanup(inputs)
  |     |
  |     +-- calls self._run(inputs)  [subclass logic]
  |     |     |
  |     |     +-- emit_step_started("preflight")
  |     |     +-- run_preflight_checks(...)    # deterministic action
  |     |     +-- emit_step_completed("preflight")
  |     |     +-- emit_step_started("implement")
  |     |     +-- self._step_executor.execute(...)  # ACP agent call
  |     |     +-- emit_step_completed("implement")
  |     |     +-- ...more steps...
  |     |
  |     +-- on exception: emit_step_failed(), _execute_rollbacks()
  |     +-- puts sentinel None into queue
  |
  +-- drains event queue, yielding ProgressEvents
  +-- emits WorkflowCompleted
```

### Concrete Workflows

| Workflow | Module | Purpose |
|----------|--------|---------|
| `FlyBeadsWorkflow` | `workflows/fly_beads/workflow.py` | Bead-driven development: preflight -> workspace -> bead loop (implement/validate/review/commit) |
| `RefuelSpeckitWorkflow` | `workflows/refuel_speckit/workflow.py` | Create beads from a SpecKit specification (`tasks.md`) |
| `RefuelMaverickWorkflow` | `workflows/refuel_maverick/workflow.py` | Create beads from Maverick flight plans |
| `GenerateFlightPlanWorkflow` | `workflows/generate_flight_plan/workflow.py` | Generate flight plans from PRDs |

### FlyBeadsWorkflow Steps (Primary Workflow)

```
1. preflight         — Check API, git, jj, bd prerequisites
2. create_workspace  — jj git clone into ~/.maverick/workspaces/<project>/
3. [bead loop]:
   a. select_bead    — Pick next ready bead via `bd`
   b. implement      — ACP agent (ImplementerAgent) writes code
   c. sync_deps      — Run dependency sync (e.g., `uv sync`)
   d. validate       — Format/lint/typecheck/test with fix-retry loop
   e. review         — Gather context, run review-fix loop (optional)
   f. commit         — jj commit + mark bead complete
   g. checkpoint     — Save progress for resume
4. Done when no more ready beads or max_beads reached
```

---

## 3. ACP Integration Layer

### What is ACP?

The **Agent Client Protocol** (`agent-client-protocol` v0.8.1+) is a standard protocol
for communicating with AI agent subprocesses over stdio. Maverick uses the `acp` Python
SDK to spawn and communicate with agent processes.

Instead of calling the Claude Agent SDK directly in-process, Maverick now:
1. Spawns an ACP-compatible subprocess (e.g., `claude-agent-acp`)
2. Initializes a protocol connection
3. Creates sessions and sends prompts
4. Receives streaming events (text chunks, tool calls, thoughts)

### AcpStepExecutor

**Location**: `src/maverick/executor/acp.py`

The primary executor implementing the `StepExecutor` protocol.

```python
class AcpStepExecutor:
    def __init__(self, provider_registry, agent_registry):
        ...

    async def execute(self, *, step_name, agent_name, prompt, instructions,
                      allowed_tools, cwd, output_schema, config, event_callback):
        # 1. Resolve provider (AgentProviderConfig)
        # 2. Resolve agent from registry, call agent.build_prompt(prompt)
        # 3. Get/create cached ACP connection (one subprocess per provider)
        # 4. Execute with retry: create session -> send prompt -> collect output
        # 5. Extract and validate output (JSON schema if output_schema provided)
        # 6. Return ExecutorResult
        ...

    async def cleanup(self):
        # Close all cached ACP connections and terminate subprocesses
        ...
```

Key features:
- **Connection caching**: One subprocess per provider, reused across steps
- **Transparent reconnect** (FR-021): On connection drop, spawns a fresh subprocess
- **Circuit breaker**: Aborts if an agent calls the same tool 15+ times
- **Tenacity retry**: Configurable retry with exponential backoff
- **JSON output extraction**: Parses `json` code blocks or brace-matched objects for structured output

### MaverickAcpClient

**Location**: `src/maverick/executor/acp_client.py`

Subclass of `acp.Client` that handles:
- **Streaming**: Maps ACP events to `AgentStreamChunk` (output, thinking, tool calls)
- **Circuit breaker**: Tracks tool call counts, cancels session at threshold
- **Permission handling**: Three modes:
  - `AUTO_APPROVE`: Allow all tool calls
  - `DENY_DANGEROUS`: Block `Bash`, `Write`, `Edit`, `NotebookEdit`; allow `Read`, `Glob`, `Grep`
  - `INTERACTIVE`: Not yet implemented

### AgentProviderRegistry

**Location**: `src/maverick/executor/provider_registry.py`

Resolves provider names to `AgentProviderConfig`. Zero-config mode synthesizes
a default `claude` provider using `claude-agent-acp`.

```python
# Zero-config: no agent_providers in maverick.yaml
# -> Synthesizes: {"claude": AgentProviderConfig(command=["claude-agent-acp"], default=True)}

# Explicit config in maverick.yaml:
agent_providers:
  claude:
    command: ["claude-agent-acp"]
    permission_mode: auto_approve
    default: true
  custom_agent:
    command: ["/path/to/my-agent"]
    env:
      MY_API_KEY: "..."
    permission_mode: deny_dangerous
```

### StepExecutor Protocol

**Location**: `src/maverick/executor/protocol.py`

Provider-agnostic `@runtime_checkable` Protocol. Any alternative executor (OpenAI, local
models) can implement this without importing Maverick internals.

```python
@runtime_checkable
class StepExecutor(Protocol):
    async def execute(
        self, *, step_name, agent_name, prompt, instructions,
        allowed_tools, cwd, output_schema, config, event_callback,
    ) -> ExecutorResult: ...
```

---

## 4. Agent System

### MaverickAgent Base Class

**Location**: `src/maverick/agents/base.py`

Abstract base for all agents. In the ACP world, an agent's only job is to
**build a prompt string** from a typed context. The executor handles everything else.

```python
class MaverickAgent(ABC, Generic[TContext, TResult]):
    def __init__(self, name, instructions, allowed_tools, model, ...):
        ...

    @abstractmethod
    def build_prompt(self, context: TContext) -> str:
        """Convert typed context into a prompt string for ACP."""
        ...
```

Each agent defines:
- `name`: Registry key (e.g., `"implementer"`)
- `instructions`: System prompt describing the agent's role
- `allowed_tools`: Tool allowlist (validated against `BUILTIN_TOOLS`)
- `build_prompt()`: Converts domain context to a flat prompt string

### Registered Agents

| Name | Class | Purpose |
|------|-------|---------|
| `implementer` | `ImplementerAgent` | Implements tasks from task descriptions |
| `code_reviewer` | `CodeReviewerAgent` | General code review |
| `unified_reviewer` | `UnifiedReviewerAgent` | Parallel spec + technical review |
| `simple_fixer` | `SimpleFixerAgent` | Fixes review findings |
| `issue_fixer` | `IssueFixerAgent` | Fixes GitHub issues |
| `validation_fixer` | `FixerAgent` | Applies validation fixes (lint, type, test) |
| `decomposer` | `DecomposerAgent` | Decomposes flight plans into work units |
| `flight_plan_generator` | `FlightPlanGeneratorAgent` | Generates flight plans from PRDs |
| `curator` | `CuratorAgent` | Reorganizes commit history for `land` |

### Agent Execution Flow

```
Workflow calls step_executor.execute(agent_name="implementer", prompt=context)
  |
  +-- AcpStepExecutor resolves "implementer" from ComponentRegistry
  +-- Instantiates ImplementerAgent()
  +-- Calls agent.build_prompt(context) -> prompt string
  +-- Sends prompt to ACP subprocess
  +-- ACP subprocess runs Claude with tools
  +-- Streams events back through MaverickAcpClient
  +-- Returns ExecutorResult(output=..., success=True)
```

---

## 5. Component Registry

**Location**: `src/maverick/registry/component_registry.py`

Facade aggregating three sub-registries:

```python
class ComponentRegistry:
    actions: ActionRegistry    # Python callables (deterministic actions)
    agents: AgentRegistry      # MaverickAgent classes (AI agents)
    generators: GeneratorRegistry  # GeneratorAgent classes
    strict: bool               # Raise immediately on lookup failure?
```

**Registration** happens at startup in `create_registered_registry()` (`src/maverick/cli/common.py`):

```python
def create_registered_registry():
    registry = ComponentRegistry(strict=False)
    register_all_actions(registry)    # from maverick.library.actions
    register_all_agents(registry)     # from maverick.library.agents
    register_all_generators(registry) # from maverick.library.generators
    return registry
```

Workflows and the executor look up components by name:
```python
agent_class = registry.agents.get("implementer")  # -> ImplementerAgent
action_fn = registry.actions.get("git_commit")     # -> callable
```

---

## 6. Configuration System

### Configuration Hierarchy

Settings are loaded with the following priority (highest wins):

1. **Environment variables** (`MAVERICK_*`, with `__` for nesting)
2. **Project config** (`./maverick.yaml`)
3. **User config** (`~/.config/maverick/config.yaml`)
4. **Built-in defaults** (Pydantic model defaults)

### MaverickConfig Structure

**Location**: `src/maverick/config.py`

```yaml
# maverick.yaml — Full reference
github:
  owner: "get2knowio"            # GitHub org/user
  repo: "sample-maverick-project" # Repository name
  default_branch: "main"         # Base branch

model:
  model_id: "claude-sonnet-4-5-20250929"  # Claude model
  max_tokens: 64000              # Max output tokens (up to 64K)
  temperature: 0.0               # 0.0 = deterministic

validation:
  sync_cmd: ["uv", "sync"]      # Dependency sync command
  format_cmd: ["ruff", "format", "."]
  lint_cmd: ["ruff", "check", "--fix", "."]
  typecheck_cmd: ["mypy", "."]
  test_cmd: ["pytest", "-x", "--tb=short"]
  timeout_seconds: 300           # Max time per validation command
  max_errors: 50                 # Max errors to report

workspace:
  root: "~/.maverick/workspaces" # Where workspaces are cloned
  setup: "uv sync"              # Run after cloning
  teardown: null                # Run before removal
  reuse: true                   # Reuse existing workspace
  env_files: [".env"]           # Files to copy into workspace

notifications:
  enabled: false
  server: "https://ntfy.sh"
  topic: null

parallel:
  max_agents: 3                 # Concurrent agent limit
  max_tasks: 5                  # Concurrent task limit

preflight:
  timeout_per_check: 5.0
  fail_on_warning: false
  custom_tools:                 # Additional tools to validate
    - name: "Docker"
      command: "docker"
      required: true
      hint: "Install from https://docker.com/"

session_log:
  enabled: false
  output_dir: ".maverick/logs"
  include_agent_text: true

tui_metrics:
  enabled: false
  max_entries: 10000

verbosity: "warning"            # error | warning | info | debug
project_conventions: ""         # Free-form text appended to agent prompts

# Per-agent overrides
agents:
  implementer:
    model_id: "claude-opus-4-5-20251101"  # Use Opus for implementation
    max_tokens: 64000
    temperature: 0.0

# Per-step execution config
steps:
  implement:
    timeout: 600
    max_retries: 2
    provider: "claude"

# Prompt overrides
prompts:
  implement:
    suffix: "Focus on test coverage."
    # OR: file: "prompts/implement.md"

# ACP agent provider configurations
agent_providers:
  claude:
    command: ["claude-agent-acp"]
    env: {}
    permission_mode: "auto_approve"  # auto_approve | deny_dangerous | interactive
    default: true
```

### Key Config Models

| Model | Purpose |
|-------|---------|
| `MaverickConfig` | Root config (BaseSettings with YAML + env sources) |
| `GitHubConfig` | GitHub owner/repo/branch |
| `ValidationConfig` | Validation commands and timeouts |
| `ModelConfig` | Claude model ID, tokens, temperature |
| `WorkspaceConfig` | Hidden workspace settings |
| `ParallelConfig` | Concurrency limits |
| `AgentConfig` | Per-agent model overrides |
| `AgentProviderConfig` | ACP provider command, env, permission mode |
| `StepConfig` | Per-step timeout, retry, provider, autonomy |
| `PreflightValidationConfig` | Preflight check settings |
| `SessionLogConfig` | Session journal settings |
| `PermissionMode` | Enum: `auto_approve`, `deny_dangerous`, `interactive` |

---

## 7. CLI Commands Reference

### Global Options

```
maverick [OPTIONS] COMMAND

Options:
  --version         Show version
  -c, --config PATH Path to config file (overrides project/user config)
  -v, --verbose     Increase verbosity (-v=INFO, -vv=DEBUG, -vvv=DEBUG+trace)
  -q, --quiet       Suppress non-essential output (ERROR only)
```

### `maverick fly`

Run a bead-driven development workflow.

```
maverick fly [OPTIONS]

Options:
  --epic TEXT         Epic bead ID to iterate over (omit for any ready bead)
  --max-beads INT     Maximum beads to process [default: 30]
  --dry-run           Preview mode — skip git and bd mutations
  --skip-review       Skip code review step for each bead
  --list-steps        List workflow steps and exit
  --session-log PATH  Write session journal (JSONL) to this file
```

**What it does**: Picks the next ready bead(s) from the `bd` tool, creates an isolated
jj workspace, then loops: implement (AI agent), sync deps, validate/fix, review/fix,
commit, close. All work happens in `~/.maverick/workspaces/<project>/`.

**Examples**:
```bash
maverick fly                           # Process any ready beads
maverick fly --epic my-epic            # Only beads under this epic
maverick fly --skip-review --max-beads 5
maverick fly --list-steps              # Show steps without running
```

### `maverick land`

Curate commit history and push after `fly` finishes.

```
maverick land [OPTIONS]

Options:
  --no-curate       Skip curation, just push
  --dry-run         Show curation plan without executing
  --yes, -y         Auto-approve curation plan
  --base TEXT       Base revision for curation scope [default: main]
  --heuristic-only  Use heuristic curation (no agent)
  --eject           Push to preview branch, keep workspace
  --finalize        Create PR from preview branch, cleanup workspace
  --branch TEXT     Branch name for pushed bookmark [default: maverick/<project>]
```

**Three modes**:
| Mode | Command | Behavior |
|------|---------|----------|
| Approve (default) | `maverick land` | Curate -> interactive prompt -> push -> teardown |
| Eject | `maverick land --eject` | Curate -> push preview branch -> keep workspace |
| Finalize | `maverick land --finalize` | Create PR from preview -> teardown |

**Examples**:
```bash
maverick land                          # Interactive: curate, approve, push
maverick land --dry-run                # Show plan without applying
maverick land --heuristic-only -y      # Non-interactive heuristic curation
maverick land --eject                  # Push to preview branch
maverick land --finalize --branch maverick/preview/my-project
```

### `maverick refuel speckit <SPEC>`

Create beads from a SpecKit specification.

```
maverick refuel speckit SPEC [OPTIONS]

Arguments:
  SPEC  Spec identifier (branch/directory under specs/)

Options:
  --dry-run         Show what beads would be created without calling bd
  --list-steps      List workflow steps and exit
  --session-log PATH  Write session journal (JSONL)
```

**Steps**: checkout spec branch -> parse tasks.md -> extract dependencies -> enrich
beads -> create via `bd` -> wire dependencies -> commit -> merge back to main.

### `maverick refuel flight-plan <PLAN>`

Decompose a flight plan into work units and beads using an AI agent.

### `maverick flight-plan create|generate|validate`

Flight plan management subcommands.

### `maverick workspace status`

Show workspace state for the current project.

```bash
maverick workspace status
# Output: workspace path, state (active/ejected), creation time
```

### `maverick workspace clean`

Remove the workspace for the current project.

```bash
maverick workspace clean
# Removes ~/.maverick/workspaces/<project>/
```

### `maverick init`

Initialize a new Maverick project (creates `maverick.yaml`).

### `maverick uninstall`

Remove Maverick configuration from the project.

### `maverick brief`

Generate a project briefing document.

---

## 8. VCS & Workspace Layer

### Three VCS Layers

Maverick uses three distinct layers for VCS operations:

```
Write Path (mutations)        Read Path (queries)        Protocol (abstraction)
-----------------------       --------------------       ----------------------
JjClient (jj CLI)            AsyncGitRepository         VcsRepository Protocol
  - commit, push             (GitPython)                  - diff, status, log
  - bookmark, merge            - diff, blame               - changed_files
  - absorb, squash             - status, log               - commit_messages
```

| Layer | Module | Usage |
|-------|--------|-------|
| **JjClient** | `maverick.jj.client` | All write operations via `jj` CLI (commit, push, merge, bookmark) |
| **GitPython** | `maverick.git` | Read-only operations (diff, status, log, blame) |
| **VcsRepository** | `maverick.vcs.protocol` | `@runtime_checkable` Protocol abstracting git/jj for reads |

Both `AsyncGitRepository` and `JjRepository` satisfy the `VcsRepository` protocol
via structural typing. The colocated mode (`jj git init --colocate`) ensures they
share the same `.git` directory.

### Workspace Manager

**Location**: `src/maverick/workspace/manager.py`

Manages hidden jj workspaces at `~/.maverick/workspaces/<project>/`.

```python
class WorkspaceManager:
    async def create()              # jj git clone into workspace
    async def bootstrap()           # Run setup command (e.g., uv sync)
    async def create_and_bootstrap()
    async def sync_from_origin()    # jj git fetch
    async def teardown()            # Run teardown command + rm -rf
    def get_state()                 # Read workspace metadata
    def set_state(state)            # Update state (ACTIVE, EJECTED)
    def get_jj_client()             # JjClient for this workspace
```

**Workspace states**: `ACTIVE` (fly in progress), `EJECTED` (pushed to preview branch),
removed after `land --finalize` or `land` approve.

---

## 9. Library: Actions, Agents, Generators

The `src/maverick/library/` directory contains all registerable components:

### Actions (`library/actions/`)

Deterministic Python functions registered with `ActionRegistry`:

| Action Module | Functions |
|---------------|-----------|
| `beads` | `select_next_bead()`, `mark_bead_complete()`, `create_beads_from_failures()`, `create_beads_from_findings()`, `check_epic_done()` |
| `jj` | `jj_commit_bead()`, `jj_describe()`, `jj_snapshot_operation()`, `jj_restore_operation()`, `curate_history()`, `gather_curation_context()`, `execute_curation_plan()` |
| `preflight` | `run_preflight_checks()` |
| `validation` | `run_fix_retry_loop()` |
| `review` | `gather_local_review_context()`, `run_review_fix_loop()` |
| `workspace` | `create_fly_workspace()` |
| `dependencies` | `sync_dependencies()` |
| `git` | `git_push()` |
| `github` | `create_github_pr()` |

### Agents (`library/agents/`)

Registers `MaverickAgent` classes (see [Agent System](#agent-system)).

### Generators (`library/generators/`)

Registers `GeneratorAgent` classes for content generation.

---

## 10. Event & Result Model

### Progress Events

**Location**: `src/maverick/events.py`

All events are frozen `@dataclass(frozen=True, slots=True)` instances. Workflows emit
them via an `asyncio.Queue`, and the CLI renders them in real time.

| Event | When |
|-------|------|
| `WorkflowStarted` | Workflow begins |
| `WorkflowCompleted` | Workflow ends (success or failure) |
| `StepStarted` | A step begins (with `StepType`) |
| `StepCompleted` | A step ends (success/failure, duration) |
| `StepOutput` | Informational output from any step |
| `AgentStreamChunk` | Real-time text from an ACP agent (output/thinking/error) |
| `CheckpointSaved` | Checkpoint persisted |
| `RollbackStarted` / `RollbackCompleted` | Rollback execution |
| `PreflightStarted` / `PreflightCheckPassed` / `PreflightCheckFailed` / `PreflightCompleted` | Preflight validation |
| `ValidationStarted` / `ValidationCompleted` / `ValidationFailed` | Semantic validation |
| `LoopIterationStarted` / `LoopIterationCompleted` / `LoopConditionChecked` | Loop progress |

The `ProgressEvent` type alias is a union of all event types.

### Results

**Location**: `src/maverick/results.py`

```python
@dataclass(frozen=True)
class StepResult:
    name: str
    step_type: StepType
    success: bool
    output: Any
    duration_ms: int
    error: str | None

@dataclass(frozen=True)
class WorkflowResult:
    workflow_name: str
    success: bool
    step_results: tuple[StepResult, ...]
    total_duration_ms: int
    final_output: Any
```

### StepType Enum

```python
class StepType(str, Enum):
    PYTHON = "python"         # Deterministic action
    AGENT = "agent"           # AI agent step
    GENERATE = "generate"     # Content generation
    VALIDATE = "validate"     # Validation check
    SUBWORKFLOW = "subworkflow"
    BRANCH = "branch"
    LOOP = "loop"
    CHECKPOINT = "checkpoint"
```

---

## Appendix: Module Map

```
src/maverick/
├── __init__.py              # Version, public API
├── main.py                  # Click CLI entry point
├── config.py                # MaverickConfig (Pydantic + YAML)
├── constants.py             # Model IDs, timeouts, retry constants
├── events.py                # Frozen dataclass ProgressEvent types
├── results.py               # StepResult, WorkflowResult
├── types.py                 # StepType, StepMode, AutonomyLevel enums
├── exceptions/              # MaverickError hierarchy
├── logging.py               # structlog configuration
│
├── cli/                     # Click commands and rendering
│   ├── commands/
│   │   ├── fly/             # maverick fly
│   │   ├── land.py          # maverick land
│   │   ├── refuel/          # maverick refuel {speckit,flight-plan,maverick}
│   │   ├── workspace/       # maverick workspace {status,clean}
│   │   ├── flight_plan/     # maverick flight-plan {create,generate,validate}
│   │   ├── init.py          # maverick init
│   │   ├── uninstall.py     # maverick uninstall
│   │   └── brief.py         # maverick brief
│   ├── common.py            # cli_error_handler, create_registered_registry
│   ├── workflow_executor.py # execute_python_workflow, render_workflow_events
│   ├── console.py           # Rich Console instances
│   ├── context.py           # CLIContext, ExitCode, async_command
│   └── output.py            # format_error, format_success, format_warning
│
├── workflows/               # Python workflow implementations
│   ├── base.py              # PythonWorkflow ABC
│   ├── fly_beads/           # FlyBeadsWorkflow (primary)
│   ├── refuel_speckit/      # RefuelSpeckitWorkflow
│   ├── refuel_maverick/     # RefuelMaverickWorkflow
│   ├── generate_flight_plan/# GenerateFlightPlanWorkflow
│   └── review_fix.py        # Shared review-fix utilities
│
├── agents/                  # MaverickAgent implementations
│   ├── base.py              # MaverickAgent ABC
│   ├── implementer.py       # ImplementerAgent
│   ├── code_reviewer.py     # CodeReviewerAgent
│   ├── curator.py           # CuratorAgent
│   ├── fixer.py             # FixerAgent (validation fixes)
│   ├── issue_fixer.py       # IssueFixerAgent
│   ├── decomposer.py        # DecomposerAgent
│   ├── flight_plan_generator.py
│   ├── reviewers/           # UnifiedReviewerAgent, SimpleFixerAgent
│   ├── registry.py          # Agent-level registration utilities
│   ├── contracts.py         # Typed output contracts (Pydantic)
│   └── context.py           # Agent context types
│
├── executor/                # Provider-agnostic step execution
│   ├── protocol.py          # StepExecutor Protocol (no provider imports)
│   ├── acp.py               # AcpStepExecutor (ACP adapter)
│   ├── acp_client.py        # MaverickAcpClient (streaming, permissions)
│   ├── provider_registry.py # AgentProviderRegistry
│   ├── config.py            # StepConfig, RetryPolicy
│   ├── result.py            # ExecutorResult, UsageMetadata
│   └── errors.py            # OutputSchemaValidationError
│
├── registry/                # Component discovery
│   ├── component_registry.py# ComponentRegistry facade
│   ├── actions.py           # ActionRegistry
│   ├── agents.py            # AgentRegistry
│   ├── generators.py        # GeneratorRegistry
│   └── protocol.py          # Registry protocol
│
├── library/                 # Registerable components
│   ├── actions/             # Deterministic action functions
│   ├── agents/              # Agent registration (register_all_agents)
│   └── generators/          # Generator registration
│
├── jj/                      # Jujutsu VCS wrapper
│   ├── client.py            # JjClient (async, typed)
│   ├── models.py            # Frozen dataclass result types
│   ├── errors.py            # JjError hierarchy
│   └── repository.py        # JjRepository (VcsRepository impl)
│
├── vcs/                     # VCS abstraction
│   ├── protocol.py          # VcsRepository Protocol
│   └── factory.py           # create_vcs_repository() auto-detection
│
├── workspace/               # Hidden workspace lifecycle
│   ├── manager.py           # WorkspaceManager
│   ├── models.py            # WorkspaceInfo, WorkspaceState
│   └── errors.py            # WorkspaceError hierarchy
│
├── git/                     # GitPython read-only wrapper
├── beads/                   # bd CLI integration
├── checkpoint/              # Checkpoint persistence
├── flight/                  # Flight plan models and parsing
├── hooks/                   # Safety/logging hooks (stubbed for ACP)
├── runners/                 # CommandRunner (subprocess with timeouts)
├── tools/                   # MCP tool definitions
├── prompts/                 # Prompt configuration and overrides
├── models/                  # Shared data models
├── utils/                   # Shared utilities (github_client, secrets)
├── tui/                     # Terminal UI components
├── skills/                  # Skill definitions
├── init/                    # Project initialization
└── session_journal.py       # JSONL session logging
```
