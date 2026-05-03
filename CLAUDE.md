# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project Overview

Maverick is a Python CLI that orchestrates AI-powered development workflows
on top of an OpenCode HTTP runtime. It runs PRD → plan → beads → implement →
review → commit using an actor-mailbox architecture; mailbox actors return
typed payloads via OpenCode's structured-output tool rather than per-agent
MCP gateways.

## Technology Stack

| Category         | Technology                            | Module / Notes                              |
| ---------------- | ------------------------------------- | ------------------------------------------- |
| Language         | Python 3.11+                          | `from __future__ import annotations`        |
| Package Manager  | uv                                    | reproducible via `uv.lock`                  |
| Build            | Make                                  | AI-friendly minimal-noise targets           |
| Agent runtime    | OpenCode HTTP (`opencode serve`)      | one server per workflow run                 |
| HTTP client      | httpx                                 | `maverick.runtime.opencode.OpenCodeClient`  |
| Actors           | xoscar                                | `n_process=0`, in-pool coroutines           |
| Structured output| Pydantic + `format=json_schema`       | `maverick.payloads`                         |
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
├── config.py            # Pydantic config models (incl. ProviderTiersConfig)
├── exceptions/          # MaverickError hierarchy
├── types.py / events.py / results.py / constants.py / payloads.py
├── runtime/opencode/    # OpenCode HTTP client, server lifecycle, tiers
├── actors/xoscar/       # supervisors + agent + deterministic actors
├── agents/              # prompt builders (HOW)
├── executor/            # StepExecutor protocol + OpenCode-backed default
├── jj/ vcs/             # JjClient + VcsRepository protocol
├── workspace/           # WorkspaceManager (hidden jj clones)
├── workflows/           # plan_generate / refuel_maverick / fly_beads / ...
├── runners/             # CommandRunner, process_group, provider_health
├── library/actions/     # typed action layer (jj, git, beads, runway, ...)
├── runway/              # episodic + semantic knowledge store
├── hooks/ utils/        # safety hooks; shared helpers
```

### Separation of concerns

- **Actors** — `xo.Actor` subclasses owning state, exposing typed `async def`
  methods. Agent actors hold a persistent OpenCode session; deterministic
  actors wrap pure async Python.
- **Supervisors** — `xo.Actor` with `@xo.generator run()` yielding
  `ProgressEvent`s, plus typed domain methods child actors invoke.
- **Agents** — know HOW (prompts, role). Don't own orchestration.
- **Workflows** — know WHAT/WHEN. Create the actor pool (which spawns one
  OpenCode server), send "start", wait for "complete".
- **Structured output** — mailbox actors declare a `result_model` Pydantic
  class; OpenCode's `format=json_schema` synthesizes a `StructuredOutput`
  tool the model is forced to call. Payloads round-trip via
  `maverick.payloads.SubmitXxxPayload`.
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

## OpenCode Runtime

All mailbox actors execute via the OpenCode HTTP runtime
(`maverick.runtime.opencode`). One `opencode serve` subprocess runs per
workflow run, spawned by `actor_pool()` on a free port with HTTP Basic
auth (username `opencode`, per-spawn random `OPENCODE_SERVER_PASSWORD`).
Mailbox actors share that one server; each actor owns its own
`OpenCodeClient` and session.

### Mailbox actor contract

Each agentic actor inherits from `OpenCodeAgentMixin` and declares:

```python
class CodeReviewerActor(OpenCodeAgentMixin, xo.Actor):
    result_model: ClassVar[type[BaseModel]] = SubmitReviewPayload
    provider_tier: ClassVar[str] = "review"  # role tier (see Provider Tiers)
