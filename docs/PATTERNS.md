# Maverick Codebase Patterns

This document records recurring implementation patterns observed across the Maverick codebase. It is not a full architecture reference and it is not a style guide in the abstract. The goal is simpler: capture the shapes that already repeat often enough to count as house patterns.

Several themes show up repeatedly:

- Supervisors own control flow; actors and runners do the work.
- MCP tools are the preferred structured-return path for agent work.
- Typed contracts, explicit execution context, and durable event logs matter more here than minimal code.
- The repo is mid-migration in a few places, so some patterns exist in both old and new forms.

## 1. Supervisor-Owned Routing And Policy

Supervisors are the policy engines. They decide what message comes next, how many retry/fix rounds are allowed, when a workflow escalates to human review, and when processing is done. Actors are intentionally narrower: they process one request and return messages or results.

Why it repeats:

- It keeps workflow policy explicit instead of scattering it across actor implementations.
- It makes fix loops, review loops, and commit/escalation behavior easier to test in isolation.
- It preserves the separation between judgment work and deterministic orchestration.

Concrete example:

- In [fly_beads supervisor](../src/maverick/workflows/fly_beads/supervisor.py), the review-fix loop is explicitly capped by `MAX_REVIEW_ROUNDS = 3`; once that cap is reached, the supervisor stops issuing further fix requests and falls through to `COMMIT_REQUEST` with `tag="needs-human-review"`.

Representative code:

- [fly_beads supervisor](../src/maverick/workflows/fly_beads/supervisor.py)
- [generate_flight_plan supervisor](../src/maverick/workflows/generate_flight_plan/supervisor.py)
- [refuel supervisor (top-level)](../src/maverick/actors/refuel_supervisor.py)
- [actor message protocol](../src/maverick/workflows/fly_beads/actors/protocol.py)

## 2. MCP Tool Calls Are The Preferred Agent Return Channel

The recurring pattern is: supervisors send natural-language prompts into agent sessions, and agents return structured data by calling MCP tools such as `submit_review`, `submit_fix_result`, `submit_scope`, or `submit_flight_plan`. Deterministic actors return Python values or messages directly.

Why it repeats:

- MCP tool schemas provide protocol-level structure instead of relying on brittle free-text JSON extraction.
- Tool-specific return channels keep each actor's response surface narrow.
- The same mental model applies across plan, refuel, and fly even when the transport varies.

Representative code:

- [AGENT-MCP architecture](AGENT-MCP.md)
- [supervisor inbox schemas](../src/maverick/tools/supervisor_inbox/schemas.py)
- [supervisor inbox server](../src/maverick/tools/supervisor_inbox/server.py)
- [fly implementer actor](../src/maverick/workflows/fly_beads/actors/implementer.py)
- [fly reviewer actor](../src/maverick/workflows/fly_beads/actors/reviewer.py)
- [plan briefing actor](../src/maverick/workflows/generate_flight_plan/actors/briefing.py)

Variant worth knowing:

- The logical contract is stable, but fly_beads and generate_flight_plan ship a second delivery variant alongside the Thespian-backed [top-level actors](../src/maverick/actors): a workflow-scoped actor package (`workflows/fly_beads/actors/`, `workflows/generate_flight_plan/actors/`) with a file-backed inbox shim used for in-process composition and tests. Refuel does not have this variant — the top-level `actors/refuel_supervisor.py` is the only refuel implementation.

## 3. Validate Strictly At The MCP Boundary, Then Parse Into Permissive Typed Models

Maverick repeatedly uses a two-step boundary:

1. JSON Schema validation at the MCP server boundary.
2. Immediate parsing into Python-side payload models that normalize aliases, preserve extra fields, and give supervisors typed access.

Why it repeats:

- The outer boundary stays strict for agents.
- The inner boundary stays resilient to prompt drift, legacy field names, and forward-compatible extensions.
- Supervisors avoid threading raw `dict[str, Any]` everywhere.

