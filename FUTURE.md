# Maverick Future

This document supersedes the previous `OPPORTUNITIES.md` files (removed from the repo in favor of this consolidated roadmap).

It reconciles those documents against the current codebase as of 2026-04-19 and folds in additional opportunities that surfaced while reviewing the actor, MCP, workflow, executor, and CLI layers.

## Status Legend

- **Active**: still missing and worth pursuing.
- **Partial**: groundwork exists, but the design is incomplete.
- **Implemented**: no longer future work; keep regression coverage.
- **Reframed**: the original idea still matters, but the architecture changed and the next step should look different now.

## Validated Changes Since The Older Opportunity Notes

- **Runway seed is no longer broken.** The current seed path writes semantic artifacts and is covered by tests in [src/maverick/runway/seed.py](src/maverick/runway/seed.py) and [tests/unit/runway/test_seed.py](tests/unit/runway/test_seed.py).
- **Provider quota clean-failure handling exists now.** Tier 1 of the quota work is implemented in [src/maverick/exceptions/quota.py](src/maverick/exceptions/quota.py) and used by the top-level supervisors such as [src/maverick/actors/refuel_supervisor.py](src/maverick/actors/refuel_supervisor.py) and [src/maverick/actors/fly_supervisor.py](src/maverick/actors/fly_supervisor.py).
- **The old "cap review retries" finding is no longer correct for fly-beads.** The fly-beads supervisor explicitly caps review-fix rounds in [src/maverick/workflows/fly_beads/supervisor.py](src/maverick/workflows/fly_beads/supervisor.py), and the library review-fix loop is also bounded by `max_attempts` in [src/maverick/library/actions/review.py](src/maverick/library/actions/review.py).
- **Workspace planning moved toward hidden workspaces.** The earlier per-epic jj workspace note still has value, but it now has to be understood in the context of the hidden workspace design in [.specify/memory/workspace-isolation-design-brief.md](.specify/memory/workspace-isolation-design-brief.md) and the current manager in [src/maverick/workspace/manager.py](src/maverick/workspace/manager.py).

## Reconciled Opportunity Index

| Opportunity | Status | Note |
|---|---|---|
| Per-epic workspaces | Reframed | Still interesting, but should build on hidden workspaces rather than replace them. |
| Runway seed agent fix | Implemented | Keep tests; remove from active roadmap. |
| Conditional verification in land | Active | Still absent. |
| Variable pipeline by bead type | Partial | Bead categories exist, but fly does not branch pipeline stages by category yet. |
| Provider-agnostic interactive review | Active | Current review is structured, not conversational. |
| Assumptions as spec quality signal | Active | Good metric idea; not wired into runway or reporting. |
| Simplify the briefing room | Active | Multi-agent briefing is still the default shape. |
| Lean out convention injection | Active | Prompt convention payloads are still heavy. |
| Observational memory for runway | Active | Consolidation exists, but retrieval is not centered on a single always-in-context summary yet. |
| Cap review retries to reduce thrashing | Implemented | Keep tuning budgets, but the original gap is largely closed. |
| Strengthen TDD as primary feedback loop | Active | Process is test-first, but prompts and artifact generation could push harder in that direction. |
| Consider Agent Teams for review | Active | Still exploratory; current actor model already covers most of the same ground. |
| Reduce jj installation friction | Active | No true git-only fallback yet. |
| Supervisor agent for adaptive orchestration | Active | Still missing. |
| Supervisor-driven resource tuning | Active | Still missing and depends on better telemetry. |
| Asynchronous human review queue | Partial | Human-review beads and CLI exist; question queue and mid-flight answering do not. |
| Provider quota detection and automatic failover | Partial | Tier 1 exists; wait-and-resume and automatic failover do not. |
| Step-level evals and prompt testing | Active | Still missing. |
| Idempotent `maverick init` | Partial | Some sub-pieces are idempotent, but the overall command still blocks on existing config. |
| Route tool calls through owning actor | Active | MCP inbox still bypasses the owning actor and talks straight to the supervisor. |
| Structured telemetry via OpenTelemetry GenAI conventions | Active | No OTel or OpenLLMetry integration yet. |
| Shared mailbox actor scaffold | Active | New opportunity observed in current code. |
| Named capability profiles end-to-end | Active | New opportunity observed in current code. |
| Unified trace and correlation envelope | Active | New opportunity observed in current code. |
| Canonical artifact rendering and formatting | Active | New opportunity observed in current code. |
| Reusable supervisor fragments | Active | New opportunity observed in current code. |
| ACP prompt-cache optimization | Implemented | Phase A observability + Phase B retry-session reuse shipped; Phases C/D/1h-TTL closed after Phase A data showed caching is content-keyed and already at ~99.98% hit on measured workloads. |
| Consolidate agent `_end_turn` helpers | Active | Five xoscar agents duplicate a ~10-line cancel-after-forward helper. Minor refactor opportunity — extract to mixin or module helper when a sixth agent-with-inbox appears. |
| Fly checkpoint resume ignores `--max-beads` | Implemented | Reporting fix: `beads_completed` now counts new-this-run, not cumulative. The cap was always enforced; the inflated count made it look ignored. |
| Review prompts don't emit `prompt_usage` | Active (observability gap) | Observed in 2026-04-24 e2e: 13 review sessions created, 12 beads closed via review, 0 `acp_executor.prompt_usage` lines for review. Reviewer's agent-side cancel likely racing against the response path in `prompt_session`. |
| Commit provenance for evals | Active | New 2026-04-27. Curator strips bead IDs from public git history; restore the commit→bead link via a conventional Refs: trailer plus runway as system of record for provider/model/prompt. |

## 1. Orchestration And Human Review

### 1.1 Per-Epic Workspaces On Top Of Hidden Workspaces

**Status:** Reframed

The original proposal assumed jj workspaces directly in the user-facing development flow. The repo has since moved toward hidden workspaces as the primary isolation model. That does not kill the underlying idea. It changes the next step.

What still matters:

- Beads that escalate to human review still create a context-management problem when other epics continue.
- Correction work still wants the original epic state, not whatever the latest shared workspace happens to contain.
- Watch mode still wants a cleaner story for concurrent producer and consumer behavior across multiple epics.

What should happen next:

- Re-scope this as **multiple hidden workspaces or multiple hidden clones per epic**, not as a return to colocated jj workspaces in the user's repo.
- Keep the user-facing model git-native.
- Treat per-epic workspace switching as a second-stage extension to the hidden workspace architecture.

Relevant code and notes:

- [.specify/memory/workspace-isolation-design-brief.md](.specify/memory/workspace-isolation-design-brief.md)
- [src/maverick/workspace/manager.py](src/maverick/workspace/manager.py)
- [src/maverick/actors/fly_supervisor.py](src/maverick/actors/fly_supervisor.py)

### 1.2 Conditional Verification In Land

**Status:** Active

Land still treats work as either done or not done. There is no first-class notion of "verified conditional on an unresolved assumption" even though the human-review and correction-bead model is pushing in that direction.

Why it still matters:

- The current human-review flow already distinguishes optimistic commits from clean approvals.
- Assumption-driven work should leave a more precise audit trail than a single needs-human-review tag.
- This is the missing reporting layer between optimistic execution and later correction.

Relevant code:

- [src/maverick/cli/commands/land.py](src/maverick/cli/commands/land.py)
- [src/maverick/workflows/fly_beads/workflow.py](src/maverick/workflows/fly_beads/workflow.py)
- [src/maverick/workflows/fly_beads/fly_report.py](src/maverick/workflows/fly_beads/fly_report.py)

### 1.3 Variable Pipelines By Bead Type

**Status:** Partial

The codebase already has bead categories and labels, but the fly execution path does not use them to vary stage sequencing yet.

What exists:

