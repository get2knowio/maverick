# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project Overview

Maverick is a Python CLI that orchestrates AI-powered development workflows
via the Agent Client Protocol (ACP). It runs PRD → plan → beads → implement →
review → commit using an actor-mailbox architecture with MCP tool-based
agent output.

## Technology Stack

| Category         | Technology                            | Module / Notes                              |
| ---------------- | ------------------------------------- | ------------------------------------------- |
| Language         | Python 3.11+                          | `from __future__ import annotations`        |
| Package Manager  | uv                                    | reproducible via `uv.lock`                  |
| Build            | Make                                  | AI-friendly minimal-noise targets           |
| AI / Agents      | ACP SDK + `claude-agent-acp`          | bridge subprocess per agent                 |
| Actors           | xoscar                                | `n_process=0`, in-pool coroutines           |
| MCP              | MCP SDK + shared HTTP gateway         | `maverick.tools.agent_inbox`                |
| CLI              | Click + Rich                          | `maverick.cli.console`                      |
| Validation       | Pydantic                              | config + data models                        |
| Testing          | pytest + pytest-asyncio + xdist       | parallel via `-n auto`                      |
| Lint / Type      | ruff / mypy (strict)                  | —                                           |
| VCS writes       | Jujutsu (jj)                          | `maverick.jj.client.JjClient`               |
| VCS reads        | GitPython                             | `maverick.git`                              |
| Workspaces       | WorkspaceManager                      | hidden jj clones in `~/.maverick/workspaces/` |
| GitHub API       | PyGithub                              | `maverick.utils.github_client`              |
| Logging          | structlog                             | `maverick.logging.get_logger`               |
| Retry            | tenacity                              | `AsyncRetrying`                             |
| Secrets          | detect-secrets                        | `maverick.utils.secrets`                    |

## Third-Party Library Standards

These libraries are canonical for their domains. Do **not** introduce
alternatives or hand-rolled equivalents.

- **jj** for all write-path VCS (`commit`, `push`, `merge`, `branch`). Never
  shell out to `git` for writes. Requires colocated mode.
- **GitPython** for read-only git ops (diff, status, log, blame). Works
  unchanged in colocated mode.
- **PyGithub** for all GitHub API ops. Never `subprocess.run("gh ...")` for
  things PyGithub supports.
- **structlog** via `maverick.logging.get_logger` for all logging. Never
  `import logging; logging.getLogger(__name__)`.
- **tenacity** (`AsyncRetrying`) for retries. Never write
  `for attempt in range(retries):` loops by hand.
- **detect-secrets** via `maverick.utils.secrets.detect_secrets` before
  commits. Never write custom regex patterns for secret detection.

## Architecture

```
src/maverick/
├── main.py              # Click entrypoint
├── config.py            # Pydantic config models
├── exceptions/          # MaverickError hierarchy
├── types.py / events.py / results.py / constants.py
├── actors/xoscar/       # supervisors + agent + deterministic actors
├── agents/              # prompt builders (HOW)
├── executor/            # ACP step executor + provider registry
├── jj/ vcs/             # JjClient + VcsRepository protocol
├── workspace/           # WorkspaceManager (hidden jj clones)
├── workflows/           # plan_generate / refuel_maverick / fly_beads / ...
├── tools/agent_inbox/   # shared HTTP MCP gateway
├── runners/             # CommandRunner, provider_health, validation
├── library/actions/     # typed action layer (jj, git, beads, runway, ...)
├── runway/              # episodic + semantic knowledge store
├── hooks/ utils/        # safety hooks; shared helpers
```

### Separation of concerns

- **Actors** — `xo.Actor` subclasses owning state, exposing typed `async def`
  methods. Agent actors hold persistent ACP sessions; deterministic actors
  wrap pure async Python.
- **Supervisors** — `xo.Actor` with `@xo.generator run()` yielding
  `ProgressEvent`s, plus typed domain methods child actors invoke.
- **Agents** — know HOW (prompts, tool selection). Don't own orchestration.
- **Workflows** — know WHAT/WHEN. Create the actor pool, send "start", wait
  for "complete".
- **MCP tools** — the supervisor's inbox. Agents deliver structured results
  via tool calls; the gateway validates schemas.
- **JjClient** — typed jj wrapper with retries/timeouts/error hierarchy.
- **WorkspaceManager** — lifecycle for hidden jj workspaces.

### Three information types

