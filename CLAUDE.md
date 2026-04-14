# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Maverick is a Python CLI application that orchestrates AI-powered development workflows using the Agent Client Protocol (ACP). It runs the full PRD-to-code pipeline: plan generation, decomposition into beads (work units), implementation, review, and commit management — using an actor-mailbox architecture with MCP tool-based communication.

## Technology Stack

| Category        | Technology              | Notes                                    |
| --------------- | ----------------------- | ---------------------------------------- |
| Language        | Python 3.11+            | Use `from __future__ import annotations` |
| Package Manager | uv                      | Fast, reproducible builds via `uv.lock`  |
| Build System    | Make                    | AI-friendly commands with minimal output |
| AI/Agents       | Agent Client Protocol   | `agent-client-protocol` SDK + `claude-agent-acp` subprocess |
| Actor Framework | Thespian                | `multiprocTCPBase` for cross-process actor messaging |
| MCP Tools       | MCP SDK                 | Supervisor inbox server for schema-enforced agent output |
| CLI             | Click                   | `click` package                          |
| CLI Output      | Rich                    | `rich` package (auto TTY detection)      |
| Validation      | Pydantic                | For configuration and data models        |
| Testing         | pytest + pytest-asyncio | Parallel via xdist (`-n auto`)           |
| Linting         | Ruff                    | Fast, comprehensive Python linter        |
| Type Checking   | MyPy                    | Strict mode recommended                  |
| VCS (writes)    | Jujutsu (jj)            | `maverick.jj.client.JjClient` for all jj ops |
| VCS (reads)     | GitPython               | `maverick.git` wraps GitPython (read-only) |
| VCS (protocol)  | VcsRepository           | `maverick.vcs` abstracts git/jj for reads  |
| Workspaces      | WorkspaceManager        | `maverick.workspace` — hidden jj clones    |
| GitHub API      | PyGithub                | `maverick.utils.github_client`           |
| Logging         | structlog               | `maverick.logging.get_logger()`          |
| Retry Logic     | tenacity                | `@retry` decorator or `AsyncRetrying`    |
| Secret Detection| detect-secrets          | `maverick.utils.secrets`                 |

## Third-Party Library Standards

These libraries are the canonical choices for their domains. Do NOT introduce alternatives or custom implementations.

### Jujutsu / jj (`maverick.library.actions.jj`)

**Use for**: All write-path VCS operations (commit, push, merge, branch).
Requires colocated mode (`jj git init --colocate`) so `.git` is shared.

```python
from maverick.library.actions.jj import git_commit, git_push

result = await git_commit("feat: add feature")
await git_push()
```

**Do NOT**: Shell out to `git` for write operations. Use `jj` actions instead.

### GitPython (`maverick.git`)

**Use for**: Read-only git operations (diffs, status, log, blame). Works
unchanged in colocated mode because jj and git share the `.git` directory.

```python
from maverick.git import AsyncGitRepository

repo = AsyncGitRepository(path)
diff = await repo.diff("main")
```

**Do NOT**: Use GitPython for write operations (commits, pushes). Use jj actions.

### PyGithub (`maverick.utils.github_client`)

**Use for**: All GitHub API operations (issues, PRs, labels, comments)

```python
from maverick.utils.github_client import GitHubClient

client = GitHubClient()
issues = await client.list_issues(repo_name, labels=["bug"])
await client.create_pr(repo_name, title, body, head, base)
```

**Do NOT**: Use `subprocess.run("gh ...")` for operations that PyGithub supports

### structlog (`maverick.logging`)

**Use for**: All logging throughout the codebase

```python
from maverick.logging import get_logger

logger = get_logger(__name__)
logger.info("processing_started", item_id=item_id, count=10)
logger.error("operation_failed", error=str(e), context="validation")
```

**Do NOT**: Use `import logging; logging.getLogger(__name__)`

### tenacity

**Use for**: All retry logic with exponential backoff

```python
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

async for attempt in AsyncRetrying(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
):
    with attempt:
        return await risky_operation()
```

**Do NOT**: Write manual `for attempt in range(retries):` loops

### detect-secrets (`maverick.utils.secrets`)

**Use for**: Detecting secrets/credentials in content before commits