- Bead category support in [src/maverick/beads/models.py](src/maverick/beads/models.py).
- Human-review and correction labels in [src/maverick/actors/fly_supervisor.py](src/maverick/actors/fly_supervisor.py) and [src/maverick/cli/commands/review.py](src/maverick/cli/commands/review.py).

What is still missing:

- A dispatcher that says validation beads, correction beads, review beads, and implementation beads should not all run the exact same pipeline.

### 1.4 Asynchronous Human Review Queue

**Status:** Partial

Maverick now has a real human-review path, but not the broader async collaboration loop imagined in the older opportunity notes.

What exists:

- Structured human review in [src/maverick/cli/commands/review.py](src/maverick/cli/commands/review.py).
- Human-review surfacing in [src/maverick/cli/commands/brief.py](src/maverick/cli/commands/brief.py) and [src/maverick/cli/commands/land.py](src/maverick/cli/commands/land.py).
- Automatic `needs-human-review` tagging in [src/maverick/actors/fly_supervisor.py](src/maverick/actors/fly_supervisor.py) and [src/maverick/workflows/fly_beads/supervisor.py](src/maverick/workflows/fly_beads/supervisor.py).

What is still missing:

- A question queue for advisory or blocking questions during execution.
- Mid-flight answer injection back into paused or retried work.
- Notification or polling mechanics beyond "review the bead later."

### 1.5 Provider-Agnostic Interactive Review

**Status:** Active

The current review command is interactive in the Click sense, but not interactive in the "open a conversational ACP session with preloaded context" sense.

Why it still matters:

- Some escalations need richer human-agent iteration than approve, reject, or defer.
- The structured review command is intentionally narrow and should stay narrow.
- A separate interactive mode could stay optional without polluting the default fast path.

Relevant code:

- [src/maverick/cli/commands/review.py](src/maverick/cli/commands/review.py)

### 1.6 Assumptions As A Spec Quality Signal

**Status:** Active

The core idea still holds: assumption-heavy execution is a signal that the plan or spec left too much open. The codebase now has enough run artifacts, human-review tags, and correction beads to measure this, but the metric is not yet surfaced.

Good next step:

- Feed assumption and human-review counts into runway consolidation or a future land summary.

Relevant code:

- [src/maverick/actors/fly_supervisor.py](src/maverick/actors/fly_supervisor.py)
- [src/maverick/cli/commands/review.py](src/maverick/cli/commands/review.py)
- [src/maverick/library/actions/consolidation.py](src/maverick/library/actions/consolidation.py)

### 1.7 Fly Checkpoint Resume Ignores `--max-beads`

**Status:** Implemented

Originally observed during the 2026-04-24 e2e run on `sample-maverick-project`: launched ``maverick fly --epic <id> --max-beads 2`` and the final report showed **12 beads** processed. The header banner showed ``max_beads=2`` parsed correctly. The first log line was:

> Resuming from checkpoint 'checkpoint' (saved at 2026-03-19T02:24:14...)

Root cause was a reporting bug, not a loop runaway. The bead loop in [src/maverick/actors/xoscar/fly_supervisor.py](src/maverick/actors/xoscar/fly_supervisor.py) (``_bead_loop``) correctly capped ``processed < max_beads`` for new work in this run. But the terminal-result payload reported ``"beads_completed": len(self._completed_beads)`` — and ``self._completed_beads`` is seeded from ``_inputs.completed_bead_ids`` (loaded from the checkpoint) so the loop's "skip already done" guard works on resume. With a stale checkpoint of 10 prior IDs and 2 new beads processed, the cumulative list was 12, so the report said "12 beads completed" without doing 12 beads of work.

**Fix shipped:** ``FlySupervisor`` tracks ``self._processed_this_run: int`` separately, set to 0 on construction and incremented inside ``_bead_loop`` alongside the local counter. All three ``_mark_done`` payloads (success, exception, prompt-error) now report ``"beads_completed": self._processed_this_run`` while keeping ``completed_bead_ids`` cumulative (still needed for resume state). Regression test in [tests/unit/actors/xoscar_runtime/test_fly_supervisor.py](tests/unit/actors/xoscar_runtime/test_fly_supervisor.py) (``test_terminal_result_reports_only_this_runs_beads``) seeds 10 prior IDs, triggers the terminal path, and asserts ``beads_completed == 0``.

Reflection: the FUTURE.md hypothesis ("the bead-loop counter must reset / re-evaluate the budget") was misdirected — the loop counter was already correct. The user-visible inflated count came from the reporting layer, not from extra agent work. Cost-control intent was always enforced; only the report was lying.

## 2. Agent Architecture And MCP Boundaries

### 2.1 Simplify The Briefing Room

**Status:** Active

The repo still pays for multiple specialist briefing agents before plan generation and refuel. The specialist fan-out pattern is real and useful, but it is also an obvious cost center.

The question is no longer whether the pattern exists. It does. The question is whether the current eight-agent footprint is still the right budget.

Relevant code:

- [src/maverick/actors/briefing.py](src/maverick/actors/briefing.py)
- [src/maverick/preflight_briefing/serializer.py](src/maverick/preflight_briefing/serializer.py)
- [src/maverick/workflows/generate_flight_plan/workflow.py](src/maverick/workflows/generate_flight_plan/workflow.py)
- [src/maverick/workflows/refuel_maverick/workflow.py](src/maverick/workflows/refuel_maverick/workflow.py)

### 2.2 Lean Out Convention Injection

**Status:** Active

Convention injection is still broad. The codebase now has more machine-enforced structure than when the older notes were written, which makes this opportunity stronger, not weaker.

The real target is not "fewer rules" in the abstract. It is:

- less prose for rules already enforced by tests, linters, or typed boundaries;
- more precise project-specific rules derived from real failures.

Relevant code:

- [src/maverick/agents/prompts/common.py](src/maverick/agents/prompts/common.py)
- [CLAUDE.md](CLAUDE.md)
- [src/maverick/agents/implementer.py](src/maverick/agents/implementer.py)

### 2.3 Route Agent Tool Calls Through The Owning Actor

**Status:** Active

This remains one of the cleanest architectural follow-ups in the repo.

Current state:

- The MCP inbox server validates tool payloads and then tells the supervisor directly.
- The owning actor does not observe its own agent's tool calls.
- Per-role tool-call policy therefore leaks downward into the ACP client or upward into the supervisor.

Why it still matters:

- It would simplify one-shot and per-role policies.
- It would make tool-call tracing more coherent.
- It would create a cleaner boundary between ACP or MCP concerns and actor concerns.

Relevant code:

- [src/maverick/tools/supervisor_inbox/server.py](src/maverick/tools/supervisor_inbox/server.py)
- [src/maverick/actors/decomposer.py](src/maverick/actors/decomposer.py)
- [src/maverick/actors/briefing.py](src/maverick/actors/briefing.py)

### 2.4 Shared Mailbox Actor Scaffold

**Status:** Active

This opportunity is new and surfaced directly from the current code.

Several mailbox-oriented actors repeat the same mechanics:

- lazy executor creation;
- session lookup or creation;
- required-tool instruction suffixes;
- inbox-file read, parse, and unlink;
- nudge retries when the tool was not called;
- shallow state snapshotting.

The repetition is visible across:

- [src/maverick/workflows/generate_flight_plan/actors/briefing.py](src/maverick/workflows/generate_flight_plan/actors/briefing.py)
- [src/maverick/workflows/fly_beads/actors/implementer.py](src/maverick/workflows/fly_beads/actors/implementer.py)
- [src/maverick/workflows/fly_beads/actors/reviewer.py](src/maverick/workflows/fly_beads/actors/reviewer.py)

Maverick already extracted async loop plumbing for top-level Thespian actors into [src/maverick/actors/_bridge.py](src/maverick/actors/_bridge.py). The mailbox actors want the same treatment.

### 2.5 Named Capability Profiles End-To-End

**Status:** Active

Tool sets are already centralized for many agent classes in [src/maverick/agents/tools.py](src/maverick/agents/tools.py), but runtime overrides still fall back to raw tool lists in several actor and executor paths.