| Type     | Lifecycle                                  | Examples                       |
| -------- | ------------------------------------------ | ------------------------------ |
| Beads    | Created at refuel, closed at commit        | "Implement UID sync"           |
| Files    | Survives restarts, durable context         | Flight plans, work units, configs |
| Messages | Created/consumed within one bead/step      | Tool calls, review findings    |

## Development Commands

**IMPORTANT**: Always use `make` commands instead of `uv run` directly. The
Makefile provides AI-agent-friendly minimal output.

| Command                 | Purpose                                |
| ----------------------- | -------------------------------------- |
| `make test`             | All tests in parallel (errors only)    |
| `make test-fast`        | Unit tests, no slow tests              |
| `make test-cov`         | Tests with coverage                    |
| `make test-integration` | Integration tests only                 |
| `make lint`             | Ruff `check` (errors only)             |
| `make typecheck`        | Mypy (errors only)                     |
| `make format`           | `ruff format --check` (diff)           |
| `make format-fix`       | Apply formatting                       |
| `make check`            | lint + typecheck + test                |
| `make ci`               | CI mode: fail-fast on any error        |
| `make VERBOSE=1 test`   | Full output for debugging              |

**Before pushing**: run `make ci` (or `make format-fix && make ci`).
`make lint` runs `ruff check` but **not** `ruff format --check` — CI's
`make ci-coverage` runs both, so a push that passed `make lint` locally can
still fail CI on formatting. Treat `make ci` as the pre-push gate;
`make lint`/`typecheck`/`test-fast` are iteration-time checks.

## Core Principles

See `.specify/memory/constitution.md` for the authoritative reference.

1. **Async-first** — all agent + workflow paths are async. No threading for I/O.
2. **Dependency injection** — agents/workflows receive config + deps; no global state.
3. **Fail gracefully** — one agent failing must not crash the workflow.
4. **Test-first** — every public class/function has tests; TDD red-green-refactor.
5. **Type safety** — full type hints; `@dataclass` / Pydantic over `dict`.
6. **Simplicity** — no global mutable state, no god-classes, no premature abstractions.
7. **Complete work** — each bead is self-contained. No TODO/FIXME/HACK punts;
   the workflow runs autonomously with no human watching.

## Operating Standard (Ownership & Follow-Through)

Default stance: full ownership of repo state. "Not my problem" is not
acceptable.

- **Do what's asked, then keep going** — finish the requested change, then
  fix collateral failures and obvious correctness issues you encountered.
- **Fix what you find** — broken tests, lint, type, or flaky behaviour gets
  fixed even if it predates your change.
- **Keep the tree green** — don't rationalize failures as "unrelated."
- **No artificial scope minimization** — prefer complete robust solutions
  over narrow patches unless explicitly told otherwise.
- **No deferral by difficulty** — "too hard" means decompose, not stop.
- **Only defer when truly blocked** (missing access, non-reproducible). When
  deferring, document what's blocked and the next concrete step.

## ACP Execution Model

All agent execution goes through `maverick.executor.acp.AcpStepExecutor`.
Don't bypass with raw `claude -p` calls — ACP provides connection caching,
retries, circuit breakers, event streaming, and provider abstraction.

### Multi-turn sessions

`create_session()` + `prompt_session()` keep conversation history across
prompts. Used by the actor-mailbox architecture so implementer/reviewer
context survives fix rounds.

### MCP tool-based agent output (shared HTTP gateway)

Agents deliver structured results via MCP tool calls, not JSON-in-text. The
actor pool owns one in-process `AgentToolGateway` bound to `127.0.0.1:0`.
Each agent actor registers under `/mcp/<actor-uid>` in `__post_create__`
and unregisters in `__pre_destroy__`. The gateway routes incoming tool
calls to that actor's `on_tool_call`. The MCP protocol provides schema
guidance; the gateway validates via `jsonschema.validate()`.

Encapsulation contract — every agentic actor owns:
1. **Schemas** — `mcp_tools: ClassVar[tuple[str, ...]]` (or `_mcp_tools()`).
2. **Handler** — `on_tool_call(name, args) -> str`, decorated `@xo.no_lock`.
3. **Session/turn state** — ACP session id, turn count, mode.
4. **The ACP executor** — the bridge subprocess hosting the LLM.

Only MCP transport (subprocess + routing) lives in the shared gateway;
subclasses inherit `AgenticActorMixin` for register/unregister.

**Do** define agent output as MCP tool schemas in
`maverick.tools.agent_inbox.schemas`. **Don't** use Pydantic `output_schema`
for mailbox actors — it appends a JSON schema to the prompt and validates
against a Pydantic model, but agents return slightly different field shapes
and there's no recovery loop. The MCP tool schemas are the single source of
truth. (`output_schema` is fine for non-mailbox plain-text steps.)

