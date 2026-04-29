# Refuel Workflow — Open Issues

This document captures issues surfaced during a critical review of the refuel workflow (2026-04-20). Each issue has three sections:

- **Summary** — plain-language description of the problem, its implications, and the suggested fix at a high level. Readable without knowing the code.
- **Details** — technical depth with file paths, line numbers, and the exact failure mode. Intended as agent context.
- **Remediation** — concrete steps, code references, and test expectations. Intended as agent context.

Issues are grouped into three categories:

1. [Code issues](#code-issues) — real bugs, fragility, or violations of stated architectural rules.
2. [Documentation issues](#documentation-issues) — places where `docs/PATTERNS.md` misdescribes the actual refuel code.
3. [Missing documented patterns](#missing-documented-patterns) — real patterns present in refuel that `PATTERNS.md` does not yet capture.

---

## Code Issues

### Issue 1: Orphaned refuel supervisor and actors — ~1,013 lines of dead code

**Priority:** High · **Effort:** Small · **Status:** Completed

#### Summary

The refuel package ships a second, parallel implementation of the supervisor and actors that is not used by anything: `src/maverick/workflows/refuel_maverick/supervisor.py` plus the entire `src/maverick/workflows/refuel_maverick/actors/` directory. One of those files even has a broken import that would crash on load, and another uses a Thespian configuration that CLAUDE.md explicitly forbids. This is unfinished migration residue, and it is dangerous: a future contributor reading the refuel package for reference will find the wrong code and copy the wrong patterns.

The fix is to delete these files, confirm the test suite still passes, and update `docs/PATTERNS.md` so it no longer presents the workflow-scoped duplication as a live pattern for refuel.

#### Details

Four files are dead code:

| File | LOC |
|---|---:|
| `src/maverick/workflows/refuel_maverick/supervisor.py` (defines `RefuelSupervisor`) | 464 |
| `src/maverick/workflows/refuel_maverick/actors/decomposer.py` | 307 |
| `src/maverick/workflows/refuel_maverick/actors/validator.py` | 112 |
| `src/maverick/workflows/refuel_maverick/actors/bead_creator.py` | 130 |

Verification:

- `grep -rn 'from maverick.workflows.refuel_maverick.supervisor\|from maverick.workflows.refuel_maverick.actors' src/ tests/` returns zero matches.
- `src/maverick/workflows/refuel_maverick/supervisor.py:86` imports `from maverick.actors.inbox import InboxActor`. The module `maverick.actors.inbox` does not exist (`ls src/maverick/actors/` confirms — no `inbox.py`). The file cannot be imported without `ModuleNotFoundError`.
- `src/maverick/workflows/refuel_maverick/supervisor.py:88` uses `ActorSystem("multiprocTCPBase", transientUnique=True)`. CLAUDE.md:302-303 explicitly forbids `transientUnique=True` because child processes (the MCP server subprocess in `serve_inbox.py`) cannot discover a random-port Admin — they rely on a fixed Admin Port.

The real, live implementation lives at `src/maverick/actors/refuel_supervisor.py`, `src/maverick/actors/decomposer.py`, `src/maverick/actors/validator.py`, and `src/maverick/actors/bead_creator.py`. The workflow at `src/maverick/workflows/refuel_maverick/workflow.py:726-730` imports only those top-level actors; the workflow-scoped duplicates are never referenced.

Contrast with the fly_beads workflow: `src/maverick/workflows/fly_beads/actors/` is actively used inside that workflow package (`grep 'from maverick.workflows.fly_beads.actors' src/` confirms). The "workflow-scoped actors" pattern is real for fly_beads and generate_flight_plan, but for refuel it is purely incomplete migration residue.

`docs/PATTERNS.md` §2 "Variant worth knowing" and the Migration Notes section describe these workflow-scoped packages as "mirror[ing] the same mailbox contract for local composition, testing, and incremental refactors." This is true for fly_beads/generate_flight_plan but false for refuel.

#### Remediation

1. Delete the four files listed above.
2. Delete the now-empty `src/maverick/workflows/refuel_maverick/actors/` directory (and its `__init__.py`).
3. Run `make test` and `make lint`. If anything still references the deleted code, it would fail — but the grep confirms nothing should.
4. Update `docs/PATTERNS.md`:
   - Section 2 "Variant worth knowing": change the claim to explicitly name `fly_beads` and `generate_flight_plan` rather than implying all workflow packages have the variant.
   - Migration Notes bullet on Thespian-backed vs. workflow-scoped: narrow the claim the same way.
5. If the intent of the workflow-scoped package was ever to become the testable in-process variant for refuel (per the Migration Notes framing), that intent is abandoned. Document the abandonment in the commit message for whoever needs to reconstruct why it went away.

---

### Issue 2: Actor async bridge leaks coroutines on timeout

**Priority:** High · **Effort:** Small · **Status:** Resolved (superseded by xoscar migration)

**Post-migration note (2026-04):** the async bridge and the entire
Thespian runtime have been removed. xoscar actor methods are native
`async def`; timeouts wrap calls in `xo.wait_for(ref.method(...),
timeout=...)` which cancels the remote coroutine cleanly — the actor
method observes `asyncio.CancelledError` and can unwind resources.
The leaked-coroutine scenario is architecturally impossible under
xoscar.

#### Summary

When a decomposer actor's async work (an ACP prompt) takes longer than the bridge's 30-minute timeout, the bridge gives up waiting and reports an error — but the underlying task **keeps running** in the background. The next incoming message starts another task that shares the same ACP session and executor, so two tasks race on the same resources. This is exactly the wedged-socket scenario the supervisor's 35-minute watchdog is designed to catch, but the watchdog only papers over the leak on the supervisor side; on the actor side the leak accumulates across retries.

The fix is to cancel the task properly when the bridge times out, not just stop waiting for it.

#### Details

`src/maverick/actors/_bridge.py:94-103`:

```python
def _run_coro(self, coro: Coroutine[Any, Any, T], *, timeout: float) -> T:
    self._ensure_async_bridge()
    future = asyncio.run_coroutine_threadsafe(coro, self._loop)
    return future.result(timeout=timeout)
```

`concurrent.futures.Future.result(timeout=...)` only stops the caller from waiting; the underlying `asyncio.Task` on the bridge loop continues. Semantic chain when the timeout fires:

1. `future.result(timeout=1800)` raises `TimeoutError` in `receiveMessage`.
2. `DecomposerActor._run_async` (`src/maverick/actors/decomposer.py:147-176`) catches the exception, sends `prompt_error` to the supervisor, and returns.
3. The supervisor's `_handle_detail_error` (`src/maverick/actors/refuel_supervisor.py:1007`) requeues the unit and calls `_dispatch_pending_details`.
4. A new `detail_request` arrives at the same actor. `receiveMessage` fires `_run_coro` again, scheduling a second coroutine on the same bridge loop.
5. Both tasks now reference `self._executor` and `self._session_id`. If the first task was genuinely wedged on a dead ACP socket, it is still holding executor state; the second task may reuse the same session mid-handshake.

The supervisor-side `STALE_IN_FLIGHT_SECONDS = 2100.0` watchdog in `refuel_supervisor.py:55` addresses the *supervisor* staying stuck, not the *actor* leaking tasks. The comment at `refuel_supervisor.py:47-55` explicitly acknowledges the "Python task gets cancelled but the underlying socket read can keep blocking" case — but does nothing on the actor side to prevent task accumulation.

Consequence: over a long run that hits repeated stale-socket conditions, each hit leaves one extra coroutine alive per pool actor. Memory and FDs grow; a later successful prompt may interleave with a leaked one and produce nonsense responses.

#### Remediation

1. Update `_run_coro` in `src/maverick/actors/_bridge.py` to cancel the task on timeout:

```python
def _run_coro(self, coro: Coroutine[Any, Any, T], *, timeout: float) -> T:
    self._ensure_async_bridge()
    future = asyncio.run_coroutine_threadsafe(coro, self._loop)
    try:
        return future.result(timeout=timeout)
    except (TimeoutError, concurrent.futures.TimeoutError):
        future.cancel()
        # Give the loop a brief window to honor the cancellation.
        try:
            future.result(timeout=5.0)
        except (TimeoutError, concurrent.futures.TimeoutError, asyncio.CancelledError,
                concurrent.futures.CancelledError):
            logger.warning("actor_bridge.task_cancel_timeout")
        raise
```

2. Verify the ACP client's `prompt_session` honors cancellation. Grep `src/maverick/executor/acp_client.py` for `asyncio.CancelledError` and `CancelNotification` — the existing `timeout_seconds` path in `acp_client` should already send an ACP `CancelNotification`; confirm the cancellation path also sends it before exiting.
3. Add a unit test in `tests/unit/actors/test_bridge.py` that:
   - Schedules a coroutine that awaits an `asyncio.Event` that never fires.
   - Calls `_run_coro(..., timeout=0.5)`.
   - Asserts that `TimeoutError` is raised.
   - Asserts the coroutine receives `CancelledError` within a second (use a sentinel flag set in a `finally` block).
4. Optional follow-up: have `_run_coro` return the `Task` handle (not the `Future`) via `asyncio.run_coroutine_threadsafe` so callers could explicitly cancel earlier if needed. Not strictly necessary for the primary fix.

---

### Issue 3: Detail phase has no per-unit nudging — silent failures surface only after 35 minutes

**Priority:** High · **Effort:** Medium · **Status:** Completed

#### Summary

When an agent finishes a prompt without calling the expected MCP tool, the supervisor normally "nudges" it with a short follow-up prompt telling it which tool to call. The refuel supervisor deliberately disables this nudging for the detail phase, so a single pool actor that silently fails to call `submit_details` holds up the whole run until the 35-minute stale-unit watchdog fires. Users see a run that appears to be working but makes no progress for more than half an hour.

The fix is to re-enable per-pool-actor nudging (not nudging the primary decomposer, which was the bug that led to disabling it).

#### Details

`src/maverick/actors/refuel_supervisor.py:650-692`, `_handle_prompt_sent`:

```python
phase_tool_map = {
    "outline": ("submit_outline", lambda: self._outline is not None),
    # Don't nudge for detail — pool actors work independently.
    # Nudging the primary decomposer about another actor's missing
    # response causes it to re-submit the outline, cascading into
    # a full re-fan-out.
    "fix": ("submit_fix", lambda: self._fix_rounds > 0 and self._details is not None),
}

if phase not in phase_tool_map:
    return
```

The comment correctly describes the original bug: when nudging was naive, it always sent the nudge to `self._decomposer` (the primary), which shared a session that had `submit_outline` seeded at the top of its tool set. The agent would re-submit the outline instead of the missing detail, triggering a second fan-out. The current code avoids that by simply not nudging for detail.

But the supervisor *does* know which pool actor is handling which unit. In `_dispatch_pending_details` (`refuel_supervisor.py:630-648`):

```python
self._detail_dispatch_info[uid] = {
    "at": _time.monotonic(),
    "pool_idx": pool_idx,
}
self.send(target, {"type": "detail_request", "unit_id": uid})
```

And the decomposer echoes `unit_id` back on `prompt_sent` (`src/maverick/actors/decomposer.py:153-156`). So the supervisor can identify a specific pool actor that confirmed prompt_sent but produced no tool call. The only recovery path today is `STALE_IN_FLIGHT_SECONDS = 2100.0` (`refuel_supervisor.py:55`), roughly 35 minutes.

Concrete user-visible failure: at `t=60s`, pool actor 2 finishes a prompt, sends `prompt_sent`, but never calls `submit_details` (prompt returned without the tool call for whatever reason — agent drift, corrupted state, flaky provider). The user stares at a stalled progress line until `t≈2160s` when the watchdog requeues the unit.

This violates `docs/PATTERNS.md` §6 "Missing Tool Calls Trigger A Nudge Loop Instead Of Best-Guess Parsing" — the pattern applies to every agent return channel, but detail phase quietly opts out.

#### Remediation

1. Add detail to `phase_tool_map` with a predicate that knows whether the specific unit's tool call arrived:

```python
phase_tool_map = {
    "outline": ("submit_outline", None, lambda _uid: self._outline is not None),
    "detail": ("submit_details", "pool", lambda uid: uid not in self._pending_detail_ids),
    "fix":    ("submit_fix",     None, lambda _uid: not getattr(self, "_awaiting_fix", False)),
}
```

2. In `_handle_prompt_sent`, grab `unit_id` from the message (currently only extracted for detail — confirm by reading `DecomposerActor._run_async` which does pass it), look up the target:

```python
def _handle_prompt_sent(self, phase, unit_id=None, sender=None):
    entry = phase_tool_map.get(phase)
    if not entry:
        return
    tool_name, target_kind, check_fn = entry
    if check_fn(unit_id):
        return  # tool call already arrived

    if self._nudge_count.get(unit_id or phase, 0) >= MAX_NUDGES:
        return

    self._nudge_count[unit_id or phase] = self._nudge_count.get(unit_id or phase, 0) + 1

    # Pick nudge target: the sender for detail, primary for outline/fix.
    target = sender if target_kind == "pool" else self._decomposer
    self.send(target, {
        "type": "nudge",
        "expected_tool": tool_name,
        "unit_id": unit_id,
    })
```

3. Update `receiveMessage` to pass `sender` into `_handle_prompt_sent` (`refuel_supervisor.py:108-111`).
4. Change `_nudge_count` from a single counter to a dict keyed by `unit_id or phase`. Reset the relevant entry inside `_handle_tool_call` when the corresponding tool call arrives.
5. In `DecomposerActor._send_nudge` (`src/maverick/actors/decomposer.py:516-523`), accept a `unit_id` in the nudge prompt so the agent can re-call `submit_details` for a specific unit.
6. Once per-unit nudging is in place, reconsider `STALE_IN_FLIGHT_SECONDS` — 2100s was chosen because nudging could not save a pool actor. With nudging, a stale threshold closer to `1200s + 300s = 1500s` is defensible. But do not change the threshold in the same commit — nudging first, threshold second.
7. Add an integration test in `tests/unit/actors/` that:
   - Spins up a fake DecomposerActor that sends `prompt_sent` without a tool call for a specific unit.
   - Asserts the supervisor sends a `nudge` to that specific actor (not the primary) within one poll interval.
   - Asserts `submit_details` arriving after the nudge is accepted normally.

---

### Issue 4: Tool payload parse errors abort the entire workflow

**Priority:** Medium · **Effort:** Small · **Status:** Completed

#### Summary

When an agent submits an MCP tool call whose arguments pass the tool's JSON schema but fail the supervisor's Pydantic parsing, the supervisor marks the whole decomposition as failed and shuts down every agent. This contradicts a pattern the project explicitly states: "strict schema outside, tolerant typed intake just inside" (PATTERNS.md §3). The right behavior is to nudge the agent to resubmit or fail only the specific unit, not kill the whole run.

The fix is to route the error back to the agent as a retryable problem for the outline/fix/detail cases, and only escalate to a hard failure if retries are exhausted.

#### Details

`src/maverick/actors/refuel_supervisor.py:702-711`:

```python
def _handle_tool_call(self, message):
    tool = message.get("tool", "")
    args = message.get("arguments", {})
    try:
        payload = parse_supervisor_tool_payload(tool, args)
    except (SupervisorToolPayloadError, ValueError) as exc:
        self._handle_error({"phase": "tool", "error": str(exc)})
        return
    self._nudge_count = 0
    ...
```

`_handle_error` (`refuel_supervisor.py:1078-1114`) calls `_shutdown_all()` and `_mark_done({"success": False, ...})`. This is a terminal action: all agents get `{"type": "shutdown"}`, and the workflow's drain loop receives `done=True` with `success=False`.

Getting here requires:
1. The MCP gateway's json-schema validation passed (the gateway does this in `src/maverick/tools/agent_inbox/gateway.py`).
2. But `parse_supervisor_tool_payload` (`src/maverick/tools/agent_inbox/models.py`) raised because a Pydantic model's validators rejected some field — typically because the model is stricter than the json-schema (Pydantic validators enforce things like kebab-case IDs, non-empty `task`, etc. that can't be expressed in pure JSON Schema).

This is exactly the "prompt drift" case PATTERNS.md §3 talks about:

> The outer boundary stays strict for agents. The inner boundary stays resilient to prompt drift, legacy field names, and forward-compatible extensions.

The refuel supervisor does the opposite — inner boundary is strict *and* escalates to terminal failure. Compare with PATTERNS.md §6, which describes the correct recovery: nudge the agent. The machinery for that already exists in the supervisor (`_handle_prompt_sent` → `nudge` path).

Real failure modes this opens up:
- Agent returns a unit id like `my_unit_1` instead of `my-unit-1` → Pydantic kebab-case validator rejects → workflow dies mid-run.
- Agent returns an empty `task` field → validator rejects → workflow dies.
- Future field additions to the Pydantic model that aren't in the JSON schema → every in-flight run dies after the model change is deployed.

#### Remediation

1. Replace the hard-abort with a phase-aware nudge/retry path:

```python
def _handle_tool_call(self, message):
    tool = message.get("tool", "")
    args = message.get("arguments", {})
    try:
        payload = parse_supervisor_tool_payload(tool, args)
    except (SupervisorToolPayloadError, ValueError) as exc:
        self._handle_payload_parse_error(tool, exc)
        return
    self._nudge_count = 0
    ...

def _handle_payload_parse_error(self, tool, exc):
    phase_map = {
        "submit_outline": "outline",
        "submit_details": "detail",
        "submit_fix":     "fix",
    }
    phase = phase_map.get(tool)

    self._emit_output(
        "refuel",
        f"Tool {tool!r} payload rejected by validator: {exc}; requesting correction",
        level="warning",
        source=_SOURCE,
    )

    if phase in ("outline", "fix"):
        # Nudge primary with a corrective prompt.
        self.send(self._decomposer, {
            "type": "nudge",
            "expected_tool": tool,
            "reason": f"Previous payload failed validation: {exc}",
        })
        return

    if phase == "detail":
        # Can't selectively requeue without knowing unit_id from the
        # bad payload. Emit error but don't kill the run.
        self._emit_output(
            "refuel",
            "Detail payload validation failed; continuing with other units",
            level="error",
            source=_SOURCE,
        )
        return

    # Unknown tool — preserve current behavior.
    self._handle_error({"phase": "tool", "error": str(exc)})
```

2. Extend `DecomposerActor._send_nudge` (`src/maverick/actors/decomposer.py:516-523`) to accept an optional `reason` and include it in the nudge prompt so the agent knows what to fix:

```python
async def _send_nudge(self, message):
    tool_name = message.get("expected_tool", "submit_outline")
    reason = message.get("reason", "")
    prompt = (
        f"Your last response was not registered: did not call `{tool_name}`"
        + (f" (reason: {reason})" if reason else "")
        + f". Please call `{tool_name}` now with corrected results."
    )
    await self._prompt(prompt, f"decompose_nudge_{tool_name}")
```

3. Add a unit test for `_handle_tool_call` that feeds a malformed but JSON-schema-valid `submit_outline` payload and asserts:
   - No `WorkflowError` is raised.
   - A `nudge` message is sent to the decomposer.
   - `_done` remains False.

---

### Issue 5: Briefing cache never invalidates

**Priority:** Medium · **Effort:** Small · **Status:** Completed

#### Summary

Refuel caches the briefing phase output in `.maverick/plans/<name>/refuel-briefing.json`. Once the file exists it is reused on every subsequent refuel of that plan, forever. If the user edits the flight plan or the codebase changes significantly, the next refuel will decompose against stale briefing context and produce misaligned work units. There is no TTL, no hash check, no refresh flag.

The fix is to tag the cache with a content hash of the inputs it was derived from and invalidate when the hash drifts.

#### Details

`src/maverick/workflows/refuel_maverick/workflow.py:744-775`:

```python
plan_dir = Path.cwd() / ".maverick" / "plans" / flight_plan.name
briefing_cache_path = plan_dir / "refuel-briefing.json"
...
if not skip_briefing and briefing_cache_path.is_file():
    try:
        cached_briefing = _json.loads(briefing_cache_path.read_text(encoding="utf-8"))
        skip_briefing = True
        ...
```

The cache is read unconditionally if the file exists. There is no check of:
- Whether the flight plan content has changed since the cache was written.
- Whether the codebase (the context the briefing agents reasoned about) has changed.
- Whether the briefing prompt template version has changed.

The cache is written in `src/maverick/actors/refuel_supervisor.py:287-316`, `_cache_briefing_results`. It also skips writing if the file already exists:

```python
path = Path(cache_path)
if path.is_file():
    return  # already cached from a prior run
```

So even deliberate re-runs cannot overwrite the cache without manual `rm`.

Outline and per-unit detail caches have the same issue but the impact is smaller: outline is cheap to re-verify, and per-unit details are meant to survive `Ctrl-C` within a single logical run.

The briefing is particularly wrong to cache indefinitely because:
- Briefing inputs include the full flight plan content (likely to change between runs).
- Briefing inputs include the codebase context derived from `gather_context` (also likely to change).
- Briefing output is the most expensive agent phase and also the most prompt-version-sensitive.

#### Remediation

1. Compute a stable hash of all briefing inputs at cache read/write time:

```python
import hashlib

def _briefing_cache_key(flight_plan_content: str, codebase_context: Any,
                       briefing_prompt: str) -> str:
    h = hashlib.sha256()
    h.update(flight_plan_content.encode("utf-8"))
    h.update(b"\x00")
    h.update(_json.dumps(codebase_context, default=str, sort_keys=True).encode("utf-8"))
    h.update(b"\x00")
    h.update(briefing_prompt.encode("utf-8"))
    return h.hexdigest()[:16]
```

2. Store the key alongside the cached data:

```json
{
  "schema_version": 1,
  "cache_key": "abc123...",
  "payloads": { "navigator": {...}, "structuralist": {...}, ... }
}
```

3. On load, compare `cache_key` to the freshly computed key. If it differs, log `refuel.briefing_cache_invalidated` (reason="key_mismatch") and treat the cache as absent.
4. Remove the `if path.is_file(): return` guard in `_cache_briefing_results` so a resumed run with a different hash can overwrite.
5. Apply the same pattern to the outline cache (`.maverick/plans/<name>/refuel-outline.json`). The outline's hash inputs include the briefing payloads + the flight plan + the verification properties.
6. Leave per-unit detail caches alone — they are already scoped tightly enough; the keying above implicitly invalidates them by invalidating the outline they depend on (update `_fan_out_details` to clear `self._detail_cache_dir` if the outline cache missed for hash reasons; or gate detail cache reads on outline cache hit).
7. Add a `--refresh-cache` / `--no-cache` flag to `maverick refuel` for escape-hatch reruns without computing hashes.
8. Tests: `tests/unit/workflows/refuel_maverick/test_briefing_cache.py`:
   - Write a cache, re-run with identical inputs, assert `skip_briefing=True`.
   - Write a cache, mutate `flight_plan_content`, re-run, assert `skip_briefing=False`.
   - Write a cache with a missing `cache_key` field, assert graceful invalidation.

---

### Issue 6: Drain-loop timeout estimation can underbound legitimate runs

**Priority:** Medium · **Effort:** Small-to-Medium · **Status:** Completed

#### Summary

The workflow computes a hard timeout for the supervisor drain loop based on a guess of how many work units the decomposer will produce (1.5× the number of success criteria). If the guess is too low, the timeout fires and kills a healthy long run just because it is taking longer than a heuristic expected. Fix either by recomputing the timeout after the outline arrives (once actual unit count is known) or by simply raising the ceiling — since the supervisor's own watchdog catches real stalls, a generous cap has no downside.

#### Details

`src/maverick/workflows/refuel_maverick/workflow.py:972-987`:

```python
sc_count = len(flight_plan.success_criteria)
estimated_units = max(1, int(sc_count * 1.5))
detail_waves = max(
    1, (estimated_units + DECOMPOSER_POOL_SIZE - 1) // DECOMPOSER_POOL_SIZE
)
briefing_phases = 2 if not skip_briefing else 0
drain_timeout = 600.0 * (briefing_phases + 1 + detail_waves + MAX_DECOMPOSE_ATTEMPTS)
result = await self._drain_supervisor_events(
    asys=asys,
    supervisor=supervisor_addr,
    poll_interval=0.25,
    hard_timeout_seconds=drain_timeout,
)
```

Two distinct problems:

**(a) The 1.5× multiplier is empirically fragile.** Worked example: a plan with 20 SCs where the decomposer produces 60 units (3×, not unusual for compound SCs like "implement CLI and persistence and migrations"):
- Estimated: 20 × 1.5 = 30 units → (30 + 3) // 4 = 8 detail waves.
- Actual: 60 units → 15 detail waves.
- Budget: 600 × (2 + 1 + 8 + 3) = 8400s ≈ 2h20m.
- Reality: 600 × (2 + 1 + 15 + 3) ≈ 3h30m.
- Result: the drain loop raises `WorkflowError("supervisor drain exceeded 8400s timeout")` well before the supervisor's own watchdog fires.

**(b) `MAX_DECOMPOSE_ATTEMPTS` lives in one module, `MAX_FIX_ROUNDS` in another** — both equal 3 today but imported from:
- `src/maverick/workflows/refuel_maverick/constants.py` (`MAX_DECOMPOSE_ATTEMPTS`) — used by the workflow for timeout math.
- `src/maverick/actors/refuel_supervisor.py:38` (`MAX_FIX_ROUNDS`) — used by the supervisor for actual round counting.

If one is changed without the other, the timeout math silently desynchronizes from actual behavior. (This is also captured separately as Issue 8.)

The supervisor-side stale-in-flight watchdog (`refuel_supervisor.py:55`, 2100s per unit) already catches truly wedged runs. The drain-loop hard timeout is belt-and-braces, but it's a belt that can tighten on legitimate work.

#### Remediation

Pick one of two strategies.

**Option A — dynamic re-scaling (cleaner):**

1. Add a `rescale_timeout` mechanism to `_drain_supervisor_events` (in `src/maverick/workflows/base.py`), or add a new event type the supervisor can emit:

```python
class TimeoutRescale(ProgressEvent):
    additional_seconds: float
```

2. The refuel supervisor emits `TimeoutRescale` after the outline arrives, computing `(actual_unit_count - estimated_unit_count) / pool_size * 600` additional seconds.
3. `_drain_supervisor_events` treats this event by adjusting `deadline = time.monotonic() + hard_timeout_seconds + additional_seconds`.

**Option B — raise the ceiling (simplest):**

1. Change the formula to assume a worst-case fan-out ratio:

```python
estimated_units = max(10, sc_count * 4)  # 4× SC is a safer upper bound
```

2. Or ignore the estimate entirely and use a flat 6-hour cap:

```python
drain_timeout = 21_600.0  # 6 hours; supervisor watchdog catches real stalls
```

3. Add a comment explaining that the supervisor-side `STALE_IN_FLIGHT_SECONDS` watchdog is the actual stall detector; the drain timeout only exists to prevent runaway cost on truly dead supervisors.

Either option is acceptable. Option B is preferable unless you also want to tighten Option A simultaneously (they are not mutually exclusive but one-at-a-time is fine).

Also, fix the constant duplication separately (Issue 8).

Tests: add `tests/unit/workflows/refuel_maverick/test_drain_timeout.py` that constructs a flight plan with 20 SCs, a mocked supervisor that produces 60 units and slow detail phases, and asserts the drain does not raise `WorkflowError` for timing reasons. Skip the test with `@pytest.mark.slow` if it actually has to wait; otherwise mock `time.monotonic`.

---

### Issue 7: Session rotation semantics diverge from PATTERNS.md §4

**Priority:** Low · **Effort:** Small (documentation) · **Status:** Completed

#### Summary

The project's pattern doc says agent sessions live for one logical unit of work and preserve conversation context. The refuel decomposer actually rotates sessions *within* a phase after 5 detail turns, which drops context intentionally to avoid token bloat. This is a reasonable engineering choice, but a reader of PATTERNS.md would not predict it — the doc and the code tell different stories. Fix by documenting the bounded-session variant in PATTERNS.md §4.

#### Details

PATTERNS.md §4 "Sessions Persist For A Logical Unit Of Work":

> The repo consistently treats session reuse as a context-preservation mechanism, not as global memory. Sessions live for the current logical work item and are then discarded or replaced.

`src/maverick/actors/decomposer.py:258-312`, `_ensure_mode_session`:

```python
def _needs_new_mode_session(self, mode, *, max_turns, seed_stale):
    return (
        not getattr(self, "_session_id", None)
        or getattr(self, "_session_mode", None) != mode
        or self._session_turns_in_mode >= max(1, max_turns)
        or seed_stale
    )
```

And in `_send_detail_prompt` (`decomposer.py:391-457`), the `max_turns` is `self._detail_session_max_turns`, which init passes in from `DETAIL_SESSION_MAX_TURNS = 5` (`src/maverick/workflows/refuel_maverick/constants.py:20`). After 5 detail turns, the session rotates: the agent gets a fresh session with a re-seed of the outline/flight-plan/verification context.

This means a decomposition producing 20 detail units per pool actor rotates the session 4 times, dropping conversation context each time. The "logical unit of work" is not a phase — it's effectively a bounded window within a phase.

The design choice is defensible: without rotation, a single session accumulates prompts + responses for every unit in the phase (potentially 30+ turns × ~10KB per turn = 300+KB of history), which degrades agent quality and blows through provider context windows. But the doc claims behavior that doesn't match.

#### Remediation

This is a documentation-only fix. Update `docs/PATTERNS.md` §4:

1. Add a new paragraph after "Why it repeats":

   > **Bounded-session variant.** When a phase can produce many turns (e.g., refuel's detail phase with dozens of units per pool actor), sessions rotate after a configured turn cap. Rotation re-seeds the conversation with the large context payloads that would otherwise accumulate. This trades conversation continuity for bounded context window usage. See `decomposer.py:_ensure_mode_session` for the implementation; `DETAIL_SESSION_MAX_TURNS` / `FIX_SESSION_MAX_TURNS` set the caps.

2. Add `src/maverick/actors/decomposer.py` to the "Representative code" list for §4 (currently only cites fly_beads and top-level briefing).

No code change is required. If future work moves away from rotation (e.g., via agent context management features), update the pattern then.

---

### Issue 8: Duplicate fix-round constants in two modules

**Priority:** Low · **Effort:** Small · **Status:** Completed

#### Summary

The number of allowed fix rounds is defined in two places with two different names — `MAX_FIX_ROUNDS` in the supervisor and `MAX_DECOMPOSE_ATTEMPTS` in the workflow constants module. Both equal 3 today, but changing one without the other silently decouples the drain-loop timeout math from actual supervisor behavior.

#### Details

- `src/maverick/actors/refuel_supervisor.py:38`: `MAX_FIX_ROUNDS = 3` — the supervisor's actual round cap for validation/fix.
- `src/maverick/workflows/refuel_maverick/constants.py`: `MAX_DECOMPOSE_ATTEMPTS = 3` — imported by `workflows/refuel_maverick/workflow.py:981` for timeout estimation:

```python
drain_timeout = 600.0 * (briefing_phases + 1 + detail_waves + MAX_DECOMPOSE_ATTEMPTS)
```

These are the same concept. The duplication is probably a byproduct of the orphaned workflow-scoped supervisor (Issue 1), which also referenced `MAX_FIX_ROUNDS`.

#### Remediation

1. Delete `MAX_DECOMPOSE_ATTEMPTS` from `src/maverick/workflows/refuel_maverick/constants.py`.
2. In `workflows/refuel_maverick/workflow.py`, import the supervisor's constant directly:

```python
from maverick.actors.refuel_supervisor import MAX_FIX_ROUNDS
...
drain_timeout = 600.0 * (briefing_phases + 1 + detail_waves + MAX_FIX_ROUNDS)
```

3. Grep for any other consumers of `MAX_DECOMPOSE_ATTEMPTS` (likely only the dead code deleted in Issue 1).
4. Run `make test` — if anything else referenced the removed name, the failure is obvious.

---

### Issue 9: Inconsistent shutdown ordering between success and error paths

**Priority:** Low · **Effort:** Small · **Status:** Completed

#### Summary

On successful completion, the supervisor sends `{"type": "shutdown"}` to the decomposer actors but not to the briefing actors. On error, it sends shutdown to both. The inconsistency means briefing ACP subprocesses on the success path rely on `ActorExitRequest` (sent by `asys.shutdown()`) for cleanup, which is a slower and less deterministic teardown path. Normalize the success path to shut down both sets.

#### Details

`src/maverick/actors/refuel_supervisor.py:918-929`, `_handle_beads_created` (success path):

```python
def _handle_beads_created(self, message):
    ...
    # Shutdown all decomposer actors (primary + pool)
    for addr in [self._decomposer] + list(self._decomposer_pool):
        if addr:
            self.send(addr, {"type": "shutdown"})
    ...
```

`_shutdown_all` (`refuel_supervisor.py:1116-1123`, error path):

```python
def _shutdown_all(self):
    for addr in [self._decomposer] + list(self._decomposer_pool):
        if addr:
            self.send(addr, {"type": "shutdown"})
    for addr in self._briefing_actors.values():
        if addr:
            self.send(addr, {"type": "shutdown"})
```

Briefing actors are missing from the success-path shutdown. They still get cleaned up eventually, via `ActorExitRequest` in `_handle_actor_exit` (`src/maverick/actors/_bridge.py:122-139`), but:
- Explicit `"shutdown"` allows the actor to send `shutdown_ok` back and participate in a coordinated teardown.
- `ActorExitRequest` arrives only when `asys.shutdown()` is called in the workflow's `finally` block (`workflows/refuel_maverick/workflow.py:990`), which is after the drain loop exits. In between `_mark_done` and `asys.shutdown()`, briefing ACP subprocesses sit idle but alive.

#### Remediation

1. Replace the inline shutdown in `_handle_beads_created` with a call to `_shutdown_all`:

```python
def _handle_beads_created(self, message):
    ...
    self._shutdown_all()
    ...
```

2. Verify that `_shutdown_all` does not trigger duplicate work — the decomposer/briefing actors will receive one `"shutdown"` message (from `_shutdown_all`) followed eventually by `ActorExitRequest` (from `asys.shutdown()`). `_cleanup_executor` is idempotent (`_bridge.py:112-120` drops `self._executor = None` after first call), so the second teardown is a no-op.
3. No test change strictly required; if coverage exists for `_handle_beads_created`, ensure the assertion on emitted messages accounts for the additional briefing shutdowns.

---

### Issue 10: Fix-phase nudge predicate cannot detect missing submit_fix after the first fix round

**Priority:** Medium · **Effort:** Small · **Status:** Completed

#### Summary

The supervisor's "did the agent actually call `submit_fix` after we asked it to?" check has a logic bug: once the workflow has seen any detail results at all, the check is permanently true regardless of whether the *current* fix call arrived. So the nudge path for fix effectively never fires after the first fix round. Track an explicit awaiting-fix flag instead.

#### Details

`src/maverick/actors/refuel_supervisor.py:660`:

```python
"fix": ("submit_fix", lambda: self._fix_rounds > 0 and self._details is not None),
```

The predicate says "we've started at least one fix round AND we have some details." But `self._details` is set after the first detail phase completes (`refuel_supervisor.py:800-802`):

```python
self._details = SubmitDetailsPayload(details=tuple(self._accumulated_details))
```

and is never reset. So by the time the first fix request is sent, `self._details is not None` is already true, and `self._fix_rounds > 0` is also true (incremented in `_handle_validation` at line 875 just before sending the fix request).

As a result, `check_fn()` returns True on every `prompt_sent` after the first fix round — the nudge is never triggered, even if the agent completely skipped calling `submit_fix` for the current round.

In practice, the `submit_fix` tool call usually does arrive, so this bug is latent. But when an agent does skip it, the supervisor has no nudge path and relies on... nothing. The run hangs or `_handle_validation` is never re-entered for this round and the workflow stalls until the drain-loop hard timeout fires (Issue 6).

#### Remediation

1. Add an explicit flag tracking whether the supervisor is waiting for a fix:

```python
# In _init:
self._awaiting_fix = False

# In _handle_validation, just before sending fix_request:
self._awaiting_fix = True
self.send(self._decomposer, {"type": "fix_request", ...})

# In _handle_tool_call, for tool == "submit_fix" after successful parse:
self._awaiting_fix = False
```

2. Update the predicate:

```python
"fix": ("submit_fix", lambda: not self._awaiting_fix),
```

3. If Issue 3 is also being addressed, fold this into the unified predicate shape there (`lambda uid: not self._awaiting_fix`).
4. Test: construct a supervisor state where a fix request has been sent; feed it a `prompt_sent` with `phase="fix"`; assert a `nudge` is sent.

---

### Issue 11: `cwd` falls back to `Path.cwd()` instead of being required

**Priority:** Low · **Effort:** Small · **Status:** Completed

#### Summary

PATTERNS.md §7 claims that `cwd` and `allowed_tools` are first-class execution inputs threaded explicitly everywhere. In refuel, decomposer and briefing actors do accept `cwd` from init, but if it's missing they silently fall back to the process's current working directory. That fallback turns what the doc calls "explicit and narrow" execution context into ambient global state. Remove the fallback so missing `cwd` is an explicit error.

#### Details

`src/maverick/actors/decomposer.py:242`:

```python
cwd = Path(self._cwd) if self._cwd else Path.cwd()
```

`src/maverick/actors/briefing.py:139`:

```python
cwd = Path(self._cwd) if self._cwd else Path.cwd()
```

PATTERNS.md §7:

> Hidden workspaces only work if every step runs in the intended `cwd`.
> Least-privilege tool access only works if allowlists are forwarded deliberately.
> Failing to pass either usually leads to subtle misbehavior rather than obvious crashes.
> ...
> This pattern shows up often enough to treat it as a design rule: execution context should be explicit and narrow.

The fallback undermines the rule. The workflow currently does always pass `cwd` (workflow.py:903, 917), so the fallback is practically dead code — but it's a footgun for future callers who might forget.

#### Remediation

1. In `DecomposerActor.receiveMessage` init branch (`src/maverick/actors/decomposer.py:58-98`), require `cwd`:

```python
if msg_type == "init":
    cwd_in = message.get("cwd")
    if not cwd_in:
        raise ValueError("DecomposerActor init requires 'cwd'")
    self._cwd = cwd_in
    ...
```

2. Same change in `BriefingActor` (`src/maverick/actors/briefing.py:43-52`).
3. Remove the `else Path.cwd()` fallback in both `_create_session` paths.
4. Tests: if any existing test constructs these actors without `cwd`, fix the test to pass one. `tests/unit/actors/` is the likely location.
5. Optional: add a check in the workflow (`workflows/refuel_maverick/workflow.py`) that `Path.cwd()` is being passed intentionally — e.g., a comment explaining that refuel runs in the user's project root (unlike fly, which uses hidden workspaces).

---

### Issue 12: `receiveMessage` blocks for up to 30 minutes on prompt work

**Priority:** Low (document) / Medium (if fixed) · **Effort:** Medium-to-Large · **Status:** Resolved (superseded by xoscar migration)

**Post-migration note (2026-04):** `receiveMessage` is gone. xoscar
supervisors are async actors; children expose typed `async def`
methods and the supervisor awaits them concurrently via
`asyncio.gather` + `xo.wait_for`. Shutdown signals, nudges, and
control traffic are ordinary awaited coroutines — none block behind
an in-flight prompt. The architectural trade-off this issue
documented no longer exists.

#### Summary

The async bridge pattern holds the Thespian `receiveMessage` method open for the entire duration of an ACP prompt — up to 30 minutes per prompt. Thespian's own documentation explicitly warns against this, and Kevin Quick (Thespian's author) specifically recommends against bridging asyncio into Thespian actors with multiproc bases. During those 30 minutes, the actor cannot process shutdown messages, cannot be canceled cleanly on Ctrl-C, and cannot respond to any other control traffic. The practical symptom is orphaned ACP subprocesses after user interrupts.

This is a deliberate pragmatic choice and the main alternative (actor-per-prompt) is a major redesign. The minimum action is to document this as a known limitation; the larger action is to design a cancellation path.

#### Details

Sources on the Thespian side:
- Kevin Quick, Thespian Google Group ("running asyncio eventloop inside a thespian actor"): "the async eventloop/uvloop will not work correctly with the blocking calls to select()." Recommendation: actor-per-session, or `ThespianWatch` for I/O.
- Thespian `using.html` Actor Guidelines: "while the Actor is running in the `receiveMessage()` method it is not able to handle other messages ... will appear to be frozen."
- Thespian Gotchas: "Actors are not intended to create other processes or threads; attempts to do so may create undefined behavior."

The refuel code:
- `src/maverick/actors/_bridge.py:94-103`, `_run_coro(timeout=1800)` — blocks `receiveMessage` for up to 30 min.
- `src/maverick/actors/decomposer.py:151`, `_run_coro(coro, timeout=1800)` — every outline/detail/fix/nudge uses this path.
- `src/maverick/actors/briefing.py:65`, same.

Consequences:
- `asys.shutdown()` during active work: each decomposer's `ActorExitRequest` is queued behind the in-flight `receiveMessage`. Shutdown can take up to 30 minutes before the actor cleanly terminates its ACP subprocess.
- Ctrl-C from user: Python's signal handling interrupts the main thread, but the actor processes (forked subprocesses) are not directly signaled. The main process may exit while actors are still executing `receiveMessage`. The `atexit` handler in `src/maverick/actors/__init__.py:127-138` calls `asys.shutdown()`, but the shutdown itself takes time. Orphaned ACP subprocesses can survive the CLI exit.
- Supervisor tell → decomposer queue: if the supervisor sends a `nudge` while the decomposer is mid-prompt, the nudge waits until the current prompt finishes. Not wrong, but worth knowing.

CLAUDE.md:317-328 already discusses the async bridge pattern and its rationale. It does not explicitly discuss the 30-minute block implication.

#### Remediation

**Minimum action (document):**

1. Add a "Known Limitations" subsection to CLAUDE.md's "Async Bridge in Actor Processes" section stating:
   - `receiveMessage` blocks for the prompt duration (up to `timeout_seconds`).
   - `asys.shutdown()` during active prompts can take up to one prompt timeout to complete.
   - Ctrl-C may orphan ACP subprocesses if the atexit handler's shutdown does not complete before process exit.

2. Add the same warning to `docs/PATTERNS.md` §12 "External Systems Sit Behind Safe Wrappers" — extend it to note that the Thespian+asyncio bridge has bounded, but non-zero, blocking in `receiveMessage`.

**Larger action (fix — optional, expensive):**

Implement a cancellation path:

1. Add a `{"type": "cancel_current"}` message handler to `DecomposerActor` and `BriefingActor`. Its contract: "if a prompt is in flight, cancel it as soon as possible."
2. The handler calls `future.cancel()` on the current bridge future (requires storing the future on `self._current_future` during `_run_coro`).
3. The supervisor sends `cancel_current` on Ctrl-C, before `shutdown`, giving the ACP session a chance to honor cancellation via `CancelNotification`.
4. A signal handler at the workflow level catches SIGINT and triggers supervisor-level orderly shutdown before the atexit path fires.

The larger action is not recommended unless the user-visible orphan-subprocess symptoms become painful. The minimum action (documentation) is the conservative first step.

---

## Documentation Issues

### Issue 13: PATTERNS.md §2, §4, §7, §11, §12, and Migration Notes misrepresent refuel

**Priority:** Medium · **Effort:** Small (all documentation) · **Status:** Completed

#### Summary

Several sections of `docs/PATTERNS.md` cite refuel as an example of patterns that, on close inspection, either don't apply to refuel at all or apply differently than described. A new contributor reading PATTERNS.md and then reading the refuel code will be confused and may copy the wrong patterns. Tighten the doc so it only claims what the refuel code actually does.

#### Details

The specific misalignments:

**§2 "Two delivery variants."** Claims Thespian-backed top-level actors and file-backed workflow-scoped actors both exist, implying both are live. For refuel, the workflow-scoped variant is orphaned (see Issue 1). The section should name fly_beads and generate_flight_plan explicitly rather than implying universality.

**§4 "Sessions Persist For A Logical Unit Of Work."** Claims sessions live for one logical work item. Refuel's decomposer rotates sessions within a phase at `DETAIL_SESSION_MAX_TURNS = 5` (see Issue 7). The pattern needs a bounded-session variant note.

**§7 "cwd And allowed_tools Are First-Class Execution Inputs."** Claims execution context is explicit and narrow. Refuel actors fall back to `Path.cwd()` when `cwd` is not provided (see Issue 11). Either fix the code or soften the claim.

**§11 "Boundaries Prefer Protocol Over Inheritance."** Cites `workflows/fly_beads/actors/protocol.py` as the representative. Refuel's live actors inherit directly from `thespian.actors.Actor` with the `ActorAsyncBridge` mixin — no Protocol in sight. The only refuel code that uses a Protocol is the orphaned `workflows/refuel_maverick/supervisor.py` (see Issue 1). The pattern is narrower than presented.

**§12 "External Systems Sit Behind Safe Wrappers."** Cites "ACP connection pool" at `src/maverick/executor/_connection_pool.py`. Refuel does not use a connection pool; each decomposer and briefing actor creates its own ACP executor via `create_default_executor()`. Worth clarifying the scope.

**Migration Notes.** The bullet about "Thespian-backed actors in top-level actors ... workflow-scoped actors in workflow packages mirror the same mailbox contract for local composition, testing, and incremental refactors" overstates the refuel case, where the workflow-scoped actors are unused.

#### Remediation

1. **§2:** Change "Thespian-backed inbox delivery in top-level actors and file-backed inbox shims in workflow-scoped actors" to name the workflows explicitly: "Fly and plan workflows both provide a workflow-scoped actor package alongside the top-level Thespian implementation for local composition and testing." Drop the refuel implication.
2. **§4:** Add a "Bounded-session variant" subsection per Issue 7 above.
3. **§7:** Either note the `Path.cwd()` fallback as an escape hatch in some actors, or tie the section to Issue 11 with a "To do" marker.
4. **§11:** Add the caveat that Thespian actor classes inherit from Thespian's base `Actor` directly and mix in `ActorAsyncBridge`. Protocol is used for cross-module seams (e.g., `StepExecutor`, `VcsRepository`, workflow-scoped actor interfaces), not for Thespian actors.
5. **§12:** Change the connection-pool citation to a note that fly uses the pool (or the executor uses it internally, depending on actual use), while refuel and plan spawn per-actor ACP executors.
6. **Migration Notes:** Explicitly call out that refuel's workflow-scoped actors package is being removed (link to Issue 1) and that the pattern applies only to fly and plan.

---

## Missing Documented Patterns

### Issue 14: Three patterns present in refuel are not captured in PATTERNS.md

**Priority:** Low · **Effort:** Medium (documentation) · **Status:** Completed

#### Summary

The critical review surfaced three reusable patterns the refuel code exemplifies that are not yet in `docs/PATTERNS.md`. Adding them will make the patterns discoverable to contributors and reduce copy-paste reinvention. The three patterns are: (1) supervisor event-bus plus polled drain, (2) persistent-event-loop async bridge, and (3) file-based resume cache per logical phase.

#### Details

**Pattern A: Supervisor as event bus + polled drain.**

`src/maverick/actors/event_bus.py` implements `SupervisorEventBusMixin`. `src/maverick/workflows/base.py:464-569` implements `_drain_supervisor_events`. Together they let a workflow's async generator stream progress events out of a Thespian supervisor running in a separate OS process. Three workflows use this: fly, refuel, and generate_flight_plan (per `grep _drain_supervisor_events` results).

The pattern:
- Supervisor accumulates `ProgressEvent` instances into `self._events`.
- Supervisor handles `{"type": "get_events", "since": int}` by returning the slice after the cursor plus `done` + terminal `result`.
- Workflow polls at `poll_interval=0.25` seconds via `asys.ask(supervisor, ..., timeout=30)`.
- Workflow pushes drained events onto its own async event queue.
- Hard timeout guards against wedged supervisors.

This is not documented anywhere in PATTERNS.md today.

**Pattern B: Persistent event loop in a daemon thread as the async/Thespian bridge.**

`src/maverick/actors/_bridge.py` — `ActorAsyncBridge` mixin. Keeps one long-lived `asyncio.new_event_loop()` running on a daemon thread for the actor's lifetime. All async work goes to that loop via `asyncio.run_coroutine_threadsafe`. `asyncio.run()` is avoided because it tears down async generators on exit, which breaks ACP's stdio transport.

CLAUDE.md:317-328 mentions this pattern but PATTERNS.md does not. Given how load-bearing it is for every agent actor in the repo, it deserves its own section.

**Pattern C: File-based resume cache per logical phase.**

Refuel caches three phases: briefing (`.maverick/plans/<name>/refuel-briefing.json`), outline (`.../refuel-outline.json`), and per-unit details (`.../refuel-details/<unit_id>.json`). On restart, the workflow seeds supervisor state from these files and skips work already completed. See `src/maverick/workflows/refuel_maverick/workflow.py:744-819` for reads and `src/maverick/actors/refuel_supervisor.py:287-376` for writes.

Other workflows have similar needs (fly for bead-level state, plan for briefing). The pattern will recur; it deserves formalization, including the hashing strategy (Issue 5 addresses a gap in how refuel currently uses it).

#### Remediation

Add three new sections to `docs/PATTERNS.md`, after the existing section that best matches in topic. Rough structure:

```markdown
## NN. Supervisor Event Bus And Polled Drain

Description (3-5 sentences) of the pattern.

Why it repeats:
- Workflow async generator stays responsive while supervisor runs.
- Event stream is preserved across OS process boundaries via ask/reply.
- Polling is simple and idempotent; no backpressure complexity.

Representative code:
- [SupervisorEventBusMixin](../src/maverick/actors/event_bus.py)
- [_drain_supervisor_events](../src/maverick/workflows/base.py)
- [refuel supervisor event usage](../src/maverick/actors/refuel_supervisor.py)
- [drain loop tests](../tests/unit/workflows/test_drain_supervisor_events.py)

## NN+1. Persistent Event Loop Bridges Async Work Into Thespian Actors

... (same shape)

## NN+2. File-Based Resume Cache Per Logical Phase

... (same shape, with a note about hash-based invalidation — see Issue 5)
```

Placement suggestions:
- Pattern A: after §9 "Events Are The Source Of Truth" — it's a consumer of that pattern.
- Pattern B: as §12.5 near "External Systems Sit Behind Safe Wrappers" — same topic (boundary management).
- Pattern C: after §13 "Long-Running Work Leaves Recovery And Audit Artifacts" — same topic (durability).

No code changes required.

---

## Priority Summary

Triage suggestion for picking an order of work:

| Priority | Issues | Rationale |
|---|---|---|
| **High** | #1, #2, #3 | Dead code is a trap; bridge leak is a real resource leak; detail-nudge gap causes 35-minute user-visible stalls. |
| **Medium** | #4, #5, #6, #10, #13 | Workflow-killer behaviors on unusual inputs (#4), stale-cache trap (#5), timeout fragility (#6), fix-nudge logic gap (#10), documentation accuracy (#13). |
| **Low** | #7, #8, #9, #11, #12, #14 | Documentation-only (#7, #13, #14), polish (#8, #9, #11), or tracked-with-workaround (#12). |

Suggested sequencing:
1. Issue 1 first — removing dead code makes every subsequent review clearer.
2. Issue 2 next — low-effort, closes a real leak.
3. Issues 3 and 10 together — related nudge-path work.
4. Issue 4 after 3/10 — reuses the nudge machinery.
5. Issue 5 — standalone, satisfying.
6. Issue 6 — small, polishes drain stability.
7. Everything else as time permits.

---

## Appendix: Working Notes for Agents

Background material that didn't warrant its own issue but will save time while fixing the ones above.

### Natural groupings (do these together)

| Group | Issues | Why |
|---|---|---|
| **G0 — clear the board** | #1 | Do first. Removes dead code so later reads of the package are clear. No functional change. |
| **G1 — bridge correctness** | #2 | Standalone, touches only `_bridge.py` + a new test. Low-risk, high-value. |
| **G2 — nudge path** | #3 + #10 | Both touch `_handle_prompt_sent` and the nudge machinery. Doing them separately causes merge conflicts and double-thinking about the predicate shape. |
| **G3 — payload resilience** | #4 | Reuses the nudge plumbing from G2 — sequence after G2. |
| **G4 — cache resilience** | #5 | Isolated; only touches the cache read/write sites in `workflow.py` and `refuel_supervisor.py`. |
| **G5 — timeout math** | #6 + #8 | Both in `workflow.py` around the drain-timeout formula. Same edit window. |
| **G6 — polish** | #9, #11 | Tiny. Can ride along with any of the above. |
| **G7 — docs** | #7, #13, #14 | Bundle the PATTERNS.md updates into one PR at the end, after code changes settle. |
| **Defer or document-only** | #12 | Larger redesign; the minimum action is a doc note that can ride with G7. |

### Commands you will want

```bash
make test-fast                    # unit tests, no slow/integration. Use during iteration.
make test                         # full parallel run. Use before committing.
make lint                         # ruff (errors only).
make typecheck                    # mypy.
make check                        # lint + typecheck + test.
make VERBOSE=1 test-fast          # full output if something is mysterious.
```

Run a live refuel end-to-end:

```bash
# Assumes .maverick/plans/<name>/flight-plan.md exists.
maverick refuel <name>

# To test your changes end-to-end, create a tiny plan first:
maverick plan generate smoke --from-prd path/to/tiny-prd.md
maverick refuel smoke
```

Watch Thespian state during a run (separate terminal):

```bash
lsof -iTCP:19500 -sTCP:LISTEN              # is the admin daemon up?
ps -ef | grep -E 'maverick|claude-agent-acp' | grep -v grep   # actor subprocesses
```

Recover from a crashed run (stale admin on port 19500):

```bash
# cleanup_stale_admin runs automatically on create_actor_system,
# but for a manual nuke:
lsof -ti:19500 | xargs -r kill -9
```

### Test infrastructure landmines

- **`tests/unit/workflows/refuel_maverick/conftest.py:291`** mocks `_run_with_thespian` on the workflow. Most refuel unit tests never exercise the actual Thespian path. If you're verifying a Thespian-side fix (Issues #2, #3, #9, #10), you need either:
  - A test that constructs actors directly without spinning up a real ActorSystem (works for Issue #2 on `_bridge.py`), or
  - A new integration test with a real `ActorSystem("multiprocTCPBase", ...)` + shutdown in a fixture finalizer. Use a different Admin Port (e.g., 19501) so concurrent tests don't collide.
- **Parallel test runner (`-n auto` via xdist)** means multiple test workers can race for port 19500. Always use a unique port or `simpleSystemBase` in tests that spin up an ActorSystem.
- **`atexit` log suppression** in `src/maverick/actors/__init__.py:127-138` silences logs during shutdown. If you're debugging a shutdown-path issue, temporarily comment out the `root.setLevel(_logging.CRITICAL)` line — otherwise you won't see the failure.

### Shared mixin alert

`SupervisorEventBusMixin` (`src/maverick/actors/event_bus.py`) and `_drain_supervisor_events` (`src/maverick/workflows/base.py`) are shared by **fly, refuel, and plan** workflows. If a fix under Issue #3 or #10 requires a change to the mixin or the drain helper, check the other two supervisors:

- `src/maverick/actors/fly_supervisor.py`
- `src/maverick/actors/plan_supervisor.py`

Their `receiveMessage` dispatch and `_handle_prompt_sent` patterns look different from refuel's. Don't assume they share the refuel bug.

### Smaller observations worth knowing (not issues)

- **`asys.ask(..., timeout=10)` during init** (`workflow.py:870-945`): each actor has 10s to ack its init. Tight but not broken. If you hit flaky init on some machines, this is the suspect.
- **`one_shot_tools=["submit_outline"]`** for the primary decomposer (`decomposer.py:244`): the ACP executor is told to allow `submit_outline` exactly once. This is why the supervisor's old "nudge the primary" bug was so bad — the agent couldn't re-submit outline, but it would try anyway and disrupt the detail phase.
- **`DETAIL_SESSION_MAX_TURNS` / `FIX_SESSION_MAX_TURNS`** in `workflows/refuel_maverick/constants.py` are **live** (threaded through `workflow.py` → decomposer init). Only `MAX_DECOMPOSE_ATTEMPTS` is dead-duplicated with the supervisor's `MAX_FIX_ROUNDS` (see Issue #8). Don't delete the whole constants module.
- **`_cache_briefing_results` won't overwrite an existing cache** (`refuel_supervisor.py:297-298`). Same for `_cache_outline` (`:328-329`). Fine today, but any fix for Issue #5 needs to remove or rework this early-return.
- **`import time as _time` is everywhere inside methods** in `refuel_supervisor.py`. Stylistic, not broken — an artifact of a refactor that extracted methods without promoting the import. Fine to leave.
- **Nested dead-code scenarios**: `workflows/refuel_maverick/supervisor.py` (Issue #1) imports `from maverick.workflows.fly_beads.actors.protocol import Actor, Message, MessageType`. When you delete it, grep other importers of those symbols before worrying about unused protocol exports — `generate_flight_plan/actors/` uses them too.

### Verification bar per group

- **G0 (Issue #1):** `make test && make lint && make typecheck` all pass. No other assertion needed.
- **G1 (Issue #2):** new unit test in `tests/unit/actors/test_bridge.py` that constructs a bridge, schedules a hung coroutine, hits the timeout, asserts `CancelledError` observed in the coroutine within 1s.
- **G2 (Issues #3, #10):** new unit test that feeds a `prompt_sent` for detail without a submit_details, asserts the nudge goes to the specific pool actor (not primary). Second test for the fix predicate: feed prompt_sent while `_awaiting_fix=True`, assert nudge fires; feed after submit_fix arrived, assert no nudge.
- **G3 (Issue #4):** new test that sends a malformed-but-schema-valid `submit_outline` payload, asserts no `WorkflowError`, asserts nudge is emitted.
- **G4 (Issue #5):** new test for content-hash invalidation (write cache, mutate input, assert cache miss).
- **G5 (Issues #6, #8):** no new test required unless you hit the dynamic rescale path (Option A). For Option B, a comment change is enough.
- **G6 (Issues #9, #11):** existing tests should cover; update mocks if they previously skipped the `cwd` argument.

### Risky changes — think twice

- **Don't touch `cleanup_stale_admin` / Admin Port plumbing** without reading `src/maverick/cli/commands/serve_inbox.py` too. The MCP subprocess discovery depends on the Admin Port staying fixed; changing the port scheme breaks it silently.
- **Don't remove the async bridge.** It exists because ACP is async-only and Thespian is sync-only. Removing it means rearchitecting every agent actor.
- **Don't change `STALE_IN_FLIGHT_SECONDS` until Issue #3 is fixed.** The long stale threshold is a crutch for the missing nudge path. Tightening it before nudging exists causes spurious requeues on healthy runs.
- **Don't rename the top-level `src/maverick/actors/` package.** Thespian forks child processes that need to re-import actor classes by fully-qualified name.

### What this review did NOT cover

Out of scope — you're on your own here:

- The `curate` / `land` workflow.
- The briefing prompts themselves (content quality) — only orchestration.
- The MCP agent tool gateway implementation beyond the actor-side calls (`src/maverick/tools/agent_inbox/`).
- Performance / memory profiling under load.
- Cross-workflow regressions a mixin change might introduce in fly or plan.
