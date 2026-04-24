# Product Requirements Document: Migrate Actor System from Thespian to xoscar

**Document Version**: 1.0  
**Date**: 2026-04-21  
**Author**: Maverick Team  
**Status**: Draft  

---

## 1. Overview

### 1.1 Problem Statement

Maverick's actor-mailbox architecture relies on [Thespian](https://thespianpy.com/), a mature but synchronous-first actor framework. The fundamental mismatch between Thespian's synchronous `receiveMessage` and the async nature of ACP (`prompt_session`, executor cleanup) has created a growing body of workarounds:

1. **`ActorAsyncBridge` mixin** — every agent actor maintains a dedicated `threading.Thread` + `asyncio` event loop just to run async ACP work from inside `receiveMessage`. This is ~160 lines of non-trivial bridge plumbing (`src/maverick/actors/_bridge.py`) that must be understood, maintained, and composed correctly in every new actor.

2. **Blocked message queues during ACP prompts** — `receiveMessage` blocks for the entire duration of an ACP prompt (up to 30 minutes). Shutdown signals (`ActorExitRequest`), supervisor nudges, and watchdog wakeups all queue behind the in-flight prompt and cannot interrupt it. This is acknowledged as a trade-off, not a solved problem (see `CLAUDE.md` "Known Limitations" and `REFUEL_ISSUES.md` Issue 2).

3. **Stale admin daemon cleanup** — Thespian's `multiprocTCPBase` Admin daemon persists after the parent process exits (e.g., on Ctrl-C). Every workflow startup must detect whether port 19500 is occupied, gracefully or forcibly terminate the stale daemon, wait for the port to free, and only then create a new `ActorSystem`. This is 40+ lines of fragile OS-level plumbing (`src/maverick/actors/__init__.py:49-91`) that runs before any real work starts.

4. **Fixed admin port coupling** — All child subprocesses (particularly the `maverick serve-inbox` MCP server) must connect to the supervisor via a hardcoded port (`--admin-port 19500`). Running two Maverick workflows concurrently is impossible without port coordination.

5. **Dict-based messaging** — All inter-actor messages are untyped `dict[str, Any]` payloads (`{"type": "detail_request", "unit_id": ...}`). The supervisor's `receiveMessage` is a large `if/elif` chain on `message.get("type")`. There is no protocol-level type safety on the message surface.

6. **Poll-based event drain** — Because Thespian has no native async push for cross-process event delivery, the workflow side polls the supervisor every 0.25 seconds (`{"type": "get_events", "since": int}`). This is the `SupervisorEventBusMixin` + `_drain_supervisor_events` pattern. It works but adds 250 ms of visible latency to every status update and is conceptually backwards from how async Python is written.

7. **Queue depth tuning** — The Thespian TCP transport defaults (`MAX_PENDING_TRANSMITS=20`, `MAX_QUEUED_TRANSMITS=950`) are too low for Maverick's fan-out patterns. Startup must override these via environment variables before importing `thespian.actors`, or the refuel supervisor's 60-message detail fan-out floods the transmit queue and blocks inbound replies.

