# Migration: maverick from ACP+MCP-gateway → OpenCode HTTP substrate

You're being asked to execute a substrate migration. Context, scope, validated findings, phasing, and acceptance criteria are below. The spike that produced this plan is at `/tmp/opencode-spike/` (assessment writeup at `/tmp/opencode-spike/ASSESSMENT.md`, working code in the same dir). Read that assessment first — it has the empirical data backing every recommendation here. Don't barrel through the whole migration before surfacing findings; **stop and report after each phase**.

## Mission

Replace the per-provider Agent Client Protocol (ACP) bridges + the in-process MCP gateway used for agent → supervisor result delivery with **OpenCode HTTP** as the runtime. Preserve everything above the runtime layer. Net change is roughly –3000 LOC: large deletions of code that no longer needs to exist, plus a small new runtime module.

## Background — why we're doing this

The current substrate has two unreliable seams:

1. **Per-provider ACP bridges** (`claude-agent-acp`, `gemini --acp`, `copilot acp`, `opencode acp`) each behave slightly differently. Gemini's ACP mode silently drops session-level `mcp_servers`. Copilot's bridge drops MCP tool-call results. Claude works but has a ~5% skip-the-tool-call rate. There's no protocol-level `tool_choice` forcing.
2. **Agent → supervisor delivery via custom MCP** (`maverick.tools.agent_inbox`). Agents call `submit_review` / `submit_implementation` / `submit_outline` etc.; the gateway routes results back to the actor. This bolted-on layer accumulated patches: JSON-in-text fallback, envelope unwrap, transient-error retry, supervisor-side reviewer escalation. It's brittle.

OpenCode (`opencode serve`, default `127.0.0.1:4096`) runs as an HTTP server with multi-provider support and a `format: { type: "json_schema", schema: ... }` mechanism. Crucially, that mechanism works by **synthesizing a `StructuredOutput` tool that the model is forced to call** — not by asking the model to emit JSON in text. That collapses the entire agent_inbox layer into one HTTP arg.

Strategic alignment: model providers are pivoting from subscriptions to pure token-based pricing. We want closed frontier → open hosted → local, picking the cheapest viable model per task. OpenCode's multi-provider story is the substrate for that pivot.

## What the spike validated

Read `/tmp/opencode-spike/ASSESSMENT.md` for full data. Headlines:

- **Structured-output reliability** with the envelope-unwrap helper added: 100% on GPT-4o-mini, 100% on qwen3-coder (open weights via OpenRouter), 97% on claude-haiku-4.5 across three realistic schemas × 10 trials each. (Without the unwrap, claude-haiku is 67% — see Landmine 3.)
- **MCP tool execution** is provider-agnostic. All three cloud providers tested invoked the same tool name (`<server-id>_<tool-name>`) and retrieved correct results. No provider-special-cases needed.
- **xoscar actor integration** works without changes to our actor model. `OpenCodeAgentActor` + `SupervisorActor` end-to-end demonstrated in `/tmp/opencode-spike/test_xoscar_actor.py`. `@xo.no_lock` discipline carries over verbatim.
- **Cancellation** via `POST /session/:id/abort` returns in ~14ms and leaves the server healthy.
- **5 concurrent sessions** wall/median ratio 1.34× — no serialization.

The spike's recommendation was **GO with caveats**. The caveats are the three landmines below.

## Three landmines you MUST handle

These each have a known fix; ignoring them produces a worse runtime than what we have today.

### Landmine 1: async dispatch + bad modelID = persistent server crash loop

`POST /session/:id/prompt_async` with an invalid `modelID` returns HTTP 200, persists the user message to `~/.local/share/opencode/opencode.db`, and crashes the server in the background dispatch (`ProviderModelNotFoundError` is unhandled). On next start, the server replays the unfinished message and crashes again — permanent crash loop until the DB row is purged.

**Mitigations to bake in:**
- Validate `modelID` against `GET /provider`'s connected providers before any send. Reject unknown ones at the maverick layer with a clear `MaverickError` subclass.
- Prefer the synchronous `POST /session/:id/message` path for everything load-bearing. Only use `prompt_async` if you have a specific reason and have validated the model first.
- Ship a runbook entry / utility for "OpenCode won't start" → run a `purge_queued.py` equivalent (see `/tmp/opencode-spike/purge_queued.py`).
- Consider this a real upstream OpenCode bug. File an issue against `sst/opencode` as part of this migration, even if we never expect to hit it ourselves.

