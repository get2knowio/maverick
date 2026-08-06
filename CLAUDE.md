# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project Overview

Maverick is a Python CLI that orchestrates AI-powered development workflows
on top of the **airframe** agent-runtime abstraction. It runs PRD → spec →
beads → implement → review → commit as **Burr** state machines; agents return
typed Pydantic payloads via airframe's structured-output support rather than
per-agent MCP gateways.

**The Spec Kit path is the default.** `maverick spec` produces
`specs/NNN-name/{spec.md,tasks.md}` and `maverick refuel --speckit` ingests
them into beads deterministically, with zero model calls. The classic
flight-plan path (`plan generate` → `refuel`) remains fully supported for
repositories without Spec Kit artifacts — it is a fallback, not deprecated.
See constitution Principle XIII and Appendix F.

## Technology Stack

| Category         | Technology                            | Module / Notes                              |
| ---------------- | ------------------------------------- | ------------------------------------------- |
| Language         | Python 3.11+                          | `from __future__ import annotations`        |
| Package Manager  | uv                                    | reproducible via `uv.lock`                  |
| Build            | Make                                  | AI-friendly minimal-noise targets           |
| Agent runtime    | airframe (`airframe.AgentRuntime`)    | `maverick.runtime.agent_factory`            |
| Orchestration    | Burr state machines                   | `maverick.burr` + `workflows/*/burr_graph.py` |
| Structured output| Pydantic result models                | `maverick.payloads`                         |
| CLI              | Click + Rich                          | `maverick.cli.console`                      |
| Validation       | Pydantic                              | config + data models                        |
| Testing          | pytest + pytest-asyncio + xdist       | parallel via `-n auto`                      |
| Lint / Type      | ruff / mypy (strict)                  | —                                           |
| VCS writes       | Jujutsu (jj)                          | `maverick.jj.client.JjClient`               |
| VCS reads        | GitPython                             | `maverick.git`                              |
| Workspaces       | spec-chain only                       | `maverick.workspace.spec_chain`             |
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
├── config.py            # Pydantic config models (agents:, actors:, tiers)
├── exceptions/          # MaverickError hierarchy
├── types.py / events.py / results.py / constants.py / payloads.py
├── runtime/             # agent_factory (role → airframe runtime), registry
├── burr/                # BurrWorkflowDriver + ProgressEventHook
├── squadron/            # per-workflow agent sets + shared tier helpers
├── agents/              # Agent subclasses: prompts + role (HOW)
├── executor/            # StepConfig resolution
├── jj/ vcs/             # JjClient + VcsRepository protocol
├── workspace/           # spec-chain workspace (Guardrail 0's one exception)
├── workflows/           # generate_flight_plan / refuel_maverick / fly_beads / ...
│                        #   each: actions.py (@action fns) + burr_graph.py (wiring)
├── runners/             # CommandRunner, process_group, provider_health
├── library/actions/     # typed action layer (jj, git, beads, runway, ...)
├── runway/              # episodic + semantic knowledge store
├── hooks/ utils/        # safety hooks; shared helpers
```

### Separation of concerns

- **Actions** — plain `async def` functions decorated with Burr's
  `@action(reads=[...], writes=[...])`. They own one step of a workflow and
  read/write only the state slots they declare.
- **Burr graphs** — `build_*_application()` wires actions into a state
  machine with explicit transitions. This is where control flow lives.
- **Agents** — know HOW (prompts, role, result model). Don't own
  orchestration.
- **Squadrons** — per-run container owning every agent a workflow needs,
  plus their airframe runtimes. Opened once per run, handed to the graph.
- **Workflows** — know WHAT/WHEN. Open the squadron, build the app, drain
  its events through `BurrWorkflowDriver`.
- **Structured output** — agents declare a `result_model` Pydantic class;
  airframe forces the model to return it. Payloads round-trip via
  `maverick.payloads.SubmitXxxPayload`.
- **JjClient** — typed jj wrapper with retries/timeouts/error hierarchy.

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
8. **Determinism over inference** — where a structured artifact already carries
   the information, parse it; don't ask a model to re-derive it. Spec Kit
   ingestion is the default path and makes zero model calls.

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

## Agent Runtime (airframe)

Every LLM call goes through **airframe**, a provider-abstraction layer.
`maverick.runtime.agent_factory.runtime_for_agent(role, ...)` maps a role
name to a constructed `airframe.AgentRuntime` plus its resolved
`(provider, model_id)` binding. There is no long-lived HTTP server and no
per-workflow subprocess to manage.

Roles are fixed: `implement`, `review`, `briefing`, `decompose`,
`generate` (`agent_factory.KNOWN_ROLES`). Each maps to an `agents.<role>`
block in `maverick.yaml`. A role with no binding raises at squadron-open
rather than silently picking a model the user never authorised — the
same reason `runtime_for_agent` validates the binding against the
adapter before returning.

### Two-layer composition: Squadron + Agent

1. **`Squadron`** (`src/maverick/squadron/`) — per-run lifecycle
   container. Builds one runtime per agent role, opens every agent, and
   closes them all on exit. Per-workflow subclasses: `FlySquadron`,
   `RefuelSquadron`, `PlanSquadron`, `ReconcileSquadron`.
2. **`Agent`** (`src/maverick/agents/`) — owns its runtime scope,
   structured-output validation, and cost telemetry. Subclass `Agent`,
   declare `result_model` / `provider_tier` / `persona_name`, add domain
   methods (`coder.implement(prompt)`).

```python
async with FlySquadron(cwd=cwd, config=config, cost_sink=sink) as squadron:
    app = build_fly_application(squadron=squadron, event_queue=queue, ...)
    driver = BurrWorkflowDriver(app, halt_after=FLY_TERMINAL_ACTIONS, event_queue=queue)
    async for evt in driver.events():
        ...
    _, _, state = driver.result