These accumulated workarounds cost development velocity, make the actor codebase harder to onboard, and place a ceiling on concurrency improvements. [xoscar](https://github.com/xorbitsai/xoscar) removes the root cause — the sync/async mismatch — by providing a fully async-native actor framework with built-in actor pools and typed RPC-style method calls.

### 1.2 Proposed Solution

Replace Thespian with **xoscar** as the actor runtime for all three supervisor workflows (fly, refuel, plan). xoscar provides:

- **Async-native actors** — `async def` methods on actor classes; no threading bridge required
- **RPC-style method dispatch** — call actor methods directly (`await actor_ref.process_bead(bead_id=...)`) instead of routing untyped dicts through `receiveMessage`
- **Built-in actor pools** — `xo.create_actor_pool()` manages process isolation and resource allocation
- **Clean lifecycle hooks** — `__post_create__` / `__pre_destroy__` for setup and teardown
- **No fixed admin port** — actor pools bind to ephemeral ports; no stale daemon, no port conflicts between parallel runs

In parallel with the runtime change, **move the three top-level Thespian supervisors to the structured async calling convention already used in `fly_beads/actors/`**. The workflow-scoped actor packages (`src/maverick/workflows/fly_beads/actors/`, `src/maverick/workflows/generate_flight_plan/actors/`) already use async `receive(message: Message) → list[Message]`. The top-level `src/maverick/actors/` Thespian actors do not. Unifying them on the same `Actor` protocol simplifies code navigation and enables shared supervisor fragments (see [FUTURE.md §2.4](../FUTURE.md)).

Finally, **update `docs/PATTERNS.md`** to replace patterns 9b (Persistent Event Loop Bridges) and the Thespian-specific variant in 9a (Supervisor Event Bus) with xoscar equivalents.

### 1.3 Design Philosophy

1. **Async-native everywhere** — The migration target is pure `asyncio`. No threading bridges, no `run_coroutine_threadsafe`, no persistent loops on daemon threads.

2. **RPC over mailbox for structured results** — Supervisors call actor methods directly and `await` typed results. The `Message`/`MessageType` contract is preserved as the typed method-call surface, but the dispatch becomes a direct `await` rather than an untyped dict delivered to `receiveMessage`.

3. **MCP tool calls remain the agent return channel** — The decision to use MCP tools for structured agent output is independent of the actor runtime. Agent actors still call `submit_implementation`, `submit_review`, etc. to deliver results. What changes is how the supervisor receives those results: instead of a Thespian `tell(supervisor, message)` from the MCP server subprocess, the server calls an async method on the supervisor actor via its xoscar reference.

4. **Preserve `fly_beads/actors/` as the canonical pattern** — The workflow-scoped actor packages already use the correct abstractions (async `receive`, typed `Message`, `Actor` protocol). The top-level Thespian actors are the legacy surface. Migration moves them up to the fly_beads pattern rather than inventing a new one.

5. **No big bang** — The three supervisor workflows (refuel, fly, plan) are independently deployable. Migration proceeds workflow by workflow, with the Thespian path kept in place until each xoscar path is validated under load.

---

## 2. Goals and Non-Goals

### 2.1 Goals

| ID | Goal |
|----|------|
| G-1 | Remove `ActorAsyncBridge` (`_bridge.py`) from all actor implementations |
| G-2 | Remove stale admin cleanup and fixed-port coupling from actor startup |
| G-3 | Replace untyped dict message routing with typed RPC method calls on all top-level supervisor actors |
| G-4 | Enable native async event push from supervisors to workflows (eliminate 0.25s poll loop) |
| G-5 | Allow multiple Maverick workflow sessions to run concurrently without port conflicts |
| G-6 | Preserve the MCP tool call pattern for structured agent return (no change to `supervisor_inbox/`) |
| G-7 | Preserve the `Actor` protocol and `Message`/`MessageType` contracts as the typed method-call surface |
| G-8 | Preserve ACP session-per-logical-unit-of-work semantics (sessions still scoped to bead / refuel / plan) |
| G-9 | Keep the overall supervisor-owns-routing policy unchanged |
| G-10 | Update `docs/PATTERNS.md` to replace Thespian-specific patterns with xoscar equivalents |
| G-11 | Eliminate `thespian` from `pyproject.toml` dependencies upon completion |

### 2.2 Non-Goals

| ID | Non-Goal | Rationale |
|----|----------|-----------|
| NG-1 | Rewrite agent prompts or change ACP executor | Out of scope; ACP layer is unchanged |
| NG-2 | Replace MCP tool calls for agent output | The MCP approach is correct and independent of actor runtime |
| NG-3 | Migrate the workflow-scoped `fly_beads/actors/` package | Already uses the correct async pattern; only the top-level actors change |
| NG-4 | Move to a distributed/multi-machine actor pool | All actors run on the same host; xoscar's local pool is sufficient |
| NG-5 | Add OpenTelemetry or structured telemetry | Tracked separately in FUTURE.md §3 |
| NG-6 | Change the `Message`/`MessageType` enum surface | Typed messages are the stable contract; the transport changes, not the protocol |
| NG-7 | Change fly_beads/supervisor.py or generate_flight_plan/supervisor.py | These workflow-scoped supervisors already run in-process; they do not use Thespian |

---

## 3. Background: Current Architecture

### 3.1 Thespian Actor Topology

```
Workflow (asyncio)
  │  asys.ask(supervisor, "start")     ← blocks caller for entire run
  │  loop: asys.ask(supervisor, {"type": "get_events", "since": N})   ← 0.25s poll
  │
  └─ [OS process: Thespian Admin (port 19500)]
       └─ [OS process: RefuelSupervisorActor]
            ├── self.createActor(DecomposerActor)  → [OS process]
            ├── self.createActor(ValidatorActor)   → [OS process]
            └── self.createActor(BeadCreatorActor) → [OS process]

  [separate subprocess: maverick serve-inbox --admin-port 19500]
       └── asys.createActor(RefuelSupervisorActor, globalName="supervisor-inbox")
           → delivers MCP tool calls via Thespian tell()
```

**Key pain points in this topology:**

- The Thespian Admin process on port 19500 survives Ctrl-C and must be force-killed on next startup.
- The MCP server subprocess must connect to the *same* fixed port to find the supervisor.
- Every DecomposerActor requires the `ActorAsyncBridge` mixin because `receiveMessage` is synchronous.
- The workflow cannot `await` completion; it polls in a tight loop.

### 3.2 Actor Implementations Affected

| File | LOC | Thespian-specific |
|------|----:|-------------------|
| `src/maverick/actors/__init__.py` | 141 | Yes — create_actor_system, stale cleanup |
| `src/maverick/actors/_bridge.py` | 158 | Yes — ActorAsyncBridge mixin |
| `src/maverick/actors/_step_config.py` | ~30 | Incidentally |
| `src/maverick/actors/event_bus.py` | 166 | Yes — SupervisorEventBusMixin (dict protocol) |
| `src/maverick/actors/refuel_supervisor.py` | ~1000 | Yes — inherits Actor, receiveMessage |
| `src/maverick/actors/decomposer.py` | ~400 | Yes — inherits Actor+Bridge, receiveMessage |
| `src/maverick/actors/validator.py` | ~100 | Yes — inherits Actor, receiveMessage |
| `src/maverick/actors/bead_creator.py` | ~100 | Yes — inherits Actor, receiveMessage |
| `src/maverick/actors/fly_supervisor.py` | ~500 | Yes — inherits Actor+Bridge, receiveMessage |
| `src/maverick/actors/implementer.py` | ~200 | Yes — inherits Actor+Bridge, receiveMessage |
| `src/maverick/actors/reviewer.py` | ~200 | Yes — inherits Actor+Bridge, receiveMessage |
| `src/maverick/actors/committer.py` | ~100 | Yes — inherits Actor, receiveMessage |
| `src/maverick/actors/gate.py` | ~100 | Yes — inherits Actor, receiveMessage |
| `src/maverick/actors/plan_supervisor.py` | ~260 | Yes — inherits Actor, receiveMessage |
| `src/maverick/actors/briefing.py` | ~300 | Yes — inherits Actor+Bridge, receiveMessage |
| `src/maverick/actors/generator.py` | ~200 | Yes — inherits Actor+Bridge, receiveMessage |
| `src/maverick/actors/plan_validator.py` | ~100 | Yes — inherits Actor, receiveMessage |
| `src/maverick/actors/plan_writer.py` | ~100 | Yes — inherits Actor, receiveMessage |
| `src/maverick/actors/spec_check.py` | ~100 | Yes — inherits Actor, receiveMessage |
| `src/maverick/actors/ac_check.py` | ~100 | Yes — inherits Actor, receiveMessage |
| `src/maverick/cli/commands/serve_inbox.py` | ~100 | Yes — ActorSystem for MCP delivery |
| `src/maverick/tools/supervisor_inbox/server.py` | ~130 | Yes — _thespian_system, _thespian_inbox |

---

## 4. Target Architecture

### 4.1 xoscar Actor Topology

```
Workflow (asyncio)
  │  pool = await xo.create_actor_pool(address="localhost:0")   ← ephemeral port
  │  supervisor_ref = await xo.create_actor(RefuelSupervisor, address=pool.external_address)
  │  async for event in supervisor_ref.run(inputs):             ← native async generator
  │      yield event
  │
  └─ [Actor Pool Process]
       ├── RefuelSupervisor
       │     ├── decomposer_ref = await xo.create_actor(DecomposerActor, ...)
       │     ├── validator_ref  = await xo.create_actor(ValidatorActor, ...)
       │     └── creator_ref    = await xo.create_actor(BeadCreatorActor, ...)
       └─ [all actors in pool; method calls are in-pool RPC]

  [MCP server subprocess]
       └── supervisor_addr passed at spawn time via env/arg
           → calls await supervisor_ref.on_tool_call(tool, args)
```

**Key improvements:**

- No fixed port; `address="localhost:0"` binds to an ephemeral port automatically.
- No stale daemon; the actor pool process is managed by the workflow and tears down cleanly on exception or cancellation.
- Agent actors are pure `async def` — no threading, no bridge.
- The workflow `await`s events via an async generator on the supervisor's method, eliminating polling.
- The MCP server receives the supervisor's address at spawn time and calls `supervisor_ref.on_tool_call(...)` directly.

### 4.2 Actor Interface Pattern

All migrated actors will be `xoscar.Actor` subclasses with typed `async def` method surfaces:

```python
import xoscar as xo

class DecomposerActor(xo.Actor):
    """Sends ACP prompts for decomposition phases."""

    async def __post_create__(self) -> None:
        self._executor: AcpStepExecutor | None = None
        self._session_id: str | None = None

    async def __pre_destroy__(self) -> None:
        if self._executor:
            await self._executor.cleanup()

    async def send_outline(self, request: OutlineRequest) -> None:
        """Send outline prompt; result delivered via MCP tool call."""
        await self._ensure_session()
        await self._executor.prompt_session(
            session_id=self._session_id,
            prompt=self._build_outline_prompt(request),
        )

    async def send_detail(self, request: DetailRequest) -> None:
        """Send detail prompt for one work unit."""
        ...
```

Key observations:
- `__post_create__` replaces `msg_type == "init"` handlers.
- `__pre_destroy__` replaces `msg_type == "shutdown"` + `_cleanup_executor` calls.
- Typed request/response dataclasses replace `dict[str, Any]` messages.
- No `receiveMessage`, no `self.send(...)`, no `ActorAsyncBridge`.

### 4.3 Supervisor Pattern

Supervisors become `xoscar.Actor` subclasses with an async `run()` generator and `on_tool_call()` receiver:

```python
import xoscar as xo
from collections.abc import AsyncGenerator
from maverick.events import ProgressEvent

class RefuelSupervisor(xo.Actor):
    """Orchestrates flight plan decomposition."""

    async def __post_create__(self) -> None:
        self._events: list[ProgressEvent] = []
        self._event_queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        self._decomposer_ref = await xo.create_actor(
            DecomposerActor,
            address=self.address,
        )

    async def run(self, inputs: dict[str, Any]) -> AsyncGenerator[ProgressEvent, None]:
        """Execute the refuel workflow, yielding progress events."""
        # Phase 1: outline
        await self._decomposer_ref.send_outline(OutlineRequest(...))
        # Events arrive via on_tool_call; yield them as they appear
        async for event in self._drain_events():
            yield event

    async def on_tool_call(self, tool: str, args: dict[str, Any]) -> str:
        """Receive structured output from the MCP server."""
        payload = parse_supervisor_tool_payload(tool, args)
        events = await self._route(tool, payload)
        for e in events:
            await self._event_queue.put(e)
        return "ok"

    async def _drain_events(self) -> AsyncGenerator[ProgressEvent, None]:
        while True:
            event = await self._event_queue.get()
            if event is None:
                return
            yield event
```

**Eliminated by this pattern:**
- `SupervisorEventBusMixin` and `get_events` polling
- `WakeupMessage` for progress heartbeats
- The entire `_drain_supervisor_events` helper in `src/maverick/workflows/base.py`

### 4.4 MCP Server Delivery

The `maverick serve-inbox` MCP server changes from Thespian messaging to async xoscar RPC:

```python
# Before (Thespian):
_thespian_system.tell(_thespian_inbox, {"tool": name, "arguments": args})

# After (xoscar):
supervisor_ref = await xo.actor_ref(supervisor_address, RefuelSupervisor)
result = await supervisor_ref.on_tool_call(name, args)
```

The supervisor address is passed to the MCP server process at spawn time (via `--supervisor-address` flag or environment variable), replacing the `--admin-port` / `globalName` discovery mechanism.

### 4.5 Fan-Out / Fan-In with Actor Pool

Refuel's detail pass currently fans out to a pool of `DecomposerActor` instances managed manually by the supervisor (round-robin dispatch, per-actor tracking dictionaries). xoscar's actor pool enables a cleaner pattern:

```python
# Create a pool of N decomposer actors
decomposers = [
    await xo.create_actor(DecomposerActor, uid=f"decomposer-{i}", address=pool_address)
    for i in range(pool_size)
]

# Fan out via asyncio.gather — native async concurrency
results = await asyncio.gather(*[
    decomposers[i % pool_size].send_detail(DetailRequest(unit_id=unit_id))
    for i, unit_id in enumerate(unit_ids)
])
```

This replaces the supervisor's per-actor `_in_flight` dict, round-robin counter, stale-unit watchdog timer, and all associated error-requeue logic.

---

## 5. ACP Integration Improvements

### 5.1 Remove the Async Bridge Entirely

The `ActorAsyncBridge` exists because Thespian's `receiveMessage` is synchronous. In xoscar actors, all methods are `async def`. The bridge, the daemon thread, the persistent event loop, and `asyncio.run_coroutine_threadsafe` all disappear. Each actor method simply `await`s its ACP calls directly:

```python
# Before (Thespian + bridge):
def receiveMessage(self, message, sender):
    if msg_type == "detail_request":
        self._run_async(
            self._send_detail_prompt(message),
            sender,
            "detail",
        )   # blocks receiveMessage for up to 1800s

# After (xoscar):
async def send_detail(self, request: DetailRequest) -> None:
    await self._send_detail_prompt(request)  # native async; supervisor awaits it
```

### 5.2 Cancellable ACP Prompts

In xoscar, an `async def` method is a normal coroutine. If the supervisor needs to cancel an in-flight ACP prompt (e.g., on timeout or quota exhaustion), it can do so via standard `asyncio.Task` cancellation:

```python
detail_task = asyncio.create_task(
    decomposer_ref.send_detail(request)
)
try:
    await asyncio.wait_for(detail_task, timeout=1800)
except asyncio.TimeoutError:
    detail_task.cancel()  # actually cancels the prompt_session coroutine
    await self._handle_detail_timeout(unit_id)
```

This closes **REFUEL_ISSUES Issue 2** (leaked coroutines on timeout) at the architectural level. The `future.cancel()` workaround in `_bridge.py:108-121` becomes unnecessary.

### 5.3 Responsive Shutdown

In Thespian, `asys.shutdown()` sends `ActorExitRequest` to each actor, but the message queues behind any in-flight `receiveMessage`. In xoscar, `xo.destroy_actor(ref)` cancels any running async method via standard asyncio cancellation. Shutdown completes in seconds rather than waiting for the current prompt to finish.

### 5.4 Session Lifecycle Simplification

The `_ensure_mode_session` rotation pattern (see `DecomposerActor._needs_new_mode_session`) tracks `_session_mode`, `_session_turns_in_mode`, stale flags, and max-turn caps in instance variables. In xoscar, this state lives as plain `self` attributes on an async actor — no dict-packed state snapshots required for the actor bridge. The logic itself is unchanged, but it is simpler to inspect and test.

### 5.5 Concurrent Fan-Out Removes Stale-Unit Watchdog

The refuel supervisor's `STALE_IN_FLIGHT_SECONDS = 2100.0` watchdog was added because the Thespian `WakeupMessage` was the only mechanism to detect a wedged pool actor. In xoscar, `asyncio.wait_for` on each `send_detail` task provides the same protection with cleaner cancellation semantics. The watchdog timer, `_dispatch_times`, and the force-requeue path in `_handle_wakeup` can be removed.

---

## 6. Migration Plan

The migration proceeds in four phases. Each phase is independently releasable.

### Phase 1: Infrastructure Swap (Refuel)

**Scope:** Migrate the refuel workflow's Thespian actors to xoscar. This is the highest-complexity workflow (pool actors, detail fan-out, fix loops) and the most mature Thespian implementation.

**Deliverables:**

1. Add `xoscar` to `pyproject.toml` dependencies; verify no xoscar security advisories.
2. Create `src/maverick/actors/xoscar_pool.py` — pool lifecycle helpers (replaces `src/maverick/actors/__init__.py`).
3. Migrate `DecomposerActor` → xoscar `Actor` with `async def send_outline`, `send_detail`, `send_fix`, `send_nudge`.
4. Migrate `ValidatorActor` → xoscar `Actor` with `async def validate`.
5. Migrate `BeadCreatorActor` → xoscar `Actor` with `async def create_beads`.
6. Migrate `RefuelSupervisorActor` → xoscar `Actor` with `async def run() → AsyncGenerator[ProgressEvent, None]` and `async def on_tool_call(tool, args) → str`.
7. Update `src/maverick/cli/commands/serve_inbox.py`: replace Thespian `tell()` with `await supervisor_ref.on_tool_call(tool, args)`.
8. Update `src/maverick/tools/supervisor_inbox/server.py`: remove `_thespian_system` / `_thespian_inbox`; add `_supervisor_ref`.
9. Update `src/maverick/workflows/refuel_maverick/workflow.py`: replace `_drain_supervisor_events` polling with `async for event in supervisor_ref.run(inputs)`.
10. Write unit tests for all migrated actors using xoscar's in-process test support.
11. Run `make ci` — verify all existing refuel tests pass.

**Completion criteria:** `maverick refuel` works end-to-end; Thespian is no longer used by the refuel path.

### Phase 2: Fly Workflow

**Scope:** Migrate the fly workflow's top-level Thespian actors to xoscar.

Note: The `fly_beads/actors/` package (ImplementerActor, ReviewerActor, etc.) already uses async `receive(message)` and does **not** use Thespian. Only the top-level `src/maverick/actors/fly_supervisor.py`, `implementer.py`, `reviewer.py`, `committer.py`, `gate.py`, `spec_check.py`, and `ac_check.py` are Thespian-backed.

**Deliverables:**

1. Migrate `FlySupervisorActor` → xoscar `Actor` with `async def run() → AsyncGenerator[ProgressEvent, None]` and `async def on_tool_call(tool, args)`.
2. Migrate `ImplementerActor` (top-level) → xoscar `Actor` with `async def send_implement`, `send_fix`.
3. Migrate `ReviewerActor` (top-level) → xoscar `Actor` with `async def send_review`.
4. Migrate deterministic actors (`CommitterActor`, `GateActor`, `SpecCheckActor`, `ACCheckActor`) → xoscar `Actor` with typed `async def` methods.
5. Update `src/maverick/workflows/fly_beads/workflow.py`: replace supervisor polling with `async for event in supervisor_ref.run(inputs)`.
6. Write unit tests for all migrated actors.
7. Run `make ci` — verify all existing fly tests pass.

**Completion criteria:** `maverick fly` works end-to-end; Thespian is no longer used by the fly path.

### Phase 3: Plan Workflow

**Scope:** Migrate the plan generation workflow's Thespian actors to xoscar.

**Deliverables:**

1. Migrate `PlanSupervisorActor` → xoscar `Actor` with `async def run()` and `async def on_tool_call(tool, args)`.
2. Migrate `BriefingActor` → xoscar `Actor` with `async def send_briefing`.
3. Migrate `GeneratorActor` → xoscar `Actor` with `async def send_generate`.
4. Migrate deterministic actors (`PlanValidatorActor`, `PlanWriterActor`) → xoscar `Actor`.
5. Update `src/maverick/workflows/generate_flight_plan/workflow.py`: replace polling with native async generator drain.
6. Write unit tests for all migrated actors.
7. Run `make ci` — verify all existing plan tests pass.

**Completion criteria:** `maverick plan generate` works end-to-end; Thespian is no longer used by the plan path.

### Phase 4: Cleanup

**Scope:** Remove all Thespian residue and update documentation.

**Deliverables:**

1. Delete `src/maverick/actors/_bridge.py` and all imports.
2. Delete `src/maverick/actors/__init__.py` stale-admin and port management code; replace with xoscar pool utilities if any remain.
3. Remove `thespian` from `pyproject.toml` dependencies.
4. Remove Thespian-specific ruff lint ignores (`N802` for `receiveMessage`, etc.) from `pyproject.toml`.
5. Update `docs/PATTERNS.md` — see §7.
6. Update `CLAUDE.md` — replace Thespian architecture sections with xoscar equivalents.
7. Update `docs/REFUEL_ISSUES.md` — mark Issues 2 and 12 as resolved/superseded.
8. Run `make ci` — full suite green.

**Completion criteria:** `thespian` appears nowhere in `src/` or `tests/`; CI is fully green.

---

## 7. Patterns.md Updates

The following sections of `docs/PATTERNS.md` require updates:

### Section 9a: Supervisor Event Bus → Async Generator on Supervisor Method

**Current description:** "Each multi-actor workflow runs its supervisor in a separate OS process via Thespian's `multiprocTCPBase`. Supervisors accumulate typed `ProgressEvent` objects and expose them through a `{"type": "get_events", "since": int}` message. The workflow-side async generator polls the supervisor at a fixed interval (typically 0.25s)."

**Replacement:** "Each multi-actor workflow creates an xoscar actor pool. The supervisor exposes a `run(inputs) → AsyncGenerator[ProgressEvent, None]` method. The workflow-side code consumes events via `async for event in supervisor_ref.run(inputs)`. There is no polling; events are pushed immediately as they are emitted. `SupervisorEventBusMixin` is replaced by an `asyncio.Queue` held on the supervisor actor instance."

### Section 9b: Persistent Event Loop Bridges → Removed

**Current description:** "Thespian's `receiveMessage` is synchronous; ACP's `prompt_session` and executor cleanup are async. The repo-wide solution is `ActorAsyncBridge`..."

**Replacement:** "xoscar actor methods are native `async def`. All ACP calls (`prompt_session`, `executor.cleanup`) are `await`ed directly. No threading bridge, no `asyncio.run_coroutine_threadsafe`, no persistent daemon thread is required. `ActorAsyncBridge` and `_bridge.py` are removed in the xoscar migration."

### Section 11: Boundaries Prefer Protocol Over Inheritance

**Current note:** "The top-level Thespian actors in `src/maverick/actors/` inherit directly from `thespian.actors.Actor` plus the `ActorAsyncBridge` mixin — Thespian requires concrete subclasses, so Protocol doesn't apply to that surface."

**Replacement:** "All actors, including supervisors, subclass `xoscar.Actor` (required by the framework). The `Actor` protocol defined in `src/maverick/workflows/fly_beads/actors/protocol.py` remains the canonical typed interface for all other cross-module seams."

### Migration Notes section

Remove the bullet: "Thespian-backed actors in top-level actors are the canonical runtime path for every workflow." Replace with: "xoscar-backed actors in `src/maverick/actors/` are the canonical runtime path for every workflow."

Update the description of the two actor variants: the workflow-scoped packages (`fly_beads/actors/`, `generate_flight_plan/actors/`) remain the in-process composition and testing layer; the top-level actors are the xoscar runtime layer. Refuel does not have a workflow-scoped variant.

### Practical Use section

Add item 8: "Use `await actor_ref.method(...)` for inter-actor RPC; do not pass untyped dicts as messages between actors."

---

## 8. Testing Strategy

### 8.1 Unit Tests

xoscar provides in-process actor test support — no TCP transport required. Each migrated actor module should have a corresponding test file under `tests/unit/actors/`:

```python
import pytest
import xoscar as xo

@pytest.fixture
async def actor_pool():
    pool = await xo.create_actor_pool(address="localhost:0", n_process=0)
    yield pool
    await pool.stop()

async def test_decomposer_sends_outline(actor_pool, mock_executor):
    ref = await xo.create_actor(DecomposerActor, address=actor_pool.external_address)
    await ref.set_executor(mock_executor)
    await ref.send_outline(OutlineRequest(flight_plan="..."))
    # assert mock_executor received the expected prompt
```

### 8.2 Integration Tests

End-to-end tests that exercise the full actor topology (supervisor + child actors + mock MCP server) should be added to `tests/integration/actors/`. These tests should use real xoscar actor pools with mock ACP executors to verify:
- Supervisor routing policy (fix loops, fan-out, fan-in)
- Event ordering and completeness
- Shutdown and cleanup under normal and error conditions
- Timeout cancellation for long-running actor methods

### 8.3 Regression Tests for Removed Workarounds

The following behaviors previously guaranteed by workarounds should have explicit regression tests post-migration:
- On `await pool.stop()`, all actor ACP subprocesses are terminated (not orphaned)
- On `asyncio.cancel()` of `supervisor_ref.run(...)`, the supervisor tears down all child actors
- Two concurrent `maverick refuel` runs do not conflict (bind to separate ephemeral ports)

---

## 9. Dependency and Security

### 9.1 Adding xoscar

```toml
# pyproject.toml
dependencies = [
    ...
    "xoscar>=0.6.0",   # minimum version with stable async actor pool API
]
```

Before merging any PR that adds `xoscar`, run `gh-advisory-database` to verify no open security advisories for the target version.

### 9.2 Removing thespian

Remove `"thespian>=4.0.1"` from `dependencies` in Phase 4. Verify no transitive dependents via `pip show thespian`.

---

## 10. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| xoscar's actor pool process model differs from Thespian's in ways that break ACP subprocess management | Medium | High | Prototype DecomposerActor migration in an isolated branch first; verify ACP subprocesses are properly reaped on `pool.stop()` |
| xoscar version instability (framework is less mature than Thespian) | Medium | Medium | Pin to a specific minor version; audit the xoscar changelog before upgrading |
| MCP server subprocess cannot discover supervisor address reliably | Low | High | Pass address via CLI flag at spawn time (`--supervisor-address host:port`); use env var as fallback |
| Fan-out concurrency via `asyncio.gather` overwhelms ACP provider rate limits | Low | Medium | Retain the existing `aiolimiter`-based rate limiting already in the ACP executor; apply it at supervisor fan-out level |
| Refuel briefing room parallelism (currently sequential in some paths) breaks under xoscar's concurrent model | Low | Low | Preserve sequential ordering where needed via `asyncio.Semaphore(1)`; add concurrency tests |
| Test infrastructure gap: existing Thespian tests cannot be reused | High | Low | Accept that actor tests are rewritten; the payoff (simpler, faster tests) justifies the work |

---

## 11. Open Questions

1. **xoscar process model** — Does xoscar's actor pool run each actor in a separate OS process (like Thespian's `multiprocTCPBase`) or in coroutines within a shared process? The default is coroutines within a pool process. For actors that spawn ACP subprocesses, this is acceptable — the ACP subprocess is the isolated unit, not the actor itself. Confirm no interference between multiple actors' ACP subprocesses sharing a pool process.