Representative code:

- [supervisor inbox server schema validation](../src/maverick/tools/supervisor_inbox/server.py)
- [typed intake payload models](../src/maverick/tools/supervisor_inbox/models.py)
- [typed intake tests](../tests/unit/tools/supervisor_inbox/test_models.py)
- [briefing serializer compatibility layer](../src/maverick/preflight_briefing/serializer.py)

This is one of the clearest recurring patterns in the repository: strict schema outside, tolerant typed intake just inside, stricter domain interpretation deeper in the pipeline.

## 4. Sessions Persist For A Logical Unit Of Work

Agent sessions are usually scoped to a bead, a plan-generation run, or a decomposition run, not to a single prompt. The first prompt creates the session; follow-up prompts reuse it so the actor retains conversation history.

Why it repeats:

- Implementers can fix issues without losing context from the initial implementation turn.
- Reviewers can verify whether their own prior findings were addressed instead of re-reviewing from scratch.
- Session creation is expensive enough that reuse is desirable when the logical task is continuous.

Representative code:

- [ACP create_session and prompt_session](../src/maverick/executor/acp.py)
- [bead session registry](../src/maverick/workflows/fly_beads/session_registry.py)
- [fly implementer actor](../src/maverick/workflows/fly_beads/actors/implementer.py)
- [fly reviewer actor](../src/maverick/workflows/fly_beads/actors/reviewer.py)
- [top-level briefing actor](../src/maverick/actors/briefing.py)
- [refuel decomposer actor](../src/maverick/actors/decomposer.py)

The repo consistently treats session reuse as a context-preservation mechanism, not as global memory. Sessions live for the current logical work item and are then discarded or replaced.

**Bounded-session variant.** When a phase can produce many turns — refuel's detail phase fans dozens of units across each pool actor — sessions rotate after a configured turn cap. See `_ensure_mode_session` in [refuel decomposer actor](../src/maverick/actors/decomposer.py); the cap is controlled by `DETAIL_SESSION_MAX_TURNS` / `FIX_SESSION_MAX_TURNS` in `workflows/refuel_maverick/constants.py`. Rotation re-seeds the new session with the large context payloads that would otherwise accumulate across turns. This trades conversation continuity within a phase for bounded context window usage and faster per-turn responses.

## 5. Create Heavy Runtime Objects Lazily

Executors, ACP connections, and even CLI command modules are often created on demand rather than at import time or actor construction time.

Why it repeats:

- ACP subprocesses are expensive enough to avoid spawning until needed.
- CLI startup time matters, especially for `--help` and light commands.
- Actors that never receive work should not pay the cost of building their full runtime.

Representative code:

- [lazy CLI group](../src/maverick/cli/lazy_group.py)
- [briefing actor lazy executor creation](../src/maverick/workflows/generate_flight_plan/actors/briefing.py)
- [implementer actor lazy executor creation](../src/maverick/workflows/fly_beads/actors/implementer.py)
- [connection pool](../src/maverick/executor/_connection_pool.py)

This pattern is pragmatic rather than ideological: startup cost is treated as a real engineering constraint.

## 6. Missing Tool Calls Trigger A Nudge Loop Instead Of Best-Guess Parsing

When an agent finishes work but fails to call its required MCP return tool, the actor does not guess from text output. It nudges the same session with a short follow-up prompt telling the agent exactly which tool to call, retries a small number of times, and then degrades gracefully if needed.

Why it repeats:

- It preserves the tool contract without pretending the tool call happened.
- It is much safer than scraping free-form text after the fact.
- It keeps the failure mode recoverable for transient model mistakes.

Representative code:

- [briefing actor nudge retry](../src/maverick/workflows/generate_flight_plan/actors/briefing.py)
- [implementer inbox retry](../src/maverick/workflows/fly_beads/actors/implementer.py)
- [reviewer inbox retry](../src/maverick/workflows/fly_beads/actors/reviewer.py)

