# OpenCode → OpenAI Agents SDK + LiteLLM + Burr migration

**Status:** Plan. Phase 0 spike pending (see
[migration-phase-0-spike.md](./migration-phase-0-spike.md)); phases 1–3
contingent on Phase 0 outcome.

## Why migrate

The current substrate works but carries real cost:

- **OpenCode HTTP runtime** (~2400 LOC in `runtime/opencode/`) wraps an
  external subprocess we spawn and manage. Four documented operational
  landmines (silent crash loops on bad modelID, HTTP-200 empty-body
  silent failures, Claude `StructuredOutput` envelope wrapping, silent
  upstream retry storms — see issue #95).
- **xoscar** ceremony (`@xo.no_lock`, `__pre_destroy__`, `xo.wait_for`
  vs `asyncio.wait_for`, `@xo.generator` semantics) is bigger than what
  we get back — we run `n_process=0` and never use the
  distributed/multi-process features.
- Together: substantial maintenance surface for capabilities we mostly
  don't use, and a subprocess dependency in the critical path.

## Decision

Migrate to a fully in-process Python stack:

- **Slot A (multi-provider routing):** [LiteLLM] — in-process library
  only; first-class `github_copilot/*` provider via OAuth device flow.
- **Slot B (structured output):** [OpenAI Agents SDK] — first-class
  `output_type=PydanticModel` at the agent level.
- **Slot C (agent loop + tools):** OpenAI Agents SDK — tools, agent loop,
  `as_tool()` for subagent delegation matching Maverick's `Task` pattern.
- **Slot D (workflow orchestration):** [Apache Burr] — state-machine
  library replacing xoscar's actor/supervisor pattern.
- **Slot E (per-workflow lifecycle):** Maverick's existing `Squadron`
  classes (merged in [#94]) — survive unchanged.
- **Slot F (domain API):** Maverick's existing `Agent` base class
  (merged in [#94]) — survives, internals rewritten.

## Target architecture

```
fly CLI command
   │
   ▼
Burr Application                    ← workflow state machine (replaces xoscar)
   │ actions reference bound agents
   ▼
Maverick Squadron                   ← per-workflow lifecycle (already in main)
   │
   ▼
Maverick Agent classes              ← domain API (already in main from PR #94)
   │
   ▼
OpenAI Agents SDK Agent             ← LLM loop + tools + structured output
   │
   ▼
LiteLLM                             ← provider routing (Copilot OAuth + others)
   │
   ▼
github_copilot / openai / openrouter / ...
```

Six layers, same count as today, but **no subprocess we manage**, no
HTTP plumbing between us and the LLM, all four landmines collapsed,
and the xoscar ceremony goes away. Responsibilities are clean:

- Burr owns workflow state machines (bead loops, fix cycles, commit phase).
- OpenAI Agents SDK owns one-LLM-call's worth of orchestration (tool
  use loop within a single `agent.run_async()`).
- Maverick owns the seam between them and the domain semantics.

## Phased plan

The phasing unit is **layers, not roles** — each phase swaps one
substitution independently with a clear back-out path.

### Phase 0 — End-to-end spike (1–2 days)

Prove the bottom-of-stack works for Maverick's hardest case before
committing. Full details in
[migration-phase-0-spike.md](./migration-phase-0-spike.md).

**Decision gate:** if any required validation fails, abort the
migration and revisit. If only cost-telemetry fails, proceed but accept
we wire cost tracking ourselves.

### Phase 1 — Replace OpenCode runtime (3–4 weeks)

Swap out the bottom two layers (OpenCode HTTP + subprocess) while
keeping xoscar at the top.

**The big win.** ~2400 LOC of `runtime/opencode/` plus the four
landmines die.

Sub-phases:

- **1a — `MaverickCascadingModel` (~200 LOC).** Implements OpenAI Agents
  SDK's `Model` interface; internally walks our tier bindings, calls
  `LitellmModel` for each, raises on terminal failure. Same algorithm
  as today's `cascade_send` in `runtime/opencode/tiers.py`, different
  transport.
- **1b — Rewrite `Agent.__init__`, `_send_structured`, `_send_text`** to
  build/call an underlying OpenAI Agents SDK `Agent`. Replace
  `_ensure_session` / `_build_client` with "construct on demand" — no
  session lifecycle.
- **1c — Wire tools.** Per-role tool lists (briefing = Read/Glob/Grep,
  implementer = full kit). Python implementations live in
  `library/actions/` and reuse `CommandRunner` for Bash.
- **1d — Strip `Squadron._build_agents`.** No more
  `spawn_opencode_server`; just construct `MaverickCascadingModel`
  instances. Drop the `validate_model_id` startup pass (cascade handles
  bad modelIDs naturally).
- **1e — Per-role migration behind a runtime flag.**
  `MaverickConfig.runtime: Literal["opencode", "openai_agents"]`. Start
  with briefing (lowest risk), then reviewer, decomposer, generator,
  implementer (hardest).

**End state of Phase 1:** xoscar still drives the workflow. OpenCode
HTTP runtime is gone. All landmines collapsed. ~2400 LOC deleted,
~500 LOC added (cascading model + tool implementations + new Agent
backend).

**Back-out path:** flip the runtime flag back to `"opencode"` per
workflow. OpenCode runtime stays in-tree until Phase 3.

### Phase 2 — Replace xoscar with Burr (2–3 weeks)

Swap the workflow-orchestration layer. Pre-condition: Phase 1 stable in
production for ≥1 week.

Why this order: xoscar isn't load-bearing for correctness. Doing the
substrate swap second means we're never debugging "is this a Burr
problem or an OpenAI-Agents-SDK problem?" — Phase 1 is proven by the
time we touch the supervisor.

Sub-phases:

- **2a — `fly_supervisor` → Burr `Application`** with explicit actions:
  `select_bead`, `implement`, `gate`, `review_correctness`,
  `review_completeness`, `fix`, `commit`. Squadron-bound agents reach
  actions via `action.bind(coder=squadron.coder)`.
- **2b — Hooks for progress events.** Replace `@xo.generator run()`
  yielding `ProgressEvent`s with Burr `Hook`s on `pre_run_step` /
  `post_run_step`. The Rich CLI consumer doesn't change.
- **2c — Two-stage Ctrl-C.** Custom hook setting a "stop after current
  step" flag. Validate at Phase 2 kickoff (BURR.md historically flagged
  as unknown).
- **2d — Bead loop as a cycle.** "Peek next ready bead → implement-or-
  exit" becomes a branching action returning `next_bead → implement` or
  `done → exit`.
- **2e — Remaining supervisors.** Refuel, plan, land — same pattern.
- **2f — Drop xoscar.** Remove the pool, drop `xoscar` from dependencies.

**End state of Phase 2:** Burr drives all workflows. xoscar is gone.
~600 LOC of supervisor ceremony deleted; Burr Applications add ~400 LOC
of declarative wiring.

**Back-out path:** keep xoscar supervisors during 2a–2e, runtime-flag
them off when Burr equivalent is ready. Last step is removal.

### Phase 3 — Cleanup (1 week)

- `rm -rf src/maverick/runtime/opencode/`.
- Drop the `opencode` binary dependency from CLAUDE.md and devcontainer.
- Update CLAUDE.md: remove the four landmines (or move them to a
  historical-context section), document the new stack.
- Close issue #95 — silent-retry-storm landmine ceases to exist.
- Tests guide for mocking at the Maverick `Agent` boundary
  (TestModel/FunctionModel equivalents).

## Risks specific to this stack

1. **Cascade is still DIY.** Neither OpenAI Agents SDK nor LiteLLM gives
   us tier-cascade across `(provider, model)` bindings out of the box.
   `MaverickCascadingModel` is ~200 LOC in Phase 1a. The SDK gives
   per-agent model selection; per-call fallback is our concern.

2. **Two "Agent" concepts.** OpenAI Agents SDK has `agents.Agent`;
   Maverick has `maverick.agents.Agent`. Use `from agents import Agent
   as _AgentSDK` at internal boundaries to keep call sites unambiguous.

3. **Tool-implementation parity.** OpenCode bundles polished
   Read/Glob/Grep/Edit/Write/Bash/Task tools. We write Python
   implementations of each in Phase 1c. Bash is essentially free (use
   `CommandRunner`); Read/Write are trivial; Edit, Glob, Grep, Task
   need ~100–200 LOC each. Total ~500–800 LOC of tool code, but it's
   *our* code we can debug.

4. **Burr maturity.** Less battle-tested than LangGraph.
   Streaming-async historically had open issues; verify current state
   at Phase 2 kickoff. If Burr disappoints, the fallback is plain
   `asyncio.TaskGroup` orchestration (which is what xoscar effectively
   is anyway minus the ceremony). Phase 1's gains stand independent of
   Burr's fate.

5. **Test mockability across the stack.** Design the Maverick `Agent`
   layer's public surface so tests mock there, not at OpenAI Agents SDK
   or LiteLLM. Existing tests in `tests/unit/agents/` (added in PR #94)
   are the template — they should survive Phase 1 substantially
   unchanged.

## Why this beats the alternatives surveyed

| Option | Verdict |
|---|---|
| Stay on OpenCode | Landmines 1–4 unaddressed, subprocess pain, 2400 LOC carried |
| PydanticAI + LiteLLM | Reasonable; LiteLLM shim is community (22★) — load-bearing single-maintainer risk |
| OpenAI Agents SDK + LiteLLM (no Burr) | Reasonable; xoscar ceremony stays |
| **OpenAI Agents SDK + LiteLLM + Burr** | **First-party LiteLLM bridge + clean workflow layer + biggest delta from current pain** |
| Vendor Agent SDKs (Claude / Codex) | Subscription bundles inaccessible, paradigms divergent, role-locks |
| Instructor + LiteLLM + custom loop | Most code we own; viable backup if Phase 0 finds OpenAI Agents SDK issues |

The decisive points: OpenAI Agents SDK has a **first-party** LiteLLM
bridge (vs PydanticAI's community shim), first-class `output_type=`
Pydantic returns, `as_tool()` for `Task` subagent delegation, and Burr
delivers clean workflow ergonomics without the xoscar overhead.

## OpenAI Agents SDK — what we use

- **`agents.Agent`** with `model=`, `tools=`, `output_type=`.
- **`agents.extensions.models.litellm_model.LitellmModel`** — wraps a
  LiteLLM model id (`"github_copilot/claude-sonnet-4.6"`).
- **`agent.run_async(prompt)`** — returns `RunResult` with typed
  `final_output` matching `output_type`.
- **`sub_agent.as_tool(name=, description=)`** — exposes a sub-agent as
  a callable tool. Direct map for Maverick's current `Task` subagent
  pattern (parallel briefings, parallel decompose-detail workers).
- **Per-agent model assignment** — each `Agent` instance has its own
  `model=`. Different agents in one workflow run on different
  (provider, model) bindings cleanly.
- **`tool_use_behavior`** — `"run_llm_again"` (default) for normal tool
  loops; `"stop_on_first_tool"` / `StopAtTools` for short-circuit
  patterns when needed.

Known issues to watch:

- Structured outputs + tools combined have provider-specific
  compatibility gaps (e.g., Gemini issue #1575). Verify for our primary
  bindings (Claude / GPT codex on github-copilot) in Phase 0.
- Mixing "Responses" and "Chat Completions" API shapes in one workflow
  isn't recommended; stick to one shape per workflow.

## Burr — what we use (and don't)

### What we use

- **`Application`** with explicit actions and transitions — replaces the
  xoscar supervisor pattern.
- **`bind()`** for injecting Squadron-owned agent instances into actions.
  Class-based actions don't support `bind()`; we keep actions as
  functions.
- **`Hook`s** on `pre_run_step` / `post_run_step` — replace
  `ProgressEvent` yields for Rich Live console.
- **Built-in `Persister`** + time-travel UI — replaces bespoke
  bead-by-bead checkpointing.

### What we don't use

- **Streaming actions.** Our actors are single-shot `_send_structured`
  calls returning typed payloads. Burr's streaming primitives are for
  chatbot-style UIs.
- **`MapActions` / `MapStates`.** Our "stream beads as they become
  ready" pattern fits a *cycle* with a "next bead?" branching action
  better than `MapActions`'s eager materialization.

### Burr-specific concerns to validate

1. **Async hard rule.** One blocking call freezes the whole
   `Application`. We're already async-first (Guardrail #1), but anything
   that sneaks in (`subprocess.run`, sync GitPython call) becomes a real
   bug, not a slow path.
2. **State is the contract.** Per-actor session IDs and OpenCode clients
   were runtime artifacts that should NOT live in `State` (they'd
   serialize into checkpoints meaninglessly). Use `bind()` for transient
   handles, `State` for workflow data. (This is moot after Phase 1
   eliminates sessions, but the principle still applies to other
   runtime handles.)
3. **`bind()` is functional-API only.** Class-based actions can't use
   `bind()`. Keep actions as functions or pass dependencies via
   `__init__`.

## Maverick → Burr mapping (preserved from original research)

| Maverick today                                 | Burr equivalent                              |
| ---------------------------------------------- | -------------------------------------------- |
| `fly`: implement → gate → review → fix → commit | `Application` with cycle (`fix → review`)    |
| Briefing/decompose fan-out                     | OpenAI Agents SDK `as_tool()` sub-agents OR Burr branching actions (TBD) |
| `ProgressEvent` to Rich CLI                    | `Hook`s on `pre_run_step` / `post_run_step` |
| Per-actor OpenCode session                     | Gone after Phase 1 (no sessions)             |
| Bead-by-bead checkpointing                     | Built-in `Persister` + time-travel UI        |
| `@xo.generator`, `__pre_destroy__`, `@xo.no_lock` | Gone — actions are async functions       |

## Actor liveness translates cleanly

Today, the same `ImplementerActor` instance handles `send_implement`
and `send_fix`; the persistent OpenCode session carries context from
implement → fix. After Phase 1, sessions don't exist — context comes
from `message_history` passed to `agent.run_async()`. The continuity
becomes structural in the Burr wiring: the same `bind()`-ed agent
appears in both `implement` and `fix` actions, with prior turns passed
in explicitly. Continuity is right there in the wiring, not buried in
actor reference identity.

## Sources

- [OpenAI Agents SDK]
- [OpenAI Agents SDK — LiteLLM extension reference](https://openai.github.io/openai-agents-python/ref/extensions/litellm/)
- [OpenAI Agents SDK — Agents (output_type, handoffs, tools)](https://openai.github.io/openai-agents-python/agents/)
- [LiteLLM]
- [LiteLLM — GitHub Copilot provider](https://docs.litellm.ai/docs/providers/github_copilot)
- [LiteLLM Router](https://docs.litellm.ai/docs/routing)
- [Apache Burr]
- [Burr — Why Burr](https://burr.dagworks.io/getting_started/why-burr/)
- [Burr — sync vs async](https://burr.dagworks.io/concepts/sync-vs-async/)
- [Burr — actions / `bind()`](https://burr.dagworks.io/concepts/actions/)
- [Issue #95 — silent retry storm landmine](https://github.com/get2knowio/maverick/issues/95)
- [PR #94 — Squadron + Agent extraction](https://github.com/get2knowio/maverick/pull/94)
- [pydantic-graph](https://ai.pydantic.dev/api/pydantic_graph/graph/) — Burr runner-up; pure state machine library, no LLM coupling
- [LangGraph complexity critique](https://www.ema.ai/additional-blogs/addition-blogs/langgraph-alternatives-to-consider)
- [Durable execution: Temporal/Restate/DBOS](https://devstarsj.github.io/2026/04/03/durable-execution-temporal-restate-dbos-distributed-workflows-2026/) — overkill for an interactive CLI

[LiteLLM]: https://docs.litellm.ai/
[OpenAI Agents SDK]: https://openai.github.io/openai-agents-python/
[Apache Burr]: https://github.com/apache/burr/
[#94]: https://github.com/get2knowio/maverick/pull/94