```

Agent base-class helpers: `_execute_via_runtime()` (structured),
`_execute_text_via_runtime()` (plain text), `rotate_session()` (fresh
context between beads), `open()` / `close()` + `async with`.

### Per-complexity tiers

`actors.<workflow>.<actor>.tiers.<complexity>` routes work to a
different provider/model by the decomposer-assigned `complexity`.
Three actors support it: fly's `implementer` and `reviewer`, refuel's
`decomposer`.

- `maverick.config.lookup_tiers_config()` parses the block into its
  typed model. Malformed blocks degrade to `None` with a warning — one
  typo must not take down workflow startup.
- `maverick.squadron.tiers` holds everything shared: `TIER_ORDER`,
  the `DEFAULT_TIER` sentinel (`"_default"` — the role's base binding,
  deliberately *not* a member of `TIER_ORDER`), `binding_for_complexity()`,
  `defined_tiers()`, `escalation_ladder()`, `merge_tier_config()`.
- **Escalation ladders come from the squadron, never hardcoded.** A rung
  may only name a tier the squadron built a *distinct* binding for, so a
  squadron with no `tiers:` config yields a one-rung ladder and nothing
  escalates. Escalating to an identical binding is a retry in disguise,
  and it hides the fact that the binding never varied.
- `escalation_threshold` means different things on different models
  ("escalation steps" on `DecomposerTiersConfig`, "fix rounds before
  promoting" on `ImplementerTiersConfig`), so `escalation_ladder()` takes
  an explicit `max_steps` instead of reading it. The implementer reading
  is currently unimplemented.

### Burr orchestration

Each workflow is a package with `actions.py` (`@action` functions) and
`burr_graph.py` (`build_*_application()` + transitions + terminal
actions). `maverick.burr.BurrWorkflowDriver` runs the app and yields
`ProgressEvent`s while it goes.

- **The driver defers exceptions.** An action that raises does *not*
  interrupt `driver.events()`; the exception is stored and re-raised
  when you touch `driver.result`. Tests that assert on a raising action
  must drain the events first, then access `.result`.
- Actions declare `reads` / `writes` explicitly. Adding a state slot
  means adding it to the producing action's `writes`, every consumer's
  `reads`, *and* the graph's `.with_state(...)` seed.
- Keep actions pure functions of state plus injected collaborators
  (`squadron`, `events`, config values) bound via `.bind(...)` in the
  graph. Disk and network reads belong in one place — see
  `refuel_maverick`'s `init_state`, which is the only action that reads
  the refuel cache.

### Adding a new agent

1. Define a payload model in `maverick.payloads` and register it in
   `SUPERVISOR_TOOL_PAYLOAD_MODELS` (keys are stable — the briefing
   agent does a per-instance schema lookup against them).
2. Add an `Agent` subclass under `src/maverick/agents/<role>.py`:
   declare `result_model` / `provider_tier` / `persona_name`, and
   implement domain methods that call `_execute_via_runtime(...)` and
   return the typed payload.
3. Build it in the workflow's `Squadron` subclass via
   `runtime_for_agent(<role>, agents_config=self._config.agents)`,
   and make sure `_all_agents()` yields it so `close()` tears it down.
4. Call it from an `@action` in the workflow's `actions.py`, and wire
   that action into `burr_graph.py`.

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

### 0. Single-repo (CWD) workflow model, jj-colocated

All long-running ops (`plan generate`, `refuel`, `fly`, `land`)
operate directly in the user's checkout under `Path.cwd()`. There
is no hidden workspace, no clone bridge, no `WorkspaceManager`.
Plans, beads, runway, and per-run metadata land in
`<cwd>/.maverick/{plans, runs, runway}/` and survive across runs
without any sync step.

**Shape** (every long-running op):
1. `maverick init` runs `jj git init --colocate` if `.jj/` is
   missing (default-on, no opt-out). After init, the user's
   checkout has both `.git/` and `.jj/` and behaves identically to
   before for git users.
2. CLI resolves `cwd = Path.cwd().resolve()`.
3. The workflow executes inside `cwd`.
4. Bead commits go straight onto the user's current branch via
   `jj_commit_bead`.
5. The user pushes / opens a PR when they're ready.

**Implications**:
- All commit-graph mutations go through `JjClient` or actions in
  `library/actions/jj.py`. Init's colocate guarantees `.jj/` exists,
  so jj-only actions work in every command's cwd. No vcs detection
  needed.
- `actions/git.py` is read-only and merge-fallback only
  (`git_has_changes`, `git_merge`); reads otherwise go through GitPython.
- Bead commits carry both the `bead(<id>): <title>` subject prefix
  (curator-greppable) and a `Bead: <id>` git trailer (forward-compatible
  with the env-aware ready check).
- Every workflow/CLI command receives `cwd: Path` from the CLI
  boundary. `Path.cwd()` defaults inside `src/maverick/workflows/` are a
  layering smell — set them at the CLI boundary and pass them down.

**Background — what was tried and rejected**: an earlier revision ran
every long-running op inside a hidden jj workspace under
`~/.maverick/workspaces/<project>/`. Two implementations were
attempted: `jj git clone` (clone-based, drifted on bd state — gone in
`cf11db4`) and `jj workspace add` (workspace-add, shared backing repo
— gone in this slice because bd's gitignored `embeddeddolt/` doesn't
travel with `jj workspace add` and bd can't function in the
workspace). The workspace pattern is theoretically clean but has an
impedance mismatch with bd that's bigger than this slice can absorb.
The full pull-work-push architecture in
`.claude/scratchpads/architecture-pull-work-push.md` solves it via bd
federation; until that lands, single-repo is the contract.

**Scoped exception — `maverick spec` (spec 050-headless-spec-chain)**:
the headless Spec Kit chain (`specify → clarify → plan → tasks →
analyze`) runs inside a hidden jj workspace at
`~/.maverick/workspaces/<project-slug>/spec-chain/<feature>/`
(`src/maverick/workspace/spec_chain.py`), one exception to the model
above. Rationale: each step mutates `specs/` and `.specify/` state over
a multi-minute model call, and only a completed step's artifacts may
land in the user's checkout — running in-checkout would expose
half-written files mid-run. The bd/`embeddeddolt/` impedance mismatch
that retired the general-purpose workspace above does **not** apply
here: the chain never runs `bd` inside the workspace — all bead/ledger
writes (assumption-ledger entries, remediation beads) happen in the
user's checkout via the workflow, never the agent. Landing is per-step
and atomic (`src/maverick/workflows/spec_chain/landing.py`); see
`.specify/memory/constitution.md` Appendix E and
`specs/050-headless-spec-chain/research.md` R3 for the full mechanism.
Every other command still follows the single-repo model unchanged.

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

Operational form of Guardrail 0. Every step receives a `cwd`, resolved
once at the CLI boundary from `Path.cwd().resolve()`:

- Agent steps: `cwd` in the step's `context` dict.
- jj actions: `cwd` (accepts `str | Path | None`).
- bd / runway / plan parsing: `cwd=cwd` — never default to `Path.cwd()`.

A grep for `Path.cwd()` inside `src/maverick/workflows/` should return
~zero hits in a clean tree; new occurrences are bugs in waiting. The CLI
resolves the path once, then every layer beneath it operates against
that explicit path.

### 8. Deterministic ingestion over model inference

Where a structured artifact already carries the information, derive it by
parsing. A model call on a path where parsing would do is a design smell.

- Spec Kit ingestion makes **zero** model calls. `--enrich` is the only
  step permitted to touch a model, and it stays opt-in.
- **Validation must not fail on conditions no fix can close.** A check the
  fixer cannot satisfy — a cross-cutting constraint like a LOC budget or
  "lint passes" — is advisory, reported to the human, never routed into a
  fix loop.
- **Advisory findings get their own state slot.** The slot that feeds the
  fixer is exactly how an uncloseable condition reaches it; that is how
  one refuel spent its entire fix budget inventing work units for a
  criterion no unit could carry.

See `.specify/memory/constitution.md` Appendix E for the workspace
architecture and Appendix F for the two decomposition entry paths.

## CLI Workflows

Beads-only workflow model. All development is driven by beads (`bd` CLI).

**Default path** (deterministic — Spec Kit):

| Command                                              | Purpose                              |
| ---------------------------------------------------- | ------------------------------------ |
| `maverick spec <feature> --from-prd <file>`          | Headless Spec Kit chain from a PRD   |
| `maverick refuel <feature> --speckit [--dry-run\|--enrich]` | Deterministic Spec Kit ingestion |

**Fallback path** (AI decomposition — repos without `specs/`):

| Command                                              | Purpose                              |
| ---------------------------------------------------- | ------------------------------------ |
| `maverick plan generate <name> --from-prd <file>`    | Flight plan from PRD                 |
| `maverick refuel <plan-name>`                        | Decompose plan into beads            |

Mode is auto-detected from repository shape; `--speckit` forces it.

**Shared by both paths**:

| Command                                              | Purpose                              |
| ---------------------------------------------------- | ------------------------------------ |
| `maverick fly --epic <id>`                           | Implement beads (Burr drain loop)    |
| `maverick land [--eject\|--finalize] [--status] [--json]` | Curate history and merge, or query the frontier |
| `maverick reconcile [--dry-run] [--json]`            | Reapply changed human answers into jj history |
| `maverick notify [--dry-run] [--json]`               | Evaluate and deliver due assumption-ledger notifications |
| `maverick init`                                      | Initialize a Maverick project (installs the `maverick-review` skill) |
| `maverick brief [--watch\|--human]`                  | Bead status + assumption counts      |
| `maverick review <bead-id> [--answer\|--waive] [--json]` | Resolve a human-assigned bead     |
| `maverick review --spec <name> --waive <reason> [--json]` | Bulk-waive a spec's open entries |
| `maverick review --list [--status\|--spec\|--severity]... [--json]` | List ledger entries with full provenance |
| `maverick runway seed\|consolidate`                  | Manage knowledge store               |

### spec (headless Spec Kit chain)

`maverick spec <feature> --from-prd <file>` runs the target repository's
own Spec Kit chain — specify → clarify → plan → tasks → analyze —
headlessly, inside a hidden jj workspace (the one documented exception to
Guardrail 0; see above), invoking the repo's own Spec Kit command surface
via an airframe `SpecChainAgent`. That surface is resolved per step from
the workspace rather than hardcoded — `.claude/skills/speckit-<step>/SKILL.md`
(invoked `/speckit-<step>`) on Spec Kit >= 0.14, falling back to the
pre-0.14 `.claude/commands/speckit.<step>.md` (`/speckit.<step>`) — see
`workflows/spec_chain/steps.py:resolve_command`. Clarify never blocks: adopted answers
are filed as standalone assumption-ledger entries
(`assumptions.ledger.record_standalone_assumption`, no epic yet) via
question interception where the provider supports it, else by parsing
Spec Kit's non-interactive `## Clarifications` convention out of the
updated `spec.md`. A failed or blocked clarify halts the chain (exit 1);
any other mid-chain failure halts the same way; an analyze failure
degrades to a `[yellow]Warning:[/yellow]` and the chain still completes
(exit 0) — analyze findings become standalone `spec-remediation` beads
that `refuel --speckit` later adopts under the epic it creates. Chain
state is checkpointed after every step transition
(`.maverick/runs/<run-id>/spec-chain.json`); re-running `maverick spec
<feature>` (no `--from-prd` needed) auto-resumes a halted or still-running
chain from the first incomplete step, re-verifying that already-landed
artifacts still exist before trusting them. Completed-step artifacts land
in the user's `specs/NNN-<feature>/` tree as ordinary markdown, one step
at a time. `maverick init` advisory-checks Spec Kit presence and offers
to install it (`uvx --from specify-cli==<pin> specify init --here`) on
interactive TTYs. See `src/maverick/workflows/spec_chain/` (workflow,
steps, landing, clarify policy, state) and
`specs/050-headless-spec-chain/` (spec/plan/research/contracts).