Built-in tools (Read/Write/Edit/Bash/Glob/Grep) do work in the workspace.
MCP tools (`submit_outline`, `submit_review`, …) deliver results to the
supervisor.

**Adding a new agent**:
1. Define an MCP tool schema in `agent_inbox.schemas` and register it in
   `ALL_TOOL_SCHEMAS`.
2. Subclass `AgenticActorMixin`, declare `mcp_tools`.
3. Call `await self._register_with_gateway()` from `__post_create__` and
   `await self._unregister_from_gateway()` from `__pre_destroy__`.
4. Pass `self.mcp_server_config()` to `executor.create_session(mcp_servers=…)`.
5. Implement `@xo.no_lock`-decorated `on_tool_call`. (Subclasses overriding
   it MUST keep the decorator — otherwise the ACP turn deadlocks against
   the actor's own `send_*` method.)

**Provider MCP reliability**: Claude reliably calls MCP tools; Copilot's
ACP bridge currently doesn't, and Gemini's CLI honours static `mcpServers`
in its settings.json but not session-level `mcp_servers` from ACP. Don't
route mailbox actors through providers that drop MCP — use Claude or
Copilot for reviewer/implementer tiers, with the JSON-in-text fallback as
defence-in-depth.

### Actor-mailbox + xoscar runtime

All workflows run on an **xoscar** pool (`maverick.actors.actor_pool()`)
bound to `127.0.0.1:0` (concurrent workflows coexist). Pool uses
`n_process=0` — all actors are coroutines on a shared event loop. Per-actor
process isolation comes from each agent's ACP subprocess.

- Supervisor created via
  `await xo.create_actor(Supervisor, inputs, address=address, uid=…)` and
  drained via `self._drain_xoscar_supervisor(supervisor)`. Children are
  created in `__post_create__` and destroyed in `__pre_destroy__` (which
  reaps the ACP subprocess).
- Wrap long-running child calls in **`xo.wait_for`** (not
  `asyncio.wait_for` — xoscar has a documented pitfall where
  `asyncio.wait_for` around a remote call can lose the timeout if the pool
  hangs).
- Async generators across actor refs require `@xo.generator` on the source
  and `async for event in await ref.run(...)` (note `await` before the
  loop) on the consumer.
- `await xo.destroy_actor(ref)` runs `__pre_destroy__`. `await pool.stop()`
  alone does NOT — supervisors destroy children explicitly on completion.
- The parent process must keep its asyncio loop running:
  `subprocess.Popen.communicate()` blocks the loop and starves both the
  in-process uvicorn gateway and the ACP bridge. Use
  `asyncio.create_subprocess_exec` instead.

Standard agent-actor lifecycle:

| Phase                | What happens                                             |
| -------------------- | -------------------------------------------------------- |
| `__post_create__`    | Init `_executor=None`, `_session_id=None`, register MCP. |
| First prompt         | `_ensure_executor()` lazily spawns ACP subprocess; `_new_session()` creates session with MCP config pointing at this actor's uid. |
| Subsequent prompts   | Reuse executor + session.                                |
| New bead             | `new_bead(request)` rotates the session.                 |
| `__pre_destroy__`    | `executor.cleanup()` kills ACP subprocess.               |

Rules:
- Do **not** call `executor.cleanup()` after every prompt.
- Do **not** recreate the executor per prompt — `_ensure_executor()` is lazy.
- Supervisors send `{"type": "shutdown"}` to all agent actors before
  `{"type": "complete"}` so ACP subprocesses tear down cleanly.

### ACP stream buffer

ACP transport is newline-delimited JSON over stdio. Default `StreamReader`
limit (64 KB) overflows on large tool calls (e.g. Write with full file
contents). The executor sets `transport_kwargs={"limit": 1_048_576}` (1 MB).

### Agent tool config

- Specify `allowed_tools` explicitly (least privilege).
- Read-only agents: `["Read", "Glob", "Grep"]`.
- File-producing agents: add `"Write"`.
- Only include `"Bash"` when the agent runs commands.

## CLI Output

All output uses Rich `console` / `err_console` from `maverick.cli.console`.
Never `click.echo()` or `print()`.

- **Human-readable phase names** ("Gathering context..."), not snake_case.
- **No implementation labels** — don't show `(python)` / `(agentic)`.
- **No emoji** — use Rich markup (`[green]✓[/]`, `[red]✗[/]`).
- **Structured warnings** — never let raw structlog leak. Format with
  `[yellow]Warning:[/yellow]`.
- **Fan-out progress** — Rich Live table for parallel agents (briefing,
  decompose detail), updates in place. Show all agents immediately
  (pending = `(waiting)`, active = spinner, done = timing + ✓).
- **Sequential ops** — single completion line with timing
  (`✓ Outline (312.0s)`), not separate start/end.

## Code Style

| Element   | Convention           | Example                        |
| --------- | -------------------- | ------------------------------ |
| Classes   | PascalCase           | `CodeReviewerAgent`            |
| Functions | snake_case           | `execute_review`               |
| Constants | SCREAMING_SNAKE_CASE | `MAX_RETRIES`                  |
| Private   | Leading underscore   | `_build_prompt`                |

- Docstrings: Google style (Args / Returns / Raises).
- Exceptions: hierarchy from `MaverickError`.
- No `print()` for output; use logging or Rich console.
- No `shell=True` without explicit security justification.

## Debt Prevention

1. **Tests are not optional** — no merge without new tests; never skip
   failing tests, fix them.
2. **Modularize early** — soft limit ~500 LOC per module; refactor at
   ~800 LOC; hard stop on adding features to >1000 LOC modules without
   first carving out a submodule.
3. **Preferred splits**:
   - CLI: thin `main.py`; one Click command per
     `cli/commands/<name>.py`; shared options in `cli/common.py`.
   - Workflows: package per workflow with `models.py`, `events.py`,
     `constants.py`, `workflow.py`.
   - MCP servers: package with `runner.py`, `errors.py`, `responses.py`,
     `prereqs.py`, `server.py`, per-resource tool modules.
   - Tests: split by unit + scenario; shared fixtures in directory-scoped
     `conftest.py`.
4. **Backwards-compatible refactors** — when splitting a public module,
   create a package and re-export from `__init__.py`; keep shim modules
   for migration.
5. **No duplication** — if logic is needed in a second place, refactor to
   a shared utility immediately. Mixins/composition over inheritance for
   shared agent capabilities.
6. **Hardening by default** — every external call has explicit timeouts,
   tenacity retries with exponential backoff, and specific exception
   handling (no bare `except Exception`).
7. **Type safety** — extract magic numbers/strings to named constants.
   Use `Protocol` (structural typing) for component interfaces to avoid
   circular deps.

## Architectural Guardrails (Non-Negotiables)

If a change would violate any item, stop and refactor the design first.

### 0. Workspace-as-remote architecture

Long-running ops (`plan generate`, `refuel`, `fly`) run inside a hidden jj
workspace under `~/.maverick/workspaces/<project>/`. The user's repo is the
remote — cloned-from at start, pushed-to at command completion.

**Hermetic shape** (`plan generate`, `refuel`):
1. `WorkspaceManager.find_or_create()` — create or attach.
2. Sync from origin (handled inside `find_or_create`).
3. Do the work in the workspace.
4. `WorkspaceManager.finalize(message=…)` — snapshot, push to user repo on
   `maverick/<project>` bookmark, merge into the user's branch (jj rebase
   in colocated mode, `git merge` fallback), tear down.