2. **Supervisor as actor vs. plain coroutine** — The supervisor could be a plain async function rather than an xoscar actor. The actor model is only necessary for `on_tool_call()` to be callable from the MCP server subprocess. If the MCP server runs in-process (sharing the same asyncio event loop), the supervisor could use a plain `asyncio.Queue` instead. Evaluate whether in-process MCP is feasible given ACP's session model.

3. **`serve-inbox` process lifecycle** — The current `maverick serve-inbox` command runs as a separate subprocess spawned by the ACP session. If the MCP server becomes in-process, the `serve_inbox` CLI command becomes unnecessary. This is a significant simplification but requires verifying that the MCP stdio server can run on the same event loop as the supervisor.

4. **Backwards compatibility for `--admin-port`** — The `serve_inbox` CLI command currently accepts `--admin-port` as the Thespian connection parameter. Post-migration, this becomes `--supervisor-address`. Any external tooling that calls `serve_inbox` directly will break. Assess whether this is a concern (likely not — it is an internal command).

5. **xoscar and hidden workspace isolation** — Each fly bead operates in a hidden workspace. If the xoscar actor pool runs actors in the same process, multiple concurrent beads share the same `cwd`. Confirm that ACP session `cwd` threading still isolates workspace access correctly — this is an existing requirement, not new.