Why it still matters:

- Capability intent is currently split between agent defaults, actor wiring, executor overrides, and MCP tool additions.
- Stronger named profiles would reduce drift and make routing or policy work easier later.

Relevant code:

- [src/maverick/agents/tools.py](src/maverick/agents/tools.py)
- [src/maverick/executor/config.py](src/maverick/executor/config.py)
- [src/maverick/actors/decomposer.py](src/maverick/actors/decomposer.py)

### 2.6 Consider Agent Teams For Parallel Review

**Status:** Active

This is still worth evaluating, but it is no longer an obvious must-have. Maverick already has a mature actor-mailbox model for reviewer concurrency.

That means the right question is narrow:

- would native Agent Teams replace meaningful orchestration code or just rename it?

Until there is a clearer payoff, this should remain exploratory.

### 2.7 ACP Prompt-Cache Optimization

**Status:** Implemented (Phase A and Phase B shipped 2026-04-24; Phases C / D / 1h-TTL closed as not needed)

Per-turn Anthropic quota burn has been unsustainable. The original hypothesis was that Maverick was getting ~0% cache hits because the Claude Agent SDK disables caching by default when MCP servers are attached (per Anthropic docs). Phase A observability proved that hypothesis **wrong**. Live run against `sample-maverick-project` on 2026-04-24:

| agent | input | cache_read | cache_write | output |
|---|---|---|---|---|
| structuralist (parallel) | 6 | 33,946 | 0 | 171 |
| recon (parallel) | 6 | 33,940 | 0 | 167 |
| navigator (parallel) | 14 | 119,754 | 19,287 | 5,526 |
| contrarian (sequential after) | 13 | 81,896 | 61,969 | 12,588 |

Caching is working end-to-end with MCP attached. Three parallel briefings all hit a warm prefix cache (~34K read tokens apiece with 0 cache writes on two of them), and the sequential contrarian then benefited from navigator's cache write (navigator wrote 19K; contrarian read 82K). The 6-token `input_tokens` on parallel briefings versus their ~19KB prompts means ~99.98% of the prompt content is being cache-served.

This reframes Phases B–D — the original framing assumed MCP was actively suppressing caching, so every agent prompt was a cold start. With caching working, the phases shrink from "unblock a broken feature" to "squeeze a few more points out of an already-working one":

**Phase A — Observability (Implemented 2026-04-24):**