Failure during finalize **preserves the workspace** so the user can
recover (`cd ~/.maverick/workspaces/<project> && jj git push`).

**Bridged shape** (`fly` + `land`): fly doesn't finalize — its commits
need curation, which is `land`'s job. Fly leaves the workspace alive; land
curates, pushes, tears down. Cancellation (Ctrl-C) and failures during fly
also preserve the workspace so completed beads remain available to land.
Do **not** register a workspace-teardown rollback on fly.

**Implications**:
- Every workflow/CLI command takes a `WorkspaceContext` (or `cwd: Path`)
  and threads it through every state-touching action (bd, runway, plans,
  jj). `Path.cwd()` defaults inside `src/maverick/workflows/` or
  `src/maverick/actors/` are a layering smell.
- All commit-graph mutations go through `JjClient` or actions in
  `library/actions/jj.py`. Do NOT add new subprocess wrappers around
  `git commit/push/merge/branch`. The dead helpers (`git_commit`,
  `git_push`, etc.) were deleted because every layer-violation bug traced
  back to them.
- `actions/git.py` is read-only and merge-fallback only (`git_has_changes`,
  `git_merge`); reads otherwise go through GitPython.
- Workspace bridging helpers (`apply_to_user_repo`,
  `cleanup_user_repo_branch`, `finalize`) live on `WorkspaceManager`.
  Don't reimplement them in commands.