```python
from maverick.utils.secrets import detect_secrets

findings = detect_secrets(file_content)
if findings:
    raise SecurityError(f"Potential secrets found: {findings}")
```

**Do NOT**: Write custom regex patterns for secret detection

## Architecture

```
src/maverick/
├── __init__.py          # Version, public API exports
├── main.py              # CLI entry point (Click commands)
├── config.py            # Pydantic configuration models
├── exceptions.py        # Custom exception hierarchy (MaverickError base)
├── types.py             # StepType, StepMode, AutonomyLevel enums
├── constants.py         # Workflow execution constants
├── events.py            # Workflow progress event dataclasses
├── results.py           # StepResult, WorkflowResult dataclasses
├── actors/              # Thespian actor definitions
│   ├── refuel_supervisor.py  # RefuelSupervisorActor (routing + inbox)
│   ├── decomposer.py        # DecomposerActor (ACP prompts)
│   ├── validator.py          # ValidatorActor (pure sync)
│   └── bead_creator.py       # BeadCreatorActor (async bd calls)
├── agents/              # Agent implementations (prompt builders)
│   ├── base.py          # MaverickAgent abstract base class
│   └── *.py             # Concrete agents (ImplementerAgent, etc.)
├── executor/            # Step execution (ACP integration)
├── checkpoint/          # Checkpoint persistence
├── registry/            # Component registry (actions/agents/generators)
├── jj/                  # JjClient — typed jj (Jujutsu) wrapper
│   ├── client.py        # JjClient (CommandRunner-based, async)
│   ├── models.py        # Frozen dataclass result types
│   ├── errors.py        # JjError hierarchy under MaverickError
│   └── repository.py    # JjRepository (VcsRepository protocol impl)
├── vcs/                 # VCS abstraction layer
│   ├── protocol.py      # VcsRepository runtime-checkable protocol
│   └── factory.py       # create_vcs_repository() auto-detection
├── workspace/           # Hidden workspace lifecycle management
│   ├── manager.py       # WorkspaceManager (create/bootstrap/teardown)
│   ├── models.py        # WorkspaceInfo, WorkspaceState, result types
│   └── errors.py        # WorkspaceError hierarchy
├── workflows/           # Workflow orchestration
│   ├── fly.py           # FlyWorkflow - full spec-based workflow
│   └── refuel.py        # RefuelWorkflow - tech-debt resolution
├── tools/               # MCP tool servers
│   └── supervisor_inbox/    # Generic MCP server for actor communication
│       ├── server.py        # MCP server (maverick serve-inbox)
│       └── schemas.py       # Tool schemas (full inbox vocabulary)
├── hooks/               # Safety and logging hooks
└── utils/               # Shared utilities
```

### Separation of Concerns

- **Actors**: Thespian actors that own state and process messages. Agent actors hold persistent ACP sessions; deterministic actors wrap Python functions.
- **Supervisors**: Route messages between actors via policy. The supervisor IS a Thespian actor — `receiveMessage` is its inbox.
- **Agents**: Know HOW to do a task (system prompts, tool selection). Build prompts; don't own orchestration.
- **Workflows**: Know WHAT to do and WHEN. Create the ActorSystem, actors, send "start", wait for "complete".
- **MCP Tools**: The supervisor's inbox. Agents call MCP tools to deliver structured results; the protocol validates schemas.
- **JjClient**: Typed wrapper around `jj` CLI with retries, timeouts, and error hierarchy
- **WorkspaceManager**: Lifecycle for hidden jj workspaces (`~/.maverick/workspaces/`)

### Three Information Types

All data in Maverick falls into one of three categories:

| Type | What | Lifecycle | Examples |
|------|------|-----------|----------|
| **Beads** | Domain work units | Created at refuel, closed at commit, persist forever | "Implement UID sync", "Add compose profiles" |
| **Files** | Durable context | Survives restarts, read across sessions | Flight plans, work units, fly reports, config |
| **Messages** | Process coordination | Created, consumed, discarded within one bead/step | Tool calls, routing signals, review findings |

## Development Commands

**IMPORTANT**: Always use `make` commands instead of `uv run` directly. The Makefile provides AI-agent-friendly output with minimal noise.