- `AcpStepExecutor` now captures `PromptResponse.usage` on both the one-shot `execute()` path and the multi-turn `prompt_session()` path.
- A structured `acp_executor.prompt_usage` INFO log line is emitted per prompt with `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `session_id`, `session_kind` (`one_shot` or `multi_turn`), and `usage_reported`.
- `ExecutorResult.usage` is populated from the ACP usage payload instead of hardcoded `None`.
- Relevant commits: `a007364` (plumbing + tests), `2e57017` (format drift sweep).

**Xoscar-migration bugs fixed on the way to validating Phase A** (2026-04-24): every xoscar actor was missing `super().__init__()` so `self._generators` was never set and `@xo.generator run()` crashed on first iteration (`4eb67ef`); every supervisor used `self.ref` instead of `self.ref()` and passed the unbound Cython method to children as `supervisor_ref` (`b9c2dd3`); `self.uid` returns bytes so supervisor-child uid f-strings produced the `b'...'` repr which garbled the MCP subprocess argv (`6be0a9d`); briefing/decomposer/implementer/reviewer/generator `on_tool_call` was missing `@xo.no_lock` and deadlocked with the agent's own `send_*` method that holds the actor lock across the ACP prompt (`4e8689f`); one-shot cancel fired on `ToolCallStart` racing against the MCP round-trip (`da65394`); supervisor callback methods (`*_ready`, `*_error`, `get_terminal_result`) all needed `@xo.no_lock` because the `@xo.generator run()` method holds the supervisor's lock while awaiting the event queue and the callbacks are what push onto that queue (`06fed8e`). None of these were caught by the existing unit tests because those tests assert on method-level routing, not on end-to-end generator iteration or cross-actor RPC. Regression guards added in `tests/unit/actors/xoscar_runtime/test_super_init.py` (parametrised per actor file) to keep new actors correct by default.

**Phase B — Retry-session reuse (Implemented 2026-04-24, `6eed6a1`):**

`_execute_with_retry` used to call `conn.new_session(...)` on every retry attempt, so a transient hiccup + one retry meant paying for two cache-prefix writes on the same content. After `6eed6a1`, `_run_single_attempt` calls `_ensure_session()` which is a no-op when a session already exists; a reconnect (subprocess died) still forces a fresh session on the new connection. Regression tests lock in both behaviors: `test_retry_reuses_session` and `test_reconnect_does_create_fresh_session`.

The originally proposed "warm-up cascade" for the briefing fan-out was dropped — Phase A data showed parallel briefings already share cache (`cache_read_tokens≈33,946` on all three with zero cache writes on two), so sequencing the first agent would buy zero tokens at the cost of wall-clock latency.

**Phase C — Unblock MCP caching (Closed, not needed):**

Phase A data contradicted the premise. The Anthropic docs claim MCP servers disable caching by default; the live run showed clear cache reads (99.98% of prompt served from cache on parallel briefings) with `agent-inbox` MCP attached. No upstream patch needed.

**Phase D — Session-lifetime refactors (Closed, not needed):**

The premise of Phase D was that rotating sessions across bead/mode boundaries discarded the prefix cache. Phase A data shows that's wrong: Anthropic's prompt cache is **content-keyed, not session-keyed**. Proof: structuralist (session A) and recon (session B) both read 33,940+ cached tokens in the same refuel — different sessions, same content, shared cache. Fusing implementer/reviewer/decomposer sessions across beads would therefore buy essentially nothing on token cost while introducing real regression risk (longer conversation history, cross-bead context bleed, harder debugging).

Reopen only if a live refuel/fly run shows `cache_write_tokens` climbing on prompts that should have been cache-fed — that would indicate either a cache-key invalidation (prompt drift) or actual 5-min TTL eviction, and the remedy would differ case by case.

**Phase B leftover — 1h TTL (`ENABLE_PROMPT_CACHING_1H=1`) (Not needed):**

The 5-min default is enough for every phase we've measured. Structuralist/recon hit cache with `cache_write=0` (didn't even need to write — already warm). Contrarian ran 215s and still completed inside 5 min of briefing start. No evidence of eviction-driven re-writes. If later data shows `cache_write_tokens` rising across same-prefix prompts in a multi-minute session, this is a one-env-var change — until then it's a bet with 2× write cost.

Relevant code:

- [src/maverick/executor/acp.py](src/maverick/executor/acp.py) (`_execute_with_retry`, `_ensure_session`)
- [src/maverick/executor/_connection_pool.py](src/maverick/executor/_connection_pool.py) (subprocess env construction — site for `ENABLE_PROMPT_CACHING_1H` if ever needed)

### 2.8 Consolidate Agent `_end_turn` Helpers

**Status:** Active (minor refactor)

Each of the five xoscar agent actors (`briefing`, `decomposer`, `implementer`, `reviewer`, `generator`) has its own ``_end_turn()`` helper that does the same thing: after ``on_tool_call`` forwards a payload to the supervisor, cancel the current ACP turn via ``self._executor.cancel_session(self._session_id)`` with best-effort error handling. The five copies are identical modulo the logger name.

This is a minor code smell rather than a bug — each copy is ~10 lines and they don't drift easily since the regression test in `test_super_init.py` forces the presence of the agent-side cancel pattern. Extraction options:

- Module-level helper: `async def end_acp_turn(executor, session_id, log_tag) -> None` in a shared utility module.
- Mixin class `AgentInboxEndTurnMixin` that every agent actor inherits alongside `xo.Actor`. Xoscar's MRO handles this cleanly since `xo.Actor` itself is just a class.

Either works; the mixin is slightly cleaner since the helper needs `self._session_id`, `self._executor`, and `self._actor_tag` anyway. Defer until a sixth agent-with-inbox gets added — at four copies it's just duplication; at six it's a pattern waiting for a name.

Relevant code:

- [src/maverick/actors/xoscar/briefing.py](src/maverick/actors/xoscar/briefing.py) (`_end_turn`)
- [src/maverick/actors/xoscar/decomposer.py](src/maverick/actors/xoscar/decomposer.py) (`_end_turn`)
- [src/maverick/actors/xoscar/implementer.py](src/maverick/actors/xoscar/implementer.py) (`_end_turn`)
- [src/maverick/actors/xoscar/reviewer.py](src/maverick/actors/xoscar/reviewer.py) (`_end_turn`)
- [src/maverick/actors/xoscar/generator.py](src/maverick/actors/xoscar/generator.py) (`_end_turn`)

### 2.9 Move Tool-Required Framework Wrapper To System Prompt

**Status:** Active (per-turn token-overhead reduction)

Commit `3d1303f` introduced `build_tool_required_prompt()` /
`build_tool_required_nudge_prompt()` in [src/maverick/actors/xoscar/_agentic.py](src/maverick/actors/xoscar/_agentic.py) to fix
a real prompt-injection-style refusal we hit on the earlybird PRD: the
codebase analyst was treating maverick's appended `## REQUIRED: Submit
via tool call` instruction as if the user-supplied document was telling
it what to do. The fix wraps every user prompt with framework-attributed
headers and `<<<BEGIN/END USER CONTENT>>>` markers that the model can
syntactically distinguish from the document.

The wrapper text is *identical* across turns within the same session
because `expected_tool` and `role_intro` don't vary turn-to-turn for a
given actor. So we send the same ~250 tokens of framework boilerplate
inside *every* user message in a session — for the decomposer detail
phase that's 5×, for the reviewer fix loop it can be more.

Anthropic prompt caching keys on contiguous *prefixes* of the full
message list, so the repeated wrappers don't hit cache (each new user
message is uncached at the byte level even when its prefix matches a
prior message's prefix). Within-session caching of prior turns still
works fine — there's no regression — but the per-turn input cost grows
linearly in the wrapper size.

Two approaches, in order of payoff:

1. **Move the framework instruction into the ACP session's system
   prompt** so it's sent once per session and the per-turn user message
   only carries the BEGIN/END user content block. The system prompt is
   also more authoritative in the model's training, which strengthens
   the prompt-injection defense as a side effect. This needs the ACP
   executor's `create_session(...)` path to expose a `system_prompt`
   parameter and thread it through `claude-agent-acp` (current call
   sites in the five actors all pass the wrapper inside `prompt_text`
   only).

2. **Drop the wrapper on follow-up turns within a session.** The agent
   already saw the framework framing on turn 1; turns 2..N could send
   bare `<<<BEGIN/END>>>` content. Smaller code change, smaller win
   (only saves the wrapper text on N-1 turns out of N), but no API
   change required.

Option (1) is the architecturally right move; option (2) is a band-aid
that's worth doing if the executor refactor is non-trivial. Defer until
prompt-cache cost is a measurable problem — the wrapper is ~250 tokens
on a typical 14k-token prompt (~1.8% overhead), and the
prompt-injection refusal it prevents costs ~50k tokens *and* a
user-visible failure.

Relevant code:

- [src/maverick/actors/xoscar/_agentic.py](src/maverick/actors/xoscar/_agentic.py) (`build_tool_required_prompt`,
  `build_tool_required_nudge_prompt`)
- [src/maverick/executor/acp.py](src/maverick/executor/acp.py) (`create_session` — would need a
  `system_prompt` parameter for option 1)
- All five actor `_send_*` methods.

### 2.10 Per-Bead Complexity-Based Model Routing

**Status:** Phases 1, 2, 2b, and 3 implemented

**Background.** Bead workloads vary wildly inside a single epic — "create
LICENSE file" and "implement complete tax engine" are both single beads
under maverick's current model. They go through the same implementer
with the same model, which means we either pay frontier prices for
trivial work or accept weaker output on hard work. With opencode +
OpenRouter giving us cheap access to the full open-weight catalog
(GPT-OSS-20B at $0.13/Mtok up through Kimi K2.6 at ~$1.70/Mtok), it's
finally cheap to route by need.

**Phase 1 (implemented).** The decomposer classifies each bead at
outline time into one of `trivial | simple | moderate | complex`.
Schema additions span:

- [src/maverick/tools/agent_inbox/models.py](src/maverick/tools/agent_inbox/models.py)
  (`WorkUnitOutlinePayload.complexity`, `WorkUnitComplexity` Literal)
- [src/maverick/tools/agent_inbox/schemas.py](src/maverick/tools/agent_inbox/schemas.py)
  (`SUBMIT_OUTLINE` JSONSchema enum + classification rubric in the
  property description)
- [src/maverick/library/actions/decompose.py](src/maverick/library/actions/decompose.py)
  (`build_outline_prompt` — the decomposer's instruction set teaches
  the rubric and asks for honest classification)
- [src/maverick/workflows/refuel_maverick/models.py](src/maverick/workflows/refuel_maverick/models.py)
  (`WorkUnitSpec.complexity`)
- [src/maverick/flight/models.py](src/maverick/flight/models.py)
  (`WorkUnit.complexity`)
- [src/maverick/flight/serializer.py](src/maverick/flight/serializer.py)
  + [src/maverick/flight/loader.py](src/maverick/flight/loader.py)
  (markdown frontmatter round-trip; unknown enum values silently
  load as None for forward compat)
- [src/maverick/workflows/refuel_maverick/workflow.py](src/maverick/workflows/refuel_maverick/workflow.py)
  (write_work_units now logs the complexity distribution after refuel
  so users can see what the decomposer produced before trusting Phase 2
  routing with money)

Nothing routes on `complexity` yet — it's hint-only. This phase exists
so we can observe whether the decomposer's classifications match human
intuition over a few real refuels before wiring routing.

**Phase 2 (implemented): Tier routing for `implement` + escalation on
fix-loop overflow.**

Configuration shape:

```yaml
steps:
  implement:
    tiers:
      trivial:    { provider: opencode, model_id: openai/gpt-oss-20b }
      simple:     { provider: opencode, model_id: openai/gpt-oss-120b }
      moderate:   { provider: opencode, model_id: moonshot/kimi-k2-6 }
      complex:    { provider: claude,   model_id: opus }
    # Backward-compat: when `tiers` is omitted, fall back to the
    # current top-level `provider` / `model_id`.
    provider: opencode
    model_id: openai/gpt-oss-120b
