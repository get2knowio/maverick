# OpenCode replacement — recommendation memo

**Audience:** Maverick maintainers, anyone evaluating the BURR migration.
**Date:** 2026-05-15.
**Author:** spike work captured in this branch and on `047-phase-0-spike` /
`spike/runtime-protocol-v0`.

## TL;DR

We ran five spikes over two days probing whether to replace OpenCode
with the substrate proposed in `docs/BURR.md` (OpenAI Agents SDK +
LiteLLM + Burr). Four findings drive the recommendation:

1. **The original BURR plan doesn't survive contact with Claude on
   GitHub Copilot.** Both candidate substrates (OpenAI Agents SDK +
   LiteLLM, PydanticAI) fail in different ways on that binding, for
   the same root cause: Copilot's Chat Completions endpoint doesn't
   honour structured-output / tool-use the way OpenAI's Responses API
   does for codex. Per-substrate workarounds are brittle.
2. **Per-binding routing is the right architectural answer.** A small
   `Runtime` interface with vendor-specific adapters lets each agent
   role route to the transport that actually works for it — codex via
   Copilot's subscription path, Claude via the Claude Code SDK
   (subscription) or `anthropic` direct (API key), anything else via
   its own dedicated SDK.
3. **Microsoft already shipped this pattern.** [microsoft/conductor]
   (released May 2026) has an `AgentProvider` ABC with nearly the
   same shape as our `Runtime` protocol, plus working adapters for
   Claude (using `anthropic` direct) and Copilot (using GitHub's
   official `copilot` Python SDK). We arrived at the same design
   independently; we should learn from their implementation rather
   than building parallel infrastructure.
4. **Anthropic's Feb 2026 terms restrict where Max subscription auth
   can be used.** Claude Pro/Max OAuth tokens are licensed for Claude
   Code and Claude.ai only — using them through `anthropic`'s Python
   SDK directly violates terms and Anthropic actively blocks it. The
   `claude-agent-sdk` (which wraps the Claude CLI) is first-party and
   keeps subscription access; the `anthropic` package requires
   pay-per-token billing. This shapes the adapter design.

**Recommendation: pursue Pattern D (the runtime abstraction we
prototyped) with two Claude adapters — a subscription-auth path via
`claude-agent-sdk` for individual dev use, and an API-key path via
`anthropic` direct for orgs / CI / pay-per-token scaling.**

The concrete shape of the path forward is in §6.

## 1. Why we ran spikes

`docs/BURR.md` proposes a substantial migration: replace OpenCode's
HTTP runtime (~2400 LOC + four documented landmines) with an
in-process Python stack — OpenAI Agents SDK on top, LiteLLM
underneath for provider routing, Apache Burr replacing xoscar for
workflow orchestration. The plan estimated 6-8 weeks of work across
three phases.

The decision gate was a Phase 0 spike: prove the bottom of the stack
works on Maverick's hardest case (one implementer bead, typed payload
via tool use) before committing. That spike triggered the rest.

## 2. What we tested