| Command               | Purpose                                     |
| --------------------- | ------------------------------------------- |
| `make test`           | Run all tests in parallel (errors only)     |
| `make test-fast`      | Unit tests only, no slow tests (fastest)    |
| `make test-cov`       | Run tests with coverage report              |
| `make test-integration` | Run integration tests only                |
| `make lint`           | Run ruff linter (errors only)               |
| `make typecheck`      | Run mypy (errors only)                      |
| `make format`         | Check formatting (diff if needed)           |
| `make format-fix`     | Apply formatting fixes                      |
| `make check`          | Run all checks (lint, typecheck, test)      |
| `make ci`             | CI mode: fail fast on any error             |
| `make clean`          | Remove build artifacts and caches           |
| `make VERBOSE=1 test` | Full output for debugging                   |

## Core Principles

See `.specify/memory/constitution.md` for the authoritative reference.

1. **Async-First**: All agent interactions and workflows MUST be async. Use `asyncio` patterns; no threading for I/O. Workflows yield progress updates as async generators for CLI consumption.

2. **Dependency Injection**: Agents and workflows receive configuration and dependencies, not global state. MCP tool servers are passed in, not created internally.

3. **Fail Gracefully**: One agent/issue failing MUST NOT crash the entire workflow. Capture and report errors with context.

4. **Test-First**: Every public class and function MUST have tests. TDD with Red-Green-Refactor.

5. **Type Safety**: Complete type hints required. Use `@dataclass` or Pydantic `BaseModel` over plain dicts.

6. **Simplicity**: No global mutable state, no god-classes, no premature abstractions.

7. **Complete Work**: Every bead must be self-contained and leave the codebase clean. No deferred work — if a change requires updating callers, removing dead code, or migrating tests, do it in the same bead. No TODO/FIXME/HACK comments that punt work to "later". The agent workflow runs autonomously; there is no human watching output to catch "good enough for now."

## Operating Standard (Ownership & Follow-Through)

The default stance is full ownership of the repository state while you work. “That’s not my problem” is not an acceptable response.

- **Do what you’re asked, then keep going**: Complete the requested change end-to-end, then address collateral failures and obvious correctness issues you encountered along the way.
- **Fix what you find**: If you encounter broken tests, lint failures, type errors, flaky behavior, or obvious bugs while working, attempt to fix them—even if they predate your changes.
- **Keep the tree green**: Don’t rationalize failures as “unrelated” or “not introduced by me.” If the repo is failing, the task is not done yet.
- **No artificial scope minimization**: We are not operating under time pressure. Unless explicitly instructed otherwise, prefer a complete, robust solution over a narrowly-scoped patch.
- **No deferral by difficulty**: “Too hard” or “too far-reaching” is a signal to decompose the work, not to stop. Break the problem down and make real progress now.
- **Only defer when truly blocked**: Defer work only when it is impossible in the current context (missing requirements, missing access, non-reproducible failures). If you must defer, document exactly what’s blocked and what the next concrete step is.

## ACP Execution Model

All agent execution MUST go through the ACP executor (`maverick.executor.acp.AcpStepExecutor`).
Do NOT bypass ACP with direct `claude -p` subprocess calls or other ad-hoc execution paths.
ACP provides connection caching, retry, circuit breakers, event streaming, and provider
abstraction that raw subprocess calls lack.

### Multi-Turn Sessions

The executor supports persistent ACP sessions via `create_session()` + `prompt_session()`.
A single session can receive multiple prompts with full conversation history preserved.
This is used by the actor-mailbox architecture to keep implementer and reviewer context
across fix rounds.

### MCP Tool-Based Agent Output (Supervisor Inbox)

Agents communicate structured results to the supervisor via MCP tool calls, not JSON in
text responses. The orchestrator runs an MCP server (`maverick serve-inbox`) whose tools
are the message types the supervisor accepts. The MCP protocol provides schema guidance;
the server validates via `jsonschema.validate()` and returns errors for self-correction.

**Do**: Define agent output as MCP tool schemas in `maverick.tools.supervisor_inbox.schemas`
**Don't**: Use `output_schema` (Pydantic model validation) for agent responses. This pattern
appends a JSON schema to the prompt and validates the response against a Pydantic model —
but agents frequently return slightly different field names or structures, causing
`OutputSchemaValidationError` at runtime. The MCP tool schemas are the single source of
truth for structured output; Pydantic models add a second, conflicting contract.