```

Code-side changes:

1. Extend `StepConfig` (or a sibling) to carry an optional `tiers`
   mapping: `dict[Literal["trivial", "simple", "moderate", "complex"],
   StepConfig]`.
2. Thread the bead's `complexity` field through `ImplementRequest` so
   the implementer can resolve the right tier. The implementer already
   rotates its ACP session per bead via `new_bead(request)`, so per-bead
   model switching is feasible — `_executor.create_session` takes a
   config and we can build a different one per session.
3. **Escalation on fix-loop overflow.** When the supervisor's
   per-bead fix-loop count exceeds a configurable threshold (default 2),
   automatically promote the bead one tier and retry once. This is the
   safety net for misclassification: if the decomposer marks a bead as
   "simple" and the cheap model can't actually deliver, we burn a retry
   on the next tier up rather than spinning indefinitely on a model
   that's out of its depth. Recorded in the runway as a
   `complexity_escalated` event so the decomposer's classification
   accuracy can be measured over time.

**As shipped** (commit pending push):

- `ImplementerTierConfig` and `ImplementerTiersConfig` Pydantic models
  in [src/maverick/config.py](src/maverick/config.py).
- `FlyInputs.implementer_tiers` carries the parsed tiers config from
  the workflow into the supervisor.
- `FlySupervisor.__post_create__` spawns one `ImplementerActor` per
  defined tier (with merged StepConfig) when tiers are configured;
  legacy single-actor behaviour preserved when omitted.
- `_resolve_implementer_tier(complexity, escalation_level)` picks the
  tier name. Unrecognised/None complexity defaults to `moderate`.
  Sparse tier configs round DOWN to the nearest cheaper defined tier
  (and round UP only when nothing at-or-below exists).
- `_load_bead_context` extracts `complexity` from the work-unit md
  YAML frontmatter and stores it on the bead dict.
- `_send_fix` checks fix-round count against the configured
  `escalation_threshold` (default 2). When exceeded and a higher
  defined tier exists, promotes the bead one tier up, rotates the
  higher-tier actor's session, and emits a structured
  `fly.complexity_escalated`-style warning.

Risks worth flagging in the implementation:

- **Misclassification under-shoots.** Decomposer marks complex bead
  as "simple" → cheap model fails review → fix-loop retries on the
  same model → eventually escalates. Net cost: extra round-trips before
  the retry. Mitigated by the fix-loop-overflow escalation above.
- **Misclassification over-shoots.** Decomposer marks LICENSE file as
  "complex" → wasted money but no broken work. Lower-stakes than
  under-shooting.
- **Operational burden.** Users now maintain a `tiers` map. Mitigated
  by sensible shipped defaults.

Relevant code:

- [src/maverick/executor/config.py](src/maverick/executor/config.py)
  (StepConfig — the place to add optional `tiers`)
- [src/maverick/actors/xoscar/messages.py](src/maverick/actors/xoscar/messages.py)
  (`ImplementRequest` — needs a `complexity` field)
- [src/maverick/actors/xoscar/implementer.py](src/maverick/actors/xoscar/implementer.py)
  (`send_implement` / `new_bead` — pick tier, build per-bead config)
- [src/maverick/actors/xoscar/fly_supervisor.py](src/maverick/actors/xoscar/fly_supervisor.py)
  (read bead complexity from the work-unit markdown / spec, pass in
  ImplementRequest, drive escalation when fix-loop count exceeds
  threshold)

**Phase 2b (implemented): Global ACP-subprocess cap with LRU eviction.**

Before Phase 2b, the only knob bounding live `claude-agent-acp` /
`opencode acp` subprocesses was *per-phase* (e.g.
`parallel.max_briefing_agents`, `parallel.decomposer_pool_size`). With
Phase 2 tier actors live, a mixed-complexity epic could spawn up to N
implementer subprocesses (one per tier actually used in the epic), all
alive until fly ended. On a small host that was too many.

The right shape is a single global ceiling: `parallel.max_agents = N`
caps total live ACP subprocesses across the whole workflow run. Per-
phase knobs are *soft ideals* (how much fan-out the phase wants); the
global cap is the hard ceiling.

**As shipped:**

- New :class:`SubprocessQuota`
  ([src/maverick/tools/agent_inbox/subprocess_quota.py](src/maverick/tools/agent_inbox/subprocess_quota.py)):
  pool-scoped acquire/release with LRU eviction of idle leases. The
  slot is held for the lifetime of the executor's subprocess pool, not
  per-prompt. Reentrant (a re-acquire by the same uid bumps activity).
- :class:`AgentToolGateway` accepts `max_subprocesses` and exposes
  `subprocess_quota`. Workflows pass `parallel.max_agents` through
  `actor_pool(max_subprocesses=...)`.
- :class:`AcpStepExecutor` accepts `subprocess_quota` + `actor_uid`;
  threads them into :class:`ConnectionPool.get_or_create` (acquire
  before first spawn) and `cleanup()` (release).
  `prompt_session` brackets each prompt with `mark_busy`/`mark_idle`
  so mid-prompt actors are shielded from eviction.
- New `cleanup_for_eviction()` on the executor: closes subprocesses
  *without* re-releasing the quota slot (the quota already popped the
  lease). Invoked via the `_on_evicted` bridge wired into the
  connection pool.
- :class:`AgenticActorMixin` exposes a `_build_quota_aware_executor()`
  helper used by every actor's `_ensure_executor()` and an
  `_invalidate_sessions_for_eviction()` hook (default: clears
  `self._session_id`) wired in via `set_session_invalidator`.
- `ParallelConfig.max_agents` flipped from advisory-only to the hard
  ceiling. Default stays at 3; tune up on richer hosts. Eviction cost
  is documented (~200ms handshake + ACP-session conversation context
  loss).

Per-phase knobs (`max_briefing_agents`, `decomposer_pool_size`,
`max_parallel_reviewers`) keep their existing semantics — they bound
*how much parallelism a phase wants*. With `max_agents=2` and
`max_briefing_agents=3`: 2 briefings concurrent, 3rd waits for an
eviction or release.

**Phase 3 (implemented): Extend tier routing to `review`, `fix`,
`decompose_detail`.**

Each of these has the same per-unit invocation pattern as `implement`
and benefits from the same complexity gating.

**As shipped:**

- New :class:`ReviewerTiersConfig` and :class:`DecomposerTiersConfig`
  in [src/maverick/config.py](src/maverick/config.py) — both reuse
  :class:`ImplementerTierConfig` for per-tier overrides.
- :class:`FlySupervisor` extracted the implementer's two-step tier
  resolver into :meth:`_resolve_tier_in` (a static method working
  against any actor map). Reviewer reuses it via
  :meth:`_resolve_reviewer_tier`. Reviewer has no escalation — review
  is one-shot per round; the *implementer* is the actor that escalates
  on fix-loop overflow.
- :class:`FlyInputs.reviewer_tiers` carries the parsed config; when
  set, the supervisor spawns one ReviewerActor per defined tier and
  routes `new_bead` + `send_review` through `_reviewer_for(complexity)`.
- :class:`RefuelInputs.decomposer_tiers` carries the parsed config;
  when set, the supervisor replaces the round-robin pool with one
  DecomposerActor per defined tier (each in `pool` role). Per-unit
  detail prompts route through the unit's outline complexity.
- The fix path is automatically tier-routed because it runs on the
  same per-tier ImplementerActor that handled the original implement
  prompt — no separate wiring needed.
- Workflows extract `actors.fly.reviewer.tiers` and
  `actors.refuel.decomposer.tiers` from `maverick.yaml` and pass them
  through the supervisor inputs.

**Tradeoff (decompose_detail):** tier mode trades cross-worker
parallelism for per-tier model differentiation. With one worker per
tier, multiple same-complexity units queue on that worker. Crank
`parallel.decomposer_pool_size` AND enable tiers if both knobs
matter; otherwise pick the one that fits the workload.

**Aggregate review** (the final cross-bead check) is *not* tiered —
it sees diff across the whole epic and can't be classified per-bead.
Stays on the base reviewer config (effectively the legacy single-
actor path even when per-bead reviewer tiers are configured).

Suggested defaults:

```yaml
steps:
  review:
    tiers:
      trivial:    { provider: opencode, model_id: openai/gpt-oss-20b }
      simple:     { provider: opencode, model_id: openai/gpt-oss-120b }
      moderate:   { provider: opencode, model_id: zai/glm-5-1 }
      complex:    { provider: claude,   model_id: sonnet }
  fix:
    tiers:
      trivial:    { provider: opencode, model_id: openai/gpt-oss-20b }
      simple:     { provider: opencode, model_id: openai/gpt-oss-120b }
      moderate:   { provider: opencode, model_id: openai/gpt-oss-120b }
      complex:    { provider: opencode, model_id: moonshot/kimi-k2-6 }
  decompose_detail:
    tiers:
      trivial:    { provider: opencode, model_id: openai/gpt-oss-120b }
      simple:     { provider: opencode, model_id: openai/gpt-oss-120b }
      moderate:   { provider: opencode, model_id: openai/gpt-oss-120b }
      complex:    { provider: opencode, model_id: moonshot/kimi-k2-6 }
