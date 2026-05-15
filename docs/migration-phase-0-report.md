# Phase 0 Spike — Report

**Parent docs:** [BURR.md](./BURR.md) (migration plan) and
[migration-phase-0-spike.md](./migration-phase-0-spike.md) (the spike brief).

**Date:** 2026-05-15.
**Author:** spike run via `scripts/spike-openai-agents-sdk-litellm.py`.
**Raw results:** `scripts/spike-openai-agents-sdk-litellm.results.json`
(checked in alongside this report). All findings below cite that file —
re-running the script regenerates it.

**Decision: Proceed to Phase 1 with two documented adjustments.** This
maps to row 4 of the decision-gate matrix (`V1 pass, V2 pass, V3 partial`).
See [Decision](#decision) below.

## Validation matrix

| ID | What | Result | Wall time | Evidence |
|----|------|--------|-----------|----------|
| V1 | Copilot OAuth → first call returns text | **PASS** | 1.2 s | `final_output: "ready."` |
| V2 | `github_copilot/gpt-5.3-codex` + tools + `SubmitImplementationPayload` | **PASS** | 75.8 s | 14 raw responses, 37 RunItems, 3 files produced on bead `37n.3` |
| V3 | `github_copilot/claude-sonnet-4.6` + tools + `SubmitImplementationPayload` | **FAIL** | 3.5 s | model emits plain text instead of typed payload (raw output below) |
| V4 | Prompt-cache hit on second run | **PASS** | ≈ 4 s | run 2: 3 456 / 3 575 input tokens cached (97 %) |
| V5 | Cost-telemetry surface | **PARTIAL** | < 1 s | tokens + cached_tokens reachable; `cost_usd` / `cache_write_tokens` / `provider_id` not exposed |

`PASS` rows used the unmodified Pydantic schemas from `maverick.payloads`.
`PARTIAL` for V5 is informational — per the spec it is the only validation
whose miss is non-blocking.

## Validation details

### V1 — OAuth (PASS, with caveat)

**The dev-environment OpenCode `auth.json` cannot bootstrap LiteLLM.** The
`ghu_…` GitHub OAuth token stored at
`~/.local/share/opencode/auth.json:github-copilot.refresh` was revoked
(GitHub `/user` returns `401 Bad credentials` for it). Even copying it to
LiteLLM's expected path (`~/.config/litellm/github_copilot/access-token`)
yields a 401 cascade when LiteLLM tries to mint a Copilot API key via
`https://api.github.com/copilot_internal/v2/token`.

The working path is LiteLLM's **own** device flow:
`from litellm.llms.github_copilot.authenticator import Authenticator;
Authenticator().get_api_key()` prints a `https://github.com/login/device`
URL + 8-char code and polls for 60 s × 3 attempts. Once authorised,
LiteLLM writes:

- `~/.config/litellm/github_copilot/access-token` (the `ghu_…` token),
- `~/.config/litellm/github_copilot/api-key.json` (the Copilot internal
  token, refreshed automatically when expired; endpoints include
  `api.individual.githubcopilot.com`).

Subsequent calls reuse cached creds without re-prompting.

**Phase 1 action:** the runbook/onboarding doc must direct devs to run
LiteLLM's device flow once. We **cannot** rely on OpenCode's
`auth.json` as a bootstrap — its tokens are stale in our dev image and
the OpenCode `auth login github-copilot` flow is itself broken in 1.14.50
(`Failed to load auth provider metadata from github-copilot: fetch() URL
is invalid`).

### V2 — `gpt-5.3-codex` + tools + typed payload (PASS)

`SubmitImplementationPayload` validated first try. The agent took 14
turns / 37 RunItems / 75.8 s on bead
`sample-maverick-project-37n.3` and produced **real implementation**:

- `src/greet_cli/renderer.py` (93 LOC) — Rich console + pyfiglet banner
  helpers with `--no-color` / `--no-figlet` paths.
- `tests/test_renderer.py` (95 LOC) — focused renderer tests with
  monkeypatched pyfiglet fallback.
- `src/greet_cli/cli.py` — reduced from 70 to 32 lines, now delegates
  to `renderer.render_greetings(...)`.

Returned payload:

```
summary:        "Implemented a focused reusable rendering path by adding
                 `render_greetings(...)` in `renderer.py` and updating the
                 CLI to use it…"
files_changed:  ['src/greet_cli/cli.py',
                 'src/greet_cli/renderer.py',
                 'tests/test_renderer.py']
```

The artefacts remain in the sample project (`git status` shows them as
unstaged); they're the spike's primary proof-of-life.

### V3 — `claude-sonnet-4.6` + tools + typed payload (FAIL)

**First-turn output is plain text, not a typed payload.** The spike's
TypeAdapter raises:

```
ModelBehaviorError: Invalid JSON when parsing
  "I'll start by reading all the relevant files in parallel."
for TypeAdapter(SubmitImplementationPayload); 1 validation error for
SubmitImplementationPayload
  Invalid JSON: expected ident at line 1 column 2
```

To isolate, I re-ran with **no tools, structured output only**, asking
the model for a trivial payload (`summary="hello", files_changed=["a.py"]`).
Claude returned a fenced code block:

````
```json
{ "summary": "hello", "files_changed": ["a.py"] }
```
````

— the right payload **wrapped in markdown fences**. The SDK does not
strip the fences before `json.loads`, so validation fails. This is the
same envelope-wrapping landmine OpenCode mitigates via
`_unwrap_envelope` in `runtime/opencode/client.py` (CLAUDE.md landmine
#3). The OpenAI Agents SDK has no equivalent normalisation.

**Root cause:** Copilot's Chat Completions endpoint (the Claude path)
does not server-side enforce `response_format=json_schema` the way
OpenAI's Responses API does. Claude believes it is returning the right
shape and decorates it with conversational scaffolding.

**Phase 1 mitigations** (in order of preference):

1. **Route claude-only roles (`decompose`, `generate`, `review`,
   `briefing`) to `openai/*` in `DEFAULT_TIERS`** until a normaliser
   exists. Codex on `github_copilot/*` continues to carry the
   subscription-leverage roles.
2. **Add an unwrap layer** in `MaverickCascadingModel` mirroring the
   OpenCode `_unwrap_envelope` mitigation — strip markdown fences and
   common envelope keys (`{"input": …}`, `{"parameter": …}`,
   `{"content": "<json>"}`) before handing to the TypeAdapter.
3. **Tool-only output** (`output_type=str` + a `submit_implementation`
   function tool) — equivalent to the OpenCode tool-call path; loses
   the SDK's elegant `final_output: PydanticModel` ergonomics but
   sidesteps the envelope issue entirely.

### V4 — Prompt cache (PASS)

Seeded context: 15 306 chars of bead description + greet-cli source +
existing tests → 3 575 input tokens. Two runs with the same prefix:

- run 1 `input_tokens=3575 cached=0` (cache miss — first time we saw
  this prefix in the past hour).
- run 2 `input_tokens=3575 cached=3456` (97 % of the prefix served
  from cache).

The cache is transparent — **no `cache_control` markers required**.
Maverick's decomposer / implementer-fix-loop cache assumptions hold
post-migration. Field path:

```python
result.raw_responses[i].usage.input_tokens_details.cached_tokens  # int
```

### V5 — Cost telemetry (PARTIAL, non-blocking)

What's reachable from `RunResult`:

| Field (today's `agent.cost`) | Reachable? | Path |
|---|---|---|
| `provider_id`             | NO  | — (must derive from the model string we passed) |
| `model_id`                | YES | derive from `LitellmModel(model_str)` (the SDK strips this) |
| `input_tokens`            | YES | `raw_responses[i].usage.input_tokens` |
| `output_tokens`           | YES | `raw_responses[i].usage.output_tokens` |
| `cache_read_tokens`       | YES | `raw_responses[i].usage.input_tokens_details.cached_tokens` |
| `cache_write_tokens`      | NO  | not exposed on `Usage` |
| `cost_usd`                | NO  | LiteLLM's `_hidden_params["response_cost"]` is not surfaced through openai-agents' `Usage` |

**Phase 1 action:** wire cost telemetry inside `Agent` (Slot F) the same
way the OpenCode runtime does today — `provider_id` and `model_id` come
from the binding we passed in, and `cost_usd` is computed against a
per-`(provider, model)` price table that Maverick already maintains in
the runway store. We lose `cache_write_tokens` until a future LiteLLM /
SDK release exposes it; the field is informational for our cost rollups
(write costs are negligible relative to read+output) so this is
acceptable.

## Cross-cutting findings (gotchas for Phase 1)

These were not in the spec's validation list but every one is a real
cost. Phase 1 must internalise them.

1. **Strict JSON schema rejects Pydantic models with defaults.** The
   first spike attempt failed in 0.0 s with:

   ```
   UserError: Strict JSON schema is enabled, but the output type is
   not valid. Either make the output type strict, or wrap your type
   with AgentOutputSchema(YourType, strict_json_schema=False)
   ```

   Every `Submit*Payload` in `maverick.payloads` that has even one
   `Field(default_factory=…)` field (`SubmitImplementationPayload`,
   `SubmitFixResultPayload`, several review/recon payloads) trips this.
   **Mitigation:** wrap with
   `AgentOutputSchema(MyPayload, strict_json_schema=False)` in
   `Agent.__init__`. Trivial; do it once in the base class.

2. **The SDK overrides `User-Agent` and breaks Copilot Chat Completions
   (Claude path).** `LitellmModel` injects
   `extra_headers={"User-Agent": "Agents/Python 0.17.2"}` on every
   request. LiteLLM's `github_copilot` chat transformation merges
   user-provided headers *after* its own (`{**copilot, **user}`), so
   the override wins. `api.individual.githubcopilot.com/chat/completions`
   then rejects the request:

   ```
   litellm.BadRequestError: Github_copilotException - bad request:
     missing Editor-Version header for IDE auth
   ```

   Codex (Responses API) is unaffected; Claude (Chat Completions) fails.
   **Mitigation:** every agent that may touch Copilot must pass

   ```python
   model_settings=ModelSettings(extra_headers={
       "User-Agent": "GithubCopilot/1.155.0",
       "editor-version": "vscode/1.95.0",
       "editor-plugin-version": "copilot/1.155.0",
   })
   ```

   The spike codifies this as `copilot_compat_settings()`. In Phase 1
   it belongs in `MaverickCascadingModel` so individual `Agent`
   subclasses don't carry the boilerplate. Without it,
   `github_copilot/claude-*` is unusable through openai-agents SDK at
   all — this is independent of V3's structured-output gap.

3. **OpenCode `auth.json` is dead weight for the new stack.** See V1.
   The migration cannot reuse OpenCode's stored creds; Phase 1 ships
   a fresh device-flow runbook.

4. **LiteLLM doesn't fail-fast on bad `modelID`.** The four OpenCode
   landmines documented in CLAUDE.md don't transfer, but landmine #1
   (silent crash on bad `modelID`) gets replaced by a different shape:
   LiteLLM raises `BadRequestError` synchronously with a clear message.
   Net win — visible failure, no DB-replay crash loop — but
   `MaverickCascadingModel` still needs the same model-id validation
   pass at startup (it's a one-line probe vs a DB-purge runbook).

## Decision

Mapping the validation matrix back to the spec's decision-gate table
(`docs/migration-phase-0-spike.md`):

```
V1=pass  V2=pass  V3=partial  V4=pass  V5=partial(non-blocking)
```

V3 is recorded as `partial` (not `fail`) because the two-binding test
splits cleanly: codex works, claude does not. The spec's `fail` row
refers to **both** primary bindings failing. We hit row 4:

> **`pass | pass | partial | * | *` → Proceed to Phase 1 with reduced
> Copilot leverage for one binding.**

**Recommendation: Proceed to Phase 1**, with these scope additions
captured in the Phase 1a/1c work plan:

1. `MaverickCascadingModel` ships with **Copilot-compat headers**
   baked in (gotcha #2). Without this, Phase 1e claude-on-Copilot
   testing is dead on arrival.
2. `MaverickCascadingModel` ships with an **envelope-unwrap layer**
   (V3 mitigation #2) that strips markdown fences and common wrapper
   shapes. This is the same mitigation the OpenCode client carries
   today; porting it costs maybe 30 LOC.
3. `DEFAULT_TIERS` for claude-favoured roles (`decompose`, `generate`,
   `review`) initially routes to `openai/*` first and falls back to
   `github_copilot/claude-sonnet-4.6` only after the envelope layer is
   verified in production. (Today's order has Copilot first; flip it
   for these roles in Phase 1e migration.)
4. `Agent.__init__` wraps `output_type` with `AgentOutputSchema(…,
   strict_json_schema=False)` automatically (gotcha #1).
5. Cost telemetry parity: `Agent` computes `cost_usd` from a Maverick-
   owned price table keyed by `(provider_id, model_id)`. We already
   maintain this for the runway store. `cache_write_tokens` is
   recorded as `None` until LiteLLM exposes it.

If the envelope-unwrap mitigation proves insufficient for Claude in
Phase 1c (e.g., we see new wrapper shapes the spike didn't cover), the
fallback per the spec is **Stack 2 (Instructor + LiteLLM + custom
loop)**. The decision to escalate to Stack 2 belongs to whoever owns
Phase 1c, not this report.

## Re-running this spike

```bash
python -m venv /tmp/spike-venv
source /tmp/spike-venv/bin/activate
pip install "openai-agents[litellm]"
pip install -e .                                    # for maverick.payloads
python scripts/spike-openai-agents-sdk-litellm.py
```

First run prompts a one-time GitHub device-flow auth
(`https://github.com/login/device` + 8-char code). Subsequent runs
reuse `~/.config/litellm/github_copilot/`.

The full per-validation JSON lives at
`scripts/spike-openai-agents-sdk-litellm.results.json` — that's the
source of every number quoted above.