For freeform analysis (briefing agents, reviewers): accept raw dicts/text. The supervisor
serializes them to JSON for downstream consumers. No Pydantic coercion needed.

Built-in tools (Read, Write, Edit, Bash, Glob, Grep) are for doing work in the workspace.
MCP tools (submit_outline, submit_review, etc.) are for sending results to the supervisor.

**Provider compatibility**: Claude reliably calls MCP tools. Copilot agents currently do not
call MCP tools in ACP sessions — use the text fallback path for Copilot-routed steps.

### Actor-Mailbox Architecture

All three workflows (plan, refuel, fly) use a supervisor that routes messages between actors:

- **Agent actors** (implementer, reviewer, decomposer): Persistent ACP sessions, deliver
  results via MCP tool calls to the supervisor's inbox
- **Deterministic actors** (gate, validator, bead creator): Pure Python, no ACP session
- **Supervisor**: Routes messages via a policy (match on message type). The supervisor IS
  the Thespian actor — its `receiveMessage` is its inbox

See `docs/AGENT-MCP.md` for the full architecture design.

### Thespian Actor System

The refuel workflow uses Thespian `multiprocTCPBase` for true cross-process actor messaging.
Each actor runs in its own OS process. The supervisor IS the Thespian actor — its
`receiveMessage` is its inbox. MCP tool calls arrive directly via Thespian `tell()`.

**Admin Port**: Use a fixed port (default 19500) via `capabilities={'Admin Port': 19500}`.
Do NOT use `transientUnique=True` — child processes (the MCP server) cannot discover a
random-port Admin. Pass `--admin-port` to `maverick serve-inbox` so it connects to the
same Admin.

**Stale Admin Cleanup**: The Admin daemon survives the parent process. Always call
`asys.shutdown()` in a finally block. Register an `atexit` handler as backup. On startup,
check if the port is occupied and shut down any stale Admin before creating a new one.

**Async Bridge in Actor Processes**: ACP's `prompt_session()` is async but Thespian's
`receiveMessage` is synchronous. Use a persistent background event loop:

```python
# In actor __init__ or init message handler:
self._loop = asyncio.new_event_loop()
self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
self._thread.start()

# In message handler:
future = asyncio.run_coroutine_threadsafe(self._do_prompt(), self._loop)
result = future.result(timeout=1800)
```