```

The mixin provides:

- `_send_structured(prompt, *, schema=None, timeout=...)` — sends the
  prompt with `format=json_schema` derived from `result_model` (or the
  per-call `schema=` override), runs the cascade, validates the response,
  returns the typed payload.
- `_send_text(prompt, *, timeout=...)` — plain-text response, no schema.
- `_rotate_session()` — drop the OpenCode session so the next send opens a
  fresh one (used by `new_bead`).

What the mixin **doesn't** provide (what the legacy ACP+MCP path had and
the new path doesn't need): MCP tool registration, `on_tool_call`,
two-turn self-nudge loop, JSON-in-text fallback. The
`StructuredOutput` tool forces the model to return a typed payload on
the first turn — the recovery loops are dead code.

### Three operational landmines (and their mitigations)

The OpenCode HTTP API has three sharp edges. Every mitigation is wired
into `maverick.runtime.opencode` already; if you find yourself writing
HTTP calls outside that module, you'll re-introduce one of these.

1. **Async dispatch + bad `modelID` = persistent server crash loop.**
   `POST /session/:id/prompt_async` with an invalid model returns
   HTTP 200 but persists the user message to the on-disk DB and crashes
   the server in the background. Restart replays it and crashes again.
   *Mitigation:* always validate the model via `validate_model_id()`
   before sending, and prefer `send_with_event_watch()` (synchronous)
   over `send_message_async()` for load-bearing work. Recovery runbook
   for an existing crash loop: `python /tmp/opencode-spike/purge_queued.py`.

2. **Errors are silent on the synchronous HTTP response.** A bad
   `modelID`, bad provider auth, or context overflow returns HTTP 200
   with an empty body. Errors only surface on the `/event` SSE stream as
   `session.error` events. *Mitigation:*
   `OpenCodeClient.send_with_event_watch()` joins the send call to a
   parallel event-drain and raises classified exceptions
   (`OpenCodeAuthError`, `OpenCodeModelNotFoundError`,
   `OpenCodeContextOverflowError`, etc.) instead of returning empty
   bodies. Don't bypass it.

3. **Claude wraps StructuredOutput payloads inconsistently.** Roughly 30%
   of haiku-4.5 responses come back as `{input: {...}}`,
   `{parameter: {...}}`, `{content: '<json-string>'}`, etc. *Mitigation:*
   `_unwrap_envelope()` in `client.py` strips the wrapper before
   `model_validate`. Treat it as a permanent client-side normalization
   layer — always go through `structured_of(message)` rather than
   reading `info["structured"]` directly.

### Provider tiers + cascade

Each actor's `provider_tier` is a role name (`"review"`, `"implement"`,
`"briefing"`, `"decompose"`, `"generate"`). The runtime resolves the tier
to an ordered list of `(provider_id, model_id)` bindings via
`maverick.runtime.opencode.tiers.resolve_tier()`. Defaults live in
`DEFAULT_TIERS`; users override per-tier in `maverick.yaml` under
`provider_tiers:`.

When a binding fails for a recoverable reason (auth /
model-not-found / sustained transient / structured-output failure) the
mixin's `_send_with_model` falls over to the next binding via
`cascade_send`. Failed bindings stick — future sends on the same actor
skip them without retry. Each successful send populates
`self._last_cost_record` and emits an `opencode_actor.cost` structured
log row.

Context-overflow is intentionally NOT cascadable; it needs a bigger
context model, not a different one. Callers handle it explicitly.

### Actor-mailbox + xoscar runtime

All workflows run on an **xoscar** pool
(`maverick.actors.xoscar.pool.actor_pool()`) bound to `127.0.0.1:0` — so
concurrent workflows coexist. Pool uses `n_process=0`, all actors run as
coroutines on a shared event loop. The pool also spawns one OpenCode
server (`with_opencode=True` is the default) and registers its handle
plus any user-config tier overrides on the pool address.

- Supervisor created via
  `await xo.create_actor(Supervisor, inputs, address=address, uid=…)` and
  drained via `self._drain_xoscar_supervisor(supervisor)`. Children are
  created in `__post_create__` and destroyed in `__pre_destroy__`.
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
  `subprocess.Popen.communicate()` blocks the loop and starves the
  OpenCode subprocess. Use `asyncio.create_subprocess_exec` instead.

Standard mailbox-actor lifecycle:

| Phase                | What happens                                              |
| -------------------- | --------------------------------------------------------- |
| `__post_create__`    | `await self._opencode_post_create()` — init lazy state.   |
| First send           | `_build_client()` looks up `opencode_handle_for(self.address)`, opens a session. |
| Subsequent sends     | Reuse the same session.                                   |
| New bead             | `_rotate_session()` deletes the current session; the next send opens a new one. |
| `__pre_destroy__`    | `await self._opencode_pre_destroy()` — delete session, close client. |

### Adding a new mailbox actor

1. Define a payload model in `maverick.payloads` and register it in
   `SUPERVISOR_TOOL_PAYLOAD_MODELS` (the dict keys are kept stable for
   the briefing actor's per-instance schema lookup).
2. Subclass `OpenCodeAgentMixin, xo.Actor`. Declare:
   - `result_model: ClassVar[type[BaseModel]]` — the payload Pydantic class.
   - `provider_tier: ClassVar[str]` — role name keyed into `DEFAULT_TIERS`
     (or null out for special cases).
3. In `__post_create__` call `await self._opencode_post_create()`. In
   `__pre_destroy__` call `await self._opencode_pre_destroy()`.
4. Implement your supervisor-facing methods (`send_review`, `send_fix`,
   etc.) by calling `await self._send_structured(prompt)` and forwarding
   the typed payload to a supervisor RPC.
5. Decorate methods that are reverse-called by the supervisor with
   `@xo.no_lock` (so they don't deadlock against the actor lock held by
   the in-flight `send_*`).

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

### 0. Single-repo (CWD) workflow model

All long-running ops (`plan generate`, `refuel`, `fly`, `land`) operate
directly in the user's checkout under `Path.cwd()`. There is no
hidden workspace, no clone bridge, and no `WorkspaceManager`. Plans,
beads, runway, and per-run metadata land in `<cwd>/.maverick/{plans,
runs, runway}/` and survive across runs without any sync step.

**Shape** (every long-running op):
1. CLI resolves `cwd = Path.cwd().resolve()`.
2. The workflow executes inside `cwd`.
3. Bead commits go straight onto the user's current branch.
4. The user pushes / opens a PR when they're ready (or runs
   `maverick land --eject` / `--finalize` for a hint).

**Implications**:
- Every workflow/CLI command takes `cwd: Path` (or `WorkspaceContext`,
  whichever the older code paths still use) and threads it through every
  state-touching action (bd, runway, plans, jj). `Path.cwd()` defaults
  inside `src/maverick/workflows/` or `src/maverick/actors/` are a
  layering smell — set them at the CLI boundary and pass them down.
- All commit-graph mutations go through `JjClient` or actions in
  `library/actions/jj.py`. The vcs-neutral
  `snapshot_uncommitted_changes` helper detects `.jj/` and dispatches
  to either jj or plain-git so a non-colocated user repo doesn't
  crash on `jj diff --stat`.
- `actions/git.py` is read-only and merge-fallback only
  (`git_has_changes`, `git_merge`); reads otherwise go through GitPython.
- Bead commits carry both the `bead(<id>): <title>` subject prefix
  (curator-greppable) and a `Bead: <id>` git trailer (forward-compatible
  with the env-aware ready check).

**Background**: an earlier revision ran every long-running op inside a
hidden jj workspace under `~/.maverick/workspaces/<project>/` with a
`WorkspaceManager` bridging clone-from → finalize → push. That dual-repo
pattern was the root of a cluster of 2026-05-02 bugs (workspace
identity mismatch, stale dolt routing, gitignore confusion). The full
pull-work-push architecture envisioned in
`.claude/scratchpads/architecture-pull-work-push.md` re-introduces a
hermetic per-invocation workspace eventually; until then, single-repo
is the contract. Don't reach for the legacy concepts (`WorkspaceManager`,
`apply_to_user_repo`, `finalize`) — they no longer exist.

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

### 7. Explicit cwd threading

Operational form of Guardrail 0. Every step receives a `cwd` (or
`WorkspaceContext`) the CLI resolved at the boundary:

- Agent steps: `cwd` in the step's `context` dict.
- jj actions: `cwd` (accepts `str | Path | None`).
- bd / runway / plan parsing: `cwd=cwd` — never default to `Path.cwd()`.

A grep for `Path.cwd()` inside `src/maverick/workflows/` or
`src/maverick/actors/` should return ~zero hits in a clean tree; new
occurrences are bugs in waiting. The motivation survives the
single-repo collapse: even when `cwd == Path.cwd()` today,
threading the path explicitly keeps test isolation, future per-
invocation workspaces, and concurrent runs all unblocked.

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
OpenCode sessions across fix rounds (rotated per bead via
`_rotate_session()`). Options: `--epic`, `--max-beads` (default 30),
`--auto-commit`. Ctrl-C is a two-stage signal: first sets a graceful stop
flag (finishes current bead, exits cleanly); second cancels the run.

### land

Three modes: `--approve` (default; curate → push → teardown),
`--eject` (curate → push preview branch, keep workspace), `--finalize`
(create PR from preview branch → teardown). Uses CuratorAgent for
intelligent reorg, with user approval. Falls back to git push when no
workspace exists.

## Dependencies

- [uv](https://docs.astral.sh/uv/) for dependencies (`uv sync`).
- [Make](https://www.gnu.org/software/make/) for development commands.
- [opencode](https://opencode.ai) — agent runtime; pinned to v1.14.x.
  `opencode auth login <provider>` populates
  `~/.local/share/opencode/auth.json` so OpenCode can route to live
  models. The runtime spawns one server per workflow run.
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