```

`decompose_detail` is mostly mechanical "fill in instructions for this
work unit" — the primary outline pass already did the architectural
work. Most beads can use a single mid-tier model regardless of
complexity; only `complex` beads benefit from extra reasoning capacity
during detail generation.

Aggregate review (the final cross-bead check) should *not* tier — it
sees diff across the whole epic and can't be classified per-bead. Keep
it on a fixed frontier model.

**Other axes worth considering, but not for v1**

Complexity is the right *first* axis because it's the cleanest signal
of "how much intelligence is needed." Other axes that may matter
eventually:

- **Domain** — writing tests vs business logic. A "moderate" test bead
  probably wants a different model than a "moderate" engine bead.
- **Risk** — security-critical vs UI tweak. Lets you keep frontier
  review on auth code regardless of complexity.
- **File language** — TypeScript-heavy beads vs Python-heavy.
  Specialists differ.

These are refinements over per-bead-complexity, not replacements. Land
Phase 2 + Phase 3 first, see how often the misclassification cases
cluster on a particular dimension, then add the next axis if they do.

### 2.11 Auto Tech-Debt Beads From Approved-With-Findings Reviews

**Status:** Active

**Background.** Today the fly review loop has a hard binary: a review is
either `approved` (bead commits, fly moves on) or `not approved` (fix
loop fires). But reviewers regularly come back with `approved` AND a
list of non-blocking findings — improvements they noticed but didn't
think warranted gating the bead. Those findings get:

* recorded to runway (`record_review_findings`) — historical context
  for future briefings,
* captured in the per-bead `fly-report.json` — audit trail,
* and otherwise *dropped on the floor*. No follow-up bead, no surface
  in the aggregate review prompt, no human nudge.

In practice this means a moderate-tier reviewer flagging "this should
use a context manager" disappears into the runway and never becomes
work someone or some implementer addresses. As cheap-tier reviewers
flag more (per Phase 3, simple/moderate beads now get reviewed by
cheaper models with looser standards), the lost-finding rate grows.

**Proposal.** When a review is `approved` AND contains findings at or
above a configurable severity floor (default `major`), the supervisor
auto-files each finding as a tech-debt bead under the same epic.

**Bead shape:**

```yaml
parent: <epic_id>            # e.g. sample_maverick_project-e6c
type: task
labels: [tech-debt]
metadata:
  source_bead: <bead_id>     # e.g. sample_maverick_project-e6c.8
  source_round: 2            # which review round produced it
  severity: major
  reviewer_tier: complex     # which tier flagged it
  finding_text: "<original message>"