### Landmine 2: errors are silent on the synchronous HTTP response

`POST /session/:id/message` returns HTTP 200 + empty body when:
- The model ID doesn't exist (silent — see Landmine 1 for the async variant which is worse).
- The provider auth is wrong (silent; surfaces only as `session.error` event).
- The prompt exceeds the model's context window (silent; OpenCode auto-compacts with `info.mode = "compaction"`).

Errors **do** surface on the `/event` SSE stream as `session.error` events with structured `error.name` and `error.data.message`. So the client must always run an event-drain in parallel with `send_message` and join the two before declaring success.

**Mitigation:** the runtime module wraps "send + watch for error event" into a single async helper. Every actor uses it. The pattern is demonstrated in `/tmp/opencode-spike/test_xoscar_actor.py:_drain_events`. Don't try to short-circuit by trusting the HTTP response alone.

The one exception observed: `StructuredOutputError` (model failed to honour `format=json_schema`) is correctly surfaced as an HTTP 4xx, so it's catchable from `send_message` directly.

### Landmine 3: Claude wraps structured-output payloads inconsistently

When `format=json_schema` is set, OpenCode emits a synthesized `StructuredOutput` tool. The validated payload appears at `info.structured`. **Claude (haiku-4.5) wraps the payload in a single envelope key** ~30% of the time: `{input: {...}}`, `{output: {...}}`, `{parameter: {...}}`, `{content: '<json-string>'}`, occasionally `{complex_type: ..., work_units: [...]}` — varied. GPT-4o-mini and qwen3-coder return the bare schema-shaped object every time.

