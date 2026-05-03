# Spike: Validate OpenCode-as-substrate for maverick's agent runtime

You're being asked to run an architectural spike. Context, scope, success criteria, and deliverables are all below. Don't shortcut the empirical questions — the whole point of this spike is to learn whether something *actually works*, not to confirm a hypothesis. If it doesn't work, that's a useful answer.

## Background

**maverick** is a Python CLI that orchestrates AI-powered development workflows (PRD → flight plan → beads/work-units → implementation → review → commit). It uses an **xoscar actor framework** for in-pool async actors, where each agent role (implementer, reviewer, decomposer, briefing agents) is an actor with a persistent agent session, and a **supervisor actor** orchestrates them via typed RPC.

Today, agent execution goes through the **Agent Client Protocol (ACP)** via per-provider bridges (`claude-agent-acp`, `gemini --acp`, `copilot acp`, `opencode acp`). Agents deliver structured results to the supervisor by calling **MCP tools** (`submit_review`, `submit_implementation`, `submit_outline`, etc.) hosted by an in-process HTTP MCP gateway. That delivery is unreliable in practice:

- Gemini's ACP mode silently drops session-level `mcp_servers` (only honors static `~/.gemini/settings.json`).
- Copilot's ACP bridge drops MCP tool-call results; agents emit prose without calling the tool.
- Claude's bridge works but Claude itself sometimes skips tool calls (~5% on real workloads).
- ACP doesn't expose `tool_choice` forcing — there's no protocol-level way to require a specific tool.

We've been patching with JSON-in-text fallback, envelope unwrap, transient-error retry, supervisor-side reviewer escalation. It's becoming sprawling and brittle. We want to evaluate **OpenCode as a replacement substrate**.

OpenCode runs as an HTTP server (`opencode serve`, default `127.0.0.1:4096`) with a documented OpenAPI 3.1 spec at `/doc`. It supports many providers (Anthropic, OpenAI, Google, OpenRouter, Ollama, LMStudio, Groq, etc.) and exposes structured output via `format: { type: "json_schema", schema: ... }`. The hypothesis: if OpenCode's structured-output mechanism is reliable across providers, our entire "agents call submit_X via MCP" layer collapses into "send prompt with json_schema, get back validated typed payload."

**Strategic context**: model providers are moving from subscriptions to pure token-based pricing. The user wants the architecture to support: closed frontier → open hosted → local models, with cost optimization via picking the cheapest viable model per task. Locking to one provider (Claude) is becoming actively bad. OpenCode's multi-provider story is the strategic alignment.

## What you're validating

The hypothesis: **OpenCode-as-runtime + maverick's xoscar-actors-as-workflow-orchestrator is a cleaner, more reliable architecture than ACP + custom MCP gateway.**

That hypothesis depends on five empirical questions. Answer all of them with code + measurements:

1. **Structured output reliability across providers.** When you ask OpenCode to return a payload conforming to a JSON schema, does it actually return one — uniformly across Claude, an OpenAI/GPT model, and at least one open/local model?
2. **MCP tool execution** for "work" tools (Read/Write/Bash). Does OpenCode reliably let the agent call them, mid-session, and surface tool-call events back to the client?
3. **Events flowing into our actor model.** Can a Python xoscar actor driving an OpenCode session subscribe to events (tool calls, completions) and forward them to a supervisor cleanly?
4. **Cancellation.** When the user Ctrl-Cs or a timeout fires, can we cancel a running session cleanly without leaving the OpenCode server in a bad state?
5. **Multi-actor coordination.** Multiple xoscar actors driving multiple OpenCode sessions concurrently — does that work, scale to ~5 actors, and integrate with the supervisor's typed-RPC model?

## Setup

Work in a scratch directory outside of `/workspaces/maverick`. Don't modify maverick's tree.

```bash
mkdir -p /tmp/opencode-spike && cd /tmp/opencode-spike
```