This pattern is especially important for new actor work: the repo prefers explicit recovery over silent coercion.

## 7. `cwd` And `allowed_tools` Are First-Class Execution Inputs

Maverick repeatedly threads working directory and tool permissions explicitly through actor init, session creation, and executor calls. These are not treated as ambient global state.

Why it repeats:

- Hidden workspaces only work if every step runs in the intended `cwd`.
- Least-privilege tool access only works if allowlists are forwarded deliberately.
- Failing to pass either usually leads to subtle misbehavior rather than obvious crashes.

Representative code:

- [ACP executor session creation](../src/maverick/executor/acp.py)
- [ACP client permission handling](../src/maverick/executor/acp_client.py)
- [bead session registry](../src/maverick/workflows/fly_beads/session_registry.py)
- [top-level briefing actor cwd threading](../src/maverick/actors/briefing.py)
- [refuel decomposer cwd threading](../src/maverick/actors/decomposer.py)
- [jj client cwd ownership](../src/maverick/jj/client.py)

This pattern shows up often enough to treat it as a design rule: execution context should be explicit and narrow. The refuel decomposer and briefing actors enforce this by raising `ValueError` at init if `cwd` is missing, rather than silently falling back to `Path.cwd()`.

## 8. Specialist Fan-Out Followed By Fan-In Or Challenge

The repo repeatedly decomposes open-ended reasoning tasks into specialist roles. Several agents analyze the same input from different angles, then a later phase either challenges the combined result or synthesizes it.

Why it repeats:

- It keeps prompts narrow and role-specific.
- It preserves multiple perspectives without forcing agents to coordinate directly.
- It gives supervisors a predictable place to merge, challenge, or serialize the partial outputs.

Representative code:

- [generate_flight_plan workflow assembly](../src/maverick/workflows/generate_flight_plan/workflow.py)
- [generate_flight_plan supervisor](../src/maverick/workflows/generate_flight_plan/supervisor.py)
- [refuel briefing room assembly](../src/maverick/workflows/refuel_maverick/workflow.py)
- [briefing serializer](../src/maverick/preflight_briefing/serializer.py)

Important nuance:

- The architectural pattern is fan-out/fan-in, but not every implementation is literally parallel today. Some in-process paths preserve the same staged structure while running specialist prompts sequentially because of current ACP/session constraints.

## 9. Events Are The Source Of Truth For UX, Logs, And Tests

The repo prefers emitting typed progress events and then rendering or recording them, rather than printing status text directly from workflow logic. `StepStarted`, `StepCompleted`, `StepOutput`, `AgentStarted`, `AgentCompleted`, and `AgentStreamChunk` form the common vocabulary.

Why it repeats:

- One event stream can drive the CLI, the session journal, and tests.
- Rendering stays decoupled from workflow logic.
- Event serialization makes long-running runs inspectable after the fact.

Representative code:

- [progress event definitions](../src/maverick/events.py)
- [PythonWorkflow emit helpers](../src/maverick/workflows/base.py)
- [workflow event renderer](../src/maverick/cli/workflow_executor.py)
- [session journal](../src/maverick/session_journal.py)
- [workflow base tests](../tests/unit/workflows/test_python_workflow_base.py)
- [CLI render tests](../tests/unit/cli/test_render_workflow_events.py)

The broader pattern is "events first, presentation second."

## 9a. Supervisor Event Bus And Polled Drain

> **Migration note:** This pattern describes the current Thespian-based implementation. The planned xoscar migration ([docs/prd-xoscar-migration.md](prd-xoscar-migration.md)) will replace it with a native async generator on the supervisor method (see §9b note below), eliminating the poll loop and `SupervisorEventBusMixin`.

Each multi-actor workflow (fly, refuel, generate_flight_plan) runs its supervisor in a separate OS process via Thespian's `multiprocTCPBase`. Supervisors accumulate typed `ProgressEvent` objects and expose them through a `{"type": "get_events", "since": int}` message. The workflow-side async generator polls the supervisor at a fixed interval (typically 0.25s) via `asys.ask(...)` and forwards each new event onto its own asyncio queue. The terminal result rides on the final reply with `done=True`.