### refuel (Spec Kit ingestion mode)

For Spec Kit-managed repositories (`specs/NNN-name/{spec.md,tasks.md}`),
`maverick refuel` can deterministically ingest a feature's task list
into beads instead of AI-decomposing a flight plan — zero model calls,
one epic + one task bead per open task, with IDs/phases/`[P]`
markers/file scope preserved and dependencies wired as a phase barrier.
Mode is auto-detected from repository shape or forced with `--speckit`;
`NAME` resolves via exact directory name, `NNN` prefix, or exact name
suffix. `--dry-run` previews the full plan with zero writes; `--enrich`
opts into one batched model call that attaches verification commands to
new task beads (the only step that may touch a model on this path). Delta
re-runs (e.g. after `tasks.md` grows) append only new tasks under the
existing epic — no duplicate epics. See
`src/maverick/speckit/` (parsing/detection/plan-building) and
`src/maverick/workflows/refuel_speckit/` (the workflow).

### fly

Iterates over ready beads. Drain loop is Burr-driven end to end
(`workflows/fly_beads/burr_graph.py`) — each ready bead flows through
the state machine: `Implementer → Gate → Reviewer → (fix loop if
needed) → Commit`. Implementer + reviewer share a persistent runtime
scope across fix rounds (rotated per bead via `rotate_session()`). Options:
`--epic`, `--max-beads` (default 30), `--auto-commit`. Ctrl-C is a
two-stage signal: first sets a graceful stop flag (finishes current
bead, exits cleanly); second cancels the run.

