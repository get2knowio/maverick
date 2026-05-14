# Burr as a potential xoscar replacement

Captured from a research thread. Not a decision — a starting point.

## Why we looked

xoscar gives us actor RPC, supervisor lifecycle, and `@xo.generator`
event streaming, but we're not using its distributed/multi-process
features (`n_process=0`, all coroutines on one loop). The framework's
ceremony — `__pre_destroy__`, `@xo.no_lock`, `xo.wait_for` vs
`asyncio.wait_for` — is bigger than what we get back. Question: would a
lighter framework simplify things, or should we drop framework support
entirely?

Frameworks surveyed: LangGraph, PyFlue, Prefect/ControlFlow,
Temporal/Restate/DBOS, pydantic-graph, Burr.

## Why Burr made the shortlist

[Apache Burr](https://github.com/apache/burr/) (formerly DAGWorks-Inc)
is explicitly positioned as the lighter alternative to LangGraph:
"while langgraph took a heavier-handed pregel-based approach... Burr
aims towards simplification." It's a state-machine library, not an LLM
framework — no LangChain dependency tree, model-agnostic. Apache
incubation as of 2026.

### Maverick → Burr mapping

| Maverick today                                 | Burr equivalent                              |
| ---------------------------------------------- | -------------------------------------------- |
| `fly`: implement → gate → review → fix → commit | `Application` with cycle (`fix → review`)    |
| Briefing/decompose fan-out                     | `MapStates` / `MapActions` (sub-applications) |
| `ProgressEvent` to Rich CLI                    | `Hook`s on `pre_run_step` / `post_run_step` |
| Per-actor OpenCode session                     | Bound dependency (not in `State`)            |
| Bead-by-bead checkpointing                     | Built-in `Persister` + time-travel UI        |
| `@xo.generator`, `__pre_destroy__`, `@xo.no_lock` | Gone — actions are async functions       |

### Things we don't actually need from Burr

- **Streaming actions.** Our actors are single-shot
  `_send_structured` calls returning typed payloads
  (`implementer.py:104`, `reviewer.py:122`). The SSE machinery in
  `runtime/opencode/client.py` is internal error detection, not token
  streaming to the supervisor. Burr's streaming primitives are for
  chatbot-style UIs and don't help us.
- **Hooks fit our needs better than streaming** for the Rich Live
  console — we already emit phase-boundary events, not deltas.

## Key concerns before adopting

1. **"Async all the way down" is a hard rule.** One blocking call
   freezes the whole `Application`. We're already async-first
   (Guardrail #1), but anything that sneaks in (`subprocess.run`, sync
   GitPython call) becomes a real bug, not a slow path. Burr enforces
   what CLAUDE.md already requires.
2. **`MapActions` materializes eagerly.** Our "stream beads as they
   become ready" pattern doesn't fit `MapActions` — it fits a *cycle*
   with a "next bead?" branching action. Still natural, not a 1:1 swap.
3. **State is the contract.** Burr wants a single `State` object
   flowing between actions. Per-actor session IDs and OpenCode clients
   are runtime artifacts that should NOT live in `State` (they'd get
   serialized into checkpoints meaninglessly). Use `bind()` for
   transient handles, `State` for workflow data.
4. **Maturity.** Less battle-tested than LangGraph. Streaming-async had
   open issues last year — verify current status before relying on it.
5. **`bind()` is functional API only.** Class-based actions don't
   support `bind()`. Either keep actions as functions or hand
   dependencies via `__init__`.

## The actor liveness pattern translates cleanly

Confirmed from code:

- Same `ImplementerActor` instance handles `send_implement` and
  `send_fix` (`fly_supervisor.py:709,717,1177`). The persistent OpenCode
  session is what carries context from implement → fix.
- Same applies to reviewers: one `new_bead`, then potentially many
  `send_review` rounds.
- `_rotate_session()` only fires inside `new_bead()` — between beads,
  not between fix rounds (`implementer.py:97`, `reviewer.py:111`).

In Burr, this becomes structural: the same `bind()`-ed agent instance
appears in both `implement` and `fix` actions. Continuity is right
there in the wiring, not buried in actor reference identity.

## The decoupled win: extract Agent classes regardless

The actor abstraction today does two unrelated jobs:

1. **RPC/lifecycle plumbing** — xoscar mailbox, `__post_create__`,
   `@xo.no_lock`.
2. **LLM session management + domain methods** — `_send_structured`,
   `_rotate_session`, prompt assembly, cascade across provider tiers.

Splitting them gives a clean three-layer stack:

```
Burr actions (or whatever)  ── calls ──>  Maverick Agents  ── calls ──>  OpenCode HTTP
   (workflow)                              (domain API)                  (transport)
```

This refactor is independently valuable — even if we don't adopt Burr,
the agent classes:

- Encapsulate OpenCode behind a domain API (`coder.implement(bead)` not
  `client.send_structured(prompt, schema=...)`).
- Make LLM calls testable without spinning up xoscar.
- Give a clear owner for the bead-boundary `new_bead()` rotation.
- Centralize cost tracking, cascade logic, error classification.
- Survive substrate churn — we already migrated ACP+MCP → OpenCode HTTP
  once (`1bc06ae`); next migration only touches `Agent.__init__`.

## Squadron: the other layer

Above `Agent`, a `Squadron` (per-workflow subclass: `FlySquadron`,
`RefuelSquadron`, `PlanSquadron`) owns:

- OpenCode server lifecycle (replaces xoscar pool's `with_opencode=True`)
- Model validation at startup (the async-dispatch + bad-modelID landmine,
  collapsed to one place)
- Agent factory + registry
- Bead-boundary session rotation across all agents

Then Burr binding becomes one step:

```python
async with FlySquadron(config) as squadron:
    app = (
        ApplicationBuilder()
        .with_actions(
            implement=implement.bind(coder=squadron.coder),
            fix=fix.bind(coder=squadron.coder),                        # SAME instance
            review_correctness=review.bind(rev=squadron.correctness_reviewer),
            review_completeness=review.bind(rev=squadron.completeness_reviewer),
        )
        .build()
    )
    await app.arun(...)
```

## Recommended order of operations

1. **Extract `Agent` classes from `OpenCodeAgentMixin`.** Actors become
   thin shells holding an `Agent` instance and forwarding calls. Zero
   behavior change, fully backward compatible.
2. **Add `Squadron`.** Initially constructed by the xoscar pool (or
   workflow), but owns server + agents.
3. **Now decide about Burr.** With steps 1–2 done, the actor layer is
   mostly RPC plumbing around stateless calls — and we can see clearly
   whether it's worth swapping to Burr, dropping to plain
   `asyncio.TaskGroup`, or keeping xoscar.

Steps 1 and 2 are net wins regardless. Step 3 is informed by what the
code actually looks like, not speculation.

## Concerns specific to a Burr migration (revisit if/when we get there)

- **`fly`'s outer bead loop** — Burr models cycles natively, but the
  "peek next ready bead, exit when none" pattern needs a branching
  action that returns either `next_bead → implement` or `done → exit`.
  Sketch this on real code before committing.
- **Two-stage Ctrl-C** — today fly catches SIGINT to set a graceful-stop
  flag. Burr's `Application.run()` doesn't natively expose a "stop after
  current step" hook. Probably solvable with a custom `Hook`, but
  verify.
- **The `new_implementer` recovery path** at `fly_supervisor.py:1163` —
  rebuilds the actor on hard failure. In a Squadron world this becomes
  `squadron.replace_coder()`; in a Burr world it's a transition into a
  recovery branch. Either works.
- **Concurrent workflows** — multiple Burr `Application`s can coexist on
  one process; multiple Squadrons each own one OpenCode server on a
  free port. No conflict.

## Sources

- [Apache Burr](https://github.com/apache/burr/)
- [Why Burr](https://burr.dagworks.io/getting_started/why-burr/)
- [Burr parallelism (MapActions/MapStates)](https://burr.dagworks.io/concepts/parallelism/)
- [Burr streaming actions](https://burr.dagworks.io/concepts/streaming-actions/)
- [Burr sync vs async](https://burr.dagworks.io/concepts/sync-vs-async/)
- [Burr actions / `bind()`](https://burr.dagworks.io/concepts/actions/)
- [pydantic-graph](https://ai.pydantic.dev/api/pydantic_graph/graph/) — runner-up; pure state machine library, no LLM coupling
- [LangGraph complexity critique](https://www.ema.ai/additional-blogs/addition-blogs/langgraph-alternatives-to-consider)
- [Durable execution: Temporal/Restate/DBOS](https://devstarsj.github.io/2026/04/03/durable-execution-temporal-restate-dbos-distributed-workflows-2026/) — overkill for an interactive CLI
