# Phase 0b Spike — PydanticAI

**Parent docs:** [BURR.md](./BURR.md),
[migration-phase-0-spike.md](./migration-phase-0-spike.md),
[migration-phase-0-report.md](./migration-phase-0-report.md).

**Date:** 2026-05-15.
**Author:** spike run via `scripts/spike-pydantic-ai.py`.
**Raw results:** `scripts/spike-pydantic-ai.results.json`.

**Why this exists.** Phase 0 closed with the recommendation to proceed,
but the V3 finding (Claude on Copilot doesn't reliably honour tool-use
through OpenAI Agents SDK) brought up an older incident — the MCP-era
"the agent just won't call the tool" problem. Phase 0b probes whether
PydanticAI delivers a fundamentally cleaner substrate, since the
hypothesis was that *provider-native* APIs and function-tool-backed
typed output would sidestep these failures.

## What this spike can and cannot answer

**Constraint.** No direct Anthropic or OpenAI API keys are configured
in this dev environment. Only the Copilot OAuth (now provisioned by
LiteLLM's device flow from Phase 0) and the opencode-go (Zen) gateway
are reachable. So the spike validates PydanticAI on the **same
transport** that broke Phase 0 — *not* on its native-API premise.

Concretely:

| Promise of PydanticAI | Tested? | Verdict |
|---|---|---|
| Typed output via Pydantic models, no `strict_json_schema` gotcha | YES | works — uses an internal `final_result` function tool |
| Function-tool pattern by default (not free-form `output_type=`) | YES | confirmed in `result.all_messages()` — every typed run ends with a `final_result` tool call |
| Provider-native APIs avoid Chat-Completions tool-use quirks | NO | no Anthropic API key available; can only test against Copilot |
| Subscription leverage via Copilot Responses API | YES (codex only) | works; Claude can't be reached at all |

The decisive comparison ("does PydanticAI's Anthropic adapter handle
Claude tool-use better than openai-agents SDK?") **requires an Anthropic
API key**. The Zen gateway exposes Anthropic-shape endpoints that 404
against PydanticAI's `AnthropicProvider`, so it's not a substitute.

## Validation matrix

| ID | What | Result | Wall time | Notes |
|----|------|--------|-----------|-------|
| V1 | Copilot Responses API (codex) returns text | **PASS** | 1.9 s | clean — no header workaround needed |
| V2 | codex + read tools + `SubmitImplementationPayload` on bead 37n.3 | **PASS** | 27.7 s | 15 messages total vs Phase 0's 14 raw_responses + 37 RunItems |
| V3 | claude on Copilot via either Responses or Chat | **FAIL** | < 2 s | Responses: 400 unsupported; Chat: PydanticAI's strict validation rejects Copilot's malformed `ChatCompletion` shape |
| V4 | prompt cache | **PASS** | ≈ 4 s | run 2 served 2 816 / 3 558 input tokens (79 %) from cache |
| V5 | cost telemetry surface | **PARTIAL** | < 1 s | richer than openai-agents (`cache_write_tokens` exposed); `cost_usd` still not computed |

## What changed vs Phase 0

### V2 codex — same task, tighter loop

PydanticAI returned the same bead plan in **27.7 s / 15 messages** vs
Phase 0's openai-agents SDK at **75.8 s / 14 raw_responses + 37
RunItems**. The implementer planned the same four files
(`src/greet_cli/renderer.py`, `src/greet_cli/cli.py`,
`tests/test_renderer.py`, `tests/test_cli_entrypoint.py`) with similar
intent. 2.7× faster wall-clock, ~60 % fewer items in the loop, on
identical input.

Token usage was higher in absolute terms (60 114 input tokens), but
36 992 of those (61 %) were served from cache — likely the bead
description being a stable prefix across multiple recent calls.

### V3 claude — same wall, different reason

Phase 0 reached Claude and Claude refused to honour the structured-
output / tool-use contract. Phase 0b doesn't reach Claude at all —
PydanticAI's `ChatCompletion` Pydantic model rejects Copilot's response
during validation:

```
UnexpectedModelBehavior: Invalid response from openai chat completions
endpoint: 2 validation errors for ChatCompletion
  choices.0.index: Input should be a valid integer
    [type=int_type, input_value=None, input_type=NoneType]
  object: Input should be ...
```

PydanticAI uses the official `openai` Python SDK's strict response
models. Copilot's Chat Completions endpoint returns Claude responses
without a `choices[].index` field (the OpenAI spec marks it required;
Copilot ships it as `null`), so the response can't be parsed. The
model never gets a chance to fail at tool-use because the transport
layer fails first.

Net of Phase 0 + Phase 0b:

- **openai-agents SDK + Copilot + Claude:** transport works, model
  doesn't call tools.
- **PydanticAI + Copilot + Claude:** transport itself is blocked.

Neither substrate makes Claude-on-Copilot work. The root cause is
upstream of either library — Copilot's Chat Completions endpoint
doesn't behave like OpenAI's for the Claude family.

### V4 — cache works, write counter exposed

PydanticAI surfaces both `cache_read_tokens` *and* `cache_write_tokens`
at the top level of its `RunUsage` object — Phase 0's openai-agents
SDK only exposed `cached_tokens` nested under `input_tokens_details`.
PydanticAI is strictly better on cache observability.

```
run1: input=3558  cache_read=0     cache_write=0
run2: input=3558  cache_read=2816  cache_write=0   (79% hit)
```

### V5 — richer surface, still no cost_usd

PydanticAI's `RunUsage` exposes:

- `requests`, `tool_calls`
- `input_tokens`, `output_tokens`
- `cache_read_tokens`, `cache_write_tokens`
- `input_audio_tokens`, `output_audio_tokens`, `cache_audio_read_tokens`
- `details` (provider-specific extras, e.g. reasoning-token counts)

That's eight of the seven fields today's `agent.cost` row needs, plus
extras. The single miss is still `cost_usd` — neither PydanticAI nor
the underlying openai SDK computes price. We compute it ourselves
against a `(provider_id, model_id)` table either way.

## What we observed about PydanticAI's architecture

While iterating on V3, I read enough of PydanticAI's internals to
confirm the **typed output is implemented as a function-tool call**.
Every run with `output_type=PydanticModel` registers a hidden
`final_result(...)` tool whose parameters mirror the model's schema.
The agent's reply chain ends with a `final_result` tool call; the SDK
intercepts it, validates the args against the Pydantic model, and
returns it as `result.output`.

This is the same architectural pattern I argued for in the V3-redo
discussion (`StopAtTools` + a `submit_implementation` function tool) —
PydanticAI ships it as the default. There's no `output_type=` ≠
`function-tool` distinction in PydanticAI; the typed output *is* a
function-tool. The strict_json_schema gotcha from Phase 0 simply
doesn't appear here.

That's the substrate property the user was asking about — "a
fundamentally more straightforward way." On the dimension that bit us
in Phase 0 (typed-output enforcement), PydanticAI wins by virtue of a
better default.

## What we still don't know

The two open questions before a substrate decision:

1. **Does PydanticAI + Anthropic-native API solve Claude tool-use?**
   This is the load-bearing question. The architecturally-clean theory
   says yes — `@ai-sdk/anthropic` uses Anthropic's Messages API, which
   enforces tool-use server-side the way the OpenAI Responses API
   enforces it for codex. But we couldn't test it without an Anthropic
   API key.

2. **Is the Copilot Chat-Completions Claude path salvageable at all,
   for *either* substrate?** Both spikes show the path is broken in
   different ways. Even if we patch PydanticAI's strict validation, we
   land back in the openai-agents SDK's failure (model doesn't call
   tools). The honest answer may be: Claude on Copilot isn't usable
   through any in-process Python SDK today — only OpenCode's adapter
   reaches it cleanly, and we'd be reimplementing that adapter to
   migrate.

## Updated recommendation

Phase 0's "proceed with two adjustments" recommendation no longer holds
clean. The substrate choice is now genuinely open, and the answer
depends on a test we can't run with current creds. Three honest paths:

### Path A — Continue with OpenAI Agents SDK + LiteLLM, accept the cost

Stay on the substrate the original spec picked. Eat the Phase 0 gotchas
(re-inject Copilot headers, `strict_json_schema=False`, envelope unwrap
or function-tool refactor). Route claude-favoured roles off Copilot
Chat Completions to *something*: `openai/*` (subscription leverage
lost), `anthropic/*` direct (requires API key + new billing line), or
keep them on OpenCode until the substrate matures.

**Net:** lots of small workarounds, codex works subscription-leveraged
on Copilot, claude is the open question.

### Path B — Switch to PydanticAI, validate against Anthropic-direct first

Get an Anthropic API key, rerun a 0c spike: PydanticAI + native
Anthropic Messages API + claude-sonnet-4.6 + tools + typed output. If
that passes cleanly first-try, PydanticAI is the substrate; the
Phase 1 plan retargets to: codex via Copilot Responses (subscription
leverage retained for the most expensive role), claude via Anthropic
direct. Loses Copilot subscription leverage for claude-favoured roles
but the typed-output guarantees become first-class.

**Net:** cleaner substrate, requires a paid API key for the long-tail
roles, and the spike has to be re-run before committing.

### Path C — Stay on OpenCode for now

Phase 0 was a decision gate, not a commitment. The honest reading of
Phase 0 + 0b is that the migration's "in-process, no subprocess" win
is real but the typed-output property is harder to preserve than the
spec assumed. If the OpenCode runtime is functioning, the right move
might be to **defer the migration** until either: (a) Copilot's Claude
path improves; (b) an in-process SDK ships a robust unwrap layer;
(c) the team has bandwidth to write the unwrap layer themselves.

**Net:** zero migration risk, keeps the four OpenCode landmines, no
subprocess removal.

### My read

Path B is the architecturally-best answer **if** you're willing to
either pay for an Anthropic API key for the validation spike or accept
that the validation can't happen until that's available. The function-
tool-by-default pattern in PydanticAI is exactly what we'd hand-build
on OpenAI Agents SDK anyway, and the cache/cost observability is
strictly better. The cost: a one-day spike against Anthropic-direct,
plus a decision about whether claude-favoured roles run on
pay-per-token billing or stay on Copilot via a custom adapter.

Path A is the conservative play if you'd rather not introduce a new
billing line. Path C is the right play if the migration isn't a
priority — Phase 1's net benefit is now smaller than the original spec
estimated.

The decision is yours; the spike has done what spikes do — moved the
unknown from "does the substrate work" to "do we want PydanticAI
enough to set up Anthropic billing for a validation."

## Re-running

```bash
source /tmp/spike-venv/bin/activate          # from Phase 0
pip install pydantic-ai
python scripts/spike-pydantic-ai.py
```

The Copilot device flow from Phase 0 is reused; no new auth required.