Do NOT use `asyncio.run()` — it tears down async generators (ACP's stdio transport) on
completion, causing `RuntimeError: aclose(): asynchronous generator is already running`.
The persistent loop keeps the event loop alive across multiple message handlers.

**Timeout Guidance**: Decomposition prompts on large flight plans take 10-20 minutes.
Set `StepConfig(timeout=1800)` for prompt_session calls. Set `asys.ask(timeout=3600)`
for the overall supervisor workflow.

**globalName Discovery**: The MCP server discovers the supervisor via
`asys.createActor(SupervisorClass, globalName='supervisor-inbox')` which returns the
existing actor, not a new one. No serialized addresses needed.

**Module Importability**: Thespian actor classes MUST be importable by forked child
processes. Actor modules must be in an installed package (on `sys.path`). Defining
actors in `__main__` or uninstalled modules causes `InvalidActorSpecification`.

**Self-Contained Actors**: Each agent actor MUST own its own ACP agent subprocess.
Do NOT share executors, sessions, or connections between actor processes.

Standard agent actor lifecycle:

| Phase | What happens |
|-------|-------------|
| **init** | Create persistent event loop + thread. Set `_executor = None`, `_session_id = None`. |
| **first prompt** | `_ensure_executor()` lazily creates executor (spawns ACP agent subprocess). `_new_session()` creates fresh ACP session with MCP config. |
| **subsequent prompts** (same bead/task) | Reuse executor + session. Agent remembers conversation context. |
| **new bead/task** | `_new_session()` creates fresh session on existing connection. Agent subprocess stays alive; only the conversation resets. |
| **shutdown** | `executor.cleanup()` kills ACP agent subprocess. Only called on explicit "shutdown" message from supervisor. |
| **ActorSystem shutdown** | Thespian kills the actor OS process. |

Key rules:
- Do NOT call `executor.cleanup()` after every prompt — agent subprocess must persist
- Do NOT recreate the executor per prompt — use `_ensure_executor()` (lazy, once)
- Supervisors MUST send `{"type": "shutdown"}` to all agent actors before sending
  `{"type": "complete"}` to the workflow — this ensures clean ACP subprocess teardown
- ACP connections are cached per provider; sessions are cheap to create

### ACP Stream Buffer

The ACP transport uses newline-delimited JSON over stdio. The default asyncio
`StreamReader` limit (64KB) can overflow when agents produce large tool-call
messages (e.g., Write tool with full file contents). The executor sets a 1MB
buffer limit via `transport_kwargs={"limit": 1_048_576}` to handle this.

### Agent Tool Configuration

- Specify `allowed_tools` explicitly (principle of least privilege)
- For agents that only need to read: `allowed_tools=["Read", "Glob", "Grep"]`
- For agents that produce file artifacts: add `"Write"` to allowed_tools
- Only include `"Bash"` when the agent needs to run commands

## CLI Output Guidelines

All CLI output MUST use Rich `console` / `err_console` from `maverick.cli.console`.
Never use `click.echo()` or `print()` for user-facing output.

### Output Principles

1. **Human-readable phase names** — use natural language ("Gathering context..."), not
   snake_case identifiers (`gather_context`).
2. **No implementation labels** — don't show `(python)` or `(agentic)`. The user doesn't
   care whether a phase runs Python or an agent.
3. **No emoji** — use Rich markup for emphasis (`[green]✓[/]`, `[red]✗[/]`), not emoji
   characters (no 🤖, no 🎉).
4. **Structured warnings** — never let raw structlog lines leak into the CLI output.
   Format warnings with `[yellow]Warning:[/yellow]` Rich markup.
5. **Progress for fan-out** — when multiple agents run in parallel, use Rich Live to
   show a table that updates in place as results arrive.
6. **Completion-only for sequential ops** — for single-agent steps, show one line when
   done with timing (`✓ Outline (312.0s)`), not separate start/end lines.

### Formatting Patterns

```python
from maverick.cli.console import console, err_console

# Phase headers
console.print("[bold cyan]Maverick Init[/]")

# Success
console.print("[green]✓[/] Configuration written to [bold]maverick.yaml[/]")

# Errors (always to stderr)
err_console.print("[red]Error:[/red] bd is not available")

# Warnings
console.print("[yellow]Warning:[/yellow] No git remote configured")

# Hints / dim text
console.print("[dim]Tip: Run 'maverick runway seed' to populate knowledge store[/]")

# Agent fan-out progress (Rich Live)
from rich.live import Live
from rich.table import Table

with Live(console=console, refresh_per_second=4) as live:
    table = _build_agent_table(agents_status)
    live.update(table)
```

### Agent Fan-Out Rendering (Rich Live)

When multiple agents run concurrently (briefing room, decompose detail pass), render
a Rich Live table that updates in place:

```
Briefing
  Navigator        228.4s  ✓
  Structuralist    208.7s  ✓
  Recon             ⠙
  Contrarian             (waiting)
```

- Show all agents immediately (pending = `(waiting)`, active = spinner, done = timing + ✓)
- Update individual rows as results arrive
- Freeze the table when all agents complete, then resume normal sequential output

### Phase Output Structure

```
Phase Name...
  Key detail or summary line
  ✓ Sub-result (timing)

Phase Name (N agents)
  ┌─────────────────────────────┐
  │ Agent table (Rich Live)     │
  └─────────────────────────────┘
  Summary: N decisions, M risks
```

## Code Style

| Element   | Convention           | Example                            |
| --------- | -------------------- | ---------------------------------- |
| Classes   | PascalCase           | `CodeReviewerAgent`, `FlyWorkflow` |
| Functions | snake_case           | `execute_review`, `create_pr`      |
| Constants | SCREAMING_SNAKE_CASE | `MAX_RETRIES`, `DEFAULT_TIMEOUT`   |
| Private   | Leading underscore   | `_build_prompt`, `_validate_input` |

- Docstrings: Google-style format with Args, Returns, Raises sections
- Exceptions: Hierarchy from `MaverickError` → `AgentError`, `WorkflowError`, `ConfigError`
- No `print()` for output; use logging or Rich Console
- No `shell=True` in subprocess calls without explicit security justification

## Debt Prevention Guidelines

Analysis of past technical debt (#61-#152) reveals recurring patterns. Strict adherence to these rules prevents debt accumulation.

### 1. Testing is Not Optional (Anti-Deferral)

- No PR shall be merged without passing **new** tests covering added functionality
- Do not comment out or skip failing tests; fix them immediately (including failures that predate your change)
- For async components (Agents/Workflows), test concurrency and error states, not just happy paths

### 2. Modularize Early (Keep Files Small)

Long, multi-responsibility modules are a primary driver of slow iteration and merge conflicts. Treat file growth as a design smell.

- **Soft limit**: aim for modules < ~500 LOC and test modules < ~400–600 LOC.
- **Refactor trigger**: if a module exceeds ~800 LOC or has many unrelated top-level definitions, split it as part of the change (or create a `tech debt` issue scoped to the split).
- **Hard stop**: avoid adding new features to modules > ~1000 LOC without first carving out a focused submodule/package.
- **Single responsibility**: each module/package should have one “reason to change” (one domain, one layer, one cohesive feature area).

### 3. Preferred Split Patterns (Repository-Specific)

Use these patterns to prevent the common “god file” failures seen in this repo:

- **CLI**: keep `src/maverick/main.py` as a thin entrypoint; put each Click command in `src/maverick/cli/commands/<command>.py`; keep shared Click options/error handling in `src/maverick/cli/common.py`.
- **Workflows**: use a package-per-workflow (`src/maverick/workflows/<name>/`) and split into `models.py`, `events.py`, `dsl.py`/`constants.py`, and `workflow.py`.
- **Tools (MCP servers)**: split into a package with `runner.py` (subprocess), `errors.py`, `responses.py`, `prereqs.py`, `server.py`, and per-resource tool modules.
- **DSL execution**: isolate per-step-type execution logic into handler modules; keep the executor/coordinator readable and small.
- **Tests**: split by unit-under-test and scenario group; move shared fixtures/factories into a local `conftest.py` (directory-scoped) instead of copy/paste.

### 4. Backwards-Compatible Refactors

When splitting a public module, preserve import stability:

- Prefer creating a package and re-exporting the current public surface from `__init__.py`.
- If external consumers import from the old module path, keep a small shim module that imports/re-exports from the new package for a migration period.
- Maintain `__all__` (or equivalent explicit exports) so the public API stays intentional and discoverable.

### 5. Zero-Tolerance for Duplication (DRY)

- If logic (Git operations, Validation, GitHub API calls) is needed in a second location, **refactor to a shared utility immediately**—do not wait for "cleanup"
- Use Mixins or Composition over inheritance for shared agent capabilities

### 6. Hardening by Default (Anti-Assumption)

- All external calls (GitHub API, Git subprocesses) **MUST** have:
  - Explicit timeouts
  - Retry logic with exponential backoff for network operations
  - Specific exception handling (no bare `except Exception`)

### 7. Type Safety & Constants

- No magic numbers or string literals in logic code; extract to named constants or configuration
- Use `Protocol` (structural typing) to define interfaces between components to avoid circular dependencies

### 8. Documentation Integrity

- Treat documentation examples as code—where possible, add tests that validate code snippets in `README.md` or `docs/quickstart.md`

## Architectural Guardrails (Non-Negotiables)

These “truisms” are required to preserve the clarity and layer boundaries described in `.specify/memory/constitution.md` and the Slidev training. If a change would violate any item below, stop and refactor the design before proceeding.

### 1. Async-first means "no blocking on the event loop"

- Never call `subprocess.run` from an `async def` path.
- Prefer `CommandRunner` (`src/maverick/runners/command.py`) for subprocess execution with timeouts.
- DSL `PythonStep` callables MUST be async, or must be run off-thread (e.g., `asyncio.to_thread`) to avoid blocking workflows.

### 2. Deterministic ops belong to workflows/runners, not agents

- Agents provide judgment (implementation/review/fix suggestions). They MUST NOT own deterministic side effects like git commits/pushes or running validation.
- Workflows (or DSL steps/actions) own deterministic execution, retries, checkpointing, and error recovery policies.

### 3. Actions must have a single, typed contract

- Workflow actions MUST not return ad-hoc `dict[str, Any]` blobs.
- Use one canonical contract:
  - preferred: frozen dataclasses (with `to_dict()` for DSL serialization), or
  - acceptable: `TypedDict` + validation at boundaries.
- Keep action outputs stable across versions; treat them as public interfaces.

### 4. Resilience features must be real, not stubs

- “Retry/fix loops” and “recovery” must actually invoke the fixer/retry validation or be removed.
- If the DSL/workflow definition is the right place for retry logic, implement it there rather than simulating it in a Python action.

### 5. One canonical wrapper per external system

- Do not create new `git`/`gh`/validation subprocess wrappers in random modules.
- Prefer:
  - `src/maverick/runners/**` for deterministic execution + parsing
  - `src/maverick/tools/**` for MCP surfaces (delegate to runners/utilities)
  - `src/maverick/dsl/context_builders.py` for context composition (delegate; no subprocess re-implementation)

### 6. Tool server factories must be async-safe and consistent

- Factory functions MUST NOT call `asyncio.run()` internally.
- Prefer lazy prerequisite verification on first tool use, or provide an explicit async `verify_prerequisites()` API callers can `await`.
- Return concrete, correct types (avoid `Any` on public APIs).

### 7. Workspace isolation requires explicit cwd threading

All DSL steps that operate inside a hidden workspace MUST receive `cwd` pointing to the
workspace path. Without it, agents and validators silently operate on the user's working
directory instead.

- Agent steps: pass `cwd` in the step's `context` dict
- Validate steps: pass `cwd` via the workflow/fragment `inputs` (not `kwargs` — ValidateStepRecord doesn't support kwargs)
- Review actions: pass `cwd` to `gather_local_review_context()` and `run_review_fix_loop()`
- jj actions: pass `cwd` (accepts `str | Path | None`); `_make_client` coerces with `Path(cwd)`

See `.specify/memory/constitution.md` Appendix E for the full architecture.

### 8. DSL expressions resolve to strings — coerce at boundaries

All `${{ }}` expressions resolve to JSON-serializable types (strings). Action handlers MUST
coerce to native Python types:

```python
# Path coercion — DSL passes string, code needs Path
cwd = Path(input_cwd) if input_cwd else Path.cwd()

# Integer coercion — YAML int fields cannot accept ${{ }} expressions
# Use hardcoded values or pass through inputs with explicit int() conversion
```

Violations cause `AttributeError: 'str' object has no attribute 'is_dir'` or similar.

## Workflows

Maverick uses a beads-only workflow model. All development is driven by beads (units of work managed by the `bd` CLI tool). All three workflows use the actor-mailbox pattern with MCP tool-based communication.

### CLI Commands

| Command | Purpose |
|---------|---------|
| `maverick plan generate <name> --from-prd <file>` | Generate flight plan from PRD |
| `maverick refuel <plan-name>` | Decompose flight plan into beads |
| `maverick fly --epic <id>` | Implement beads (actor-mailbox supervisor) |
| `maverick land [--eject\|--finalize]` | Curate history and merge |
| `maverick serve-inbox --tools <list>` | MCP supervisor inbox server (internal) |
| `maverick workspace status\|clean` | Manage hidden workspace |
| `maverick init` | Initialize a new Maverick project |
| `maverick brief [--watch]` | Review bead status |
| `maverick runway seed\|consolidate` | Manage knowledge store |

### fly (Bead-Driven Development)

Iterates over ready beads. Each bead is processed by a BeadSupervisor using the actor-mailbox pattern:

1. **Preflight**: Check prerequisites
2. **Create workspace**: Clone via `jj git clone` into `~/.maverick/workspaces/<project>/`
3. **Bead Loop**: Select bead → BeadSupervisor processes it:
   - ImplementerActor (persistent ACP session, calls `submit_implementation` MCP tool)
   - GateActor (deterministic: build/lint/test)
   - ReviewerActor (persistent ACP session, calls `submit_review` MCP tool)
   - CommitActor (jj commit)
   - Review negotiation happens via messages within the bead — no follow-up beads

The supervisor routes messages: implement → gate → review → (fix loop if needed) → commit.
Implementer and reviewer share persistent sessions — no context loss between rounds.

Options: `--epic`, `--max-beads` (default 30), `--dry-run`, `--auto-commit`

### land (Curate and Push)

Finalizes work from `fly` by reorganizing commits into clean history and pushing. Three modes:

- **Approve** (default): curate → interactive prompt → `jj git push` → teardown workspace
- **Eject** (`--eject`): curate → push preview branch → keep workspace
- **Finalize** (`--finalize`): create PR from preview branch → teardown

Uses an AI agent (CuratorAgent) for intelligent reorganization, with user approval. Falls back to git push when no workspace exists.

Options: `--no-curate`, `--dry-run`, `--yes`/`-y`, `--base` (default "main"), `--heuristic-only`, `--eject`, `--finalize`, `--branch`

### Review-and-Fix with Registry Fragment

Accountability-tracked code review workflow fragment (`src/maverick/library/fragments/review-and-fix-with-registry.yaml`):

1. **Gather Context**: Collect PR diff, changed files, and spec files
2. **Parallel Reviews**: Run spec and technical reviewers concurrently
3. **Create Registry**: Merge findings into IssueRegistry with deduplication
4. **Detect Deleted Files**: Auto-block findings for deleted files
5. **Fix Loop**: Iterate until all actionable items resolved or max iterations:
   - Prepare fixer input with attempt history
   - Run ReviewFixerAgent with accountability
   - Update registry with outcomes
   - Check exit conditions
6. **Create Tech Debt Issues**: GitHub issues for blocked/deferred findings

Key accountability features:
- Fixer must report on EVERY issue (no silent skipping)
- Deferred items with invalid justifications are re-sent
- Blocked items require valid technical justification
- Full attempt history preserved for debugging
- Unresolved items become GitHub tech-debt issues

## Dependencies

- [uv](https://docs.astral.sh/uv/) for dependency management (`uv sync`)
- [Make](https://www.gnu.org/software/make/) for development commands (see Development Commands section)
- [GitHub CLI](https://cli.github.com/) (`gh`) for PR and issue management
- Optional: [CodeRabbit CLI](https://coderabbit.ai/) for enhanced code review
- Optional: [ntfy](https://ntfy.sh) for push notifications

## Multi-Repository Development

Maverick development involves two distinct repositories. **Never confuse them.**

| Repository | Purpose | Remote URL |
|------------|---------|------------|
| **maverick** | Core CLI application | `get2knowio/maverick.git` |
| **sample-maverick-project** | E2E test project | `get2knowio/sample-maverick-project.git` |

### Branch Naming Conventions

- **Maverick branches**: `###-feature-name` where `###` >= 020 (e.g., `030-tui-streaming`)
- **Sample project branches**: `###-feature-name` where `###` starts at 001 (e.g., `001-greet-cli`)

**CRITICAL**: Before pushing any branch, verify you're in the correct repository:

```bash
git remote -v  # Check remote URL
pwd            # Check working directory
```

**Do NOT push sample project branches (001-xxx) to the maverick repository.** This causes
confusion and requires cleanup. See `.specify/memory/constitution.md` Appendix D for full
conventions and recovery procedures.

## Active Technologies
- Python 3.11+ with `from __future__ import annotations`
- Agent Client Protocol (ACP) via `agent-client-protocol` SDK + `claude-agent-acp` subprocess
- MCP SDK for supervisor inbox tool server
- Thespian actor framework for cross-process actor messaging
- Click + Rich for CLI, Pydantic for models, structlog for logging
- Jujutsu (jj) for VCS writes, GitPython for VCS reads
- Beads via `bd` CLI for work unit management

## Recent Changes
- All workflows use Thespian actor system exclusively (no legacy fallbacks)
- Rich Live CLI output with agent fan-out rendering
- Parallel decomposer pool for detail pass
- Self-contained actors (create own ACP executors)
- Completeness enforcement in agent prompts
