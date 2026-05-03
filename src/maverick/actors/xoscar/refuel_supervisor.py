"""xoscar RefuelSupervisor — async-native refuel orchestrator.

Preserves the Thespian RefuelSupervisorActor's state-machine semantics —
briefing fan-out → outline → detail fan-out → validation → bead
creation (with fix loop) — while swapping the runtime to xoscar and
adopting the agent-owned-inbox design: MCP tool calls land on the
agent actors; the supervisor exposes a narrow typed domain surface
(``outline_ready``, ``detail_ready``, ``fix_ready``, briefing callbacks,
``prompt_error``, ``payload_parse_error``) that children invoke via
in-pool RPC.

Scope notes:

* On-disk caching (briefing / outline / per-unit detail) is preserved
  so a Ctrl-C'd run resumes mid-phase. The workflow seeds
  ``initial_payload`` with any cached JSON; the supervisor writes each
  artifact back to its cache path as soon as it arrives.
* Stale-in-flight watchdog is replaced with per-task ``xo.wait_for``
  timeouts plus a retry-capable fan-out; the separate 30s heartbeat
  task is intentionally not ported.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import xoscar as xo

from maverick.actors.xoscar.bead_creator import BeadCreatorActor
from maverick.actors.xoscar.briefing import BriefingActor
from maverick.actors.xoscar.decomposer import DecomposerActor
from maverick.actors.xoscar.fly_supervisor import (
    TIER_ORDER,
    FlySupervisor,
)
from maverick.actors.xoscar.messages import (
    BriefingRequest,
    CreateBeadsRequest,
    DecomposerContext,
    DetailRequest,
    FixRequest,
    NudgeRequest,
    OutlineRequest,
    PromptError,
    ValidateRequest,
    ValidationResult,
)
from maverick.actors.xoscar.validator import ValidatorActor
from maverick.events import (
    AgentCompleted,
    AgentStarted,
    ProgressEvent,
    StepCompleted,
    StepOutput,
    StepStarted,
)
from maverick.logging import get_logger
from maverick.payloads import (
    SubmitContrarianBriefPayload,
    SubmitDetailsPayload,
    SubmitFixPayload,
    SubmitNavigatorBriefPayload,
    SubmitOutlinePayload,
    SubmitReconBriefPayload,
    SubmitStructuralistBriefPayload,
    SupervisorInboxPayload,
    WorkUnitDetailPayload,
    dump_supervisor_payload,
)
from maverick.types import StepType

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

MAX_FIX_ROUNDS = 3
MAX_DETAIL_RETRIES = 1
STALE_IN_FLIGHT_SECONDS = 2100.0

_SOURCE = "refuel-supervisor"

REFUEL_BRIEFING_CONFIG: tuple[tuple[str, str, str], ...] = (
    ("navigator", "submit_navigator_brief", "navigator_brief_ready"),
    ("structuralist", "submit_structuralist_brief", "structuralist_brief_ready"),
    ("recon", "submit_recon_brief", "recon_brief_ready"),
    ("contrarian", "submit_contrarian_brief", "contrarian_brief_ready"),
)
PARALLEL_BRIEFING_NAMES: tuple[str, ...] = ("navigator", "structuralist", "recon")


class _DecomposerPool:
    """Demand-driven, LRU-evicting cache of per-tier DecomposerActors.

    The pool is empty at start. ``acquire(tier)``:

    1. **Reuse**: an idle actor of ``tier`` is in the cache → return it.
    2. **Spawn**: under the cap → create a fresh actor for ``tier``.
    3. **Evict + spawn**: at cap with idle actors of other tiers →
       destroy the LRU idle actor, create a fresh actor for ``tier``.
    4. **Wait**: at cap with no idle actors → block until ``release``.

    ``release(actor, tier)`` returns the actor to the idle cache and
    notifies any waiters. ``teardown()`` destroys every live actor.

    The pool reflects the workload it's seen — a 42-bead all-moderate
    epic ends up with up to ``cap`` moderate actors and zero of the
    other tiers. A subsequent complex bead evicts an idle moderate to
    spawn a complex actor on demand.

    The cap is a system-resource budget (subprocess slots, memory),
    not a classification axis. ``parallel.max_agents`` is the natural
    fit since SubprocessQuota uses the same number for hard subprocess
    capping; the actor-level cap here keeps the actor-object count
    aligned with that budget so we don't churn idle Python actors that
    SubprocessQuota would just keep killing the subprocess of.
    """

    def __init__(
        self,
        *,
        supervisor: Any,  # RefuelSupervisor; forward-declared
        cap: int,
        base_config: Any,
        decomposer_tiers: Any,  # DecomposerTiersConfig | None
        detail_session_max_turns: int,
        fix_session_max_turns: int,
    ) -> None:
        self._sup = supervisor
        self._cap = max(1, cap)
        self._base_config = base_config
        self._decomposer_tiers = decomposer_tiers
        self._detail_max_turns = detail_session_max_turns
        self._fix_max_turns = fix_session_max_turns
        # tier_name → list of idle actors (LIFO; tail is most recent)
        self._idle: dict[str, list[xo.ActorRef]] = {}
        # actor → tier_name (every live actor, idle or busy)
        self._actor_tier: dict[xo.ActorRef, str] = {}
        # idle actors in LRU order (oldest at index 0, newest at tail)
        self._lru: list[xo.ActorRef] = []
        # Awoken on every release / eviction so blocked acquirers retry.
        self._cond = asyncio.Condition()
        # Most recent broadcast context — applied to every freshly
        # spawned actor so it has the same outline/flight-plan view as
        # actors that already received it. None until first set_context.
        self._context: Any = None
        # Monotonic counter for unique actor uids.
        self._next_id = 0

    @property
    def total_live(self) -> int:
        """Total live actors across all tiers (busy + idle)."""
        return len(self._actor_tier)

    def tier_label(self, tier: str) -> str:
        """``provider/model`` label for ``tier`` (used in AgentStarted events)."""
        merged = self._merged_config_for(tier)
        return RefuelSupervisor._format_provider_label(merged)

    def _merged_config_for(self, tier: str) -> Any:
        if self._decomposer_tiers is None:
            return self._base_config
        override = getattr(self._decomposer_tiers, tier, None)
        if override is None:
            return self._base_config
        return FlySupervisor._merge_tier_config(base=self._base_config, override=override)

    async def set_context(self, context: Any) -> None:
        """Update the broadcast context. Applies to every existing actor
        AND every actor spawned later."""
        async with self._cond:
            self._context = context
            actors = list(self._actor_tier)
        # Set on each actor outside the lock to avoid serialising on it.
        if actors:
            await asyncio.gather(*[a.set_context(context) for a in actors])

    async def acquire(self, tier: str) -> xo.ActorRef:
        async with self._cond:
            while True:
                # 1. Reuse an idle actor of this tier.
                idle = self._idle.get(tier)
                if idle:
                    actor = idle.pop()
                    self._lru.remove(actor)
                    return actor
                # 2. Spawn fresh under the cap.
                if self.total_live < self._cap:
                    return await self._spawn(tier)
                # 3. Evict an LRU idle actor of any tier and spawn fresh.
                if self._lru:
                    victim = self._lru[0]
                    await self._evict(victim)
                    return await self._spawn(tier)
                # 4. At cap with everything busy — wait for a release.
                await self._cond.wait()

    async def release(self, actor: xo.ActorRef, tier: str) -> None:
        async with self._cond:
            self._idle.setdefault(tier, []).append(actor)
            self._lru.append(actor)
            self._cond.notify()

    async def teardown(self) -> None:
        async with self._cond:
            actors = list(self._actor_tier)
            self._idle.clear()
            self._lru.clear()
            self._actor_tier.clear()
        for a in actors:
            try:
                await xo.destroy_actor(a)
            except Exception as exc:  # noqa: BLE001
                logger.debug("decomposer_pool.teardown_destroy_failed", error=str(exc))

    async def _spawn(self, tier: str) -> xo.ActorRef:
        """Create + register a fresh actor for ``tier``. Caller holds cond."""
        config = self._merged_config_for(tier)
        self._next_id += 1
        sup_uid = self._sup.uid.decode()
        actor = await xo.create_actor(
            DecomposerActor,
            self._sup.ref(),
            cwd=self._sup._inputs.cwd,
            config=config,
            role="pool",
            detail_session_max_turns=self._detail_max_turns,
            fix_session_max_turns=self._fix_max_turns,
            address=self._sup.address,
            uid=f"{sup_uid}:dec-tier-{tier}-{self._next_id}",
        )
        self._actor_tier[actor] = tier
        # Seed broadcast context so the new actor's first send_detail
        # has the same outline as its peers.
        if self._context is not None:
            await actor.set_context(self._context)
        return actor

    async def _evict(self, victim: xo.ActorRef) -> None:
        """Destroy ``victim`` and remove it from all bookkeeping. Caller
        holds cond. ``xo.destroy_actor`` is awaited within the lock to
        ensure the slot count is consistent across acquirers."""
        victim_tier = self._actor_tier.pop(victim, None)
        if victim_tier is not None and victim in self._idle.get(victim_tier, []):
            self._idle[victim_tier].remove(victim)
        if victim in self._lru:
            self._lru.remove(victim)
        try:
            await xo.destroy_actor(victim)
        except Exception as exc:  # noqa: BLE001
            logger.debug("decomposer_pool.evict_destroy_failed", error=str(exc))

    def snapshot(self) -> dict[str, Any]:
        """Read-only view of pool state for tests / diagnostics.

        Empty tier entries are filtered out so the snapshot reflects
        the *current* set of cached / live tiers, not a history.
        """
        return {
            "cap": self._cap,
            "total": self.total_live,
            "idle_by_tier": {t: len(v) for t, v in self._idle.items() if v},
            "actors_by_tier": {
                t: sum(1 for at in self._actor_tier.values() if at == t)
                for t in set(self._actor_tier.values())
            },
        }


@dataclass(frozen=True)
class RefuelInputs:
    """Construction payload for ``RefuelSupervisor``.

    Mirrors the legacy init-dict fields so workflow callers port
    field-for-field. Optional fields default to safe no-ops.
    """

    cwd: str
    flight_plan: Any
    initial_payload: dict[str, Any] = field(default_factory=dict)
    config: Any = None
    decomposer_pool_size: int = 3
    skip_briefing: bool = False
    provider_labels: dict[str, str] = field(default_factory=dict)
    # Per-agent ACP StepConfig keyed by briefing agent_name (e.g.
    # "navigator", "structuralist", "recon", "contrarian"). Resolved via
    # ``actors.refuel.<agent_name>`` / legacy steps:/agents: surfaces.
    # Missing entries fall back to ``config`` (the decomposer's
    # StepConfig) so older callers remain compatible.
    briefing_configs: dict[str, Any] = field(default_factory=dict)
    detail_session_max_turns: int = 5
    fix_session_max_turns: int = 1
    # Cap on how many briefing agents may be in-flight concurrently.
    # Default 3 matches legacy behaviour (navigator/structuralist/recon all
    # run via asyncio.gather). Setting this lower (e.g. 1) makes them run
    # sequentially — useful on resource-constrained hosts.
    max_briefing_agents: int = 3
    # Per-unit complexity tier routing for detail generation
    # (FUTURE.md §2.10 Phase 3). When set, replaces the round-robin
    # ``decomposer_pool_size`` pool with one DecomposerActor per defined
    # tier; each unit's detail prompt routes to the worker matching the
    # unit's outline complexity. None = legacy round-robin pool.
    decomposer_tiers: Any = None  # DecomposerTiersConfig | None
    # Cache paths — when set, the supervisor writes briefing / outline /
    # per-unit detail JSON back so a resumed run short-circuits each
    # phase. Empty strings disable caching.
    briefing_cache_path: str = ""
    outline_cache_path: str = ""
    detail_cache_dir: str = ""
    briefing_cache_key: str = ""
    briefing_cache_schema_version: int = 1
    outline_cache_key_inputs: dict[str, str] = field(default_factory=dict)
    outline_cache_schema_version: int = 1


class RefuelSupervisor(xo.Actor):
    """Orchestrates flight-plan decomposition.

    Children (created in ``__post_create__``):

    * One ``DecomposerActor`` in ``primary`` role (owns all three
      decomposer MCP tools).
    * N ``DecomposerActor``s in ``pool`` role (one tool: submit_details).
    * One ``ValidatorActor`` (deterministic, typed RPC).
    * One ``BeadCreatorActor`` (deterministic, typed RPC).
    * Four ``BriefingActor``s — navigator, structuralist, recon,
      contrarian — unless ``skip_briefing`` is set.
    """

    def __init__(self, inputs: RefuelInputs) -> None:
        super().__init__()
        if not inputs.cwd:
            raise ValueError("RefuelSupervisor requires 'cwd'")
        self._inputs = inputs

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def __post_create__(self) -> None:  # noqa: C901 — long but flat
        self._event_queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        self._done = False
        self._terminal_result: dict[str, Any] | None = None
        self._driver_task: asyncio.Task[None] | None = None

        # Decomposition state
        self._outline: SubmitOutlinePayload | None = None
        self._details: SubmitDetailsPayload | None = None
        self._specs: list[Any] = []
        self._fix_rounds = 0
        self._accumulated_details: list[WorkUnitDetailPayload] = []
        self._pending_detail_ids: set[str] = set()
        self._detail_retries: dict[str, int] = {}
        # Per-unit dispatch tracking — drives the AgentStarted/AgentCompleted
        # events that surface "which model is working on which unit" in the
        # Rich Live decompose table. Populated in `_run_detail_fan_out`.
        self._unit_start_times: dict[str, float] = {}
        # Total unit count + abandoned set, set at the start of the detail
        # fan-out. Used for the X/Y progress denominator (so it stays
        # stable when units are abandoned) and for fail-the-step logic
        # (we can't ship a partial decomposition).
        self._detail_total_count: int = 0
        self._abandoned_unit_ids: set[str] = set()
        # Per-unit quota signal — populated by ``prompt_error`` when an
        # agent reports ``quota_exhausted=True`` during detail phase.
        # Keyed by unit_id, value is the upstream error string. Read by
        # ``_one`` to skip the remaining retry attempts (retrying against
        # an exhausted provider is wasted budget) and surfaced in the
        # abandon-step error so the user knows quota was the cause.
        self._detail_quota_errors: dict[str, str] = {}
        # Per-unit escalation state. ``_unit_escalation_levels[uid]`` is
        # the current escalation level (0 = base tier, 1 = one tier up,
        # etc.). ``_unit_current_display_name[uid]`` is the agent_name
        # used for AgentStarted/AgentCompleted events at the unit's
        # CURRENT tier attempt — same as ``uid`` initially, with a "↑"
        # suffix per escalation step (so the CLI shows each tier attempt
        # as its own row). ``detail_ready`` reads this map to emit the
        # success ✓ against the right row.
        self._unit_escalation_levels: dict[str, int] = {}
        self._unit_current_display_name: dict[str, str] = {}
        self._unit_escalated_count: int = 0

        # Briefing state
        self._briefing_results: dict[str, SupervisorInboxPayload] = {}
        self._briefing_expected: set[str] = set()
        self._briefing_start_times: dict[str, float] = {}
        self._awaiting_fix = False

        # Seed outline from cache if pre-populated by workflow.
        cached_outline = self._inputs.initial_payload.get("outline")
        if isinstance(cached_outline, dict):
            from maverick.payloads import (
                SupervisorToolPayloadError,
                parse_supervisor_tool_payload,
            )

            try:
                parsed = parse_supervisor_tool_payload("submit_outline", cached_outline)
                if isinstance(parsed, SubmitOutlinePayload):
                    self._outline = parsed
            except (SupervisorToolPayloadError, ValueError) as exc:
                logger.warning("refuel_supervisor.invalid_outline_cache", error=str(exc))

        self_ref = self.ref()

        # --- Decomposer primary ---
        self._decomposer = await xo.create_actor(
            DecomposerActor,
            self_ref,
            cwd=self._inputs.cwd,
            config=self._inputs.config,
            role="primary",
            detail_session_max_turns=self._inputs.detail_session_max_turns,
            fix_session_max_turns=self._inputs.fix_session_max_turns,
            address=self.address,
            uid=f"{self.uid.decode()}:decomposer-primary",
        )

        # --- Decomposer pool ---
        # Two layouts:
        #   * Legacy round-robin (default): N pool workers identified by
        #     index — see ``_decomposer_pool: list``.
        #   * Per-tier (Phase 3): one worker per defined tier under
        #     ``_decomposer_tiers``; the pool list stays empty so callers
        #     that ignore tier mode see no workers and gracefully fall
        #     back to the primary decomposer.
        self._decomposer_pool: list[xo.ActorRef] = []
        # Tier mode uses a demand-driven, LRU-evicting pool of decomposer
        # actors. The pool is empty at start; actors spawn on demand as
        # specific tiers are requested, and reuse / get evicted to make
        # room for tiers that aren't currently cached. Cap = budget for
        # decomposer subprocesses (currently ``parallel.max_agents``).
        # Legacy round-robin mode keeps the eager pre-spawn shape.
        self._decomposer_pool_dynamic: _DecomposerPool | None = None
        # Three branches:
        #   * decomposer_tiers is None → legacy round-robin with
        #     ``decomposer_pool_size`` workers.
        #   * decomposer_tiers is a DecomposerTiersConfig with at least
        #     one populated tier → demand-driven pool.
        #   * decomposer_tiers is a config with EVERY slot None → fall
        #     back to a single legacy worker (preserves the historical
        #     defensive default for "user wanted tiers but configured
        #     nothing").
        d_tiers_input = self._inputs.decomposer_tiers
        has_any_tier = d_tiers_input is not None and any(
            getattr(d_tiers_input, t, None) is not None for t in TIER_ORDER
        )
        if d_tiers_input is None:
            for i in range(self._inputs.decomposer_pool_size):
                pool_ref = await xo.create_actor(
                    DecomposerActor,
                    self_ref,
                    cwd=self._inputs.cwd,
                    config=self._inputs.config,
                    role="pool",
                    detail_session_max_turns=self._inputs.detail_session_max_turns,
                    fix_session_max_turns=self._inputs.fix_session_max_turns,
                    address=self.address,
                    uid=f"{self.uid.decode()}:decomposer-pool-{i}",
                )
                self._decomposer_pool.append(pool_ref)
        elif not has_any_tier:
            self._decomposer_pool.append(
                await xo.create_actor(
                    DecomposerActor,
                    self_ref,
                    cwd=self._inputs.cwd,
                    config=self._inputs.config,
                    role="pool",
                    detail_session_max_turns=self._inputs.detail_session_max_turns,
                    fix_session_max_turns=self._inputs.fix_session_max_turns,
                    address=self.address,
                    uid=f"{self.uid.decode()}:decomposer-pool-0",
                )
            )
        else:
            # Demand pool — cap from ``decomposer_pool_size`` (interpreted
            # as the *total* concurrency budget for tier mode). The pool
            # starts empty; first acquire(tier) spawns the first actor.
            self._decomposer_pool_dynamic = _DecomposerPool(
                supervisor=self,
                cap=max(1, self._inputs.decomposer_pool_size),
                base_config=self._inputs.config,
                decomposer_tiers=self._inputs.decomposer_tiers,
                detail_session_max_turns=self._inputs.detail_session_max_turns,
                fix_session_max_turns=self._inputs.fix_session_max_turns,
            )

        # Round-robin / single-actor fallback label — used for the
        # legacy non-tier path. Tier mode's per-tier labels come from
        # ``self._decomposer_pool_dynamic.tier_label(tier_name)``.
        self._default_decomposer_label: str = self._format_provider_label(self._inputs.config)

        # --- Validator + BeadCreator ---
        self._validator = await xo.create_actor(
            ValidatorActor,
            self._inputs.flight_plan,
            address=self.address,
            uid=f"{self.uid.decode()}:validator",
        )
        plan_name = getattr(self._inputs.flight_plan, "name", "") or ""
        plan_objective = getattr(self._inputs.flight_plan, "objective", "") or ""
        self._bead_creator = await xo.create_actor(
            BeadCreatorActor,
            plan_name=plan_name,
            plan_objective=plan_objective,
            cwd=self._inputs.cwd,
            address=self.address,
            uid=f"{self.uid.decode()}:bead-creator",
        )

        # --- Briefing actors ---
        # Per-agent StepConfig from ``inputs.briefing_configs`` lets each
        # briefing actor run on its own provider/model. Missing entries
        # fall back to ``inputs.config`` (the decomposer's config).
        self._briefing_actors: dict[str, xo.ActorRef] = {}
        if not self._inputs.skip_briefing:
            for name, tool, method in REFUEL_BRIEFING_CONFIG:
                actor_config = self._inputs.briefing_configs.get(name, self._inputs.config)
                self._briefing_actors[name] = await xo.create_actor(
                    BriefingActor,
                    self_ref,
                    agent_name=name,
                    mcp_tool=tool,
                    forward_method=method,
                    cwd=self._inputs.cwd,
                    config=actor_config,
                    address=self.address,
                    uid=f"{self.uid.decode()}:briefing-{name}",
                )

    async def __pre_destroy__(self) -> None:
        """Destroy all children so their __pre_destroy__ hooks run."""
        # Demand pool owns its own actors — tear it down first so its
        # actors get properly destroyed (it also clears state).
        if self._decomposer_pool_dynamic is not None:
            await self._decomposer_pool_dynamic.teardown()
        refs: list[xo.ActorRef] = [
            self._decomposer,
            *self._decomposer_pool,
            self._validator,
            self._bead_creator,
            *self._briefing_actors.values(),
        ]
        for ref in refs:
            try:
                await xo.destroy_actor(ref)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "refuel_supervisor.destroy_child_failed",
                    uid=getattr(ref, "uid", "?"),
                    error=str(exc),
                )

    # ------------------------------------------------------------------
    # Workflow entry point
    # ------------------------------------------------------------------

    @xo.generator
    async def run(self) -> AsyncGenerator[ProgressEvent, None]:
        """Drive the state machine, yielding progress events."""
        self._driver_task = asyncio.create_task(self._drive())
        try:
            while True:
                evt = await self._event_queue.get()
                if evt is None:
                    break
                yield evt
        finally:
            if self._driver_task and not self._driver_task.done():
                self._driver_task.cancel()
                try:
                    await self._driver_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

    async def _drive(self) -> None:
        """Run the state machine. Catches its own errors and marks done."""
        try:
            if self._briefing_actors and not self._inputs.skip_briefing:
                await self._run_briefing_phase()
            await self._run_decompose_phase()
        except Exception as exc:  # noqa: BLE001 — terminal failure
            logger.exception("refuel_supervisor.drive_failed", error=str(exc))
            await self._emit_output(
                "refuel",
                f"Decomposition failed: {exc}",
                level="error",
            )
            self._mark_done(
                {
                    "success": False,
                    "error": str(exc),
                    "specs": self._specs,
                    "fix_rounds": self._fix_rounds,
                }
            )

    # ------------------------------------------------------------------
    # Briefing phase
    # ------------------------------------------------------------------

    async def _run_briefing_phase(self) -> None:
        import time as _time

        prompt = self._inputs.initial_payload.get("briefing_prompt", "")
        await self._emit_phase_started("briefing", "Briefing")

        for name in PARALLEL_BRIEFING_NAMES:
            if name not in self._briefing_actors:
                continue
            label = name.replace("_", " ").title()
            await self._emit_agent_started(
                "briefing", label, self._inputs.provider_labels.get(label, "")
            )
            self._briefing_start_times[name] = _time.monotonic()
            self._briefing_expected.add(name)

        briefing_start = _time.monotonic()

        # Cap concurrent briefings at parallel.max_briefing_agents (default 3
        # = legacy fan-out). Each briefing is its own claude-agent-acp
        # subprocess, so this is the lever for resource-constrained hosts.
        sem = asyncio.Semaphore(max(1, self._inputs.max_briefing_agents))

        async def _bounded_send(name: str) -> None:
            async with sem:
                await self._briefing_actors[name].send_briefing(
                    BriefingRequest(agent_name=name, prompt=prompt)
                )

        await asyncio.gather(
            *[
                _bounded_send(name)
                for name in PARALLEL_BRIEFING_NAMES
                if name in self._briefing_actors
            ]
        )

        # Each BriefingActor self-nudges if its agent finishes without
        # calling its tool, then routes a prompt_error if the nudge also
        # fails. So when we get here, either every expected briefing
        # delivered its payload, or self._done was already flipped via
        # prompt_error → _mark_done. Bail in the latter case so the driver
        # surfaces the recorded failure.
        if self._done:
            return
        missing = self._briefing_expected - set(self._briefing_results.keys())
        if missing:
            # Defensive guard against an actor contract regression — should
            # not be reachable in normal operation.
            raise RuntimeError(
                f"Briefing actor returned without delivering and without "
                f"reporting a prompt_error — actor contract violation: "
                f"{sorted(missing)}"
            )

        if "contrarian" in self._briefing_actors:
            await self._run_contrarian_phase()
            if self._done:
                return

        elapsed_ms = int((_time.monotonic() - briefing_start) * 1000)
        await self._emit_phase_completed("briefing", "Briefing", elapsed_ms)

        self._inputs.initial_payload["briefing"] = {
            agent_name: dump_supervisor_payload(payload)
            for agent_name, payload in self._briefing_results.items()
        }
        # Persist briefing so a Ctrl-C during decomposition doesn't
        # force the expensive briefing pass to repeat.
        self._cache_briefing_results()

    async def _run_contrarian_phase(self) -> None:
        import time as _time

        from maverick.agents.briefing.prompts import build_contrarian_prompt

        raw_content = self._inputs.initial_payload.get("flight_plan_content", "")
        contrarian_prompt = build_contrarian_prompt(
            raw_content,
            self._briefing_payload("navigator"),
            self._briefing_payload("structuralist"),
            self._briefing_payload("recon"),
        )

        label = "Contrarian"
        await self._emit_agent_started(
            "briefing", label, self._inputs.provider_labels.get(label, "")
        )
        self._briefing_start_times["contrarian"] = _time.monotonic()
        self._briefing_expected.add("contrarian")

        await self._briefing_actors["contrarian"].send_briefing(
            BriefingRequest(agent_name="contrarian", prompt=contrarian_prompt)
        )

        if "contrarian" not in self._briefing_results and not self._done:
            raise RuntimeError(
                "Contrarian briefing returned without delivering and "
                "without reporting a prompt_error — actor contract violation"
            )

    # ------------------------------------------------------------------
    # Decomposition phase
    # ------------------------------------------------------------------

    async def _run_decompose_phase(self) -> None:
        import time as _time

        await self._emit_phase_started("decompose", "Decomposing")
        decompose_start = _time.monotonic()

        # Outline. The actor self-nudges if the agent skips the tool call;
        # send_outline only returns once submit_outline has been delivered
        # to outline_ready (or routes a prompt_error to mark the workflow
        # done, in which case _check_done_or_quota_error below trips). The
        # ``self._outline is None`` assertion is a defensive guard against
        # a contract regression in the actor.
        if self._outline is None:
            await self._emit_output("refuel", "Requesting outline from decomposer")
            await self._decomposer.send_outline(
                OutlineRequest(
                    flight_plan_content=self._inputs.initial_payload.get(
                        "flight_plan_content", ""
                    ),
                    codebase_context=self._inputs.initial_payload.get("codebase_context"),
                    briefing=self._inputs.initial_payload.get("briefing"),
                    runway_context=self._inputs.initial_payload.get("runway_context"),
                )
            )
            if self._outline is None:
                if self._done:
                    # Normal failure path: decomposer already routed a
                    # prompt_error (via the actor's self-nudge exhaustion or
                    # any other prompt failure) and _mark_done flipped
                    # _done. The driver catches the early return and the
                    # workflow surfaces the recorded error.
                    return
                raise RuntimeError(
                    "Decomposer returned without delivering an outline "
                    "and without reporting a prompt_error — actor contract "
                    "violation"
                )
        else:
            unit_ids_seed = [wu.id for wu in self._outline.work_units if wu.id]
            await self._emit_output(
                "refuel",
                f"Outline loaded from cache: {len(unit_ids_seed)} work unit(s)",
                level="success",
                metadata={"unit_count": len(unit_ids_seed)},
            )

        # Details — by the time we get here the outline is non-None (the
        # only way past the block above with self._outline still None is
        # the early return on self._done).
        assert self._outline is not None
        unit_ids = [wu.id for wu in self._outline.work_units if wu.id]
        await self._run_detail_fan_out(unit_ids)

        # Abandons short-circuit the rest of the pipeline. The fix loop
        # can address SC-coverage gaps and similar issues the LLM can
        # re-reason about, but it cannot recover units the worker model
        # never produced details for — that would require re-running
        # decompose with a different (more reliable) tier model. Emit a
        # clear error and fail the step so the user gets actionable
        # feedback instead of three doomed fix rounds + a Pydantic error.
        if self._abandoned_unit_ids:
            abandoned_count = len(self._abandoned_unit_ids)
            abandoned_list = ", ".join(sorted(self._abandoned_unit_ids))
            quota_count = sum(
                1 for uid in self._abandoned_unit_ids if uid in self._detail_quota_errors
            )
            elapsed_ms = int((_time.monotonic() - decompose_start) * 1000)
            if quota_count:
                # Pull a sample reset-time hint from one of the quota
                # error messages — helps the user know when to retry.
                sample = next(iter(self._detail_quota_errors.values()), "")
                from maverick.exceptions.quota import parse_quota_reset

                reset_hint = parse_quota_reset(sample)
                reset_suffix = f" (resets {reset_hint})" if reset_hint else ""
                msg = (
                    f"{abandoned_count}/{self._detail_total_count} unit(s) "
                    f"abandoned ({abandoned_list}) — {quota_count} due to "
                    f"provider quota exhaustion{reset_suffix}. The "
                    f"successful units are cached on disk, so re-running "
                    f"after capacity returns will only re-process the "
                    f"failures. Consider switching the affected tier to a "
                    f"different provider in your "
                    f"actors.refuel.decomposer.tiers config."
                )
            else:
                msg = (
                    f"{abandoned_count}/{self._detail_total_count} unit(s) "
                    f"abandoned during decompose ({abandoned_list}) — the "
                    f"worker model didn't submit details. Likely cause: an "
                    f"unreliable MCP-tool caller in the affected tier. "
                    f"Check the per-unit table above for the failed model; "
                    f"consider switching to claude/sonnet for that tier."
                )
            await self._emit_output("refuel", msg, level="error")
            await self._emit_phase_completed(
                "decompose",
                "Decomposing",
                elapsed_ms,
                success=False,
                error=f"{abandoned_count} unit(s) abandoned"
                + (f" ({quota_count} quota)" if quota_count else ""),
            )
            self._mark_done(
                {
                    "success": False,
                    "error": f"{abandoned_count} unit(s) abandoned",
                    "abandoned_unit_ids": sorted(self._abandoned_unit_ids),
                    "quota_abandoned_unit_ids": sorted(self._detail_quota_errors.keys()),
                    "specs": [],
                    "fix_rounds": 0,
                }
            )
            return

        # Validate (with fix loop)
        self._details = SubmitDetailsPayload(details=tuple(self._accumulated_details))
        self._specs = self._merge_to_specs()
        while True:
            result = await self._validator.validate(ValidateRequest(specs=tuple(self._specs)))
            if result.passed or self._fix_rounds >= MAX_FIX_ROUNDS:
                if not result.passed:
                    await self._emit_output(
                        "refuel",
                        f"Fix rounds exhausted ({MAX_FIX_ROUNDS}); proceeding with current specs",
                        level="warning",
                    )
                else:
                    await self._emit_output(
                        "refuel",
                        f"Validation passed ({len(self._specs)} spec(s))",
                        level="success",
                    )
                break
            await self._request_fix(result)

        # Create beads
        deps = self._extract_deps()
        await self._emit_output(
            "refuel",
            f"Creating beads for {len(self._specs)} spec(s)",
        )
        beads_result = await self._bead_creator.create_beads(
            CreateBeadsRequest(specs=tuple(self._specs), deps=tuple(deps))
        )

        elapsed_ms = int((_time.monotonic() - decompose_start) * 1000)
        await self._emit_phase_completed(
            "decompose",
            "Decomposing",
            elapsed_ms,
            success=beads_result.success,
            error=beads_result.error or None,
        )

        if beads_result.success:
            await self._emit_output(
                "refuel",
                f"Created {beads_result.bead_count} bead(s)"
                + (f" in epic {beads_result.epic_id}" if beads_result.epic_id else ""),
                level="success",
                metadata={
                    "bead_count": beads_result.bead_count,
                    "epic_id": beads_result.epic_id,
                },
            )
        else:
            await self._emit_output(
                "refuel",
                f"Bead creation failed: {beads_result.error}",
                level="error",
            )

        self._mark_done(
            {
                "success": beads_result.success,
                "epic_id": beads_result.epic_id,
                "bead_count": beads_result.bead_count,
                "deps_wired": beads_result.deps_wired,
                "epic": beads_result.epic,
                "work_beads": list(beads_result.work_beads),
                "created_map": dict(beads_result.created_map),
                "dependencies": list(beads_result.dependencies),
                "specs": self._specs,
                "fix_rounds": self._fix_rounds,
                "error": beads_result.error or None,
            }
        )

    async def _run_detail_fan_out(self, unit_ids: list[str]) -> None:
        import time as _time

        if not unit_ids:
            await self._emit_output(
                "refuel",
                "No units to detail; proceeding to validation",
            )
            return

        # Two dispatch modes — keep the routing logic in one place.
        #   * Tier mode: ``_decomposer_pool_dynamic`` is a demand-driven
        #     pool. Per-unit ``acquire(tier)`` reuses an idle actor of
        #     that tier, spawns a new one under the cap, or evicts an
        #     LRU idle actor of a different tier and spawns fresh.
        #   * Legacy round-robin: ``_decomposer_pool`` (or fallback to the
        #     primary) handles units by index modulo pool size.
        in_tier_mode = self._decomposer_pool_dynamic is not None

        # Broadcast context once. In tier mode the pool seeds each
        # actor it spawns; this call updates currently-cached actors
        # (none on first call, but keeps the code resumable).
        context = DecomposerContext(
            outline_json=json.dumps(self._outline_payload()),
            flight_plan_content=self._inputs.initial_payload.get("flight_plan_content", ""),
            verification_properties=self._inputs.initial_payload.get(
                "verification_properties", ""
            ),
        )
        if in_tier_mode:
            assert self._decomposer_pool_dynamic is not None
            await self._decomposer_pool_dynamic.set_context(context)
            tier_summary = f"demand pool, cap={self._decomposer_pool_dynamic._cap}"
            pool_size = self._decomposer_pool_dynamic._cap
        else:
            workers = self._decomposer_pool or [self._decomposer]
            await asyncio.gather(*[ref.set_context(context) for ref in workers])
            tier_summary = f"{len(workers)} round-robin"
            pool_size = len(workers)

        # Seed _accumulated_details from the on-disk cache so a resumed
        # run skips units that already succeeded.
        cached_unit_ids = self._seed_cached_details(unit_ids)
        unit_ids_to_dispatch = [uid for uid in unit_ids if uid not in cached_unit_ids]

        self._pending_detail_ids = set(unit_ids_to_dispatch)
        # Stable denominator + abandon / quota / escalation tracking for the run.
        self._detail_total_count = len(unit_ids)
        self._abandoned_unit_ids = set()
        self._detail_quota_errors = {}
        self._unit_escalation_levels = {}
        self._unit_current_display_name = {}
        self._unit_escalated_count = 0
        if cached_unit_ids:
            await self._emit_output(
                "refuel",
                (
                    f"Reusing {len(cached_unit_ids)} cached detail(s); "
                    f"detailing {len(unit_ids_to_dispatch)} unit(s) across "
                    f"{tier_summary} worker(s)"
                ),
            )
        else:
            await self._emit_output(
                "refuel",
                f"Detailing {len(unit_ids)} unit(s) across {tier_summary} worker(s)",
            )

        # Switch the working list to the not-cached subset so the rest
        # of the function (semaphore sizing, complexity index, fan-out)
        # operates on units that actually need a worker.
        unit_ids = unit_ids_to_dispatch
        if not unit_ids:
            # Everything was cached — short-circuit before the (empty)
            # asyncio.gather so we don't emit a misleading "demand pool"
            # summary for a no-op fan-out.
            return

        # Bound concurrency at the budget. In tier mode this matches the
        # demand pool's cap, so we never spawn more dispatch tasks than
        # the pool can serve in parallel; pool.acquire() blocks if needed
        # and concurrency naturally stabilizes at the budget.
        semaphore = asyncio.Semaphore(max(1, pool_size))

        # Build a unit_id → outline-complexity index for tier dispatch.
        # Outline carries the decomposer-assigned complexity per work
        # unit. Empty when no outline (defensive — shouldn't happen
        # because the detail fan-out runs after outline_ready).
        complexity_by_unit: dict[str, str | None] = {}
        if self._outline is not None:
            for wu in self._outline.work_units:
                complexity_by_unit[wu.id] = getattr(wu, "complexity", None)

        def _tier_for_level(unit_id: str, escalation_level: int) -> str:
            """Resolve the tier name for ``unit_id`` at a given escalation
            level. ``escalation_level=0`` is the unit's natural tier;
            higher levels walk up to the next-defined tier (skipping
            undefined gaps). Mirrors :meth:`FlySupervisor._resolve_tier_in`
            usage in the implementer-tier path."""
            assert self._decomposer_pool_dynamic is not None
            d_tiers = self._inputs.decomposer_tiers
            tier_keys = {t: True for t in TIER_ORDER if getattr(d_tiers, t, None) is not None}
            return FlySupervisor._resolve_tier_in(
                tier_keys, complexity_by_unit.get(unit_id), escalation_level
            )

        def _can_escalate(unit_id: str, current_level: int) -> bool:
            """True iff escalating ``unit_id`` from ``current_level`` would
            land on a different (higher-defined) tier. False when the
            current tier is already the highest defined."""
            if not in_tier_mode:
                return False
            current_tier = _tier_for_level(unit_id, current_level)
            next_tier = _tier_for_level(unit_id, current_level + 1)
            return current_tier != next_tier

        def _legacy_worker_for(fallback_index: int) -> Any:
            return workers[fallback_index % pool_size]

        def _label_for_tier(tier: str) -> str:
            """Return "tier · provider/model" for the AgentStarted display."""
            assert self._decomposer_pool_dynamic is not None
            return f"{tier} · {self._decomposer_pool_dynamic.tier_label(tier)}"

        # Escalation budget for this run. ``threshold`` is the maximum
        # number of escalation steps any unit may take; ``0`` means the
        # legacy "abandon after same-tier retries" behaviour.
        escalation_threshold = 0
        if in_tier_mode and self._inputs.decomposer_tiers is not None:
            escalation_threshold = getattr(
                self._inputs.decomposer_tiers, "escalation_threshold", 0
            )

        async def _try_one_tier(
            index: int, unit_id: str, escalation_level: int
        ) -> tuple[str, str]:
            """Run the same-tier retry loop for one tier attempt.

            Returns ``(outcome, error_message)`` where ``outcome`` is one
            of ``"success"`` / ``"timeout"`` / ``"no_tool_call"`` /
            ``"quota"``. The caller decides whether to escalate or
            abandon based on the outcome.

            Emits AgentStarted on first attempt and AgentCompleted on
            any non-success outcome (success is emitted by ``detail_ready``
            via ``_emit_unit_completed``). The unit's display name is
            updated before this is called so AgentStarted/Completed land
            on the right CLI row.
            """
            tier_name = ""  # populated inside the loop in tier mode
            label = self._default_decomposer_label
            started = False
            for attempt in range(MAX_DETAIL_RETRIES + 1):
                async with semaphore:
                    if in_tier_mode:
                        assert self._decomposer_pool_dynamic is not None
                        tier_name = _tier_for_level(unit_id, escalation_level)
                        assigned = await self._decomposer_pool_dynamic.acquire(tier_name)
                        label = _label_for_tier(tier_name)
                    else:
                        assigned = _legacy_worker_for(index)
                        tier_name = ""
                        label = self._default_decomposer_label
                    try:
                        if not started:
                            self._unit_start_times[unit_id] = _time.monotonic()
                            await self._emit_agent_started(
                                "decompose",
                                self._unit_current_display_name.get(unit_id, unit_id),
                                label,
                            )
                            started = True
                        try:
                            await xo.wait_for(
                                assigned.send_detail(DetailRequest.for_unit(unit_id)),
                                timeout=STALE_IN_FLIGHT_SECONDS,
                            )
                        except TimeoutError:
                            if attempt < MAX_DETAIL_RETRIES:
                                logger.debug(
                                    "refuel.detail.timeout_retry",
                                    unit_id=unit_id,
                                    attempt=attempt + 1,
                                    escalation_level=escalation_level,
                                )
                                continue
                            logger.warning(
                                "refuel.detail.tier_failed_timeout",
                                unit_id=unit_id,
                                escalation_level=escalation_level,
                            )
                            await self._emit_unit_completed(
                                unit_id, success=False, error="timed out"
                            )
                            return ("timeout", "timed out")
                    finally:
                        if in_tier_mode:
                            assert self._decomposer_pool_dynamic is not None
                            await self._decomposer_pool_dynamic.release(assigned, tier_name)
                # send_detail returned. If detail_ready cleared pending,
                # we succeeded.
                if unit_id not in self._pending_detail_ids:
                    return ("success", "")
                if unit_id in self._detail_quota_errors:
                    err = self._detail_quota_errors[unit_id]
                    logger.warning(
                        "refuel.detail.tier_failed_quota",
                        unit_id=unit_id,
                        attempt=attempt + 1,
                        provider=label,
                        escalation_level=escalation_level,
                    )
                    await self._emit_unit_completed(
                        unit_id,
                        success=False,
                        error=f"quota: {err[:80]}",
                    )
                    return ("quota", err)
                # No-tool-call failure: the actor already did prompt +
                # nudge inside its turn (via
                # ``_agentic._run_with_self_nudge``), so by the time we
                # see pending still set the model has had two chances to
                # call the tool and refused. A third same-model attempt
                # is overwhelmingly likely to refuse again — escalation
                # to a more capable tier is the right next move, not
                # another same-tier retry. (Timeouts above DO retry —
                # they're often transient and a same-model second try
                # frequently succeeds.)
                logger.warning(
                    "refuel.detail.tier_failed_no_tool_call",
                    unit_id=unit_id,
                    escalation_level=escalation_level,
                )
                await self._emit_unit_completed(unit_id, success=False, error="no tool call")
                return ("no_tool_call", "no tool call")
            # Defensive fallthrough — should be unreachable.
            return ("no_tool_call", "no tool call")

        async def _one(index: int, unit_id: str) -> None:
            # AgentStarted fires only after we hold both the semaphore
            # AND a worker (inside _try_one_tier), so queued units don't
            # show a misleading spinner while waiting on the budget.
            self._unit_current_display_name[unit_id] = unit_id
            self._unit_escalation_levels[unit_id] = 0
            for level in range(escalation_threshold + 1):
                if level > 0:
                    # Update display name so the new tier attempt shows
                    # as a fresh CLI row. ``↑`` per escalation step.
                    self._unit_current_display_name[unit_id] = f"{unit_id}" + " ↑" * level
                    self._unit_escalation_levels[unit_id] = level
                    # Clear any quota signal recorded against the previous
                    # tier; we may now be on a different provider.
                    self._detail_quota_errors.pop(unit_id, None)
                outcome, err_msg = await _try_one_tier(index, unit_id, level)
                if outcome == "success":
                    return
                # Failure on this tier. Escalate if budget allows AND a
                # higher tier exists.
                if level < escalation_threshold and _can_escalate(unit_id, level):
                    from_tier = _tier_for_level(unit_id, level)
                    to_tier = _tier_for_level(unit_id, level + 1)
                    self._unit_escalated_count += 1
                    await self._emit_output(
                        "refuel",
                        (f"Escalating {unit_id!r}: {from_tier} → {to_tier} ({err_msg})"),
                        level="info",
                    )
                    continue
                # No more escalation possible — final abandon.
                self._pending_detail_ids.discard(unit_id)
                self._abandoned_unit_ids.add(unit_id)
                return

        await asyncio.gather(*[_one(i, uid) for i, uid in enumerate(unit_ids)])

    async def _request_fix(self, validation: ValidationResult) -> None:
        self._fix_rounds += 1
        gaps = self._enrich_gaps(list(validation.gaps))
        # Distinguish "coverage gaps the fixer can address" from "the
        # validator raised an unexpected error" (error_type="other").
        # The latter is the cascade that bit us before — silently fixing
        # what the agent never produced, then crashing later. Surface
        # the real error so the user can spot the problem.
        if validation.error_type == "other":
            await self._emit_output(
                "refuel",
                (
                    f"Validation raised an error (round "
                    f"{self._fix_rounds}/{MAX_FIX_ROUNDS}): "
                    f"{validation.message or 'unknown error'} — fixer is "
                    f"unlikely to address this; consider re-running "
                    f"decompose."
                ),
                level="error",
                metadata={
                    "fix_round": self._fix_rounds,
                    "error_type": validation.error_type,
                },
            )
        else:
            await self._emit_output(
                "refuel",
                f"Validation found {len(gaps)} gap(s); "
                f"requesting fix (round {self._fix_rounds}/{MAX_FIX_ROUNDS})",
                level="warning",
                metadata={"gap_count": len(gaps), "fix_round": self._fix_rounds},
            )
        # Surface the fix attempt as its own row in the agent-tracker
        # table so the user has visible progress (and a duration) for
        # the fix prompt — previously this was a silent ~minutes-long
        # call into the primary decomposer with no UI feedback.
        import time as _time

        fix_agent_name = f"fix-round-{self._fix_rounds}"
        fix_provider_label = self._default_decomposer_label
        fix_start = _time.monotonic()
        await self._emit_agent_started("decompose", fix_agent_name, fix_provider_label)

        self._awaiting_fix = True
        try:
            await self._decomposer.send_fix(
                FixRequest(
                    outline_json=json.dumps(self._outline_payload()),
                    details_json=json.dumps(self._details_payload()),
                    verification_properties=self._inputs.initial_payload.get(
                        "verification_properties", ""
                    ),
                    coverage_gaps=tuple(gaps),
                    overloaded=(),
                )
            )
        except Exception as exc:  # noqa: BLE001 — surface as ✗ then re-raise
            elapsed = _time.monotonic() - fix_start
            await self._emit_agent_completed(
                "decompose",
                fix_agent_name,
                elapsed,
                success=False,
                error=str(exc)[:80] or "error",
            )
            raise

        elapsed = _time.monotonic() - fix_start
        if self._awaiting_fix:
            # send_fix returned without fix_ready firing — the agent
            # finished its turn without calling submit_fix. Mark the row
            # ✗ so the user can see the round didn't land; the supervisor
            # will fall through to the next round (or exhaust the budget).
            await self._emit_agent_completed(
                "decompose",
                fix_agent_name,
                elapsed,
                success=False,
                error="no tool call",
            )
        else:
            await self._emit_agent_completed("decompose", fix_agent_name, elapsed, success=True)

        # After send_fix returns, fix_ready should have updated self._outline/_details.
        # Refresh specs for the next validation pass.
        self._details = SubmitDetailsPayload(details=tuple(self._accumulated_details))
        self._specs = self._merge_to_specs()

    # ------------------------------------------------------------------
    # Typed domain methods (called by children via in-pool RPC)
    # ------------------------------------------------------------------

    @xo.no_lock
    async def outline_ready(self, payload: SubmitOutlinePayload) -> None:
        if self._outline is not None:
            await self._emit_output(
                "refuel",
                "Duplicate outline ignored",
                level="warning",
            )
            return
        self._outline = payload
        unit_ids = [wu.id for wu in payload.work_units if wu.id]
        await self._emit_output(
            "refuel",
            f"Outline received: {len(unit_ids)} work unit(s)",
            level="success",
            metadata={"unit_count": len(unit_ids)},
        )
        # Persist outline so a Ctrl-C mid-detail keeps the cheap phase.
        self._cache_outline()

    @xo.no_lock
    async def detail_ready(self, payload: SubmitDetailsPayload) -> None:
        completed_uids: list[str] = []
        for detail in payload.details:
            uid = detail.id
            self._accumulated_details = [d for d in self._accumulated_details if d.id != uid]
            self._accumulated_details.append(detail)
            # Only emit completion for units we were waiting on — guards
            # against double-emit when a worker re-submits a unit's detail.
            if uid in self._pending_detail_ids:
                completed_uids.append(uid)
            self._pending_detail_ids.discard(uid)
            # Per-unit cache write so a killed run resumes at N-of-M.
            self._cache_detail(uid, detail)
        # Emit per-unit AgentCompleted so the Live decompose table marks
        # each row done as soon as its worker submits.
        for uid in completed_uids:
            await self._emit_unit_completed(uid, success=True)
        # No aggregate "Detail X/Y complete" emit — the per-unit table
        # already shows progress with ✓/✗ per row, so the counter would
        # be redundant noise in the buffered post-table output.

    @xo.no_lock
    async def fix_ready(self, payload: SubmitFixPayload) -> None:
        # The fix payload is a DELTA — only units the fixer changed.
        # MUST merge into existing state; replacing wholesale drops the
        # 41 untouched units and the validator then sees a 1-unit
        # decomposition with dangling dependencies. This was an
        # observed-in-the-wild bug: a fix targeting one missing
        # ``trace_ref`` reduced a 42-unit run to 4 created beads.
        if payload.work_units:
            if self._outline is None:
                self._outline = SubmitOutlinePayload(work_units=payload.work_units)
            else:
                merged_units = {wu.id: wu for wu in self._outline.work_units}
                for fixed_wu in payload.work_units:
                    merged_units[fixed_wu.id] = fixed_wu
                self._outline = SubmitOutlinePayload(work_units=tuple(merged_units.values()))
            # Persist the merged outline so a re-run picks up the
            # corrections instead of re-loading the pre-fix version
            # and burning through the fix loop again.
            self._cache_outline()
        if payload.details:
            merged_details = {d.id: d for d in self._accumulated_details}
            for fixed_d in payload.details:
                merged_details[fixed_d.id] = fixed_d
            self._accumulated_details = list(merged_details.values())
            self._details = SubmitDetailsPayload(details=tuple(self._accumulated_details))
            # Persist each fixed detail per-unit so a re-run resumes at
            # the post-fix state. The cache writer overwrites the
            # existing JSON, so units the fix didn't touch keep their
            # existing cache entries; only the fixed ones get
            # rewritten.
            for detail in payload.details:
                self._cache_detail(detail.id, detail)
        self._awaiting_fix = False
        await self._emit_output(
            "refuel",
            f"Fix submitted (round {self._fix_rounds}); re-validating",
        )

    # --- Briefing forward methods ---

    @xo.no_lock
    async def navigator_brief_ready(self, payload: SubmitNavigatorBriefPayload) -> None:
        await self._record_brief("navigator", payload)

    @xo.no_lock
    async def structuralist_brief_ready(self, payload: SubmitStructuralistBriefPayload) -> None:
        await self._record_brief("structuralist", payload)

    @xo.no_lock
    async def recon_brief_ready(self, payload: SubmitReconBriefPayload) -> None:
        await self._record_brief("recon", payload)

    @xo.no_lock
    async def contrarian_brief_ready(self, payload: SubmitContrarianBriefPayload) -> None:
        await self._record_brief("contrarian", payload)

    async def _record_brief(self, agent_name: str, payload: SupervisorInboxPayload) -> None:
        import time as _time

        self._briefing_results[agent_name] = payload
        self._briefing_expected.discard(agent_name)
        label = agent_name.replace("_", " ").title()
        elapsed = _time.monotonic() - self._briefing_start_times.get(agent_name, 0)
        await self._emit_agent_completed("briefing", label, elapsed)

    @xo.no_lock
    async def prompt_error(self, error: PromptError) -> None:
        """Handle an ACP prompt failure reported by an agent.

        Outline/fix/briefing phase errors are fatal (they abort the
        driver). Detail-phase errors are handled by the fan-out retry
        loop — this callback logs at debug AND records quota signals so
        the dispatcher can short-circuit doomed retries against an
        exhausted provider.
        """
        if error.phase == "detail":
            logger.debug(
                "refuel_supervisor.detail_prompt_error",
                unit_id=error.unit_id,
                error=error.error,
                quota=error.quota_exhausted,
            )
            # Record quota signal so the fan-out retry loop can abandon
            # immediately rather than burning more retries against the
            # same exhausted provider. The unit_id may be None for
            # global errors not tied to a specific dispatch — in that
            # case there's nothing to record (the per-unit error path
            # doesn't apply).
            if error.quota_exhausted and error.unit_id:
                self._detail_quota_errors[error.unit_id] = error.error or "quota exhausted"
            return
        await self._emit_output(
            "refuel",
            f"{error.phase} prompt failed: {error.error}",
            level="error",
            metadata={"phase": error.phase, "quota": error.quota_exhausted},
        )
        # Abort the driver by raising on the driver task; simplest is
        # to mark done with failure — the driver will notice on next
        # awaited action.
        self._mark_done(
            {
                "success": False,
                "error": error.error,
                "phase": error.phase,
                "quota_exhausted": error.quota_exhausted,
                "specs": self._specs,
                "fix_rounds": self._fix_rounds,
            }
        )

    @xo.no_lock
    async def payload_parse_error(self, tool: str, message: str) -> None:
        """Handle a malformed MCP tool payload.

        Nudges the primary decomposer to resubmit for outline/fix,
        warns for detail (one bad unit shouldn't kill the batch),
        escalates otherwise.
        """
        phase_map = {
            "submit_outline": "outline",
            "submit_details": "detail",
            "submit_fix": "fix",
        }
        phase = phase_map.get(tool)

        await self._emit_output(
            "refuel",
            f"Tool {tool!r} payload rejected by validator: {message}; requesting correction",
            level="warning",
        )

        if phase in ("outline", "fix"):
            try:
                await self._decomposer.send_nudge(NudgeRequest(expected_tool=tool, reason=message))
            except Exception as exc:  # noqa: BLE001 — nudge is best-effort
                logger.debug(
                    "refuel_supervisor.nudge_failed",
                    tool=tool,
                    error=str(exc),
                )
            return

        if phase == "detail":
            # Fan-out retry loop will cover a dropped unit.
            return

        # Unknown tool — escalate.
        self._mark_done(
            {
                "success": False,
                "error": f"Unknown tool {tool!r}: {message}",
                "specs": self._specs,
                "fix_rounds": self._fix_rounds,
            }
        )

    # ------------------------------------------------------------------
    # Event bus (asyncio.Queue-backed, replaces SupervisorEventBusMixin)
    # ------------------------------------------------------------------

    async def _emit(self, event: ProgressEvent) -> None:
        await self._event_queue.put(event)

    async def _emit_output(
        self,
        step_name: str,
        message: str,
        *,
        level: str = "info",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._emit(
            StepOutput(
                step_name=step_name,
                message=message,
                display_label="",
                level=level,  # type: ignore[arg-type]
                source=_SOURCE,
                metadata=metadata,
            )
        )

    async def _emit_phase_started(self, step_name: str, display_label: str) -> None:
        await self._emit(
            StepStarted(
                step_name=step_name,
                step_type=StepType.PYTHON,
                display_label=display_label,
            )
        )

    async def _emit_phase_completed(
        self,
        step_name: str,
        display_label: str,
        duration_ms: int,
        *,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        await self._emit(
            StepCompleted(
                step_name=step_name,
                step_type=StepType.PYTHON,
                success=success,
                duration_ms=duration_ms,
                display_label=display_label,
                error=error,
            )
        )

    async def _emit_agent_started(
        self, step_name: str, agent_name: str, provider: str = ""
    ) -> None:
        await self._emit(
            AgentStarted(step_name=step_name, agent_name=agent_name, provider=provider)
        )

    async def _emit_agent_completed(
        self,
        step_name: str,
        agent_name: str,
        duration_seconds: float,
        *,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        await self._emit(
            AgentCompleted(
                step_name=step_name,
                agent_name=agent_name,
                duration_seconds=duration_seconds,
                success=success,
                error=error,
            )
        )

    # ------------------------------------------------------------------
    # Test inspection hooks (public methods so xoscar dispatches; tests
    # use these to seed/drain private state without reaching across the
    # actor boundary). Prefixed ``t_`` per the fly_supervisor convention.
    # ------------------------------------------------------------------

    async def t_seed_detail_state(
        self, pending: list[str], start_times: dict[str, float] | None = None
    ) -> None:
        import time as _time

        self._pending_detail_ids = set(pending)
        seed = start_times or {}
        self._unit_start_times = {uid: seed.get(uid, _time.monotonic()) for uid in pending}

    async def t_drain_events(self) -> list[Any]:
        events: list[Any] = []
        while not self._event_queue.empty():
            evt = self._event_queue.get_nowait()
            if evt is not None:
                events.append(evt)
        return events

    async def t_peek_detail_quota_errors(self) -> dict[str, str]:
        return dict(self._detail_quota_errors)

    async def t_peek_outline_and_details(self) -> dict[str, Any]:
        """Test snapshot of merged outline + details — used to verify the
        fix-merge semantics. Plain dicts so the result crosses the actor
        boundary cleanly."""
        return {
            "outline_ids": [wu.id for wu in self._outline.work_units] if self._outline else [],
            "outline_tasks": {
                wu.id: wu.task for wu in (self._outline.work_units if self._outline else ())
            },
            "detail_ids": [d.id for d in self._accumulated_details],
            "detail_instructions": {d.id: d.instructions for d in self._accumulated_details},
        }

    @staticmethod
    def _format_provider_label(config: Any) -> str:
        """Build a "provider/model" label from a StepConfig (or None)."""
        if config is None:
            return ""
        provider = getattr(config, "provider", None) or "default"
        model_id = getattr(config, "model_id", None) or "default"
        return f"{provider}/{model_id}"

    async def _emit_unit_completed(
        self, unit_id: str, *, success: bool = True, error: str | None = None
    ) -> None:
        """Emit AgentCompleted for a single detail-phase unit.

        Wall-clock duration is computed from ``_unit_start_times``,
        seeded by the dispatch in ``_run_detail_fan_out``. A missing
        start time (defensive) yields 0.0s. The agent_name used in the
        event is the unit's current display name (``unit_id`` for the
        base tier attempt, ``"unit_id ↑"`` after one escalation, etc.)
        so the right CLI row gets the ✓/✗.
        """
        import time as _time

        start = self._unit_start_times.pop(unit_id, _time.monotonic())
        elapsed = _time.monotonic() - start
        display_name = self._unit_current_display_name.get(unit_id, unit_id)
        await self._emit_agent_completed(
            "decompose", display_name, elapsed, success=success, error=error
        )

    def _mark_done(self, result: dict[str, Any] | None) -> None:
        self._terminal_result = result
        self._done = True
        self._event_queue.put_nowait(None)

    @xo.no_lock
    async def get_terminal_result(self) -> dict[str, Any] | None:
        """Fetch the supervisor's terminal result after ``run()`` completes.

        Callers should await the full ``run()`` generator first; the
        result is only stable once the supervisor has called
        ``_mark_done``. Returns ``None`` if the supervisor never reached
        a terminal state (cancellation, exception before completion).
        """
        return self._terminal_result

    # ------------------------------------------------------------------
    # Helpers — ported 1:1 from the Thespian supervisor
    # ------------------------------------------------------------------

    def _briefing_payload(self, agent_name: str) -> dict[str, Any] | None:
        payload = self._briefing_results.get(agent_name)
        if payload is None:
            return None
        return dump_supervisor_payload(payload)

    def _outline_payload(self) -> dict[str, Any]:
        if self._outline is None:
            return {"work_units": []}
        return dump_supervisor_payload(self._outline)

    def _details_payload(self) -> dict[str, Any]:
        if self._details is None:
            return {"details": []}
        return dump_supervisor_payload(self._details)

    def _merge_to_specs(self) -> list[Any]:
        """Merge outline + details into typed ``WorkUnitSpec`` instances.

        Units missing a detail (because the worker model never submitted
        for them) are skipped — the abandon short-circuit before this
        method runs ensures we never reach here with abandoned units in
        the happy path, but the guard stays for defense-in-depth.

        Units that fail ``WorkUnitSpec.model_validate`` are logged and
        skipped rather than appended as raw dicts. Mixing dicts into the
        spec list breaks every downstream consumer that calls ``.id`` or
        similar on the items, and burying the parse error as a silent
        fallback was the root cause of the 'dict' object has no
        attribute 'id' validator crashes that ate three fix rounds.
        """
        from maverick.workflows.refuel_maverick.models import WorkUnitSpec

        work_units = self._outline.work_units if self._outline else ()
        details = self._details.details if self._details else ()

        detail_map: dict[str, WorkUnitDetailPayload] = {d.id: d for d in details}
        specs: list[Any] = []
        for wu in work_units:
            detail = detail_map.get(wu.id)
            if detail is None:
                logger.warning("refuel.merge.skipping_no_detail", unit_id=wu.id)
                continue
            merged = {
                "id": wu.id,
                "task": wu.task,
                "sequence": wu.sequence,
                "parallel_group": wu.parallel_group,
                "depends_on": list(wu.depends_on),
                "file_scope": dump_supervisor_payload(wu.file_scope),
                "instructions": detail.instructions,
                "acceptance_criteria": [
                    dump_supervisor_payload(ac) for ac in detail.acceptance_criteria
                ],
                "verification": list(detail.verification),
                "test_specification": detail.test_specification,
                # Decomposer-assigned tier hint (None when not classified).
                "complexity": getattr(wu, "complexity", None),
            }
            try:
                specs.append(WorkUnitSpec.model_validate(merged))
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "refuel.merge.spec_validation_failed",
                    unit_id=wu.id,
                    error=str(exc),
                )
                # Skip rather than appending raw dict — see docstring.
                continue
        return specs

    def _extract_deps(self) -> list[list[str]]:
        deps: list[list[str]] = []
        for spec in self._specs:
            sid = spec.id if hasattr(spec, "id") else spec.get("id", "")
            dep_list = (
                spec.depends_on if hasattr(spec, "depends_on") else spec.get("depends_on", [])
            )
            for dep_id in dep_list:
                deps.append([sid, dep_id])
        return deps

    # ------------------------------------------------------------------
    # On-disk cache writes (resumes short-circuit re-doing phases)
    # ------------------------------------------------------------------

    def _cache_briefing_results(self) -> None:
        """Persist briefing payloads. Always overwrites so a resumed run
        whose inputs drifted refreshes the cache instead of keeping a
        stale copy."""
        import hashlib
        from pathlib import Path

        cache_path = self._inputs.briefing_cache_path
        if not cache_path or not self._briefing_results:
            return

        path = Path(cache_path)
        payloads = self._inputs.initial_payload.get("briefing", {})
        cache_key = self._inputs.briefing_cache_key
        if not cache_key:
            raw = json.dumps(payloads, default=str, sort_keys=True).encode("utf-8")
            cache_key = hashlib.sha256(raw).hexdigest()[:16]

        envelope = {
            "schema_version": self._inputs.briefing_cache_schema_version,
            "cache_key": cache_key,
            "payloads": payloads,
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(envelope, indent=2, default=str),
                encoding="utf-8",
            )
            logger.info(
                "refuel_supervisor.briefing_cached",
                path=cache_path,
                agents=list(self._briefing_results.keys()),
                cache_key=cache_key,
            )
        except OSError as exc:
            logger.warning(
                "refuel_supervisor.briefing_cache_write_failed",
                path=cache_path,
                error=str(exc),
            )

    def _cache_outline(self) -> None:
        """Persist the decomposer outline."""
        import hashlib
        from pathlib import Path

        cache_path = self._inputs.outline_cache_path
        if not cache_path or not self._outline:
            return

        path = Path(cache_path)
        payload = self._outline_payload()

        inputs = self._inputs.outline_cache_key_inputs or {}
        briefing_payloads = self._inputs.initial_payload.get("briefing") or {}
        h = hashlib.sha256()
        h.update(inputs.get("flight_plan_content", "").encode("utf-8"))
        h.update(b"\x00")
        h.update(inputs.get("verification_properties", "").encode("utf-8"))
        h.update(b"\x00")
        h.update(json.dumps(briefing_payloads, default=str, sort_keys=True).encode("utf-8"))
        cache_key = h.hexdigest()[:16]

        envelope = {
            "schema_version": self._inputs.outline_cache_schema_version,
            "cache_key": cache_key,
            "payload": payload,
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(envelope, indent=2, default=str),
                encoding="utf-8",
            )
            logger.info(
                "refuel_supervisor.outline_cached",
                path=cache_path,
                unit_count=len(self._outline.work_units),
                cache_key=cache_key,
            )
        except OSError as exc:
            logger.warning(
                "refuel_supervisor.outline_cache_write_failed",
                path=cache_path,
                error=str(exc),
            )

    def _seed_cached_details(self, outline_unit_ids: list[str]) -> set[str]:
        """Seed ``_accumulated_details`` from the on-disk detail cache.

        The workflow loads ``.maverick/plans/<plan>/refuel-details/*.json``
        into ``initial_payload["cached_details"]`` (dict keyed by unit
        id). Each entry parses back to a ``WorkUnitDetailPayload``;
        malformed entries are logged and skipped so a partially-corrupt
        cache doesn't take the whole run down. Stale entries — units no
        longer in the outline — are dropped silently (outline
        regeneration is the canonical signal for "re-do everything").

        Args:
            outline_unit_ids: Unit ids from the current outline. Cache
                entries outside this set are stale and ignored.

        Returns:
            Set of unit ids successfully seeded from the cache.
        """
        cached_raw = self._inputs.initial_payload.get("cached_details") or {}
        if not isinstance(cached_raw, dict) or not cached_raw:
            return set()

        outline_ids = set(outline_unit_ids)
        seeded: set[str] = set()
        for uid, detail_dict in cached_raw.items():
            if uid not in outline_ids:
                continue
            if not isinstance(detail_dict, dict):
                continue
            try:
                detail = WorkUnitDetailPayload.model_validate(detail_dict)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "refuel.detail_cache_parse_failed",
                    unit_id=uid,
                    error=str(exc),
                )
                continue
            # Replace any earlier instance of this uid (defensive).
            self._accumulated_details = [d for d in self._accumulated_details if d.id != uid]
            self._accumulated_details.append(detail)
            seeded.add(uid)
        return seeded

    def _cache_detail(self, unit_id: str, detail: WorkUnitDetailPayload) -> None:
        """Persist a single unit's detail JSON."""
        from pathlib import Path

        cache_dir = self._inputs.detail_cache_dir
        if not cache_dir or not unit_id:
            return

        path = Path(cache_dir) / f"{unit_id}.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(dump_supervisor_payload(detail), indent=2, default=str),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning(
                "refuel_supervisor.detail_cache_write_failed",
                unit_id=unit_id,
                error=str(exc),
            )

    def _enrich_gaps(self, gaps: list[str]) -> list[str]:
        flight_plan = self._inputs.flight_plan
        sc_list = getattr(flight_plan, "success_criteria", []) or []
        sc_map: dict[str, str] = {}
        for i, sc in enumerate(sc_list):
            ref = getattr(sc, "ref", None) or f"SC-{i + 1:03d}"
            text = getattr(sc, "text", str(sc))
            sc_map[ref] = text

        enriched: list[str] = []
        for gap in gaps:
            for ref, text in sc_map.items():
                if ref in gap:
                    gap = f"{gap} — Full text: {text}"
                    break
            enriched.append(gap)
        return enriched

    # ------------------------------------------------------------------
    # Test inspection helpers (FUTURE.md §2.10 Phase 3) — see the
    # corresponding ``t_*`` methods on FlySupervisor for rationale. The
    # ``t_`` prefix avoids the xoscar `_`-prefixed RPC restriction.
    # ------------------------------------------------------------------

    @xo.no_lock
    async def t_peek_decomposers(self) -> dict[str, Any]:
        """Snapshot of decomposer-pool state for tests.

        Tier mode is now demand-driven, so the snapshot reflects what
        the pool currently caches (which depends on what work has run
        through it), not what was pre-spawned.

        Returns:
          * ``mode``: ``"legacy"`` (round-robin pool) or ``"tiered"``
          * ``pool_size``: count of legacy round-robin workers
          * ``demand_pool``: snapshot of the demand pool (tier mode only),
            with keys ``cap``, ``total``, ``idle_by_tier``, ``actors_by_tier``
        """
        return {
            "mode": "tiered" if self._decomposer_pool_dynamic is not None else "legacy",
            "pool_size": len(self._decomposer_pool),
            "demand_pool": (
                self._decomposer_pool_dynamic.snapshot()
                if self._decomposer_pool_dynamic is not None
                else None
            ),
        }