Why it repeats:

- The workflow's async generator stays responsive to the CLI while the supervisor runs in its own process.
- Events survive the cross-process boundary without shared memory or pubsub infrastructure.
- Polling is simple, idempotent, and avoids backpressure complexity.
- A hard timeout on the drain loop guards against wedged supervisors without interfering with healthy long runs (the supervisor has its own stale-unit watchdog).

Representative code:

- [SupervisorEventBusMixin](../src/maverick/actors/event_bus.py)
- [_drain_supervisor_events helper](../src/maverick/workflows/base.py)
- [fly supervisor event usage](../src/maverick/actors/fly_supervisor.py)
- [refuel supervisor event usage](../src/maverick/actors/refuel_supervisor.py)

**xoscar target pattern:** Each multi-actor workflow creates an xoscar actor pool and obtains a typed `supervisor_ref`. The supervisor exposes `async def run(inputs) → AsyncGenerator[ProgressEvent, None]`. The workflow-side code consumes events via `async for event in supervisor_ref.run(inputs)`. No polling; events are pushed immediately via an `asyncio.Queue` on the supervisor instance. `SupervisorEventBusMixin` and `_drain_supervisor_events` are removed.

## 9b. Persistent Event Loop Bridges Async Work Into Thespian Actors

> **Migration note:** This pattern is superseded by the planned xoscar migration ([docs/prd-xoscar-migration.md](prd-xoscar-migration.md)). In xoscar, all actor methods are native `async def`. The `ActorAsyncBridge`, daemon thread, and `asyncio.run_coroutine_threadsafe` are eliminated. This section documents the current Thespian-era pattern for historical reference.

Thespian's `receiveMessage` is synchronous; ACP's `prompt_session` and executor cleanup are async. The repo-wide solution is `ActorAsyncBridge`: one long-lived `asyncio` event loop on a daemon thread per actor, with all async work handed to it via `asyncio.run_coroutine_threadsafe`. On timeout, the bridge cancels its own coroutine so leaked tasks do not accumulate across retries.

Why it repeats:

- `asyncio.run()` tears down async generators on exit, which breaks ACP's stdio transport.
- Every agent actor needs to reach into async code; centralizing the pattern prevents per-actor reinvention.
- The loop stays alive across many messages in the actor's lifetime, so session reuse and ACP connection caching work correctly.

Representative code:

- [ActorAsyncBridge mixin](../src/maverick/actors/_bridge.py)
- [refuel decomposer actor](../src/maverick/actors/decomposer.py)
- [top-level briefing actor](../src/maverick/actors/briefing.py)
- [bridge tests](../tests/unit/actors/test_bridge.py)

**xoscar target pattern:** Actor methods are `async def`; `await executor.prompt_session(...)` is called directly. No threading bridge, no persistent daemon thread, no `run_coroutine_threadsafe`. `ActorAsyncBridge` and `_bridge.py` are removed in the xoscar migration.

## 10. Stable Outputs Use Frozen Dataclasses With `to_dict()`

When Maverick wants a contract to survive checkpointing, logging, or workflow boundaries, it tends to model that contract as a frozen dataclass with a small `to_dict()` serializer. Message envelopes and result payloads follow the same style.

Why it repeats:

- Immutability makes it harder to accidentally mutate workflow state after publication.
- `to_dict()` gives a stable escape hatch for persistence and logging.
- The same shape works well for checkpoints, journals, and JSON reports.

Representative code:

- [workflow results](../src/maverick/results.py)
- [executor result](../src/maverick/executor/result.py)
- [jj typed models](../src/maverick/jj/models.py)
- [fly message contract](../src/maverick/workflows/fly_beads/actors/protocol.py)
- [fly report](../src/maverick/workflows/fly_beads/fly_report.py)