Per-invocation hermetic workspaces are tracked in `FUTURE.md` — don't add
that ad-hoc.

### 1. Async-first means no blocking on the event loop

- Never call `subprocess.run` from an `async def` path.
- Prefer `CommandRunner` (`runners/command.py`) for subprocess execution
  with timeouts.

### 2. Deterministic ops belong to workflows/runners, not agents

Agents provide judgment (implementation, review, fix suggestions). They
must NOT own deterministic side effects (commits, pushes, validation).
Workflows own deterministic execution, retries, checkpointing, and error
recovery policy.

### 3. Actions have a single typed contract

No ad-hoc `dict[str, Any]` blobs. Use frozen dataclasses (with `to_dict()`
where needed) or `TypedDict` validated at boundaries. Treat action outputs
as public interfaces.

### 4. Resilience features must be real, not stubs

Retry/fix loops must actually invoke the fixer/retry path or be removed.
No simulated retries.

### 5. One canonical wrapper per external system

No new `git`/`gh`/validation subprocess wrappers in random modules. Use
`runners/**` for execution + parsing and `tools/**` for MCP surfaces
(delegating to runners, not re-implementing).

### 6. Tool-server factories are async-safe

No `asyncio.run()` inside factory functions. Prefer lazy prerequisite
verification on first use, or an explicit async `verify_prerequisites()`.
Return concrete types (avoid `Any` on public APIs).

### 7. Workspace isolation requires explicit cwd threading

Operational form of Guardrail 0. Every step inside the workspace receives
a `cwd` (or `WorkspaceContext`) pointing at the workspace path:

- Agent steps: `cwd` in the step's `context` dict.
- jj actions: `cwd` (accepts `str | Path | None`).
- bd / runway / plan parsing: `cwd=ws_cwd` — never default to `Path.cwd()`.

A grep for `Path.cwd()` inside `src/maverick/workflows/` or
`src/maverick/actors/` should return ~zero hits in a clean tree; new
occurrences are bugs in waiting.

See `.specify/memory/constitution.md` Appendix E for the full architecture.

## CLI Workflows

Beads-only workflow model. All development is driven by beads (`bd` CLI).

| Command                                              | Purpose                              |
| ---------------------------------------------------- | ------------------------------------ |
| `maverick plan generate <name> --from-prd <file>`    | Flight plan from PRD                 |
| `maverick refuel <plan-name>`                        | Decompose plan into beads            |
| `maverick fly --epic <id>`                           | Implement beads (actor-mailbox)      |
| `maverick land [--eject\|--finalize]`                | Curate history and merge             |
| `maverick workspace status\|clean`                   | Manage hidden workspace              |
| `maverick init`                                      | Initialize a Maverick project        |
| `maverick brief [--watch]`                           | Bead status                          |
| `maverick runway seed\|consolidate`                  | Manage knowledge store               |

### fly

Iterates over ready beads. For each: `Implementer → Gate → Reviewer →
(fix loop if needed) → Commit`. Implementer + reviewer share persistent
ACP sessions across fix rounds. Options: `--epic`, `--max-beads` (default
30), `--auto-commit`. Ctrl-C is a two-stage signal: first sets a graceful
stop flag (finishes current bead, exits cleanly); second cancels the run.

### land

Three modes: `--approve` (default; curate → push → teardown),
`--eject` (curate → push preview branch, keep workspace), `--finalize`
(create PR from preview branch → teardown). Uses CuratorAgent for
intelligent reorg, with user approval. Falls back to git push when no
workspace exists.

## Dependencies

- [uv](https://docs.astral.sh/uv/) for dependencies (`uv sync`).
- [Make](https://www.gnu.org/software/make/) for development commands.
- [GitHub CLI](https://cli.github.com/) (`gh`) for PRs/issues outside the
  PyGithub-covered surface.
- Optional: [CodeRabbit CLI](https://coderabbit.ai/), [ntfy](https://ntfy.sh).

## Multi-Repository Development

Maverick development involves two repos. **Never confuse them.**

| Repository                  | Remote                                |
| --------------------------- | ------------------------------------- |
| **maverick**                | `get2knowio/maverick.git`             |
| **sample-maverick-project** | `get2knowio/sample-maverick-project.git` |

Branch numbering: maverick uses `###-feature-name` with `### >= 020`;
sample project uses `### >= 001`.

**Before pushing any branch**, verify the repo:

```bash
git remote -v
pwd
```

Don't push sample-project branches (001-xxx) to maverick. See
`.specify/memory/constitution.md` Appendix D for recovery procedures.