title: "[tech-debt] <one-line summary from finding>"
```

**Design choices:**

* **Child of the epic, no `depends_on`.** The source bead already
  shipped and the reviewer explicitly didn't gate on these — they're
  not blockers. Filing under the epic preserves lineage without
  blocking epic closure. Six months later, "why are we using this
  awkward pattern?" → one click to the source review finding.
* **`tech-debt` label** so users can filter the normal ready queue
  (`bd ready --exclude-label tech-debt`) or batch-triage them
  (`bd ready --label tech-debt`).
* **Severity floor (default `major`)** to keep noise down. `minor`
  findings stay in the runway only. Configurable per project via
  `fly.tech_debt_severity_floor` so teams can tighten or loosen.
* **One bead per source finding (no dedupe in v1).** If the same
  pattern fires across 5 beads in an epic, you get 5 tech-debt beads.
  Dedupe (by similarity-hash of `finding_text` within an epic) is a
  v2 add if it gets noisy in practice.

**Cost considerations:**

* No extra LLM cost — reviews already produce findings; this only
  changes what we *do* with them.
* Linear bd writes per qualifying finding. Negligible at typical fly
  volumes (≤5 beads × ≤3 review rounds × ~3 findings).

**Code-side changes:**

* New `record_tech_debt_findings` action in
  [src/maverick/library/actions/runway.py](src/maverick/library/actions/runway.py)
  (sibling of `record_review_findings`).
* `FlySupervisor._review_loop` calls it when a review returns
  `approved=True` with findings ≥ severity floor.
* New `fly.tech_debt_severity_floor: Literal["minor", "major", "critical"]`
  field in `MaverickConfig`. Default `"major"`.
* Bead-creation goes through the existing `BeadCreatorActor` /
  `bd add` path — adds the parent + label + metadata fields.
* CLI surfacing: a one-line `created N tech-debt bead(s)` event after
  each approved-with-findings review so the user sees what got filed.

**Telemetry / future tuning:**

The runway already tracks per-tier review patterns. Add a
`tech_debt_created` event so we can later answer: "do moderate-tier
reviewers create more tech-debt-worthy findings than complex-tier
ones?" That's a signal for whether to bump moderate review up a tier
in the default config.

**Out of scope for v1:**

* Auto-resolution of tech-debt beads when a later bead happens to fix
  the issue.
* GitHub Issue mirroring (the existing `review-and-fix-with-registry`
  fragment does this for the legacy review path; we'd port it later
  if there's demand).
* Cross-epic dedupe (only same-epic dedupe is even on the table).

**Relevant code:**

* [src/maverick/actors/xoscar/fly_supervisor.py](src/maverick/actors/xoscar/fly_supervisor.py)
  (`_review_loop` — natural call site)
* [src/maverick/library/actions/runway.py](src/maverick/library/actions/runway.py)
  (existing `record_review_findings` — add a sibling)
* [src/maverick/library/actions/beads.py](src/maverick/library/actions/beads.py)
  (existing bead creation — extend with parent + label fields)
* [src/maverick/config.py](src/maverick/config.py) (new
  `tech_debt_severity_floor` knob)
* [src/maverick/library/fragments/review-and-fix-with-registry.yaml](src/maverick/library/fragments/review-and-fix-with-registry.yaml)
  (precedent for how the legacy review path handles this — worth
  reading before implementing for consistency)

### 2.12 Free OpenRouter Models Often Skip MCP Tool Calls

**Status:** Active (known limitation, hit during 2026-04-27 Phase 3
validation)

When `qwen3-coder:free` was wired into the moderate implementer tier
via opencode/OpenRouter, the agent returned empty responses on both
the initial prompt and the self-nudge — the model finished its turn
without calling `submit_implementation` at all, and our `_run_with_self_nudge`
helper correctly routed a `PromptError`. We've also seen similar
patterns with other `:free`-suffixed OpenRouter models in earlier
sessions.

The hypothesis: free-tier OpenRouter routing tends to land on smaller
or more aggressively rate-limited variants that either (a) don't
reliably parse and emit MCP tool-call structure, or (b) are throttled
hard enough that the response never lands within the prompt timeout.
Either way, the mailbox-pattern actors (which require an MCP tool
call to produce any useful output) silently fail.

What we'd want:

- **Detect the failure mode at config-load time**: when a tier is
  configured with `provider: opencode` + `model_id: *:free`, emit a
  warning that MCP-tool reliability is not guaranteed and recommend a
  fallback tier or a paid alternative.
- **Optionally auto-fallback on consecutive empty turns**: if an actor
  produces N empty turns in a row, escalate the bead one tier up
  (similar to the implementer fix-loop escalation in §2.10 Phase 2)
  rather than just failing the bead. The runway already records
  per-bead outcomes — this would be observable.
- **Prefer copilot or claude for tool-required actors**: the four
  agentic actor types (briefing, decomposer, implementer, reviewer,
  generator) all *require* MCP tool calls. The non-agentic `steps`
  paths (navigator, structuralist, recon, etc. when not using the
  mailbox pattern) tolerate text-only responses fine. Document this
  distinction in the config schema so users don't accidentally wire
  a free-tier model into a mailbox actor.

Workaround in the meantime: **use copilot's free tier (gpt-5-mini) or
gemini's free tier instead of OpenRouter `:free` models** for any
tier that powers a mailbox actor. Both reliably call MCP tools.

Relevant code:

- [src/maverick/actors/xoscar/_agentic.py](src/maverick/actors/xoscar/_agentic.py)
  (`_run_with_self_nudge` — natural place to count consecutive empty
  turns and trigger escalation)
- [src/maverick/config.py](src/maverick/config.py) (warn on
  `:free`-model + mailbox-actor config combos)

## 3. Learning, Feedback, And Telemetry

### 3.1 Observational Memory For Runway

**Status:** Active

Runway has already moved partway toward summary-first memory, but it has not fully crossed over.

What exists:

- episodic records;
- consolidation logic;
- semantic seed files.

What is missing:

- one canonical, always-in-context summary as the primary memory surface;
- a cleaner split between summary context and deeper retrieval;
- process-level learning as a first-class output.

Relevant code:

- [src/maverick/workflows/fly_beads/_runway.py](src/maverick/workflows/fly_beads/_runway.py)
- [src/maverick/library/actions/consolidation.py](src/maverick/library/actions/consolidation.py)
- [src/maverick/runway/seed.py](src/maverick/runway/seed.py)

### 3.2 Supervisor Agent For Adaptive Orchestration

**Status:** Active

The repo still has deterministic orchestration with static timeouts, thresholds, and retry budgets. The newer code has better typed payloads and clearer event paths, but that only strengthens the case for a small advisor layer.

The most important constraint remains the same:

- the workflow loop should stay authoritative;
- any supervisor agent should advise or patch policy, not replace routing logic.

Relevant code:

- [src/maverick/actors/fly_supervisor.py](src/maverick/actors/fly_supervisor.py)
- [src/maverick/workflows/base.py](src/maverick/workflows/base.py)
- [src/maverick/session_journal.py](src/maverick/session_journal.py)

### 3.3 Supervisor-Driven Resource Tuning

**Status:** Active

Static resource envelopes remain the default. This is still a separate opportunity from the broader supervisor-agent idea because it needs durable runtime metrics, not just policy hooks.

This item now depends even more clearly on better telemetry and traceability than it did in the older notes.

### 3.4 Step-Level Evals And Prompt Or Provider Testing

**Status:** Active

There is still no first-class eval layer, no fixture capture pipeline, and no dedicated command for replaying a step across provider or prompt variants.

This remains high leverage because it speeds up every other optimization loop.

Relevant code:

- [src/maverick/executor/acp.py](src/maverick/executor/acp.py)
- [src/maverick/cli/workflow_executor.py](src/maverick/cli/workflow_executor.py)
- [pyproject.toml](pyproject.toml)

### 3.5 Structured Telemetry Via OpenTelemetry GenAI Conventions

**Status:** Active

No OpenTelemetry or OpenLLMetry dependencies are present today, and there is no standard trace model spanning workflows, actor invocations, tool calls, or token usage.

Why it still matters:

- it unlocks adaptive orchestration and resource tuning;
- it makes provider comparison tractable;
- it gives child-process observability that structlog alone does not.

Relevant code:

- [pyproject.toml](pyproject.toml)
- [src/maverick/events.py](src/maverick/events.py)
- [src/maverick/logging.py](src/maverick/logging.py)

### 3.6 Unified Trace And Correlation Envelope

**Status:** Active

This is a distinct, codebase-driven opportunity that should exist whether or not full OTel support lands soon.

Pieces already exist:

- workflow identifiers in [src/maverick/events.py](src/maverick/events.py);
- run metadata in [src/maverick/runway/run_metadata.py](src/maverick/runway/run_metadata.py);
- sequence and reply edges in [src/maverick/workflows/fly_beads/actors/protocol.py](src/maverick/workflows/fly_beads/actors/protocol.py).

What is missing is one causality envelope that ties logs, events, actor messages, and persisted artifacts together end to end.

### 3.7 Canonical Artifact Rendering And Formatting

**Status:** Active

The codebase has started moving toward canonical renderers, especially around generated flight plans, but it is not yet universal.

What exists:

- canonical flight plan markdown in [src/maverick/workflows/generate_flight_plan/markdown.py](src/maverick/workflows/generate_flight_plan/markdown.py);
- typed MCP intake models in [src/maverick/tools/supervisor_inbox/models.py](src/maverick/tools/supervisor_inbox/models.py).

What should happen next:

- give every durable artifact a single renderer and a single reader;
- stop scattering format rules across ad hoc JSON dumps and inline markdown assembly.

### 3.8 Review Prompts Don't Emit `acp_executor.prompt_usage`

**Status:** Active (observability gap)

Observed during the 2026-04-24 e2e run on `sample-maverick-project`. The fly run closed 12 beads — every bead went through the implement → gate → ac → spec → review → commit cycle, so there should have been at least 12 review prompts. Log evidence:

| signal | count |
|---|---|
| ``acp_executor.session_created`` with ``step_name=review`` | 13 |
| ``bead_closed`` (review gate passed) | 12 |
| ``acp_executor.prompt_usage`` with ``step_name=review`` | **0** |

Implementer prompts on the same run logged 12 ``prompt_usage`` events as expected (with ``usage_reported=False`` because copilot's ACP bridge doesn't surface token counts — that part is upstream and not Maverick's bug). Reviewer prompts produced zero log lines despite the sessions clearly being created and the reviews clearly running successfully.

Most likely cause: the agent-side cancel from ``reviewer.on_tool_call._end_turn`` is firing fast enough that ``prompt_session()`` returns via an exception path rather than via the response-with-usage path, bypassing the ``logger.info("acp_executor.prompt_usage", ...)`` call at the bottom of the success branch in [src/maverick/executor/acp.py](src/maverick/executor/acp.py). The implementer somehow doesn't hit this path — possibly because the implementer's submit tool is followed by a small wrap-up that delays the cancel just enough for the response to land first.

Why it matters:

- Phase A observability is the foundation of all the prompt-cache and cost-tracking work — any agent that silently doesn't log usage is invisible to that monitoring.
- Reviewers run on every bead; this is half of the fly token budget going unobserved.

Relevant code:

- [src/maverick/executor/acp.py](src/maverick/executor/acp.py) (``prompt_session``, lines around the ``acp_executor.prompt_usage`` info log)
- [src/maverick/actors/xoscar/reviewer.py](src/maverick/actors/xoscar/reviewer.py) (``_end_turn``, ``on_tool_call``)
- Compare with [src/maverick/actors/xoscar/implementer.py](src/maverick/actors/xoscar/implementer.py) which works correctly.

Investigation should add a DEBUG-level log right at the start of every ``prompt_session()`` exception branch and at the success branch entry, then re-run the same fly scenario — the missing path will become obvious.

### 3.9 Commit Provenance For Evals

**Status:** Active (surfaced in 2026-04-27 design discussion)

The CuratorAgent system prompt at [src/maverick/agents/curator.py](src/maverick/agents/curator.py) (lines 42-48) deliberately strips bead IDs and pipeline mechanics from commit messages so the public git history reads as human-authored. That is correct for the public history, but it severs the link between any landed commit and the bead that produced it — so there is no path from a landed commit back to the provider, model, prompt, or fix-loop history that created it. For eval work (§3.4), commit-level traceability is one of the two natural query axes (the other being bead-level via runway).

Pre-`land`, the data exists: [src/maverick/workflows/fly_beads/_commit.py](src/maverick/workflows/fly_beads/_commit.py) writes ``bead({id}): {title}`` as the per-bead commit subject. The curator's squash + describe pass then erases it by design.

**Proposal.** Two layers:

1. **Conventional `Refs:` trailer in landed commits.** Update the curator system prompt to keep stripping bead IDs from the *subject* but append a ``Refs: bd-NNN[, bd-MMM]`` trailer at the bottom of the message — plural because curator squash collapses many beads into one commit. This matches existing git trailer conventions (``Signed-off-by:``, ``Co-Authored-By:``) and reads as human-authored, satisfying the curator's "no pipeline output" rule. Cost: one prompt edit plus a regression test that asserts the trailer survives squash and reorder.

2. **Runway as system of record for full provenance.** Provider, model, prompt hash, response, fix-loop history, complexity tier — all keyed by bead ID. Some of this already lands via ``record_bead_outcome`` / ``record_review_findings``; what is missing is per-attempt ``(provider, model, prompt_hash)`` capture on the implementer and reviewer paths. With the trailer in place, any ``commit → bead → runway`` lookup works; without runway behind it, the trailer alone is just a foreign key pointing at nothing.

**Why now:**

- Cheapest possible step toward §3.4 — a stable join key from public history into runway, with no new infrastructure.
- Combines naturally with §3.6 (unified trace envelope) — ``Refs:`` is the trace-id projection into git.
- The curator change is additive (keep stripping subject IDs, also append a trailer), so regression risk is small.

**Out of scope for v1:**

- Embedding full prompts in the trailer. Too big; runway is the right home.
- jj-native metadata via the still-pending design in jj-vcs/jj #8166 / #6664. The trailer approach is git-tooling-agnostic and works today.
- Notes-based storage. Squash and rebase make ``refs/notes/*`` brittle, and jj has no ``jj notes`` command yet.

**Relevant code:**

- [src/maverick/agents/curator.py](src/maverick/agents/curator.py) (system prompt — the rule that strips bead IDs is the same rule that needs to append the trailer)
- [src/maverick/workflows/fly_beads/_commit.py](src/maverick/workflows/fly_beads/_commit.py) (existing ``bead({id}): {title}`` source)
- [src/maverick/runway/](src/maverick/runway/) (per-attempt ``(provider, model, prompt_hash)`` capture)

## 4. Developer Experience And Platform

### 4.1 Strengthen TDD As The Primary Feedback Loop

**Status:** Active

The repo already values tests highly, but the opportunity still stands because the prompt and artifact layers do not yet make the test target as explicit as they could.

The best next move is not ideological TDD messaging. It is tighter coupling between acceptance criteria, test specification fields, and the actual implementation loop.

Relevant code:

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [src/maverick/library/actions/decompose.py](src/maverick/library/actions/decompose.py)
- [src/maverick/workflows/refuel_maverick/models.py](src/maverick/workflows/refuel_maverick/models.py)

### 4.2 Reduce jj Installation Friction

**Status:** Active

There is still no true fallback path for environments that cannot or should not rely on jj.

The future shape of this work should be informed by the hidden workspace direction, not the older colocated-jj assumptions. The most promising version is likely:

- keep jj as the primary internal engine;
- bundle or manage it more transparently;
- only add a degraded fallback if the operational cost is justified.

### 4.3 Idempotent `maverick init`

**Status:** Partial

Some initialization subpaths are already safe to repeat, but the full command still fails fast when `maverick.yaml` exists unless `--force` is used.

Relevant code:

- [src/maverick/init/config_generator.py](src/maverick/init/config_generator.py)
- [src/maverick/cli/commands/init.py](src/maverick/cli/commands/init.py)
- [src/maverick/init/mcp_config.py](src/maverick/init/mcp_config.py)

### 4.4 `maverick land` Fails On `.beads/issues.jsonl` Merge Conflict

**Status:** Active (real bug, hit during 2026-04-27 Phase 3 live validation)

When a fly run ends with the workspace's `.beads/issues.jsonl` deleted
(bd's dolt backend regenerates it on demand) and the source repo has
modified the same file, `maverick land` blows up:

```
CONFLICT (modify/delete): .beads/issues.jsonl deleted in
maverick/sample-maverick-project and modified in HEAD.
```

Both `--no-curate` and `--finalize` modes hit it. There's no clean
recovery path inside the land command — users are reduced to manual
`git checkout FETCH_HEAD -- src tests pyproject.toml` and skipping
the merge entirely.

The root cause: `.beads/` is a dolt-managed working area, not source
the merge driver should be touching. Files inside it represent the
*current shared dolt state*, which is the same state on both branches
(since dolt writes back to the shared DB), so the diff is spurious.

Fixes to consider:

- **Add `.beads/` to a default `.gitattributes` merge=ours strategy**
  during `maverick init` so dolt-managed files always take the local
  version on merge.
- **Pre-merge filter in `maverick land`**: explicitly stash or reset
  any `.beads/`-only diffs in the workspace branch before invoking
  `git merge`.
- **Track the failure mode in preflight**: detect a known-bad merge
  state and emit a clear "this is a known land bug, here's the
  workaround" message rather than the raw git error.

Relevant code:

- [src/maverick/cli/commands/land.py](src/maverick/cli/commands/land.py)
- [src/maverick/library/actions/jj.py](src/maverick/library/actions/jj.py)
  (the merge invocation)
- [src/maverick/init/](src/maverick/init/) (where `.gitattributes` setup
  could go)

## 5. Reusable Workflow Building Blocks

### 5.1 Reusable Supervisor Fragments

**Status:** Active

This is another new opportunity that became obvious while comparing the supervisor implementations.

The major supervisors are intentionally different, but they repeat a recognizable set of shapes:

- specialist fan-out followed by synthesis;
- typed tool-intake and routing;
- validation or gate stages with fallback behavior;
- result aggregation and artifact writing.

Relevant code:

- [src/maverick/workflows/generate_flight_plan/supervisor.py](src/maverick/workflows/generate_flight_plan/supervisor.py)
- [src/maverick/actors/refuel_supervisor.py](src/maverick/actors/refuel_supervisor.py)
- [src/maverick/workflows/fly_beads/supervisor.py](src/maverick/workflows/fly_beads/supervisor.py)

This should stay small and compositional. The opportunity is not "add another framework." It is "extract the two or three orchestration fragments that already repeat."

## 6. Completed Or Mostly Addressed Items

These should not be treated as primary future work anymore.

### 6.1 Runway Seed Agent Fix

**Status:** Implemented

The current seed path is exercised by [tests/unit/runway/test_seed.py](tests/unit/runway/test_seed.py) and backed by [src/maverick/runway/seed.py](src/maverick/runway/seed.py). Keep regression coverage, but retire the old "seed is broken" framing.

### 6.2 Provider Quota Detection Tier 1

**Status:** Partial

The clean-failure baseline is in place. The remaining future work is:

- wait and resume after reset;
- automatic provider failover;
- maybe usage tracking that makes those decisions easier later.

Relevant code:

- [src/maverick/exceptions/quota.py](src/maverick/exceptions/quota.py)
- [src/maverick/actors/plan_supervisor.py](src/maverick/actors/plan_supervisor.py)
- [src/maverick/actors/refuel_supervisor.py](src/maverick/actors/refuel_supervisor.py)

### 6.3 Review Retry Caps

**Status:** Implemented, with follow-on tuning still possible

The old future item was too broad. The important distinction now is:

- the fly-beads supervisor has a hard review cap in [src/maverick/workflows/fly_beads/supervisor.py](src/maverick/workflows/fly_beads/supervisor.py);
- the library review-fix loop is bounded by `max_attempts` in [src/maverick/library/actions/review.py](src/maverick/library/actions/review.py).

The remaining work is observability and budget tuning, not adding a cap from scratch.

## 7. Recommended Next Moves

If Maverick only takes a few of these forward in the near term, the highest-leverage sequence looks like this:

1. **Shared mailbox actor scaffold** plus **tool calls through the owning actor**.
2. **Structured telemetry** plus a **unified trace and correlation envelope**.
3. **Step-level evals** for provider and prompt selection.
4. **Asynchronous human review queue** beyond the current review-bead model.
5. **Per-epic hidden workspace strategy** once the hidden workspace model is fully settled.

That sequence improves correctness, operability, and iteration speed before taking on the larger product-facing workflow expansions.