This is one of the repo's strongest repeating conventions.

## 11. Boundaries Prefer `Protocol` Over Inheritance

Many cross-module seams are modeled as runtime-checkable protocols rather than base classes. That keeps implementations swappable while making the expected surface area explicit.

Why it repeats:

- Structural typing reduces coupling between workflow code and concrete implementations.
- Test doubles can satisfy the contract without inheriting framework classes.
- Read-only abstractions such as VCS and runner validation stay lightweight.

Representative code:

- [StepExecutor protocol](../src/maverick/executor/protocol.py)
- [VcsRepository protocol](../src/maverick/vcs/protocol.py)
- [ValidatableRunner protocol](../src/maverick/runners/protocols.py)
- [Actor protocol (workflow-scoped)](../src/maverick/workflows/fly_beads/actors/protocol.py)
- [runner protocol tests](../tests/unit/runners/test_protocols.py)

One subtle repeated lesson from the tests: `@runtime_checkable` verifies attribute presence, not full signature correctness. Static typing still matters.

Scope note: the Protocol-over-inheritance rule applies to cross-module seams (step executors, VCS reads, runner validation, the workflow-scoped actor mailbox). The top-level actors in [`src/maverick/actors/`](../src/maverick/actors) currently inherit directly from `thespian.actors.Actor` plus the `ActorAsyncBridge` mixin — Thespian requires concrete subclasses, so Protocol doesn't apply to that surface. In the planned xoscar migration, the top-level actors will inherit from `xoscar.Actor` instead; the `Actor` protocol defined in `src/maverick/workflows/fly_beads/actors/protocol.py` remains the canonical typed interface for all other cross-module seams.

## 12. External Systems Sit Behind Safe Wrappers

The codebase keeps retry logic, timeouts, environment handling, and process cleanup inside a small number of wrappers instead of scattering subprocess calls everywhere.

Why it repeats:

- Long-running workflows need resilient subprocess and network handling.
- Cleanup behavior has to be correct across ACP agents, jj, git, and validation tools.
- Central wrappers make error translation and secret scrubbing consistent.

Representative code:

- [command runner](../src/maverick/runners/command.py)
- [ACP connection pool](../src/maverick/executor/_connection_pool.py) — used internally by `create_default_executor`; self-contained actors (refuel decomposer, briefing, fly implementer) each get their own executor, so the pool is per-actor-process rather than cross-process
- [ACP client streaming and permission handling](../src/maverick/executor/acp_client.py)
- [Git repository wrapper](../src/maverick/git/repository.py)
- [jj client](../src/maverick/jj/client.py)
- [actor async bridge](../src/maverick/actors/_bridge.py) *(Thespian-era; removed in xoscar migration)*

Repeated sub-patterns inside these wrappers include explicit timeouts, Tenacity-based retries, structured logging, and specific error mapping.

One known-but-acknowledged boundary (Thespian era): the Thespian+asyncio bridge in [actor bridge](../src/maverick/actors/_bridge.py) blocks `receiveMessage` for the entire duration of an ACP prompt (typically 10–30 minutes). The bridge cancels its own coroutine on timeout, but control traffic (shutdown, nudges) still queues behind the in-flight prompt until it completes. This is an acknowledged trade-off of Thespian's synchronous message model; it is eliminated by the xoscar migration.

## 13. Long-Running Work Leaves Recovery And Audit Artifacts

Maverick does not treat workflows as disposable terminal sessions. It repeatedly records enough state to resume, replay, inspect, or learn from a run later.

Why it repeats:

- Fly and refuel can run long enough that interruption and post-run inspection are real concerns.
- Process-level learning depends on keeping structured records of what happened.
- Recovery needs serializable snapshots rather than in-memory-only state.

Representative code:

