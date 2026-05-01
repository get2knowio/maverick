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
| Actor Framework | xoscar                  | Async-native in-pool actors (`n_process=0`) |
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
├── actors/              # xoscar actor definitions (xoscar/ subpackage)
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
│   └── agent_inbox/         # Shared HTTP MCP gateway for actor communication
│       ├── gateway.py       # AgentToolGateway (uvicorn ASGI app, per-actor /mcp/<uid>)
│       ├── schemas.py       # Tool schemas (full inbox vocabulary)
│       └── models.py        # Pydantic intake models for tool payloads
├── hooks/               # Safety and logging hooks
└── utils/               # Shared utilities
```

### Separation of Concerns

- **Actors**: ``xo.Actor`` subclasses that own state and expose typed ``async def`` methods. Agent actors hold persistent ACP sessions and an MCP inbox; deterministic actors wrap Python functions.
- **Supervisors**: ``xo.Actor``s that orchestrate a workflow via typed RPC to children and emit ``ProgressEvent``s through an ``@xo.generator`` ``run()`` method consumed by the workflow.
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

### MCP Tool-Based Agent Output (Shared HTTP Gateway)

Agents communicate structured results to the supervisor via MCP tool calls, not JSON
in text responses. A single in-process :class:`AgentToolGateway` (`maverick.tools.agent_inbox.gateway`)
hosts an HTTP MCP server bound to `127.0.0.1:0` per actor pool. Each agentic actor
registers its tool subset under `/mcp/<actor-uid>` in `__post_create__`; the gateway
routes each incoming tool call to the right actor's ``on_tool_call`` handler. The MCP
protocol provides schema guidance; the gateway validates via ``jsonschema.validate()``
and returns errors for self-correction.

Encapsulation contract — every agentic actor still owns:
1. **Schemas** — declared via the ``mcp_tools: ClassVar[tuple[str, ...]]`` attribute
   (or returned from ``_mcp_tools()`` for instance-variant declarations).
2. **Handler** — ``on_tool_call(name, args) -> str``; receives parsed tool arguments
   and forwards a typed payload to the supervisor.
3. **Session/turn state** — ACP session ID, mode rotation, turn count.
4. **The ACP executor** — the bridge subprocess that hosts the LLM.

Only the MCP transport (subprocess + routing) lives in the shared gateway. Subclasses
inherit :class:`AgenticActorMixin`, which handles inbox registration in
``__post_create__`` and unregistration in ``__pre_destroy__``.

**Do**: Define agent output as MCP tool schemas in `maverick.tools.agent_inbox.schemas`.
**Don't**: Use `output_schema` (Pydantic model validation) for mailbox/MCP-tool agent
responses. That pattern appends a JSON schema to the prompt and validates the response
against a Pydantic model — but agents frequently return slightly different field names
or structures, causing `OutputSchemaValidationError` at runtime with no recovery loop.
The MCP tool schemas are the single source of truth for structured output; Pydantic
models add a second, conflicting contract.

`output_schema` remains valid for non-mailbox, plain text-response steps that intentionally
return structured JSON in text.

Built-in tools (Read, Write, Edit, Bash, Glob, Grep) are for doing work in the workspace.
MCP tools (submit_outline, submit_review, etc.) are for sending results to the supervisor.

**Every agent actor MUST use an MCP tool to deliver results.** When adding a new agent:
1. Define an MCP tool schema in `maverick.tools.agent_inbox.schemas`
2. Register it in `ALL_TOOL_SCHEMAS`
3. Subclass ``AgenticActorMixin`` and declare ``mcp_tools: ClassVar[tuple[str, ...]]``
   (or override ``_mcp_tools()``)
4. Call ``await self._register_with_gateway()`` from ``__post_create__`` and
   ``await self._unregister_from_gateway()`` from ``__pre_destroy__``
5. Pass ``self.mcp_server_config()`` to ``executor.create_session(mcp_servers=[...])``
6. Implement ``on_tool_call(name, args)`` decorated ``@xo.no_lock`` (subclass override
   must keep the decorator — otherwise the ACP turn deadlocks against the actor's own
   send_* method)

**Provider compatibility**: Claude reliably calls MCP tools. Copilot agents currently do not
call MCP tools in ACP sessions — use the text fallback path for Copilot-routed steps.

### Actor-Mailbox Architecture

All three workflows (plan, refuel, fly) use a supervisor that orchestrates typed
calls between actors:

- **Agent actors** (implementer, reviewer, decomposer, briefing, generator): Persistent
  ACP sessions; register their tool handler with the shared :class:`AgentToolGateway`
  via :class:`AgenticActorMixin`. Their ``on_tool_call`` handler parses the tool
  payload and forwards typed results to the supervisor via in-pool RPC
  (e.g. ``await self._supervisor_ref.outline_ready(payload)``).
- **Deterministic actors** (gate, validator, bead creator, committer, ac_check,
  spec_check, plan_validator, plan_writer): Pure async Python, no ACP session, no
  inbox registration — the supervisor calls a typed method and awaits the typed result
- **Supervisor**: ``xo.Actor`` with an ``@xo.generator run()`` method that yields
  ``ProgressEvent``s to the workflow, and typed domain methods (``outline_ready``,
  ``review_ready``, etc.) that child actors invoke

### xoscar Actor System

All workflows run on an **xoscar** actor pool (see
``src/maverick/actors/xoscar/``). The pool is created per workflow run via
``maverick.actors.actor_pool()`` bound to an ephemeral port
(``127.0.0.1:0``) — two concurrent workflows can coexist with no
port-coordination problem. Per-actor process isolation comes from the
ACP agent subprocess each agent actor owns, not from the actor runtime
(the pool uses ``n_process=0``: every actor is a coroutine in a shared
event loop).

**Pool lifecycle**: workflows use the ``actor_pool()`` async context
manager. The supervisor is created via
``await xo.create_actor(Supervisor, inputs, address=address, uid=...)``
and drained via ``self._drain_xoscar_supervisor(supervisor)`` on
``PythonWorkflow``. Children are created in ``__post_create__`` and
destroyed in ``__pre_destroy__`` (which reaps each agent actor's ACP
subprocess).

**Shared HTTP MCP gateway**: the actor pool owns one in-process
:class:`AgentToolGateway` (``maverick.tools.agent_inbox.gateway``) bound to
``127.0.0.1:0``. Each agent actor registers its tool subset under
``/mcp/<agent_uid>`` via :class:`AgenticActorMixin` in
``__post_create__`` and unregisters in ``__pre_destroy__``. The
gateway routes incoming tool calls back to that actor's
``on_tool_call`` method, which parses the payload and forwards a typed
call to the supervisor (``await self._supervisor_ref.outline_ready(payload)``).
The supervisor exposes only typed domain methods — **no**
``on_tool_call`` — so its surface stays dict-free. The actor still
owns its schemas, handler, session state, and ACP executor; only the
MCP transport lives in shared infrastructure.

**Cancellation and timeouts**: wrap any long-running child call in
``xo.wait_for`` (not ``asyncio.wait_for`` — xoscar has a documented
pitfall where ``asyncio.wait_for`` around a remote call can lose the
timeout if the pool hangs). ``xo.wait_for(child.send_detail(req),
timeout=STALE_IN_FLIGHT_SECONDS)`` cancels the remote coroutine
cleanly; the actor method observes ``asyncio.CancelledError``. The
STALE watchdog that existed under Thespian is replaced by per-call
timeouts on the fan-out tasks.

**Async generators across actor refs**: a supervisor's ``run()`` must
be decorated with ``@xo.generator``; callers consume via
``async for event in await supervisor_ref.run(...)`` (note the
``await`` before the loop). Plain ``AsyncGenerator`` returns do not
stream across an actor ref — this is a published xoscar API
constraint.

**Teardown**: ``await xo.destroy_actor(ref)`` runs ``__pre_destroy__``
before removing the actor. ``await pool.stop()`` alone does NOT invoke
``__pre_destroy__`` per actor — supervisors destroy their children
explicitly on completion so each agent's ACP subprocess is reaped
cleanly.

**Cross-process / async-loop constraint**: the parent process hosting
the pool must keep its asyncio loop running. The shared
:class:`AgentToolGateway` runs an in-process uvicorn server, and the
``claude-agent-acp`` Node bridge subprocess connects back to it over
loopback HTTP — both depend on the parent's loop being responsive.
``subprocess.Popen.communicate()`` blocks the loop and starves both;
use ``asyncio.create_subprocess_exec`` instead. The ACP executor and
the gateway already follow this rule.

Standard agent actor lifecycle:

| Phase | What happens |
|-------|-------------|
| **``__post_create__``** | Initialise state: ``_executor = None``, ``_session_id = None``, plus any caches. |
| **first prompt** | ``_ensure_executor()`` lazily creates the ACP executor (spawns ACP agent subprocess). ``_new_session()`` creates a fresh ACP session with MCP config pointing at this actor's own uid. |
| **subsequent prompts** (same bead/task) | Reuse executor + session. Agent remembers conversation context. |
| **new bead/task** | ``new_bead(request)`` rotates the session; agent subprocess stays alive. |
| **``__pre_destroy__``** | ``await self._executor.cleanup()`` kills the ACP agent subprocess. Runs automatically when the supervisor destroys the child on completion. |

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

### 0. Architecture A — Maverick operates in a workspace; the user repo is its remote

Long-running operations (`plan generate`, `refuel`, `fly`) run inside a hidden jj workspace under `~/.maverick/workspaces/<project>/`. The user's repo is treated like a remote: cloned-from at start, pushed-to at the natural completion of each command.

**Hermetic command shape** (current model — `plan generate`, `refuel`):

1. `WorkspaceManager.find_or_create()` — create workspace or attach to existing.
2. `sync_from_origin()` — pull any user-repo edits into the workspace (handled inside `find_or_create()` on attach).
3. Do the work inside the workspace.
4. `WorkspaceManager.finalize(message=...)` — snapshot, push to user repo on `maverick/<project>` bookmark, merge into the user's current branch (jj rebase if colocated, `git merge` fallback), tear down the workspace.

Failure during finalize preserves the workspace so the user can recover (`cd ~/.maverick/workspaces/<project> && jj git push`).

**Bridged command shape** (`fly` + `land`):

`fly` doesn't finalize on its own — its commits need curation, which is `land`'s job. Fly leaves the workspace alive; land curates, pushes, and tears down. This is the one remaining special case where two commands share a workspace.

**Implications for new code**:

- Every workflow/CLI command takes a `WorkspaceContext` (or `cwd: Path`) and threads it through every action that touches state — bd, runway, plans, run logs, jj. Default-`Path.cwd()` calls inside `src/maverick/workflows/` and `src/maverick/actors/` are a layering smell.
- All commit-graph mutations go through `JjClient` (or actions in `src/maverick/library/actions/jj.py`). Do **not** add new `subprocess` wrappers around `git commit/push/merge/branch` in actions or workflows. The dead helpers (`git_commit`, `git_push`, `git_add`, etc.) were deleted because every layer-violation bug traced back to them — don't reintroduce them.
- `actions/git.py` is now scoped to read-only and merge-fallback only (`git_has_changes`, `git_merge`). Reads still go through GitPython where possible.
- The shared workspace bridging helpers live on `WorkspaceManager` — `apply_to_user_repo`, `cleanup_user_repo_branch`, `finalize`. Don't re-implement them in commands.
- v1 stores workspace state locally — switching machines mid-flight starts a fresh workspace.

Fly remains the bridged exception today (its commits need curation by `land`). The future direction toward fully hermetic per-invocation workspaces is captured in `FUTURE.md` under "Per-invocation hermetic workspaces" — don't add per-invocation workspace logic ad-hoc; it should land as one coordinated change.

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

This is the operational form of Guardrail #0. Every step operating inside the workspace MUST receive a `cwd` (or `WorkspaceContext`) pointing to the workspace path. Without it, agents, bd, runway recording, and validators silently operate on the user's working directory.

- Agent steps: pass `cwd` in the step's `context` dict
- Validate steps: pass `cwd` via the workflow/fragment `inputs`
- Review actions: pass `cwd` to `gather_local_review_context()` and `run_review_fix_loop()`
- jj actions: pass `cwd` (accepts `str | Path | None`); `_make_client` coerces with `Path(cwd)`
- bd / runway / plan parsing: pass `cwd=ws_cwd` (or `ctx.cwd` from `BeadContext`) — never default to `Path.cwd()`

A grep for `Path.cwd()` inside `src/maverick/workflows/` or `src/maverick/actors/` should return ~zero results in a clean tree; new occurrences are bugs in waiting.

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

Options: `--epic`, `--max-beads` (default 30), `--auto-commit`

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
- xoscar actor framework for in-pool async actor messaging
- Click + Rich for CLI, Pydantic for models, structlog for logging
- Jujutsu (jj) for VCS writes, GitPython for VCS reads
- Beads via `bd` CLI for work unit management

## Recent Changes
- All workflows migrated to xoscar (Thespian removed in Phase 4)
- Rich Live CLI output with agent fan-out rendering
- Parallel decomposer pool for detail pass
- Self-contained actors (create own ACP executors)
- Completeness enforcement in agent prompts