**Mitigation:** a 15-LOC `_unwrap_envelope` helper. Implementation is in `/tmp/opencode-spike/opencode_client.py:_unwrap_envelope`. Always unwrap before calling `model_validate`. Treat this as a permanent client-side normalization layer (no plan to fix upstream — Claude's tool-call shape is what it is).

## Migration scope

### Delete (the migration's payload)

| path                                             | replaced by                                       |
| ------------------------------------------------ | ------------------------------------------------- |
| `src/maverick/tools/agent_inbox/`                | OpenCode `format=json_schema` — no replacement needed |
| `src/maverick/executor/acp/`                     | New `src/maverick/runtime/opencode/` runtime      |
| `src/maverick/actors/xoscar/agentic_mixin.py` (or wherever `AgenticActorMixin` lives) | New `OpenCodeAgentMixin` |
| ACP bridge dependencies in `pyproject.toml`: `acp` (the SDK), `claude-agent-acp` | OpenCode SDK is HTTP-only; no python deps needed |
| `submit_review` / `submit_implementation` / `submit_outline` MCP tool schemas | Pydantic models passed to `format=json_schema` |
| JSON-in-text fallback in the briefing actor (just merged) | Not needed — OpenCode's tool-forcing makes this dead code |
| Supervisor-side reviewer escalation logic        | Replaced by provider tier cascade (Phase 5)      |
| Per-actor MCP gateway register/unregister (`_register_with_gateway`, `_unregister_from_gateway`) | Gone — supervisor is no longer an HTTP surface |
| `transport_kwargs={"limit": 1_048_576}` (1 MB stdio buffer hack for ACP) | Not needed |

### Preserve (do NOT touch)

- The xoscar actor pattern: `n_process=0`, `@xo.no_lock` on supervisor reverse-call methods, `__post_create__` / `__pre_destroy__` lifecycle, `xo.wait_for(...)` (not `asyncio.wait_for`).
- The supervisor + actor + workflow separation of concerns (CLAUDE.md "Separation of concerns").
- The workspace-as-remote architecture (CLAUDE.md "Guardrail 0"). All commit-graph mutations through `JjClient`. `WorkspaceManager` lifecycle unchanged.
- The bead model, the flight plan model, the runway store. Those are above the substrate.
- Every workflow shape: `plan generate`, `refuel`, `fly`, `land`, `runway`. Workflows orchestrate; only their executor changes.
- Every agent's prompt content. Prompts move with their actors; only the transport changes.
- jj for write-path VCS, GitPython for reads, PyGithub for GitHub API, structlog for logging, tenacity for retries, detect-secrets for secret scanning. All unchanged.
- The CLI surface. `maverick fly`, `maverick land`, `maverick refuel`, etc. — invocation and outputs identical.

### Add (the new code)

- `src/maverick/runtime/opencode/`: HTTP client, event watcher, error classifier, server lifecycle (spawn/health-check), provider validation. Adapted from `/tmp/opencode-spike/opencode_client.py` with maverick conventions (structlog, tenacity, dataclass results, MaverickError subclasses).
- `OpenCodeAgentMixin` (replaces `AgenticActorMixin`): each actor declares ONE Pydantic model (its result type) instead of MCP tool schemas. `__post_create__` opens an OpenCode session; `send_*` methods use `format=json_schema` and return typed payloads. No `on_tool_call`, no `mcp_tools` ClassVar, no gateway registration.
- Provider tier system (Phase 5): config-driven model selection with cascading fallback, replacing the current "Claude / Copilot" tier.

## Phased plan

Each phase is a separable commit. Run `make ci` green at each phase boundary. Open the PR when Phase 1 lands so the foundation can be early-reviewed; merge the rest as phases complete (single PR is also acceptable — implementer's choice). Work on a feature branch (next available number per CLAUDE.md branch numbering — likely `041-opencode-substrate-migration` or similar).

### Phase 1: Foundation — `maverick/runtime/opencode/` package

**Scope:** Productionize the spike client. No behaviour changes anywhere else yet. Old ACP path keeps working in parallel.

**Files:**
- `src/maverick/runtime/__init__.py` — new package
- `src/maverick/runtime/opencode/__init__.py`
- `src/maverick/runtime/opencode/client.py` — adapted from `/tmp/opencode-spike/opencode_client.py`
- `src/maverick/runtime/opencode/events.py` — SSE stream watcher with session-id filtering and error-event detection
- `src/maverick/runtime/opencode/errors.py` — `OpenCodeError` hierarchy: `OpenCodeAuthError`, `OpenCodeModelNotFoundError`, `OpenCodeStructuredOutputError`, `OpenCodeTransientError`, etc. — subclasses of `MaverickError`
- `src/maverick/runtime/opencode/server.py` — spawn / health-check / lifecycle for an OpenCode subprocess (use `asyncio.create_subprocess_exec`, NOT `subprocess.Popen.communicate()` — that'd block the loop; see CLAUDE.md ACP-runtime section)
- `src/maverick/runtime/opencode/validation.py` — model-id validator that calls `GET /provider` and rejects unknowns (Landmine 1 mitigation)
- `tests/unit/runtime/opencode/` — unit tests with httpx mock transport
- `tests/integration/runtime/test_opencode_runtime.py` — integration test that spawns a real OpenCode server, exercises send_message + structured output + cancellation + concurrent sessions

**Adapt the spike code, don't copy verbatim:**
- Use `structlog.get_logger(__name__)` for logging.
- Wrap retryable HTTP calls with `tenacity.AsyncRetrying`.
- Replace `OpenCodeError` with the proper subclass hierarchy. Map `StructuredOutputError` → `OpenCodeStructuredOutputError`. Map "Model not found in event" → `OpenCodeModelNotFoundError`.
- Preserve the `_unwrap_envelope` helper (Landmine 3) and `structured_of` extractor.
- Add `validate_model_id(provider_id, model_id) -> None` that raises `OpenCodeModelNotFoundError` if the model isn't in the connected provider list. Every send path calls it first.
- Add `send_with_event_watch(session_id, content, *, format, model, timeout)` that fires the send and event-drain concurrently, raises `OpenCodeAuthError` / etc. if a `session.error` event arrives, returns the parsed response otherwise (Landmine 2 mitigation).
- Decide: does maverick spawn the OpenCode server itself (matching the actor pool model — bind to `127.0.0.1:0`, port discovery by reading the server's startup log)? Or is the server external and we discover it via env var? **Recommend: maverick spawns it.** The actor-pool architecture is hermetic and we want one OpenCode per workflow run, on a free port, cleaned up at workflow end. Pattern mirrors how `actor_pool()` works today.
- Consider: `OPENCODE_SERVER_PASSWORD` should be set when we spawn. Use a per-run random secret; pass via `Authorization: Bearer <secret>` header from the client.

**Acceptance:**
- `make lint typecheck test-fast` green.
- New integration test passes against a fresh OpenCode subprocess.
- All three landmines have explicit unit tests demonstrating correct handling.

**Stop and report.** First-phase findings often change the rest of the plan.

### Phase 2: Mixin replacement — `OpenCodeAgentMixin`

**Scope:** Build the new mixin alongside the old `AgenticActorMixin`. Migrate ONE actor (recommend: `CodeReviewerActor`) end-to-end. Do not migrate the rest yet — prove the pattern first.

**The new contract:**

Every agentic actor declares:

```python
class CodeReviewerActor(OpenCodeAgentMixin, xo.Actor):
    result_model: ClassVar[type[BaseModel]] = SubmitReviewPayload
    provider_tier: ClassVar[str] = "review"  # see Phase 5

    async def review(self, request: ReviewRequest) -> SubmitReviewPayload:
        prompt = build_review_prompt(request)
        return await self._send_structured(prompt)
```

`OpenCodeAgentMixin` provides:
- `__post_create__`: lazy — initializes the OpenCode session on first `_send_structured` call. `_session_id` and `_client` start as `None`.
- `_ensure_session()`: creates the OpenCode session if not already created; reuses across calls.
- `_send_structured(prompt: str, *, schema: type[BaseModel] | None = None, timeout: float = 120) -> BaseModel`: convenience wrapper. Defaults `schema` to `self.result_model`. Calls `client.send_with_event_watch(format=json_schema(schema), ...)`. Unwraps envelope. Validates with the Pydantic model. Returns the typed result.
- `_send_text(prompt: str, *, timeout: float = 120) -> str`: for non-mailbox plain-text steps.
- `new_bead(request)`: rotates the OpenCode session for a fresh context.
- `__pre_destroy__`: deletes the OpenCode session, closes the client.

**No more:**
- `mcp_tools` ClassVar.
- `_register_with_gateway` / `_unregister_from_gateway`.
- `on_tool_call` (the supervisor inbox entry — completely deleted).
- `mcp_server_config()` for routing the agent to its inbox.
- Actor's involvement in the inbox protocol at all.

**Files:**
- `src/maverick/actors/xoscar/opencode_mixin.py` — new mixin
- `src/maverick/actors/xoscar/code_reviewer.py` (or wherever it lives) — migrated to new mixin
- Existing `agentic_mixin.py` stays in place; remaining actors continue to use it.
- `tests/unit/actors/xoscar/test_opencode_mixin.py`
- `tests/integration/actors/test_code_reviewer_opencode.py`

**Acceptance:**
- The migrated reviewer produces equivalent output to the old reviewer for at least 3 representative test cases (write a comparison test if needed).
- `make ci` passes.
- The supervisor never deadlocks — confirm with the same `@xo.no_lock` discipline as today.

**Stop and report.** Pattern validation matters more than speed here; if the mixin shape is wrong, you want to find that out before migrating 12 actors.

### Phase 3: Executor replacement

**Scope:** Replace `AcpStepExecutor` with an OpenCode-backed equivalent for all non-mailbox steps (plain prompt → text response paths). The `StepExecutor` Protocol stays the same; only the implementation changes.

**Files:**
- `src/maverick/runtime/opencode/executor.py` — `OpenCodeStepExecutor` implementing the `StepExecutor` Protocol
- `src/maverick/executor/__init__.py` — wire the new executor as the default
- Tests for executor: migrate from ACP-based fixtures to OpenCode-based fixtures
- Don't delete `src/maverick/executor/acp/` yet — Phase 4 does that

**What the new executor does:**
- Accepts a `Step`, runs it via OpenCode's HTTP client.
- Multi-turn sessions: same `create_session` + multiple `send_message` calls — works the same way ACP's session caching does.
- `output_schema` (existing field for non-mailbox steps): translates to `format=json_schema` in OpenCode. Same reliability guarantees we just measured.
- Cancellation: `xo.wait_for(...)` around `client.send_*` (same pattern); also `client.cancel(session_id)` if the workflow needs to abort mid-step.

**Acceptance:**
- All existing executor tests pass against the new implementation.
- The `briefing_actor` (which has the recently-merged JSON-in-text fallback) loses that fallback — it's no longer needed. Confirm reliability is at least equal.

**Stop and report.**

### Phase 4: Migrate remaining actors and workflows; delete old code

**Scope:** Bulk migration. Every `AgenticActorMixin` user moves to `OpenCodeAgentMixin`. Every workflow that referenced the old executor uses the new one. Then delete.

**Order of operations within the phase:**
1. Migrate every remaining agentic actor to `OpenCodeAgentMixin` (one commit per actor; CI green at each commit).
2. Migrate every workflow's executor reference (one commit).
3. Delete `src/maverick/tools/agent_inbox/` (one commit).
4. Delete `src/maverick/executor/acp/` (one commit).
5. Remove ACP dependencies from `pyproject.toml` (one commit, with `uv lock` regen).
6. Delete `src/maverick/actors/xoscar/agentic_mixin.py` if nothing references it (one commit).

**Acceptance:**
- `git grep -E 'agent_inbox|AcpStepExecutor|AgenticActorMixin|claude-agent-acp'` returns zero hits in `src/`.
- All workflows run end-to-end on the new substrate.
- `make ci` green.
- Integration tests in `tests/integration/` migrated and passing.

**Stop and report.** This is the largest phase by LOC change; verify nothing was missed.

### Phase 5: Provider tier system

**Scope:** Replace the current "Claude / Copilot fallback" tier with an OpenCode-driven cascade. Default to qwen3-coder via OpenRouter for most agents; reserve Claude for hard cases.

**Design (let the implementer refine):**
- Tiers are named: `cheap`, `balanced`, `frontier` (or similar). Each tier maps to an ordered list of (provider_id, model_id) pairs.
- Each agent role has a `provider_tier: ClassVar[str]` (set in Phase 2's mixin).
- Config (Pydantic) lets the user override per-tier model lists in `~/.maverick/config.toml`.
- Cascade: try first model in tier; on `OpenCodeModelNotFoundError` / `OpenCodeAuthError` / sustained `OpenCodeTransientError`, fall back to the next.
- Telemetry: log `info.cost` from each response per-bead, aggregated per workflow run. (The `info` field on send_message responses includes `cost`, `tokens`, `modelID`, `providerID` — capture these.)

**Recommended tier defaults (revise based on cost data):**

| tier      | first choice                               | fallback                  |
| --------- | ------------------------------------------ | ------------------------- |
| cheap     | `openrouter/qwen/qwen3-coder`              | `openrouter/openai/gpt-4o-mini` |
| balanced  | `openrouter/anthropic/claude-haiku-4.5`    | `openrouter/qwen/qwen3-coder` |
| frontier  | `openrouter/anthropic/claude-sonnet-4.5`   | `openrouter/openai/gpt-5` (when avail.) |

Agents that need frontier reasoning (decomposer for complex outlines, escalated review) use `frontier`. Reviewer/implementer in steady state can use `balanced` or `cheap` depending on bead complexity.

**Files:**
- `src/maverick/runtime/opencode/tiers.py` — tier resolution, cascade logic
- `src/maverick/config.py` — add `ProviderTierConfig`
- Per-actor `provider_tier` declarations (revise from Phase 2's defaults if needed)

**Acceptance:**
- A "force tier=cheap" run of a real maverick workflow produces equivalent output to a "force tier=frontier" run for at least one bead, demonstrating the cheap tier is viable for most work.
- Cost telemetry visible in the workflow output.
- Cascade fallback exercised by a unit test (mock first provider returning `OpenCodeAuthError`, verify fallback engages).

**Stop and report.** This is where the strategic-pivot value materializes.

### Phase 6: Tests, telemetry, docs, shake-out

**Scope:** Bring CI, telemetry, and documentation up to date with the new substrate.

**Files:**
- `tests/integration/conftest.py` — fixture that spawns an OpenCode subprocess with `OPENCODE_SERVER_PASSWORD` set, tears down after suite
- `CLAUDE.md` — replace the "ACP Execution Model" section with a concise "OpenCode Runtime" section. Mention the three landmines and their mitigations. Update the technology stack table.
- `.specify/memory/constitution.md` — if any of the architectural guardrails reference ACP specifically, refresh
- `Makefile` — if there are ACP-specific make targets, update or remove
- `pyproject.toml` — ensure no leftover ACP deps; add any OpenCode-specific deps (none expected — we're HTTP-direct)
- Update README, docs/, etc. as needed

**Acceptance:**
- `make ci` green on a clean clone.
- A fresh PR description capturing the change for reviewers.
- The three-landmine mitigations are documented in CLAUDE.md so future contributors don't trip on them.

## Out of scope / what NOT to do

- **Don't add a runtime feature flag to switch between ACP and OpenCode.** Maverick is a single-developer codebase on a feature branch; clean cutover is fine and simpler. Toggle complexity is debt we'd carry forever for no gain.
- **Don't preserve the agent_inbox MCP gateway "for backwards compat".** No external consumers exist. Delete it.
- **Don't keep `AcpStepExecutor` as a fallback.** Same reasoning.
- **Don't migrate one workflow at a time across releases.** Within a phase boundary, complete the phase. Half-finished migrations bit us in the past (see "041-remove-yaml-dsl" in the memory — that was a successful complete-cutover; mirror that style).
- **Don't change the agent prompts during migration.** If a prompt needs to change to play nice with the new substrate, that's a separate commit with its own justification, NOT bundled into the migration.
- **Don't rebuild the supervisor or workflow event model.** The events emitted by workflows (`ProgressEvent`s) stay identical. Only the executor's *source* of those events changes.
- **Don't add MCP server wrappers for things OpenCode handles built-in.** OpenCode bundles `read`, `write`, `bash`, `glob`, `grep`, `edit` etc. as built-in tools. Use them. Only wrap external tools (e.g., a `bd` MCP server, runway tools) that aren't built-in.
- **Don't ignore the landmines.** Each one has a specific mitigation; bake all three into Phase 1.
- **Don't `subprocess.Popen.communicate()` anywhere.** It blocks the event loop. Use `asyncio.create_subprocess_exec`. (This is already in CLAUDE.md but worth restating.)
- **Don't push an unsecured OpenCode server.** Set `OPENCODE_SERVER_PASSWORD` per spawn. The spike's "Warning: OPENCODE_SERVER_PASSWORD is not set" line is acceptable for spike work, not for production.

## Reference: spike artifacts

All under `/tmp/opencode-spike/`:

| file                              | role                                                              |
| --------------------------------- | ----------------------------------------------------------------- |
| `ASSESSMENT.md`                   | The full spike writeup. Read this before Phase 1.                 |
| `opencode_client.py`              | Reference HTTP client. Adapt; don't copy verbatim.                |
| `purge_queued.py`                 | Runbook for Landmine 1.                                           |
| `test_xoscar_actor.py`            | Reference pattern for the Phase 2 mixin.                          |
| `test_structured_output.py`       | Reliability harness — port the test methodology, not the file.   |
| `test_mcp_tools.py`               | Reference for MCP tool wiring.                                    |
| `test_cancellation.py`            | Reference for `xo.wait_for` + abort patterns.                     |
| `test_errors.py` / `test_errors_via_events.py` | Reference for Landmine 2 mitigation.                |
| `opencode.jsonc`                  | Reference for declaring external MCP servers.                     |
| `results-*.json`                  | Raw trial data backing every reliability claim in this prompt.    |

## Reference: maverick code you'll touch

Roughly. Confirm with grep — these paths might have moved.

| current location                                      | what happens to it                                           |
| ----------------------------------------------------- | ------------------------------------------------------------ |
| `src/maverick/executor/acp/`                          | Delete in Phase 4                                            |
| `src/maverick/tools/agent_inbox/`                     | Delete in Phase 4                                            |
| `src/maverick/actors/xoscar/agentic_mixin.py`         | Delete in Phase 4 (after replacement merged)                 |
| `src/maverick/actors/xoscar/*_actor.py`               | Migrate to `OpenCodeAgentMixin` in Phase 2 (one) and Phase 4 (rest) |
| `src/maverick/agents/`                                | Prompt content stays. Imports may change to point at new mixin. |
| `src/maverick/workflows/`                             | Update executor reference in Phase 4                         |
| `src/maverick/runners/provider_health.py`             | Replace ACP health checks with OpenCode `/global/health`     |
| `src/maverick/config.py`                              | Add `ProviderTierConfig` in Phase 5                          |
| `pyproject.toml`                                      | Drop ACP deps in Phase 4                                     |
| `CLAUDE.md`                                           | Update in Phase 6                                            |

## Reporting cadence

Stop after each phase and report:
- What changed (files, LOC, behaviour).
- What you measured / verified vs what's still hypothesis.
- Anything that surprised you.
- Open questions before the next phase.

The original spike brief had this rule for a reason. The migration is risky enough that early-phase findings ("the OpenCode subprocess doesn't fit our actor-pool spawn pattern", "the structured-output reliability isn't holding up under our actual prompts", etc.) should reshape the rest of the plan, not be discovered in Phase 6.

## Open questions you'll need to resolve as you go

1. **Server lifecycle:** does maverick spawn one OpenCode per workflow run (mirroring the actor pool), or one shared per-process? Recommend per-workflow for hermeticity, but verify spawn cost (~1s per spawn would dominate fast workflows).
2. **Auth credentials:** today we depend on `~/.local/share/opencode/auth.json` being pre-populated by `opencode auth login`. Acceptable for local dev; for CI we'll need a strategy. Probably env-var-driven `PUT /auth/{provider}` at spawn time.
3. **MCP servers in workflows:** which external MCP servers do we declare in the per-workflow `opencode.jsonc`? At minimum, anything wrapping `bd` (beads) or runway. Identify these in Phase 4.
4. **Cost telemetry storage:** runway is the obvious place. Decide on schema + recording point.
5. **Tier names and defaults:** the `cheap/balanced/frontier` triplet is a starting point. Final naming + per-agent assignments need a small design pass in Phase 5.
6. **OpenCode version pinning:** pin `opencode` to a specific version (currently spike used 1.14.25) and document the bump procedure. The `prompt_async` crash bug (Landmine 1) might get fixed upstream; check before each version bump.

## Cost & quota

This migration will burn meaningful tokens. Two budgets to watch:

- **Anthropic Pro/Max quota** (your Claude Code session). If you hit "You're out of extra usage" mid-phase, **stop and document where you got to in a commit or scratchpad** — don't keep retrying. The user can resume after reset; a clean checkpoint at a phase boundary is much better than half-applied edits.
- **OpenRouter credits.** The spike confirmed there's an OpenRouter API key cached in `~/.local/share/opencode/auth.json` from a prior `opencode auth login`. Every test run, every equivalence check, every workflow re-run during this migration will bill that account. Two implications:
  - Be deliberate about test runs. Don't loop full workflows for incidental verification — use unit tests with mocked transports for fast-feedback work, and reserve real-substrate runs for phase acceptance.
  - If you see auth/billing failures from OpenRouter, **don't retry blindly** — that means the key is exhausted or revoked. Surface it to the user and stop.

If both budgets look healthy, no need to optimize for cost — finish the migration cleanly. But if either signals trouble, halt at a phase boundary and report rather than pushing through.

## Constraints — repeated for emphasis

- Use `make` commands, not raw `uv run`. CI gate is `make ci`.
- jj for write-path VCS, never `git commit/push/merge/branch`.
- Async-first: no `subprocess.run` in `async def` paths; no `asyncio.run()` inside factory functions.
- Single typed contract per action; no `dict[str, Any]` blobs.
- Hardening by default: explicit timeouts, tenacity retries, specific exception handling.
- No global mutable state, no god-classes, no premature abstractions.
- Don't add features beyond migration scope. Net LOC should go *down*, not up.
- Tests are not optional. Each phase's acceptance criteria includes new + migrated tests.

---

Begin with Phase 1. Read `/tmp/opencode-spike/ASSESSMENT.md` first. Then read the spike code under `/tmp/opencode-spike/*.py` to understand the empirical patterns. Then plan Phase 1 (use the Plan agent if helpful), execute, and stop to report.