Install OpenCode (https://opencode.ai/docs/install). Verify it works standalone:

```bash
opencode --version
opencode serve --port 4096 --hostname 127.0.0.1 &
curl http://127.0.0.1:4096/doc | head -50  # OpenAPI spec
```

Configure at least three providers in `opencode.jsonc` for this spike:

- **Anthropic Claude** (something like `claude-haiku-4-5`)
- **One non-Claude hosted model** (OpenAI `gpt-4o-mini` or similar via direct API or OpenRouter)
- **One open/local model**: install Ollama if you don't have it, pull `qwen2.5-coder:7b` or `llama3.1:8b`, configure as a provider

If you can't get a third provider stood up in reasonable time, document that and proceed with two — but note it as a gap. The cross-provider claim is what we're testing; one provider proves nothing.

Python deps for the spike:

```bash
uv venv && source .venv/bin/activate
uv pip install httpx pydantic xoscar
```

(Use whatever Python tooling you prefer; the spike doesn't need to match maverick's exact stack.)

## Build the spike incrementally

### Task 1: Bare Python HTTP client to OpenCode

Write `opencode_client.py` with:

- `async def create_session(agent: str | None = None, model: dict | None = None) -> str` — returns session id.
- `async def send_message(session_id: str, content: str, format: dict | None = None, timeout: float = 300.0) -> dict` — sends a synchronous prompt; returns the response including any `structured_output` field.
- `async def stream_events(session_id: str | None = None) -> AsyncIterator[dict]` — subscribes to `/global/event` SSE; if session_id given, filters to that session.
- `async def cancel(session_id: str) -> None` — best-effort cancellation. (Look up the actual endpoint in OpenCode's OpenAPI; if there's no cancel endpoint, document that.)

Don't use OpenCode's official TypeScript SDK. We need Python, so we're talking HTTP directly. Check OpenCode's OpenAPI spec at `http://127.0.0.1:4096/doc` for exact endpoint shapes — the docs we have are paraphrased and may be wrong. Trust the spec.

### Task 2: Structured-output reliability test

Write `test_structured_output.py` that exercises the *core hypothesis*. Define a realistic Pydantic model modeled on our actual review-result type:

```python
from pydantic import BaseModel, Field

class ReviewFinding(BaseModel):
    severity: str = Field(pattern="^(critical|major|minor)$")
    file: str | None = None
    line: int | None = None
    issue: str

class SubmitReviewPayload(BaseModel):
    approved: bool
    findings: tuple[ReviewFinding, ...] = ()
    findings_count: int | None = None
```

For each provider you configured (Claude, GPT, Ollama-qwen-coder, others if available):

1. Create a session bound to that provider's model.
2. Send a prompt asking for a code review of a small synthetic diff (provide a real-looking 30-line diff with one obvious bug — say, an off-by-one error or a missing null check) with `format={"type": "json_schema", "schema": SubmitReviewPayload.model_json_schema()}`.
3. Validate the response against `SubmitReviewPayload`.
4. Run **at least 10 trials per provider**. Record success rate (validated) vs. failure rate.

Categorize failures:
- **Schema mismatch**: response was JSON but didn't match the schema (wrong fields, wrong types).
- **Not JSON**: response was prose despite the format instruction.
- **Empty / no response**: model returned nothing or an error.
- **HTTP error**: OpenCode returned an error (quota, transport, etc.).

Tabulate results per provider. **This is the load-bearing measurement.** If reliability is <90% on any provider you'd want to use, document it.

Also test with two more schemas, varied to flush out shape-specific issues:

```python
class SubmitImplementationPayload(BaseModel):
    summary: str
    files_changed: tuple[str, ...]
    notes: str | None = None

class SubmitOutlinePayload(BaseModel):
    work_units: tuple[dict, ...]  # nested structure
```

For the outline schema, use a more nested shape (work units with required `id`, `task`, `sequence`, optional `depends_on: list[str]`, `complexity: Literal["trivial", "simple", "moderate", "complex"]`). Models often choke on nested + optional fields. We need to know.

### Task 3: MCP tool execution

Configure OpenCode (in `opencode.jsonc`) with at least one stdio MCP server (e.g., a filesystem MCP server). Standard MCP servers list: https://github.com/modelcontextprotocol/servers.

Write `test_mcp_tools.py`:

1. Create a session.
2. Send a prompt that requires the agent to use a tool (e.g., "Read the file at /tmp/opencode-spike/sample.txt and tell me its contents"). Pre-create that file with known contents.
3. Subscribe to events. Verify a tool-call event fires, including the tool name and arguments.
4. Verify the agent's final response contains the file contents (proving the tool actually executed and the model got the result).

Test on **all three providers** to see whether tool execution is uniform. Record any provider where MCP tool execution fails or behaves differently.

### Task 4: Events into actor model

Write `test_xoscar_actor.py`. Set up:

```python
import xoscar as xo

class OpenCodeAgentActor(xo.Actor):
    """Single-role actor wrapping an OpenCode session."""
    
    def __init__(self, supervisor_ref: xo.ActorRef, role: str, model: dict) -> None:
        super().__init__()
        self._supervisor_ref = supervisor_ref
        self._role = role
        self._model = model

    async def __post_create__(self) -> None:
        self._client = OpencodeClient(...)
        self._session_id = await self._client.create_session(model=self._model)
        self._event_task = asyncio.create_task(self._drain_events())

    async def _drain_events(self) -> None:
        async for event in self._client.stream_events(session_id=self._session_id):
            # Forward tool-call / progress events to the supervisor for UI rendering.
            await self._supervisor_ref.agent_event(self._role, event)

    async def send_review(self, prompt: str, schema: dict) -> None:
        result = await self._client.send_message(
            session_id=self._session_id,
            content=prompt,
            format={"type": "json_schema", "schema": schema},
        )
        payload = SubmitReviewPayload.model_validate(result["structured_output"])
        await self._supervisor_ref.review_ready(payload)

class SupervisorActor(xo.Actor):
    async def __post_create__(self) -> None:
        self._results: list[Any] = []
        self._events: list[Any] = []

    @xo.no_lock
    async def agent_event(self, role: str, event: dict) -> None:
        self._events.append((role, event))

    @xo.no_lock
    async def review_ready(self, payload: SubmitReviewPayload) -> None:
        self._results.append(payload)
```

Run a small workflow: supervisor creates two `OpenCodeAgentActor` children (different roles, different models), invokes them concurrently with realistic prompts, collects typed payloads. Verify:

- Both actors complete cleanly.
- Events reach the supervisor in the right order.
- Payloads are correctly typed.
- No deadlocks (`@xo.no_lock` on supervisor's reverse-call methods is critical — the supervisor's RPC methods called from inside the actor must not hold the actor lock).

If you don't know xoscar, the gist: actors are coroutines on a shared event loop (`n_process=0`), method calls between actors are typed RPC. `@xo.no_lock` is required on supervisor methods that are called from a child actor while the supervisor itself is awaiting that child — otherwise the actor lock deadlocks.

### Task 5: Cancellation

Write `test_cancellation.py`:

1. Start a long-running prompt (e.g., "write me a 5000-word essay on...").
2. After 2 seconds, cancel the session via OpenCode's cancellation API (find the right endpoint in the OpenAPI spec).
3. Verify: server doesn't hang, subsequent requests on a *different* session work, no zombie subprocesses.
4. Also test: cancel the entire HTTP request from the client side (close the connection mid-stream). Does OpenCode handle that gracefully?

Document the actual cancellation semantics. Today our ACP path uses `xo.wait_for(...)` to bound calls; we need an equivalent story for OpenCode.

### Task 6: Error surfacing

Write `test_errors.py`. Try to trigger known error modes:

1. Provider quota exhaustion (deliberately use an account that's hit its rate limit, or use a fake API key for a hosted provider).
2. Network failure (kill the OpenCode server mid-prompt, or block its outbound network).
3. Schema-mismatch from the model (use a deliberately mismatched format expectation — request schema A but instruct the model to produce shape B; see how OpenCode reports the mismatch).
4. Provider-side error (e.g., context-length exceeded — send a very long prompt).

For each, record: how does OpenCode surface the error? HTTP status code? Event with type `"error"`? Both? Is the error type/code consistent across providers, or does it leak provider-specific detail?

This determines how we wire transient-retry / escalation logic on top.

### Task 7: Concurrent sessions

Write `test_concurrent.py`:

1. Create five OpenCodeAgentActors in parallel, all calling the same provider.
2. Send all five a prompt simultaneously.
3. Measure: do they actually run concurrently (response times don't multiply)? Does OpenCode handle concurrent sessions cleanly?

If OpenCode serializes requests under the hood, that's a critical finding for our parallel decomposer / parallel briefing patterns.

## Success criteria

This spike is a **go** if all of:

- Structured output reliability ≥95% on Claude (matches what we already have).
- Structured output reliability ≥90% on at least one non-Claude provider, including at least one open/local model.
- MCP tool execution works uniformly across the providers tested.
- xoscar actors driving OpenCode sessions work cleanly without deadlocks.
- Cancellation actually stops the agent (not just disconnects the client).
- Errors are surfaced in a way we can classify (transient vs. quota vs. fatal).
- Concurrent sessions don't serialize.

This spike is a **no-go** if any of:

- Cross-provider structured output is meaningfully worse than Claude alone (e.g., <70% on open/local models). That means we just relocate the brittleness.
- xoscar + OpenCode HTTP client deadlocks or has lifecycle issues that aren't trivially fixable.
- Cancellation is broken (running prompts can't be killed).
- Concurrent sessions actually serialize at the OpenCode layer.

This spike is **inconclusive** (proceed cautiously, gather more data) if:

- Reliability is provider-dependent in a way we can predict and route around.
- Specific issues are documented and have known workarounds upstream.

## Deliverables

1. **Working spike code** at `/tmp/opencode-spike/` — all seven test scripts. Each must be runnable independently.
2. **Results table** for Task 2 — per-provider success rate, failure-mode breakdown.
3. **A written assessment** at `/tmp/opencode-spike/ASSESSMENT.md` covering:
   - The five empirical questions, answered with data.
   - Go / no-go / inconclusive recommendation with justification.
   - Surprises and gotchas you hit during the spike (these matter — gotchas now prevent them later).
   - Concrete migration risks or open questions for a follow-up spike.
   - If go: estimate the migration cost in person-days for porting maverick's existing actors. Use the existing maverick code at `/workspaces/maverick/src/maverick/actors/xoscar/` as the reference scope.
   - If no-go: what would need to change upstream (in OpenCode or elsewhere) for this to become viable, if anything?

## Constraints and reminders

- **Don't fake it.** If a provider isn't reliable, write that down. The spike's value is in honest data.
- **Don't generalize from one trial.** 10 trials per provider per schema, minimum. Reliability claims need n.
- **Don't hide failures in retries.** Measure the *base* success rate. Retry logic is downstream of this measurement.
- **Document deviations from the plan.** If something in the OpenAPI spec contradicts what you read in the docs, the spec wins, but flag it.
- **Don't modify `/workspaces/maverick`.** Keep the spike self-contained.
- **Quota note**: This work shares the user's Anthropic Pro/Max subscription quota. If you hit "You're out of extra usage" mid-spike, stop and document where you got to — don't keep retrying. The user can resume after quota reset.

## Reference

- OpenCode docs: https://opencode.ai/docs/
- OpenCode HTTP server: https://opencode.ai/docs/server (read this first)
- OpenAPI spec at runtime: `http://127.0.0.1:4096/doc` once the server is running
- OpenCode SDK source (TypeScript, useful as reference for endpoint shapes): https://github.com/sst/opencode
- xoscar docs: https://github.com/xorbitsai/xoscar
- Existing maverick actors for reference: https://github.com/get2knowio/maverick/tree/main/src/maverick/actors/xoscar
- Existing maverick MCP gateway (what we'd be replacing): https://github.com/get2knowio/maverick/tree/main/src/maverick/tools/agent_inbox

---

Begin with Task 1. Stop and report after each task — don't barrel through the whole spike before surfacing findings. The user will redirect based on what you learn.