- [PythonWorkflow checkpoint and rollback infrastructure](../src/maverick/workflows/base.py)
- [bead session registry serialization](../src/maverick/workflows/fly_beads/session_registry.py)
- [fly report](../src/maverick/workflows/fly_beads/fly_report.py)
- [session journal](../src/maverick/session_journal.py)
- [fly workflow checkpoint usage](../src/maverick/workflows/fly_beads/workflow.py)

The recurring pattern is durable traces over ephemeral execution.

## 13a. File-Based Resume Cache Per Logical Phase

Long-running workflows cache each expensive phase to disk so that a killed or restarted run picks up at N-of-M instead of 0-of-M. The canonical shape is one JSON file (or one per unit of work) under `.maverick/plans/<name>/`, wrapped in a versioned envelope with a `cache_key` field derived from the phase's inputs. On read, the workflow recomputes the key and discards the cache on mismatch so stale caches do not silently misdescribe inputs that have drifted.

Why it repeats:

- Briefing and outline generation are expensive; Ctrl-C during a later phase should not invalidate earlier work.
- Per-unit detail caches let parallel fan-out resume mid-batch.
- Versioned envelopes with hashed cache keys keep the cache self-invalidating when the flight plan, codebase context, or prompt templates change.

Representative code:

- [refuel briefing/outline cache helpers](../src/maverick/workflows/refuel_maverick/workflow.py)
- [refuel supervisor cache writers](../src/maverick/actors/refuel_supervisor.py)
- [briefing cache tests](../tests/unit/workflows/refuel_maverick/test_briefing_cache.py)

Key convention: the cache envelope is `{"schema_version": int, "cache_key": str, "payload(s)": {...}}`. Bumping `schema_version` retires every existing cache of that phase; changing any input the `cache_key` hashes invalidates a single run's cache without touching other plans.

## Migration Notes And Tensions

These are the main places where the codebase currently carries more than one version of the same idea:

- **Thespian → xoscar migration planned.** The top-level actors in [`src/maverick/actors/`](../src/maverick/actors) are the canonical runtime path for every workflow and currently run on Thespian. A full migration to xoscar is planned; see [docs/prd-xoscar-migration.md](prd-xoscar-migration.md) for the detailed plan. Fly and plan also ship workflow-scoped actor packages (`workflows/fly_beads/actors/`, `workflows/generate_flight_plan/actors/`) that use the correct async pattern and do **not** depend on Thespian. Refuel does not have a workflow-scoped variant — the top-level `actors/refuel_supervisor.py` is the only refuel implementation.
- MCP tool-backed structured returns are the preferred path, but plain text plus `output_schema` still exists for some one-shot execution paths. The executor explicitly rejects `output_schema` on MCP tool-backed sessions in [ACP executor](../src/maverick/executor/acp.py).
- The legacy rules in [cli-output-rules.md](cli-output-rules.md) do not fully describe the current renderer in [workflow_executor.py](../src/maverick/cli/workflow_executor.py), which now collapses simple steps, buffers interim output, and uses Rich Live tables for concurrent agent views.
- "Parallel briefing" is a stable conceptual pattern, but some in-process supervisors currently run specialist prompts sequentially while preserving the same fan-in shape. The pattern is stable; the transport and scheduling details are still settling.
- Some compatibility layers still intentionally accept raw dicts and legacy alias fields, especially around briefing serialization. That is deliberate migration support, not an accident.

## Practical Use

When adding new infrastructure, the safest default is:

1. Put control flow in a supervisor or workflow, not inside the agent.
2. Use an MCP tool for structured agent returns.
3. Parse tool payloads immediately into typed Python models.
4. Reuse sessions within one logical work item when follow-up turns need prior context.
5. Thread `cwd` and `allowed_tools` explicitly.
6. Emit typed events rather than printing directly from workflow logic.
7. Use frozen, serializable result contracts at workflow boundaries.
8. Use `await actor_ref.method(...)` for inter-actor RPC; do not pass untyped dicts as messages between actors (the xoscar migration targets typed method calls throughout).

That sequence matches the strongest repeated patterns already present in the repository.