---

## Appendix A: Thespian Pain Point Index

| Pain Point | Source | Phase Resolved |
|---|---|---|
| Stale admin daemon on port 19500 | `actors/__init__.py:49-91` | Phase 1 |
| `ActorAsyncBridge` threading workaround | `actors/_bridge.py` | Phase 1–3 |
| Fixed port coupling between supervisor and MCP server | `cli/commands/serve_inbox.py` | Phase 1 |
| Leaked coroutines on ACP timeout | `actors/_bridge.py:108-121` + REFUEL_ISSUES #2 | Phase 1 |
| 0.25s event poll loop | `actors/event_bus.py` + `workflows/base.py` | Phase 1–3 |
| Untyped dict message routing | all `receiveMessage` handlers | Phase 1–3 |
| TCP queue depth tuning via env vars | `actors/__init__.py:114-116` | Phase 1 |
| `WakeupMessage`-based watchdog | `actors/refuel_supervisor.py:55` | Phase 1 |
| Blocked shutdown (ActorExitRequest queues) | `CLAUDE.md` "Known Limitations" | Phase 1–3 |
| `globalName` actor discovery | `cli/commands/serve_inbox.py:73` | Phase 1–3 |
| `transientUnique=True` prohibition | CLAUDE.md, REFUEL_ISSUES #1 | Phase 1–3 |

---

## Appendix B: xoscar Reference

- **Repository**: https://github.com/xorbitsai/xoscar
- **PyPI**: https://pypi.org/project/xoscar/
- **Documentation**: https://xoscar.dev/en/latest/
- **Actor lifecycle**: `__post_create__` / `__pre_destroy__` hooks
- **Actor creation**: `await xo.create_actor(ActorClass, *args, address=pool.external_address, uid="optional-name")`
- **Actor reference**: `await xo.actor_ref(address, ActorClass)` or reuse the ref returned by `create_actor`
- **Method call**: `result = await actor_ref.method_name(arg1, arg2)`
- **Pool creation**: `pool = await xo.create_actor_pool(address="localhost:0", n_process=0)` — `n_process=0` means all actors run as coroutines in the pool's event loop (no forked processes); `n_process=N` creates N sub-pools in separate processes
- **Teardown**: `await xo.destroy_actor(ref)` or `await pool.stop()`