| Spike | Question | Outcome | Branch / PR |
|---|---|---|---|
| **Phase 0** | Does OpenAI Agents SDK + LiteLLM work end-to-end on bead 37n.3? | Mixed — codex passed, Claude failed at structured output | [`047-phase-0-spike`](https://github.com/get2knowio/maverick/pull/97) |
| **V3 redo** | Does the function-tool + StopAtTools pattern fix Claude? | No — Claude on Copilot Chat Completions doesn't call tools at all | (same branch) |
| **Phase 0b** | Does PydanticAI's substrate avoid the Claude problem? | No, but for a different reason — Pydantic's strict response validation rejects Copilot's Chat response shape | (same branch) |
| **Runtime protocol v0** | Can we abstract over both OpenCode and Claude Agent SDK behind one interface? | Yes — clean abstraction, end-to-end run passed | [`spike/runtime-protocol-v0`](https://github.com/get2knowio/maverick/tree/spike/runtime-protocol-v0) |
| **Market research** | Has anyone shipped this pattern already? | Yes — Microsoft Conductor (May 2026) ships nearly the same abstraction with adapters for Claude (Anthropic direct) and Copilot (GitHub's Python SDK) | (notes in this memo) |

Every spike has a self-contained report; this memo is the synthesis,
not a replacement.

## 3. What we learned

### 3a. The original BURR plan has a fatal flaw

Both Phase 0 and 0b found the same wall: **Claude models routed
through GitHub Copilot's Chat Completions endpoint don't honour
structured-output / tool-use contracts.** Specifically:

- OpenAI Agents SDK route: Claude returns text wrapped in markdown
  code fences instead of the typed payload. The SDK has no
  envelope-unwrap layer, so validation fails.
- With `StopAtTools` workaround: Claude on Copilot Chat Completions
  doesn't call tools at all — returns `"Sure! Let me calculate that
  for you!"` and ends the turn.
- PydanticAI route: Pydantic's strict response validation rejects
  Copilot's Chat response shape entirely (missing required field
  `choices[].index`). The framework can't even parse the response,
  let alone evaluate tool-use.

This isn't a framework bug. It's an *upstream* problem: Copilot's
Chat Completions endpoint behaves differently from OpenAI's for the
Claude family. OpenCode works today because it doesn't route Claude
through that endpoint — it uses Copilot's underlying Anthropic
adapter.

Implication: **any substrate that tries to handle every binding
through one transport will hit this wall.** The BURR plan's
"replace OpenCode with one in-process stack" doesn't work as
written.

### 3b. The right pattern is per-binding routing

Each binding has a *native* transport that works. Codex works fine
through OpenAI's Responses API. Claude works fine through
Anthropic's Messages API. The framework problem is forcing
everything through one wire format.

A small `Runtime` interface with one adapter per native transport
lets each role go through the path that actually works:

```
codex roles      → Copilot (subscription leverage) via Copilot's Python SDK
Claude roles     → Anthropic Messages API direct
specialty roles  → whatever fits (LiteLLM for openrouter, etc.)
```

We prototyped this in `spike/runtime-protocol-v0`. After reviewer
pushback on the first draft, the protocol is ACP-shaped — consumers
call `execute(prompt, schema=…)` and get a typed result. No
session IDs visible at the call site. End-to-end run on bead 37n.3
produced a valid typed payload with full cost telemetry
(`cost_usd=$0.14`).

### 3c. The substrate-management differential is large

I initially called OpenCode and Claude SDK "equivalently subprocess-
based." That was wrong. What matters is **who maintains the code
that manages the subprocess.** OpenCode is ours (~2400 LOC, four
landmines, port allocation, password juggling, model-ID
validation). Claude Agent SDK is Anthropic's (`pip install`,
nothing else). Anthropic's `anthropic` Python package isn't even
subprocess-based at all — straight HTTP to the Messages API.

### 3d. PydanticAI's hidden architecture

Phase 0b's most useful finding was structural: PydanticAI
implements typed output as a hidden `final_result` function-tool
call. It doesn't trust the model to emit JSON; it forces a tool
call whose args are validated against the Pydantic schema. This is
exactly what OpenCode does today via its `StructuredOutput` tool,
and it's what Anthropic's tool-use API enforces server-side.

The function-tool route is the substrate-agnostic answer to
structured output. Every modern stack converges on it once they
stop trusting model behaviour.

### 3e. Microsoft Conductor exists

The [microsoft/conductor] project, released May 14, 2026, has:

- An `AgentProvider` ABC with `execute / validate_connection / close
  / execute_dialog_turn / get_max_prompt_tokens`. Nearly identical
  to our `Runtime` protocol.
- A `ClaudeProvider` using the `anthropic` Python package directly
  (no Claude CLI subprocess). Defines an `emit_output` tool for
  structured output. ~2200 LOC including retry/parsing logic.
- A `CopilotProvider` using GitHub's official `copilot` Python SDK.
  This is the path we didn't know existed — Copilot has a Python
  SDK, we don't need OpenCode to talk to it.
- A factory with `provider_type: Literal["copilot", "openai-agents",
  "claude"]`. The OpenAI Agents provider is a planned placeholder.
- YAML/CLI workflow orchestration on top — the parts we don't need.

We arrived at the same provider abstraction independently. That
convergent evolution is signal that this is the right pattern; it
also tells us **we don't need to extract our own version of the
abstraction.**

## 4. What the market already built

| Layer | What's there | Status |
|---|---|---|
| LLM call abstraction | LiteLLM, PydanticAI, Instructor | Mature, multi-vendor |
| **Agent runtime abstraction** | **Microsoft Conductor** | **1 month old, Microsoft-backed** |
| Agent orchestration | Overstory (TypeScript), AutoGen, LangGraph, CrewAI | Active |

Our `Runtime` protocol sits in the middle layer. Conductor occupies
the same niche, with a one-month head start and Microsoft's
distribution.

## 5. What this means for OpenCode specifically

OpenCode is ~2400 LOC of code Maverick maintains, plus four
documented operational landmines (silent crash loops, empty-body
errors, envelope wrapping, retry storms). Conductor demonstrates
that:

- The **Claude route doesn't need OpenCode** — Anthropic's Python
  package does it in a few hundred lines with no subprocess.
- The **Copilot route doesn't need OpenCode either** — GitHub
  publishes a `copilot` Python SDK that Conductor uses directly.

If both halves of OpenCode's current job can be done by ~600 LOC of
vendor-specific adapter code, then OpenCode is replaceable in a way
the BURR plan didn't anticipate. Not by another all-in-one
substrate; by two small native-API adapters behind one common
interface.

## 6. Recommendation

**Adopt Pattern D (the runtime abstraction we prototyped). Build
three adapters — Copilot for codex, two Claude paths (subscription
and pay-per-token). Delete OpenCode.**

Concretely:

1. **Promote the `Runtime` protocol from spike to production.** It
   already typechecks and lints clean. Drop the OpenCode-leaking
   names (rename `OpenCodeAuthError` → `RuntimeAuthError`, etc.;
   keep aliases for one cycle). Move `CostRecord` to a neutral
   location.

2. **Build `ClaudeCodeRuntime` wrapping `claude-agent-sdk`.** This
   is the production-default Claude path because it preserves Claude
   Pro/Max subscription auth (the only legitimate way per Anthropic's
   Feb 2026 terms). Reference is the spike's existing
   `ClaudeSdkRuntime`; production version drops the OpenCode-named
   error types and adds proper handling for the
   `CLAUDE_CODE_OAUTH_TOKEN` long-lived token format. Estimated
   ~300-500 LOC. Trade-off: pays ~50k tokens of Claude Code system-
   prompt overhead per subprocess restart, charged to the user's
   existing subscription budget.

3. **Build `AnthropicRuntime` using the `anthropic` Python package
   directly.** This is the pay-per-token alternative for orgs / CI /
   scaled deployments that have an API key. Reference is Conductor's
   `ClaudeProvider` (`anthropic` `messages.create()` with an
   `emit_output` tool for structured output). Estimated ~400-600 LOC
   after stripping Conductor's retry/parse logic to the bones.
   Configuration-time selection between this and `ClaudeCodeRuntime`
   based on which auth the deployment has.

4. **Build `CopilotRuntime` using GitHub's `copilot` Python SDK.**
   Reference is Conductor's `CopilotProvider`. Subscription auth via
   the existing GitHub OAuth flow. Estimated ~400-600 LOC. Replaces
   OpenCode's Copilot routing entirely.

5. **Migrate agents one at a time, behind a per-role flag.**
   Briefings first (simplest, fan-out friendly, the agent we already
   migrated). Then decomposer, generator, reviewer, implementer.
   Each migration is a small PR that flips that role from
   `OpenCodeRuntime` to whichever Pattern D adapter the role's tier
   wants. Backed-out by flipping the flag back.

6. **Delete OpenCode once every role is migrated.** Drop the
   `opencode` binary dependency from CLAUDE.md and the devcontainer.
   Close the four landmine issues. The ~2400 LOC of
   `runtime/opencode/` goes away.

7. **Skip Burr.** The BURR plan called for replacing xoscar with
   Apache Burr in Phase 2. With Pattern D, the xoscar layer doesn't
   need to change. If we want to revisit xoscar later, that's a
   separate decision.

### Why three adapters not one for Claude

Anthropic's Feb 2026 terms made the Claude path a billing decision,
not just an architectural one:

| Need | Adapter | Auth | Billing |
|---|---|---|---|
| Individual dev with Max subscription | `ClaudeCodeRuntime` | Browser OAuth → `~/.claude/.credentials.json` | Subscription |
| CI / non-interactive with subscription | `ClaudeCodeRuntime` | `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` | Subscription (with June 15 2026 Agent SDK credit pool change) |
| Org / scaled production | `AnthropicRuntime` | `ANTHROPIC_API_KEY` | Pay-per-token |

The `Runtime` protocol accommodates all three without change. Default
selection in `DEFAULT_TIERS` is the subscription path (`ClaudeCodeRuntime`)
because that's Maverick's existing user base. Orgs override per
config to opt into pay-per-token.

### What this does and doesn't change vs the BURR plan

| | BURR plan | Pattern D |
|---|---|---|
| Replace OpenCode | One substrate (Agents SDK + LiteLLM) | Three adapters (Copilot Python SDK, Claude Code SDK, `anthropic` direct) |
| Replace xoscar | Phase 2 with Burr | Don't replace |
| Claude on Copilot Chat | Doesn't work | Doesn't work — but we don't need it; Claude routes go through Anthropic's native path instead |
| Subscription leverage | Lost for Claude roles | **Preserved** for both codex (Copilot) and Claude (Claude Code SDK) by default |
| LOC deleted | ~2400 (OpenCode) | ~2400 (OpenCode) |
| LOC added | ~500 (cascading model + tool implementations) | ~1100-1700 (three native adapters; Claude Code SDK + Anthropic direct can share a common parent) |
| Phase 2 (xoscar) | 2-3 weeks of Burr work | None |
| Total scope | 6-8 weeks | 3-5 weeks |

Net effect: smaller migration, same OpenCode-deletion benefit, no
"one substrate to rule them all" wall on Claude, **and subscription
auth preserved end-to-end for the existing user base.**

### Cost trade-off worth flagging

`ClaudeCodeRuntime` keeps Claude work on the user's subscription
budget but pays ~50k tokens of Claude Code system-prompt overhead per
subprocess restart. The spike measured ~$0.14 per navigator briefing
when computed via Anthropic's pricing table; for subscription users
that's drawn from monthly limits, not a separate API bill. Starting
June 15, 2026, Agent SDK non-interactive usage draws from a separate
"Agent SDK credit" pool (per Anthropic's announced policy change) —
worth tracking for usage forecasting but not a Phase 1 blocker.

`AnthropicRuntime` (pay-per-token) avoids the system-prompt overhead
entirely (~$0.01-0.02 per equivalent briefing, by our estimates from
token counts) but requires a separate billing account. Orgs that
process high volumes will likely prefer this; individuals will prefer
the subscription path.

Both adapters use the same `Runtime` interface, so cascading between
them (try subscription first, fall over to API key on quota errors,
or vice versa) is straightforward once we want it — but not v0.

## 7. Concrete next steps

These are the work items I'd schedule if this recommendation is
accepted. Sequencing matters: do them in order.

1. **Day 1-2: Promote `ClaudeCodeRuntime` to production.** Lift the
   spike's `ClaudeSdkRuntime` into `src/maverick/runtime/`. Rename
   the OpenCode-leaking error types (`OpenCodeAuthError` →
   `RuntimeAuthError`, etc.). Add support for the
   `CLAUDE_CODE_OAUTH_TOKEN` env var (for non-interactive auth via
   `claude setup-token`). Migrate `BriefingAgent` to use it as the
   proof-of-concept. End-to-end test on bead 37n.3.

2. **Day 3-5: Read Conductor's `ClaudeProvider` in detail.** Decide
   which retry/parse logic transfers and which we can drop. Make
   the adoption-vs-reimplementation call (we have permission to
   either depend on Conductor as a library or reimplement; my
   default is reimplement at much smaller LOC since we want full
   control over the wire format).

3. **Week 2: Build `AnthropicRuntime` for API-key deployments.**
   Reference Conductor's `ClaudeProvider`. Test it against an
   Anthropic API key on the same bead 37n.3 as `ClaudeCodeRuntime`,
   to confirm equivalent typed-output behavior and lower per-call
   cost.

4. **Week 2-3: Build `CopilotRuntime` against the `copilot` Python
   SDK.** Reference Conductor's `CopilotProvider`. Migrate one
   codex-routed agent (e.g., outlines or coding) to use it.
   Confirm subscription auth flow + structured output via Copilot's
   native shape.

5. **Week 3-4: Migrate remaining agents.** Per-role flag for safety;
   roll back trivially per role. Default tier config routes Claude
   roles to `ClaudeCodeRuntime` (subscription) and codex roles to
   `CopilotRuntime` (subscription). Orgs override to swap in
   `AnthropicRuntime` for Claude roles where they want pay-per-token.

6. **Week 5: Delete `src/maverick/runtime/opencode/`** and the
   OpenCode binary dependency. Update CLAUDE.md to remove the four
   landmines (or move them to a historical-context section).

7. **Watch Conductor + Anthropic policy for 3-6 months.** If
   Conductor's abstraction stabilises and we converge further,
   evaluate adopting their library directly. If Anthropic's June 15
   2026 Agent SDK credit change materially affects subscription
   economics, revisit the per-role routing defaults.

## 8. What we explicitly are NOT doing

- **Not extracting our own runtime project.** The space has
  Microsoft Conductor at the same layer with a head start. Building
  a competitor is quixotic.
- **Not replacing xoscar with Burr.** Pattern D doesn't require it.
  If we want to revisit xoscar later, it's a separate decision with
  separate justification.
- **Not wrapping or being wrapped by PydanticAI.** PydanticAI lives
  at the same "agent runtime" layer as our `Runtime` protocol.
  Wrapping it would add a dependency without adding capability — its
  `final_result` typed-output pattern is exactly what each of our
  adapters already implements (via `submit_result` / `emit_output` /
  similar). PydanticAI's provider ecosystem doesn't include
  `claude-agent-sdk` (the subscription-auth path) so it doesn't
  cover our load-bearing case. We may later implement PydanticAI's
  `Model` interface on top of our adapters as an _exposed face_ for
  PydanticAI-using clients, but that's a forward-looking feature
  with no current consumer.
- **Not migrating everything at once.** Per-role flags, roll back
  trivially, one PR at a time.

## Appendix: artifacts

All spike code is checked in:

- `scripts/spike-openai-agents-sdk-litellm.py` + results JSON
- `scripts/spike-v3-redo.py` + results JSON
- `scripts/spike-pydantic-ai.py` + results JSON
- `scripts/spike-runtime-protocol-driver.py`
- `src/maverick/runtime/protocol.py`,
  `src/maverick/runtime/opencode_adapter.py`,
  `src/maverick/runtime/claude_sdk_adapter.py` (on the spike
  branch; production version goes in a fresh PR)

Reports:

- `docs/migration-phase-0-report.md`
- `docs/migration-phase-0b-report.md`
- `docs/spikes/runtime-protocol-v0.md`

External:

- [microsoft/conductor (GitHub)][microsoft/conductor]
- [Conductor: Deterministic orchestration for multi-agent AI
  workflows (Microsoft blog)](https://opensource.microsoft.com/blog/2026/05/14/conductor-deterministic-orchestration-for-multi-agent-ai-workflows/)
- [jayminwest/overstory (GitHub)](https://github.com/jayminwest/overstory)
- [PR #97 — Phase 0 + 0b on Maverick](https://github.com/get2knowio/maverick/pull/97)

[microsoft/conductor]: https://github.com/microsoft/conductor
