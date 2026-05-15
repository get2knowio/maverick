# Pattern D — Implementation Plan

**Status:** Draft for review. Not yet started.
**Parent docs:** [migration-recommendation.md](./migration-recommendation.md),
[spikes/runtime-protocol-v0.md](./spikes/runtime-protocol-v0.md).

## Scope

Implement Maverick's Pattern D substrate: a `Runtime` protocol with
**five vendor-specific adapters**. Migrate every agent off the
existing OpenCode HTTP runtime. Delete `src/maverick/runtime/opencode/`
(the ~2400-LOC local-server wrapper) once empty.

Targeted runtime adapters:

| Adapter | Wraps | What it serves |
|---|---|---|
| **ClaudeCodeRuntime** | `claude-agent-sdk` (`pip install claude-agent-sdk`) | Claude family — subscription auth via Claude Max / Pro |
| **CodexRuntime** | `openai-codex-sdk` (`pip install openai-codex-sdk`; `from codex_app_server import Codex`) | OpenAI codex models — ChatGPT Plus subscription auth |
| **CopilotRuntime** | `github-copilot-sdk` (`pip install github-copilot-sdk`; `from copilot import CopilotClient`) | GitHub Copilot subscription (codex + Claude routes via Copilot) |
| **OpenCodeRuntime** | Direct HTTP against `https://opencode.ai/zen/v1` (OpenAI-compatible) | opencode-go subscription (Zen-gated models — gpt-5-nano, deepseek, minimax, etc.) |
| **AnthropicRuntime** | `anthropic` (`pip install anthropic`) | Pay-per-token Anthropic for orgs / CI (optional, lower priority) |

All five sit behind the same `Runtime` Protocol (`execute`, `reset`,
`aclose`, `validate_binding`). Agents don't know which adapter they
talk to. Routing happens via tier config.

Three of the five (Claude Code, Codex, Copilot) are **CLI-wrapper
SDKs** — each wraps a vendor-maintained subprocess. We don't allocate
ports, manage passwords, validate model IDs at startup, or own the
client code. The fourth (OpenCode Zen) is a thin HTTP call. The
fifth (Anthropic direct) is the pay-per-token escape hatch.

## What gets deleted at the end

- `src/maverick/runtime/opencode/` — the local-server wrapper
  (~2400 LOC including `client.py`, `server.py`, `errors.py`,
  `tiers.py` cascade impl, `executor.py`, profile bundle).
- The `opencode` binary dependency from CLAUDE.md +
  `.devcontainer/devcontainer.json`.
- Four documented landmines.
- The `spawn_opencode_server` flow + handle infrastructure in
  `Squadron`.

What survives:
- `Squadron` — keeps its cost-sink, tier-override, and lifecycle
  semantics. Just stops spawning a local server.
- `Agent` base class — minor surgery to depend on `Runtime`
  instead of `OpenCodeServerHandle`.
- The cascade machinery in `tiers.py` — re-targeted to work across
  runtimes (filter bindings by `runtime.validate_binding()` before
  trying them).
- All payload classes in `maverick.payloads`.

## Phasing

```
Phase 1 — Foundation                                  (3-4 days)
Phase 2 — ClaudeCodeRuntime + first agent             (3-5 days)
Phase 3 — OpenCodeRuntime (Zen)                       (2-3 days)
Phase 4 — CopilotRuntime                              (3-5 days)
Phase 5 — CodexRuntime                                (3-5 days)
Phase 6 — Migrate remaining agents                    (1 week)
Phase 7 — Delete OpenCode HTTP runtime + cleanup      (2-3 days)
Phase 8 — Optional: AnthropicRuntime                  (2-3 days)
```

Total estimated effort: **4-6 weeks**, single developer, with
per-role flag rollouts so each phase is independently revertable.

## Phase 1 — Foundation

**Goal:** promote the spike's `Runtime` protocol to production, with
neutral naming and a clean import boundary.

Work:

1. **Move `src/maverick/runtime/protocol.py` to production.** Add
   tests. Settle the API: `execute / reset / aclose / validate_binding`
   is the v1 shape from the spike revision. Move `system` and
   `persona` from per-call to runtime construction (so
   schema/persona changes don't trigger a reconnect mid-scope).
2. **Move `CostRecord` from `runtime/opencode/tiers.py` to a neutral
   location** (`runtime/cost.py`). All adapters import from there.
3. **Rename the error hierarchy.** `OpenCodeAuthError` →
   `RuntimeAuthError`, `OpenCodeTransientError` →
   `RuntimeTransientError`, `OpenCodeStructuredOutputError` →
   `RuntimeStructuredOutputError`, `OpenCodeModelNotFoundError` →
   `RuntimeModelNotFoundError`, `OpenCodeContextOverflowError` →
   `RuntimeContextOverflowError`, `OpenCodeProtocolError` →
   `RuntimeProtocolError`. Keep `OpenCode*` aliases for one cycle
   so the existing cascade module compiles unchanged.
4. **Extract a `BaseRuntime` mixin** with the boring stuff every
   adapter does the same way: cost-record logging, async context
   manager, error wrapping. Subclasses override `execute / reset /
   aclose / validate_binding`.
5. **Adjust `Agent` base class** to take a `Runtime` instance
   instead of an `OpenCodeServerHandle`. Lazy session inside the
   runtime, not the agent. Migrate `_send_structured` /
   `_send_text` to call `runtime.execute(...)`. Single backward-
   compat wrapper so existing tests keep passing.
6. **Adjust `Squadron`** to build runtime instances per agent
   instead of spawning a server. Per-role wiring decides which
   runtime each agent gets. For Phase 1 the dispatch defaults to
   the legacy OpenCode path (still works) — actual runtime
   selection lights up in Phase 2+.

**Validation:** existing `make ci` passes against the renamed
hierarchy with `OpenCode*` aliases. No behavior change yet.

## Phase 2 — ClaudeCodeRuntime + Briefing migration

**Goal:** ship the first real adapter, prove the migration shape
end-to-end on a real agent, validate subscription auth works in
production.

Work:

1. **Lift `ClaudeSdkRuntime` from spike to
   `src/maverick/runtime/claude_code_adapter.py`.** Rename to
   `ClaudeCodeRuntime`. Drop the OpenCode-named error imports (we
   now use `RuntimeAuthError`, etc.).
2. **Add support for `CLAUDE_CODE_OAUTH_TOKEN` env var** so CI /
   non-interactive contexts can use a long-lived OAuth token from
   `claude setup-token` instead of the interactive browser flow.
3. **Build a proper structured-output forcing flow.** Today the
   spike uses prompt-engineering ("call submit_result exactly
   once"). Investigate whether the SDK supports
   `tool_choice={type:"tool",name:"submit_result"}` for guaranteed
   forcing — if yes, use it; if not, document the failure mode.
4. **Test against all four briefing roles** (navigator,
   structuralist, recon, contrarian) on `sample-maverick-project`.
   Confirm typed payloads, cost records, parallel execution
   (refuel runs them via `asyncio.gather`).
5. **Wire `RefuelSquadron.build_briefing_agent` to use
   `ClaudeCodeRuntime` by default.** Remove the `MAVERICK_SPIKE_RUNTIME`
   env-var toggle from the spike.

**Validation:** `maverick refuel` end-to-end on the sample project
produces 4 valid briefings, then an outline, then ~10 detail passes,
then a fix. Cost telemetry shows up in structlog rows. Subscription
budget consumed (not API quota).

**Open question to resolve before starting:** does the briefing
fan-out (4 briefings in parallel via `asyncio.gather`) work with 4
independent `ClaudeCodeRuntime` instances each spawning a Claude
subprocess? If subprocess fork overhead is heavy (~1-2s × 4), we
may want a process pool. Measure first.

## Phase 3 — OpenCodeRuntime (Zen)

**Goal:** preserve opencode-go subscription leverage with the
simplest possible adapter.

Work:

1. **Build `src/maverick/runtime/opencode_zen_adapter.py`.**
   Class name: `OpenCodeRuntime`. Wraps the `openai` Python package
   pointed at `https://opencode.ai/zen/v1`. Use the existing
   opencode-go API key from `~/.local/share/opencode/auth.json`
   (or `OPENCODE_API_KEY` env override).
2. **Structured output via OpenAI Chat Completions
   `response_format=json_schema`.** Zen is OpenAI-compatible, so we
   can use the standard structured-output mechanism without inventing
   one. Watch for the 30%-envelope-wrapping quirk on some models —
   keep a minimal `_unwrap_envelope` helper as defence.
3. **Cost telemetry** from the OpenAI response shape. Zen pricing
   table is per-model (see `https://opencode.ai/zen/`); compute
   `cost_usd` ourselves against a price map.
4. **No subprocess.** Just `AsyncOpenAI(base_url=..., api_key=...)`.

**Validation:** point one cheap role (probably the
`outlines.summary` step in plan generation, or the
`fast_text` tier) at OpenCodeRuntime. Run it on a small flight plan.
Confirm typed output, cost telemetry, ~$0 actual cost (these are
mostly free models).

**Open questions:**
- Does Zen support all the structured-output shapes we need? Some
  providers via Zen route to Anthropic-shape adapters internally —
  may not honour OpenAI's `response_format`. Test before
  committing roles.
- What's the model menu we actually want to use? gpt-5-nano,
  deepseek-v4-flash-free, etc. — need to pick which to declare as
  fallbacks in `DEFAULT_TIERS`.

## Phase 4 — CopilotRuntime

**Goal:** preserve Copilot subscription leverage; replace OpenCode's
Copilot routing entirely.

Work:

1. **Build `src/maverick/runtime/copilot_adapter.py`.** Wraps
   `github-copilot-sdk` (`from copilot import CopilotClient`).
   Reference: Conductor's `CopilotProvider` in
   `/tmp/conductor/src/conductor/providers/copilot.py`
   (~2000 LOC, much of which is retry/idle-recovery logic we may
   not need).
2. **Auth: existing GitHub Copilot OAuth.** The SDK uses the same
   `~/.config/github-copilot/` / `gh auth` credential store. If
   `gh` is logged in and the user has Copilot, auth Just Works.
3. **Structured output forcing.** The Copilot SDK exposes tools;
   use the same `emit_output` forced-tool pattern Conductor uses.
4. **Model menu:** Copilot offers codex models (`gpt-5.3-codex`,
   `gpt-5-mini`, `gpt-5.4-mini`) AND Claude variants
   (`claude-sonnet-4.6`). The Claude-on-Copilot path is broken
   (Phase 0/0b findings) — exclude those bindings from CopilotRuntime
   by `validate_binding` returning False for `model_id` starting
   with `claude-`. Force Claude routes through ClaudeCodeRuntime
   or AnthropicRuntime.

**Validation:** migrate one codex-routed role (`generate` tier)
to CopilotRuntime. Confirm structured output + subscription
billing + typed payloads. Run a real refuel through generate.

**Open question:** the Copilot Python SDK is in public preview
("may change in breaking ways"). Pin to a specific version in
pyproject.toml and document the upgrade path.

## Phase 5 — CodexRuntime

**Goal:** add ChatGPT Plus subscription as a third codex-capable
auth path; useful as a fallback when Copilot is rate-limited.

Work:

1. **Build `src/maverick/runtime/codex_adapter.py`.** Wraps
   `openai-codex-sdk` (`from codex_app_server import Codex`).
   Async client + Pydantic models for the JSONL event stream.
2. **Auth: ChatGPT OAuth from `~/.local/share/opencode/auth.json`
   `openai.access`** — that's a Plus-plan OAuth token. Plus the
   API-key fallback via `OPENAI_API_KEY`.
3. **Structured output forcing** via the Codex SDK's
   tool-invocation mechanism. The SDK is JSON-RPC over stdin/stdout,
   similar to claude-agent-sdk; expect a similar tool-registration
   pattern.
4. **Model menu:** codex variants only. Doesn't serve Claude.

**Validation:** point one role (perhaps `implement` tier's secondary
binding) at CodexRuntime. Run a real fly on a bead. Confirm cost
telemetry and subscription draw.

**Open questions:**
- Is the Codex SDK production-ready or still beta-flavoured? It's
  4 months old (Jan 2026). Worth a quick stability check before
  committing roles to it.
- Does the SDK return enough cost info to populate `CostRecord`?
  If not, we maintain a pricing table for codex like we do for
  Anthropic.

## Phase 6 — Migrate remaining agents

**Goal:** every role in Maverick runs on a Pattern D runtime.

Work item per agent (briefing already migrated in Phase 2):

- DecomposerAgent → ClaudeCodeRuntime (outline + detail + fix)
- GeneratorAgent → ClaudeCodeRuntime  (flight plan synth)
- ReviewerAgent → ClaudeCodeRuntime  (frontier role)
- CodingAgent (implementer) → CopilotRuntime (codex via Copilot
  subscription)
- Any cheap/fast role currently in `fast_text` tier →
  OpenCodeRuntime (Zen)

Each migration:

1. Construct the appropriate runtime in the agent's squadron.
2. Pass it to the agent via the constructor.
3. Behind a per-role flag — default to legacy OpenCode HTTP for
   the first PR, flip to new runtime after one end-to-end run
   succeeds.
4. Run `make ci` + a real workflow on `sample-maverick-project`.

**Validation:** full refuel + fly + land workflow against a bead.
Cost telemetry rolls up correctly across runtimes.

## Phase 7 — Delete OpenCode HTTP runtime

**Goal:** the ~2400 LOC + four landmines disappear.

Work:

1. Remove `src/maverick/runtime/opencode/` (the local-server
   wrapper). Keep the new `opencode_zen_adapter.py` — those are
   different things.
2. Remove `opencode` binary dependency from CLAUDE.md and
   `.devcontainer/devcontainer.json`.
3. Update CLAUDE.md: move the four landmines to a historical-context
   section under "Why we migrated."
4. Close issue #95 (silent-retry-storm landmine — the bug ceases
   to exist).
5. Update `pyproject.toml` to add the new SDK deps
   (`claude-agent-sdk`, `openai-codex-sdk`, `github-copilot-sdk`,
   `anthropic` if Phase 8 ships).
6. Drop `acp`, `agent-client-protocol`, `xoscar` if anything else
   becomes prunable (unlikely — xoscar is still load-bearing
   for the workflow layer).

**Validation:** `make ci` passes. A fresh devcontainer build
doesn't need `opencode` installed. A full `maverick refuel` +
`fly` works.

## Phase 8 — Optional: AnthropicRuntime

**Goal:** pay-per-token escape hatch for orgs / CI that prefer
explicit API billing over subscription consumption.

Work:

1. **Build `src/maverick/runtime/anthropic_adapter.py`.** Wraps
   `anthropic` Python package's `AsyncAnthropic.messages.create()`.
   Reference: Conductor's `ClaudeProvider`.
2. **Auth: `ANTHROPIC_API_KEY` env var only.**
3. **Structured output via `emit_output` forced tool.** Same
   pattern as ClaudeCodeRuntime; different transport.
4. **Cost telemetry:** Anthropic's raw API doesn't return
   `total_cost_usd`; compute from token counts × pricing table.

**Configuration-time selection** between this and ClaudeCodeRuntime
based on which auth the deployment has. Default remains
ClaudeCodeRuntime; set `MAVERICK_CLAUDE_RUNTIME=anthropic` in env
to switch.

**Validation:** point one Claude role at AnthropicRuntime. Confirm
typed output, cost telemetry, lower per-call cost.

## Tier configuration

After all adapters land, `DEFAULT_TIERS` in
`runtime/cost.py` (or wherever it ends up) looks roughly like:

```python
DEFAULT_TIERS = {
    "briefing":  Tier(bindings=(
        Binding("claude_code", "claude-haiku-4-5"),
        Binding("anthropic",   "claude-haiku-4-5"),       # fallback
    )),
    "decompose": Tier(bindings=(
        Binding("claude_code", "claude-sonnet-4.6"),
        Binding("anthropic",   "claude-sonnet-4.6"),
    )),
    "generate":  Tier(bindings=(
        Binding("claude_code", "claude-sonnet-4.6"),
        Binding("anthropic",   "claude-sonnet-4.6"),
    )),
    "implement": Tier(bindings=(
        Binding("copilot",     "gpt-5.3-codex"),
        Binding("codex",       "gpt-5.3-codex"),          # fallback
        Binding("opencode",    "gpt-5.3-codex"),
    )),
    "review":    Tier(bindings=(
        Binding("claude_code", "claude-sonnet-4.6"),
        Binding("anthropic",   "claude-sonnet-4.6"),
    )),
    "fast_text": Tier(bindings=(
        Binding("opencode",    "gpt-5-nano"),
        Binding("copilot",     "gpt-5-mini"),
    )),
}
```

Cross-runtime cascade: a tier can mix runtimes; the cascade tries
them in order. `validate_binding()` on each runtime filters
impossible bindings (Claude can't go to CopilotRuntime; codex can't
go to ClaudeCodeRuntime) before the attempt.

## Testing strategy

Three levels of test:

1. **Unit tests per adapter** — mock the SDK at the boundary
   (`claude_agent_sdk.ClaudeSDKClient`, `copilot.CopilotClient`,
   etc.). Validate auth handling, error classification, cost
   extraction, structured-output parsing. Pattern: same shape as
   today's `tests/unit/runtime/opencode/`.
2. **One end-to-end probe per adapter** — a `scripts/probe-<adapter>.py`
   that runs a real call against the real SDK with real creds.
   Run manually, not in CI. Update when the SDK changes.
3. **Real workflow on `sample-maverick-project`** — every adapter
   migration ends with a real `maverick refuel` / `fly` / `land`
   run on the sample project. Either it works or it doesn't.

Don't write integration tests that hit real APIs in CI — too
expensive, too flaky. Probes are manual; unit tests are CI.

## Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Subprocess fan-out overhead (4 parallel briefings × ~2s subprocess startup) | Medium | Measure in Phase 2; if material, add a per-runtime process pool with LRU eviction |
| Copilot Python SDK breaking changes (public preview) | High | Pin version, monitor releases, keep `gh` + OAuth path as fallback |
| Codex SDK immaturity (4 months old) | Medium | Defer to Phase 5; if too unstable, use OpenAI's `openai` package with `OPENAI_API_KEY` directly as a stopgap |
| Zen gateway not honoring `response_format` for some models | Medium | Test per-model in Phase 3; restrict Zen to models we've confirmed |
| Anthropic Agent SDK credit pool change (June 15 2026) | Known | Measure subscription draw in Phase 2; if quotas tight, push toward Phase 8 (AnthropicRuntime) sooner |
| Per-role flag rollout drags on | Low | Each phase blocks the next; force atomic completion per agent |

## Open questions to resolve before starting

These need answers before writing code:

1. **Anthropic licensing — the change you mentioned.** Need a
   primary source link for the updated terms (specifically: is
   Claude Agent SDK now permitted for *all* third-party use cases,
   not just first-party Claude Code? What quota does it draw
   from?). The memo currently assumes the answer is "yes, all use
   cases, separate Agent SDK quota pool" — confirm before
   committing the recommendation to that.
2. **Briefing fan-out subprocess cost.** Measure before Phase 2
   ships. If 4 parallel Claude subprocesses cost 4-8s of startup,
   we may want to redesign briefings to share one subprocess.
3. **OpenAI Codex SDK auth.** Confirm whether the SDK accepts the
   ChatGPT OAuth token in `~/.local/share/opencode/auth.json` or
   requires a different auth flow. If the former, no extra setup.
   If the latter, document the bootstrap.
4. **xoscar fate.** Pattern D doesn't require replacing it, but if
   we're deleting OpenCode and rebuilding the agent layer anyway,
   is this the moment to also drop xoscar in favor of plain
   `asyncio.TaskGroup`? Separate decision; raise after Phase 6 lands.
5. **Where does `DEFAULT_TIERS` live after the rename?**
   Currently in `runtime/opencode/tiers.py` — that gets deleted.
   Probably `runtime/tiers.py` or `runtime/defaults.py`. Trivial
   but pick before Phase 1 lands.
6. **Pricing tables.** ClaudeCodeRuntime gets `cost_usd` for free
   from the SDK. AnthropicRuntime, CopilotRuntime, CodexRuntime,
   OpenCodeRuntime probably don't. We maintain a per-(provider,
   model) price map. Where? Likely `runtime/pricing.py`. How fresh
   does it need to be? Probably monthly update is fine.