At every bead boundary (`record_outcome → reconcile_answers →
select_next_bead`) and once more at loop-exit before the aggregate
review, a thin Burr action detects answered-but-unreconciled ledger
entries (`assumptions.ledger.answered_unreconciled_entries`) and, when
any are found, runs `ReconcileWorkflow` in-process
(`workflows/fly_beads/mid_flight.py`) — closing the human-latency gap
without ever stopping the drain loop. See `### reconcile` below for the
mid-flight contract and its `reconcile.mid_flight` kill-switch.

### land

Three modes: `--approve` (default; curate → push → teardown),
`--eject` (curate → push preview branch, keep workspace), `--finalize`
(create PR from preview branch → teardown). Uses CuratorAgent for
intelligent reorg, with user approval. Falls back to git push when no
workspace exists.

Before curation, land evaluates the **assumption frontier gate**
(`assumptions.land_report.frontier`, over `ledger.report_entries()`):
any open entry of **any severity** — including low, and including open
legacy escalation beads (treated as medium) — or any answered entry
pending reconciliation (051's `answered_unreconciled_entries` predicate)
blocks the command with a per-spec table (open rows hint `maverick
review <id>`; pending-reconciliation rows hint `maverick reconcile`),
exit non-zero. There is no bypass flag — `maverick review` (answer or
waive) and `maverick reconcile` are the only ways through. `--dry-run`
still evaluates and renders but only exits non-zero at the end, after
the rest of the preview runs — this holds on all three curation paths
(no-curate, heuristic, agent).

A successful land is classified `verified` (every entry answered, or
none at all) or `conditionally-verified` (frontier empty but ≥1 entry
was waived) — printed as a banner line. Every evaluation (blocked,
dry-run, successful) renders a grouped provenance report to the
terminal and persists `.maverick/runs/<run-id>/land-report.{json,md}`
(`assumptions.land_report.build_report`/`persist_report`; schema in
`specs/052-conditional-landing/contracts/land-report-schema.md`) —
persistence failure degrades to a warning, never blocks landing. The
`--finalize` hint references the markdown artifact via `gh pr create
--body-file`. `maverick review --spec <name> --waive <reason>
[--severity low|medium|high]...` bulk-waives every open entry a spec
owns matching the severity filter (default: low only) in one
invocation — the strict any-severity gate makes clearing accepted-risk
low-severity noise a named operation rather than one-by-one.

**JSON verbs (053-assumption-review-console)**: `land --status --json`
runs the gate evaluation and builds/persists the report without
curating — a read-only frontier query (`verb: land.status`, always
exits 0 on a completed evaluation, blocked is an answer not a failure).
`land --json` (with `--yes` to skip the interactive curation-approval
prompt, which is unreachable in JSON mode) emits the same envelope
shape as every other JSON verb; a frontier refusal is `ok: false`,
`kind: frontier-blocked`, with the full report under
`error.details.report`. Both documents carry a top-level `degraded`
flag: when the ledger can't be read at all the gate degrades *open*
and materializes zero entries, so `frontier_clear` is trivially true —
consumers must read `frontier_clear && !degraded` as the landable
condition. See
`specs/053-assumption-review-console/contracts/cli-land-json.md` and
`error-envelope.md` for the full contract; `src/maverick/cli/json_output.py`
is the shared envelope/error-kind implementation every JSON verb uses.

The gate evaluation, report building, terminal rendering, and
persistence shared by `land` and `land --status` live in
`src/maverick/cli/commands/land_gate.py` — both commands import it,
neither imports the other.

### reconcile

`maverick reconcile [--dry-run]` retroactively reapplies human answers to
assumption-ledger entries whose answer changed after it was first
adopted, folding an updated correction back into jj history. Detection
is deterministic (research R1,
`assumptions.ledger.answered_unreconciled_entries`): entry
`assumption_status=answered`, normalized `assumption_answer` differs
from both the normalized adopted answer and the normalized
`assumption_reconciled_answer` idempotence guard (SC-008), and no
terminal `assumption_reconcile_status` is already set. Detected answers
are ordered earliest-in-stack-first and processed one at a time; a
mutability guard (`library.actions.jj.jj_check_mutability`) skips any
answer whose target or a descendant it would rebase is immutable,
terminal-marking it `skipped` before any mutation is attempted.

Correction (research R3, `workflows/reconcile/correction.py`) positions
an empty child on the resolved target change, hands it to
`ReconcilerAgent.correct(...)` to edit in place, then folds the delta
back via `jj squash --into` (single stamped change) or `jj absorb`
(multi-stamp entries) — the same child → agent → verify →
squash-into/absorb mechanism reused by the round-budgeted
conflict-resolution pass (`conflicts.py`) and the semantic-dependents
pass (`semantic.py`, judged by `SemanticDependentsAgent`), each capped
at `ReconcileConfig.resolution_rounds`/`semantic_rounds` (default 3)
before escalating.

Transaction model (research R8, `workflows/reconcile/workflow.py`): each
answer captures a `jj_snapshot_operation` restore point before any
mutation; any failure — correction, conflicts, semantic pass, or the
independent gate — restores that jj operation *before* any bd terminal
write, so a rolled-back repo state never leaves a stray ledger write
behind. Exhausting the conflict or semantic round budget creates a
human-triage bead via `assumptions.ledger.create_reconcile_escalation`
(same label/state shape as fly's `create_human_bead`), then
terminal-marks the entry `needs-interactive-review`. `--dry-run` runs
detection, ordering, target resolution, and the mutability guard only —
zero jj/bd/filesystem mutations. Re-answering a terminal-marked entry
via `maverick review` re-arms it for the next reconcile run (FR-017).
See `src/maverick/workflows/reconcile/` and
`specs/051-reconcile-changed-answers/` for the full contract.

**JSON verbs (053-assumption-review-console)**: `reconcile --json`
(verb `reconcile.run`) and `reconcile --dry-run --json` (verb
`reconcile.dry-run`) emit `ReconcileReport.to_dict()` under `result`
with workflow progress routed to stderr; precondition failures
(dirty working copy, concurrent fly run, held lockfile, missing
`.jj`) map to the `dirty-working-copy`/`concurrent-run`/`locked`/`vcs`
error kinds instead of a bare stderr message. That mapping keys off
`WorkflowError.reason` — a stable code (`maverick.exceptions.workflow`'s
`REASON_*` constants) the raiser sets, so rewording a precondition
message can't silently reclassify it as `internal`; prose-marker
matching survives only as a fallback for raisers that set no `reason`.
Exit-code semantics are unchanged from the non-JSON contract. See
`specs/053-assumption-review-console/contracts/cli-reconcile-json.md`.

**Mid-flight integration (052-conditional-landing)**: a running
`maverick fly` triggers this same workflow in-process at every bead
boundary (`### fly` above) when detection is non-empty, passing
`active_fly_run_id` so `_find_flying_run`'s concurrent-fly guard
excludes the calling run (it's parked at a safe empty-`@` boundary) while
still blocking a genuinely concurrent *other* fly run. Gated by
`ReconcileConfig.mid_flight` (`maverick.yaml` `reconcile.mid_flight`,
default `true`) — set `false` to disable and fall back to manual
`maverick reconcile` runs. See
`specs/052-conditional-landing/contracts/mid-flight-reconcile.md` and
`src/maverick/workflows/fly_beads/mid_flight.py`.

### notify (assumption batch scheduler)

`maverick notify [--dry-run] [--json]` (054-assumption-batch-scheduler) is an
idempotent, daemonless command that reads the assumption ledger, evaluates it
against a configured delivery schedule, and pushes anything due via ntfy —
designed to be wired into cron or a systemd timer, not run as a resident
process (FR-001, FR-017). Severity drives the delivery policy (FR-002):
`high` interrupts at the next evaluation after recording; `medium` batches
into the next configured review window; `low` accumulates silently and is
only counted (never delivered) in a batch summary, surfacing via a review
sweep or bulk waive. A medium/high entry older than `max_entry_age_hours`
escalates past the batching rules (FR-006); an unanswered high-severity
interrupt then re-notifies on a backoff ladder (`renotify_backoff_hours`,
default `4→8→16→24h`, repeating) rather than on every evaluation (FR-007).
Legacy entries (no structured severity) are treated as medium — no new
mapping code, `report_entries` already synthesizes it (research R9). An
opt-in `auto_waive_low` policy (research R10) waives aged low-severity
entries through the existing `assumptions.ledger.waive()` path, stamped
`waived_by="maverick-scheduler"` with a recorded rationale — already
distinguishable in `review --list`/land reporting via the existing waiver
object, no ledger schema change.

Configuration lives in two blocks (`contracts/config-schema.md`): the new
`assumptions.schedule` block (`windows`, `quiet_hours`, `high_overrides_quiet`
default `true`, `min_batch_size` default 1, `max_entry_age_hours` default 24,
`renotify_backoff_hours`, `auto_waive_low`) plus the existing `notifications`
block (`enabled`/`server`/`topic`) for the ntfy endpoint — reused rather than
duplicated (research R3). No `assumptions.schedule` block means the command
is strictly inert: exit 0, "not configured", zero deliveries (FR-021) — there
is no built-in default schedule. A window whose pending batch is under
`min_batch_size` rolls to the next window (FR-005); quiet hours suppress
everything except high-severity interrupts unless `high_overrides_quiet` is
set to make quiet hours absolute (FR-004); a window occurrence inside quiet
hours shifts its due time to quiet-hours end rather than creating a second
decision (research R8). Evaluation is a pure function of `(entries, schedule,
state, now)` with `now` injected at the CLI boundary — the codebase's first
clock seam (research R6).

Delivery state persists at `.maverick/notify/state.json`
(`schema_version: 1`, atomic writes) plus a pid-stamped advisory lockfile at
`.maverick/notify/lock`, mirroring `workflows/reconcile/state.py`'s
lock pattern byte-for-byte (research R4) — this is what makes re-running the
same window a no-op (FR-010) and every delivery/skip reconstructible from
ledger + config + state alone (FR-011). Records are retained while any
covered entry stays open, plus 90 days past terminal state (FR-023).
**Lock contention diverges from `reconcile` by design** (research R7):
overlapping cron fires are expected operation here, not a fault, so a held
lock is a benign `SUCCESS` exit with `result.skipped: "concurrent-evaluation"`
and zero evaluation performed — not `reconcile`'s `locked` error kind. `bd`
unavailability maps to `bd-unavailable`; an unusable `notifications` block
(disabled or no `topic`) maps to `validation`, naming the exact missing key
(FR-009). `--dry-run` evaluates and reports every decision with zero ntfy
calls, zero bd writes, zero state writes.

**JSON verbs**: `notify --json` (verb `notify.run`) and `notify --dry-run
--json` (verb `notify.dry-run`) emit the shared envelope
(`src/maverick/cli/json_output.py`) with every delivery and skip tagged by
the rule that decided it (SC-004). Exhausted ntfy retries map to the new
additive `ErrorKind.DELIVERY_FAILED` (`"delivery-failed"`, research R11),
exit 1, with the batch left due — a failed delivery is never recorded as
delivered (FR-012). See
`specs/054-assumption-batch-scheduler/contracts/cli-notify-json.md` and
`config-schema.md`; implementation in `src/maverick/cli/commands/notify.py`
and `src/maverick/assumptions/schedule/`: `evaluate.py` (the pure entry
point + orchestration) over four decision engines — `windows.py` (occurrence
construction, DST-aware localization, quiet hours, window batching),
`severity.py` (high-severity interrupts), `escalation.py` (max-age
escalation, renotify backoff, auto-waive), all sharing the table-driven
`decisions.py` — plus `tracking.py`, `models.py`, `state.py`, `deliver.py`,
and `clock.py` (stdlib IANA local-zone resolution; the CLI's `now` must
carry a real zone, not `datetime.now().astimezone()`'s fixed offset, or the
DST handling is inert). Quiet hours suppress **deliveries**, not bookkeeping,
and `high_overrides_quiet` governs high severity **only** — a medium
escalation or a backlogged window batch is always held until quiet hours end
(FR-004). Zero model calls, zero agents, zero Burr — deterministic library
and CLI only.

### Assumption ledger

Agents report adopted assumptions (question / adopted answer /
alternatives / severity) in the `assumptions` field of their
`submit_implementation` / `submit_review` / `submit_fix_result`
payloads. The fly workflow's `record_assumptions` action turns each
into a structured bead under the owning epic (labels `assumption` +
the legacy `assumption-review`/`needs-human-review` pair, so existing
agent-skip and `brief --human` filters keep working unchanged), wires a
`discovered-from` edge to the spawning bead, and the `commit` action
stamps it with the jj change ID. Severity drives ready-queue
enforcement: `low` is `bd defer`red (out of `bd ready`, but — per
052-conditional-landing's strict land gate — still blocks `maverick
land` like every other open entry); `high` additionally gains a
`blocks` edge onto the next spec's epic (wired at recording time and at
`refuel --speckit`'s epic-chaining step), so downstream work never
becomes `bd ready` until the entry is answered or waived via `maverick
review <id>`.
`maverick brief` reports per-spec assumption counts (open/answered/
waived × severity, plus a legacy bucket) as a spec-quality signal. All
ledger logic lives in `src/maverick/assumptions/` — see
`specs/049-assumption-ledger/` for the full contract.

The ledger's lifecycle extends per-entry with reconcile state
(`assumption_reconcile_status`/`assumption_reconciled_at`/
`assumption_reconciled_answer`/`assumption_reconcile_change_id`/
`assumption_reconcile_reason`) via `ledger.mark_reconciled`/
`ledger.mark_needs_interactive_review`; per FR-017, `ledger.answer()`
clears any prior reconcile status on re-answer so a corrected human
answer re-enters reconcile detection without special-casing elsewhere.
See `### reconcile` above and `specs/051-reconcile-changed-answers/`.

### Assumption review console (053-assumption-review-console)

Every review-lifecycle verb is invocable headlessly with `--json`:
`review --list [--status\|--spec\|--severity]...` (verb `review.list`,
full provenance rows filtered/sorted server-side — owning spec asc,
severity high→low, stable ledger order), `review <id> --answer/--waive`
(verbs `review.answer`/`review.waive`, with an already-resolved
pre-check that applies in both JSON and human mode), and
`review --spec <name> --waive <reason>` (verb `review.bulk-waive`). All
JSON verbs across `review`/`reconcile`/`land` share one envelope shape
and error-kind registry (`src/maverick/cli/json_output.py`,
`specs/053-assumption-review-console/contracts/error-envelope.md`); the
canonical entry-row projection (`src/maverick/assumptions/serialize.py`
`entry_to_dict`) is shared verbatim by `review --list` and the land
report so both surfaces can never drift. `maverick review` without
`--json` is unchanged (FR-018) — it remains the bare-terminal fallback
for humans without Claude Code.

`maverick init` installs a packaged Claude Code skill,
`maverick-review` (`src/maverick/skills/review_console/SKILL.md`,
installed to `<project>/.claude/skills/maverick-review/SKILL.md`,
always overwritten — Maverick-owned, versions with the wheel; removed
by `maverick uninstall`). Invoked as `/maverick-review` or by prose, it
sweeps the open queue one entry at a time via `AskUserQuestion`
(adopted answer + alternatives + free-form + waive/skip), applies each
decision immediately through the JSON verbs above, then — once, after
the sweep — runs `reconcile --json`, reports the frontier via
`land --status --json`, and offers to land only on explicit
confirmation. The skill never touches jj/git/bd or files directly; see
`specs/053-assumption-review-console/contracts/skill-review-console.md`
for its full behavioral contract.

## Dependencies

- [uv](https://docs.astral.sh/uv/) for dependencies (`uv sync`).
- [Make](https://www.gnu.org/software/make/) for development commands.
- **airframe** — the agent-runtime abstraction every LLM call goes
  through. Providers (Claude Code, Copilot, OpenCode, OpenRouter,
  Bedrock, Kimi, …) are selected per role in `maverick.yaml` under
  `agents:`; `maverick init` discovers which are authenticated locally.
  Each provider carries its own auth step — e.g. `opencode auth login
  <provider>` for the OpenCode-backed adapters.
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