## Out of scope for this plan

- Replacing xoscar with Burr (defer; separate decision).
- Adopting Microsoft Conductor as a library dependency (defer;
  watch for 3-6 months first).
- Implementing PydanticAI's `Model` interface on top of our
  adapters as an exposed face for PydanticAI-using clients
  (forward-looking; no current consumer).
- Cross-runtime caching strategies (e.g., re-using a warm Claude
  Code subprocess across multiple agents within a workflow). The
  v0 protocol's `reset()` semantics handle scope correctly; cache
  optimization is a Phase 9+ concern.

## Deliverables checklist

- [ ] `src/maverick/runtime/protocol.py` (production)
- [ ] `src/maverick/runtime/cost.py` (neutral CostRecord home)
- [ ] `src/maverick/runtime/errors.py` (`Runtime*` hierarchy + `OpenCode*` aliases)
- [ ] `src/maverick/runtime/claude_code_adapter.py`
- [ ] `src/maverick/runtime/opencode_zen_adapter.py`
- [ ] `src/maverick/runtime/copilot_adapter.py`
- [ ] `src/maverick/runtime/codex_adapter.py`
- [ ] `src/maverick/runtime/anthropic_adapter.py` (optional / Phase 8)
- [ ] `src/maverick/runtime/pricing.py` (per-model price map)
- [ ] `src/maverick/runtime/tiers.py` (DEFAULT_TIERS — moved from `runtime/opencode/`)
- [ ] Updated `src/maverick/agents/base.py` (depends on `Runtime`)
- [ ] Updated `src/maverick/squadron/*.py` (constructs runtimes, not server handles)
- [ ] One `scripts/probe-<adapter>.py` per adapter
- [ ] Updated `CLAUDE.md` (replaces OpenCode HTTP narrative with Pattern D)
- [ ] Deleted `src/maverick/runtime/opencode/`
- [ ] Updated `.devcontainer/devcontainer.json` (drops `opencode` binary)
