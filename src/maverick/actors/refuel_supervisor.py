"""RefuelSupervisorActor — Thespian actor that orchestrates decomposition.

The supervisor IS the actor with the inbox. MCP tool calls arrive
directly here. Routing logic is methods on this class. All inter-actor
communication uses Thespian message passing.

The workflow sends "start" and then drains progress events via
``{"type": "get_events", "since": int}`` polls until the supervisor
marks itself done. The terminal result payload rides on the final
``done=True`` reply — see ``SupervisorEventBusMixin``.

Detail pass parallelism: the supervisor creates a pool of decomposer
actors (each with its own ACP connection). After the outline arrives,
individual work unit IDs are fanned out round-robin across the pool.
Each actor produces one ``submit_details`` call per unit. The supervisor
collects all responses and proceeds to validation once every unit has
been detailed.
"""

import json
from typing import Any

from thespian.actors import Actor, WakeupMessage

from maverick.actors.event_bus import SupervisorEventBusMixin
from maverick.logging import get_logger

MAX_FIX_ROUNDS = 3

# A unit can time out and be requeued this many times before we give up
# and surface it as a failure. 1 full retry is usually enough — a second
# timeout on the same unit almost always means a systemic issue, not a
# transient one.
MAX_DETAIL_RETRIES = 1

_SOURCE = "refuel-supervisor"

logger = get_logger(__name__)


class RefuelSupervisorActor(SupervisorEventBusMixin, Actor):
    """Orchestrates flight plan decomposition via message routing.

    Message protocol:
    - {"type": "init"} → configure child actor addresses
    - "start" from workflow → kicks off outline phase
    - {"type": "get_events", "since": int} → event-bus drain poll
    - {"tool": ...} from MCP server → tool call result
    - {"type": "prompt_sent"} from decomposer → informational
    - {"type": "prompt_error"} from decomposer → error
    - {"type": "validation_result"} from validator
    - {"type": "beads_created"} from bead creator
    """

    def receiveMessage(self, message, sender):
        logger.debug(
            "refuel_supervisor.received",
            msg_type=type(message).__name__,
            preview=str(message)[:200] if message else "None",
        )

        # --- Init: receive config and child actor addresses ---
        if isinstance(message, dict) and message.get("type") == "init":
            self._init(message, sender)
            return

        # --- Event-bus drain poll (must precede other dict routing) ---
        if isinstance(message, dict) and message.get("type") == "get_events":
            self._handle_get_events(message, sender)
            return

        # --- Wakeup (self-scheduled heartbeat) ---
        if isinstance(message, WakeupMessage):
            self._handle_wakeup(message)
            return

        # --- Start signal from workflow ---
        if message == "start":
            if self._skip_briefing or not self._briefing_actors:
                self._start_outline()
            else:
                self._start_briefing()
            return

        # --- Decomposer prompt confirmation ---
        # Check BEFORE tool routing — prompt_sent may contain a "tool" key
        if isinstance(message, dict) and message.get("type") == "prompt_sent":
            phase = message.get("phase", "")
            self._handle_prompt_sent(phase)
            return

        # --- Tool call from MCP server (via Thespian tell) ---
        if isinstance(message, dict) and "tool" in message:
            self._handle_tool_call(message)
            return

        if isinstance(message, dict) and message.get("type") == "prompt_error":
            phase = message.get("phase", "")
            if phase == "briefing":
                self._handle_briefing_error(message)
            elif phase == "detail":
                self._handle_detail_error(message)
            else:
                self._handle_error(message)
            return

        # --- Validation result ---
        if isinstance(message, dict) and message.get("type") == "validation_result":
            self._handle_validation(message)
            return

        # --- Beads created ---
        if isinstance(message, dict) and message.get("type") == "beads_created":
            self._handle_beads_created(message)
            return

        # --- Init acks from child actors ---
        if isinstance(message, dict) and message.get("type") == "init_ok":
            return

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def _init(self, message, sender):
        """Store config and create child actors."""
        self._init_event_bus()
        self._config = message.get("config", {})
        self._decomposer = message.get("decomposer_addr")
        self._validator = message.get("validator_addr")
        self._bead_creator = message.get("bead_creator_addr")

        # Decomposer pool
        self._decomposer_pool: list = message.get("decomposer_pool", [])

        # Briefing actors (optional — empty if skip_briefing)
        self._briefing_actors: dict[str, Any] = message.get("briefing_actors", {})
        self._provider_labels: dict[str, str] = message.get("provider_labels", {})
        self._skip_briefing: bool = message.get("skip_briefing", False)

        # State
        self._details = None
        self._specs = []
        self._fix_rounds = 0
        self._nudge_count = 0
        self._initial_payload = message.get("initial_payload", {})
        self._briefing_cache_path = message.get("briefing_cache_path")
        self._outline_cache_path = message.get("outline_cache_path")
        self._detail_cache_dir = message.get("detail_cache_dir")

        # Seed outline from cache if pre-populated by workflow.
        _cached_outline = self._initial_payload.get("outline")
        self._outline = _cached_outline if isinstance(_cached_outline, dict) else None

        # Briefing state
        self._briefing_results: dict[str, Any] = {}
        self._briefing_expected: set[str] = set()
        import time as _time

        self._briefing_start_times: dict[str, float] = {}
        self._briefing_start = _time.monotonic()

        # Detail fan-out state
        self._pending_detail_ids: set[str] = set()
        # Seed accumulated details from per-unit cache so a killed run
        # resumes at N-of-M instead of 0-of-M.
        _cached_details = self._initial_payload.get("cached_details", {})
        if isinstance(_cached_details, dict):
            self._accumulated_details: list[dict] = [
                d for d in _cached_details.values() if isinstance(d, dict)
            ]
        else:
            self._accumulated_details = []

        # Heartbeat / liveness state (populated in _fan_out_details).
        self._detail_dispatch_info: dict[str, dict[str, Any]] = {}
        self._detail_retries: dict[str, int] = {}
        self._last_detail_time: float = 0.0
        self._heartbeat_active: bool = False

        self.send(sender, {"type": "init_ok"})

    # ------------------------------------------------------------------
    # Briefing
    # ------------------------------------------------------------------

    def _start_briefing(self):
        """Fan out briefing to parallel actors."""
        import time as _time

        self._emit_phase_started("briefing", "Briefing")

        prompt = self._initial_payload.get("briefing_prompt", "")

        # Emit agent-started events for all parallel agents
        parallel_agents = [n for n in self._briefing_actors if n != "contrarian"]
        for name in parallel_agents:
            label = name.replace("_", " ").title()
            self._emit_agent_started("briefing", label, self._provider_labels.get(label, ""))
            self._briefing_start_times[name] = _time.monotonic()
            self._briefing_expected.add(name)

        # Send briefing prompts to parallel actors
        for name in parallel_agents:
            addr = self._briefing_actors[name]
            self.send(addr, {"type": "briefing", "prompt": prompt})

    def _start_contrarian(self):
        """Send contrarian prompt with all briefing results."""
        import time as _time

        from maverick.agents.briefing.prompts import build_contrarian_prompt

        raw_content = self._initial_payload.get("flight_plan_content", "")
        contrarian_prompt = build_contrarian_prompt(
            raw_content,
            self._briefing_results.get("navigator"),
            self._briefing_results.get("structuralist"),
            self._briefing_results.get("recon"),
        )

        label = "Contrarian"
        self._emit_agent_started("briefing", label, self._provider_labels.get(label, ""))
        self._briefing_start_times["contrarian"] = _time.monotonic()
        self._briefing_expected.add("contrarian")

        addr = self._briefing_actors["contrarian"]
        self.send(addr, {"type": "briefing", "prompt": contrarian_prompt})

    def _briefing_complete(self):
        """All briefing done — cache results and pass to decomposer."""
        import time as _time

        elapsed_ms = int((_time.monotonic() - self._briefing_start) * 1000)
        self._emit_phase_completed("briefing", "Briefing", elapsed_ms)

        self._initial_payload["briefing"] = self._briefing_results

        # Write cache immediately so a Ctrl-C during decomposition
        # doesn't lose the expensive briefing work.
        self._cache_briefing_results()

        # Proceed to decomposition
        self._start_outline()

    def _cache_briefing_results(self):
        """Persist briefing results to disk for future runs."""
        import json as _json
        from pathlib import Path

        cache_path = getattr(self, "_briefing_cache_path", None)
        if not cache_path or not self._briefing_results:
            return

        path = Path(cache_path)
        if path.is_file():
            return  # already cached from a prior run

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                _json.dumps(self._briefing_results, indent=2, default=str),
                encoding="utf-8",
            )
            logger.info(
                "refuel_supervisor.briefing_cached",
                path=cache_path,
                agents=list(self._briefing_results.keys()),
            )
        except OSError as exc:
            logger.warning(
                "refuel_supervisor.briefing_cache_write_failed",
                path=cache_path,
                error=str(exc),
            )

    def _cache_outline(self):
        """Persist the decomposer outline to disk for future runs."""
        import json as _json
        from pathlib import Path

        cache_path = getattr(self, "_outline_cache_path", None)
        if not cache_path or not self._outline:
            return

        path = Path(cache_path)
        if path.is_file():
            return  # already cached from a prior run

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                _json.dumps(self._outline, indent=2, default=str),
                encoding="utf-8",
            )
            logger.info(
                "refuel_supervisor.outline_cached",
                path=cache_path,
                unit_count=len(self._outline.get("work_units", [])),
            )
        except OSError as exc:
            logger.warning(
                "refuel_supervisor.outline_cache_write_failed",
                path=cache_path,
                error=str(exc),
            )

    def _cache_detail(self, unit_id: str, detail: dict[str, Any]) -> None:
        """Persist a single unit's detail to disk.

        Writes one JSON file per unit under
        ``.maverick/plans/<name>/refuel-details/<unit_id>.json``.
        A resumed run seeds ``_accumulated_details`` from this directory
        so we don't re-pay for LLM details already produced.
        """
        import json as _json
        from pathlib import Path

        cache_dir = getattr(self, "_detail_cache_dir", None)
        if not cache_dir or not unit_id:
            return

        path = Path(cache_dir) / f"{unit_id}.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                _json.dumps(detail, indent=2, default=str),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning(
                "refuel_supervisor.detail_cache_write_failed",
                unit_id=unit_id,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    _HEARTBEAT_INTERVAL_SECONDS = 30

    def _start_heartbeat(self) -> None:
        """Schedule the first detail-phase heartbeat wakeup."""
        from datetime import timedelta

        self._heartbeat_active = True
        self.wakeupAfter(
            timedelta(seconds=self._HEARTBEAT_INTERVAL_SECONDS),
            payload="detail_heartbeat",
        )

    def _handle_wakeup(self, message: WakeupMessage) -> None:
        """Emit a heartbeat status line if detail work is still in flight."""
        payload = getattr(message, "payload", None)
        if payload != "detail_heartbeat":
            return
        if not getattr(self, "_heartbeat_active", False):
            return
        if not self._pending_detail_ids:
            # Done — stop the loop.
            self._heartbeat_active = False
            return

        import time as _time

        now = _time.monotonic()
        done = len(self._accumulated_details)
        pending = len(self._pending_detail_ids)
        since_last = now - self._last_detail_time

        # Age of the oldest in-flight request.
        oldest_uid: str | None = None
        oldest_age = 0.0
        oldest_pool = -1
        for uid, info in self._detail_dispatch_info.items():
            age = now - info.get("at", now)
            if age > oldest_age:
                oldest_age = age
                oldest_uid = uid
                oldest_pool = info.get("pool_idx", -1)

        msg = (
            f"Still working — {done}/{done + pending} done, "
            f"{self._detail_in_flight} in flight, "
            f"{len(self._detail_queue)} queued, "
            f"{since_last:.0f}s since last detail"
        )
        if oldest_uid:
            msg += f"; oldest in flight: {oldest_uid} on pool[{oldest_pool}] for {oldest_age:.0f}s"

        self._emit_output(
            "refuel",
            msg,
            level="info",
            source=_SOURCE,
        )

        # Reschedule.
        from datetime import timedelta

        self.wakeupAfter(
            timedelta(seconds=self._HEARTBEAT_INTERVAL_SECONDS),
            payload="detail_heartbeat",
        )

    # ------------------------------------------------------------------
    # Decomposition
    # ------------------------------------------------------------------

    def _start_outline(self):
        """Kick off the outline phase.

        If the outline was seeded from a cache in init, skip straight to
        the detail fan-out instead of dispatching the (expensive) outline
        request to the decomposer.
        """
        import time as _time

        self._emit_phase_started("decompose", "Decomposing")
        self._decompose_start = _time.monotonic()

        if self._outline is not None:
            unit_ids = [
                wu.get("id", "")
                for wu in self._outline.get("work_units", [])
                if isinstance(wu, dict)
            ]
            self._emit_output(
                "refuel",
                f"Outline loaded from cache: {len(unit_ids)} work unit(s)",
                level="success",
                source=_SOURCE,
                metadata={"unit_count": len(unit_ids)},
            )
            self._fan_out_details(unit_ids)
            return

        self._emit_output(
            "refuel",
            "Requesting outline from decomposer",
            level="info",
            source=_SOURCE,
        )
        self.send(
            self._decomposer,
            {
                "type": "outline_request",
                **self._initial_payload,
            },
        )

    def _fan_out_details(self, unit_ids):
        """Dispatch individual detail requests across the decomposer pool.

        Uses round-robin assignment across pool decomposer actors only.
        The primary decomposer is excluded because it has submit_outline
        in its MCP tool set and a persistent session with the outline
        conversation in context — detail prompts on that session cause
        the agent to call submit_outline instead of submit_details,
        triggering cascading re-fan-outs.

        Two size/flow-control optimizations:

        1. Large payloads (outline JSON, full flight plan, verification
           properties) are broadcast ONCE via ``set_context`` to each
           pool actor. Subsequent ``detail_request`` messages only carry
           a unit_id — roughly 50 bytes instead of ~60 KB each. This
           keeps the fan-out well below Thespian's TCP transport
           watermarks even with large flight plans.

        2. The fan-out is bounded by ``_detail_in_flight_max``. The
           supervisor keeps that many messages active at once and
           dispatches the next unit when a ``submit_details`` tool call
           arrives. Remaining work lives in ``_detail_queue`` on the
           supervisor instead of piling up in pool actor mailboxes.
        """
        from collections import deque

        all_decomposers = (
            list(self._decomposer_pool) if self._decomposer_pool else [self._decomposer]
        )
        pool_size = len(all_decomposers)
        self._detail_pool = all_decomposers
        self._detail_round_robin = 0
        # At most 2 in-flight per pool actor keeps everyone busy
        # without queueing deeply in any one mailbox.
        self._detail_in_flight_max = max(1, pool_size * 2)
        self._detail_in_flight = 0

        # Skip units already in the per-unit detail cache. These survive
        # across Ctrl-C so a resumed run picks up where it stopped.
        cached_ids = {
            d.get("id", "")
            for d in self._accumulated_details
            if isinstance(d, dict) and d.get("id")
        }
        remaining = [uid for uid in unit_ids if uid and uid not in cached_ids]
        skipped = len(unit_ids) - len(remaining)

        self._detail_queue: deque[str] = deque(remaining)
        self._pending_detail_ids = set(remaining)

        if skipped:
            self._emit_output(
                "refuel",
                f"Loaded {skipped} detail(s) from cache; "
                f"detailing {len(remaining)} remaining unit(s) across {pool_size} actor(s)",
                level="info",
                source=_SOURCE,
            )
        else:
            self._emit_output(
                "refuel",
                f"Detailing {len(unit_ids)} unit(s) across {pool_size} actor(s)",
                level="info",
                source=_SOURCE,
            )

        # Nothing to do — skip straight to validation.
        if not remaining:
            self._details = {"details": self._accumulated_details}
            self._specs = self._merge_to_specs()
            self.send(
                self._validator,
                {"type": "validate", "specs": self._specs},
            )
            return

        # Broadcast context once per pool actor so subsequent
        # detail_request messages can stay tiny.
        outline_json = json.dumps(self._outline)
        fp_content = self._initial_payload.get("flight_plan_content", "")
        verif_props = self._initial_payload.get("verification_properties", "")
        for pool_addr in all_decomposers:
            self.send(
                pool_addr,
                {
                    "type": "set_context",
                    "outline_json": outline_json,
                    "flight_plan_content": fp_content,
                    "verification_properties": verif_props,
                },
            )

        # Start heartbeat.
        import time as _time

        self._last_detail_time = _time.monotonic()
        self._detail_dispatch_info = {}
        self._start_heartbeat()

        self._dispatch_pending_details()

    def _dispatch_pending_details(self) -> None:
        """Send as many queued unit_ids as the in-flight budget allows."""
        import time as _time

        while self._detail_in_flight < self._detail_in_flight_max and self._detail_queue:
            uid = self._detail_queue.popleft()
            pool_idx = self._detail_round_robin % len(self._detail_pool)
            target = self._detail_pool[pool_idx]
            self._detail_round_robin += 1
            self._detail_in_flight += 1
            # Record so the heartbeat can report oldest-in-flight age.
            self._detail_dispatch_info[uid] = {
                "at": _time.monotonic(),
                "pool_idx": pool_idx,
            }
            self.send(
                target,
                {"type": "detail_request", "unit_id": uid},
            )

    def _handle_prompt_sent(self, phase):
        """Check if expected tool call arrived; nudge if not."""
        MAX_NUDGES = 2
        # Map phase to expected tool and state check
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

        tool_name, check_fn = phase_tool_map[phase]
        if check_fn():
            # Tool call already arrived — nothing to do
            return

        if self._nudge_count >= MAX_NUDGES:
            self._emit_output(
                "refuel",
                f"Max nudges reached for {phase}; skipping",
                level="warning",
                source=_SOURCE,
            )
            return

        self._nudge_count += 1
        logger.debug(
            "refuel_supervisor.nudging",
            tool=tool_name,
            attempt=self._nudge_count,
        )
        self.send(
            self._decomposer,
            {
                "type": "nudge",
                "expected_tool": tool_name,
            },
        )

    # Briefing tool name → agent name mapping
    _BRIEFING_TOOLS: dict[str, str] = {
        "submit_navigator_brief": "navigator",
        "submit_structuralist_brief": "structuralist",
        "submit_recon_brief": "recon",
        "submit_contrarian_brief": "contrarian",
    }

    def _handle_tool_call(self, message):
        """Route MCP tool call to appropriate handler."""
        tool = message.get("tool", "")
        args = message.get("arguments", {})

        self._nudge_count = 0  # Reset on successful tool call

        # Briefing tools
        if tool in self._BRIEFING_TOOLS:
            agent_name = self._BRIEFING_TOOLS[tool]
            self._briefing_results[agent_name] = args
            self._briefing_expected.discard(agent_name)

            import time as _time

            label = agent_name.replace("_", " ").title()
            elapsed = _time.monotonic() - self._briefing_start_times.get(agent_name, 0)
            self._emit_agent_completed("briefing", label, elapsed)

            if self._briefing_expected:
                return  # Still waiting

            if (
                "contrarian" in self._briefing_actors
                and "contrarian" not in self._briefing_results
            ):
                self._start_contrarian()
            else:
                self._briefing_complete()
            return

        if tool == "submit_outline":
            if self._outline is not None:
                self._emit_output(
                    "refuel",
                    "Duplicate outline ignored",
                    level="warning",
                    source=_SOURCE,
                )
                return

            self._outline = args
            self._cache_outline()
            unit_ids = [
                wu.get("id", "") for wu in args.get("work_units", []) if isinstance(wu, dict)
            ]
            self._emit_output(
                "refuel",
                f"Outline received: {len(unit_ids)} work unit(s)",
                level="success",
                source=_SOURCE,
                metadata={"unit_count": len(unit_ids)},
            )
            self._fan_out_details(unit_ids)

        elif tool == "submit_details":
            import time as _time

            # Collect details and mark units as done
            batch_details = args.get("details", [])
            for d in batch_details:
                if isinstance(d, dict):
                    uid = d.get("id", "")
                    self._accumulated_details.append(d)
                    self._pending_detail_ids.discard(uid)
                    # Persist to per-unit cache so a Ctrl-C preserves work.
                    self._cache_detail(uid, d)
                    # Drop from in-flight tracker.
                    self._detail_dispatch_info.pop(uid, None)

            self._last_detail_time = _time.monotonic()

            # One pool actor just finished a unit — free an in-flight
            # slot and dispatch the next queued unit (if any).
            if getattr(self, "_detail_in_flight", 0) > 0:
                self._detail_in_flight -= 1
            self._dispatch_pending_details()

            remaining = len(self._pending_detail_ids)
            done = len(self._accumulated_details)
            if remaining > 0:
                self._emit_output(
                    "refuel",
                    f"Detail {done}/{done + remaining} complete",
                    level="info",
                    source=_SOURCE,
                )
            else:
                # All units detailed — merge and validate
                self._details = {"details": self._accumulated_details}
                self._specs = self._merge_to_specs()
                self._emit_output(
                    "refuel",
                    f"Details received; validating {len(self._specs)} spec(s)",
                    level="info",
                    source=_SOURCE,
                    metadata={"spec_count": len(self._specs)},
                )
                self.send(
                    self._validator,
                    {
                        "type": "validate",
                        "specs": self._specs,
                    },
                )

        elif tool == "submit_fix":
            if args.get("work_units"):
                self._outline = {"work_units": args["work_units"]}
            if args.get("details"):
                self._details = {"details": args["details"]}
            self._specs = self._merge_to_specs()
            self._emit_output(
                "refuel",
                f"Fix submitted (round {self._fix_rounds}); re-validating",
                level="info",
                source=_SOURCE,
            )
            self.send(
                self._validator,
                {
                    "type": "validate",
                    "specs": self._specs,
                },
            )

        else:
            logger.warning(
                "refuel_supervisor.unexpected_tool",
                tool=tool,
                arg_keys=list(args.keys()) if isinstance(args, dict) else None,
            )
            self._emit_output(
                "refuel",
                f"Unexpected tool call: {tool}",
                level="warning",
                source=_SOURCE,
            )

    def _handle_validation(self, message):
        """Route validation result."""
        if message.get("passed"):
            self._emit_output(
                "refuel",
                f"Validation passed ({len(self._specs)} spec(s))",
                level="success",
                source=_SOURCE,
            )
            deps = self._extract_deps()
            self.send(
                self._bead_creator,
                {
                    "type": "create_beads",
                    "specs": self._specs,
                    "deps": deps,
                },
            )
        elif self._fix_rounds < MAX_FIX_ROUNDS:
            self._fix_rounds += 1
            gaps = message.get("gaps", [])
            enriched = self._enrich_gaps(gaps)
            self._emit_output(
                "refuel",
                f"Validation found {len(gaps)} gap(s); "
                f"requesting fix (round {self._fix_rounds}/{MAX_FIX_ROUNDS})",
                level="warning",
                source=_SOURCE,
                metadata={"gap_count": len(gaps), "fix_round": self._fix_rounds},
            )
            self.send(
                self._decomposer,
                {
                    "type": "fix_request",
                    "coverage_gaps": enriched,
                    "overloaded": message.get("overloaded", []),
                },
            )
        else:
            # Exhausted — proceed with what we have
            self._emit_output(
                "refuel",
                f"Fix rounds exhausted ({MAX_FIX_ROUNDS}); proceeding with current specs",
                level="warning",
                source=_SOURCE,
            )
            deps = self._extract_deps()
            self.send(
                self._bead_creator,
                {
                    "type": "create_beads",
                    "specs": self._specs,
                    "deps": deps,
                },
            )

    def _handle_beads_created(self, message):
        """Decomposition complete — shutdown agents, mark done."""
        import time as _time

        if hasattr(self, "_decompose_start"):
            elapsed_ms = int((_time.monotonic() - self._decompose_start) * 1000)
            self._emit_phase_completed("decompose", "Decomposing", elapsed_ms)

        # Shutdown all decomposer actors (primary + pool)
        for addr in [self._decomposer] + list(self._decomposer_pool):
            if addr:
                self.send(addr, {"type": "shutdown"})
        bead_count = message.get("bead_count", 0)
        success = message.get("success", False)
        self._emit_output(
            "refuel",
            f"Created {bead_count} bead(s)"
            + (f" in epic {message.get('epic_id', '')}" if message.get("epic_id") else ""),
            level="success" if success else "error",
            source=_SOURCE,
            metadata={"bead_count": bead_count, "epic_id": message.get("epic_id", "")},
        )
        self._mark_done(
            {
                "success": success,
                "epic_id": message.get("epic_id", ""),
                "bead_count": bead_count,
                "specs": self._specs,
                "fix_rounds": self._fix_rounds,
            }
        )

    def _handle_briefing_error(self, message):
        """Handle a briefing actor error — mark agent failed, check for quota."""
        import time as _time

        agent_name = message.get("agent_name", "")
        error_str = message.get("error", "unknown error")
        is_quota = message.get("quota_exhausted", False)

        # Mark the agent as failed in the tracker (✗ instead of ✓)
        label = agent_name.replace("_", " ").title()
        elapsed = _time.monotonic() - self._briefing_start_times.get(agent_name, 0)
        self._emit_agent_completed_with_error("briefing", label, elapsed, error_str)
        self._briefing_expected.discard(agent_name)

        if is_quota:
            # Quota exhausted — abort the entire workflow immediately.
            # No point continuing: other agents will hit the same wall.
            from maverick.exceptions.quota import parse_quota_reset

            reset_time = parse_quota_reset(error_str)
            reset_suffix = f" (resets {reset_time})" if reset_time else ""
            clean_msg = f"Provider quota exhausted{reset_suffix}"
            self._emit_output(
                "refuel",
                clean_msg,
                level="error",
                source=_SOURCE,
            )
            # Close the briefing phase as failed
            elapsed_ms = int((_time.monotonic() - self._briefing_start) * 1000)
            self._emit_phase_completed(
                "briefing", "Briefing", elapsed_ms, success=False, error=clean_msg
            )
            self._shutdown_all()
            self._mark_done(
                {
                    "success": False,
                    "error": clean_msg,
                    "specs": self._specs,
                    "fix_rounds": self._fix_rounds,
                }
            )
            return

        # Non-quota error: record as failed but continue with remaining agents.
        # The briefing result will be None for this agent.
        if not self._briefing_expected:
            # All expected agents have responded (or failed).
            if (
                "contrarian" in self._briefing_actors
                and "contrarian" not in self._briefing_results
                and agent_name != "contrarian"
            ):
                self._start_contrarian()
            else:
                self._briefing_complete()

    def _handle_detail_error(self, message):
        """Requeue the unit on timeout / transient error, or fail it.

        The decomposer echoes ``unit_id`` in its prompt_error reply for
        the detail phase. We decrement in-flight, clear the unit's
        dispatch info, and either push it back onto the queue for
        another pool actor to try or give up after ``MAX_DETAIL_RETRIES``
        attempts. Quota errors are fatal regardless of retry count.
        """
        if not isinstance(message, dict):
            return

        unit_id = message.get("unit_id", "")
        error_str = message.get("error", "unknown error")
        is_quota = message.get("quota_exhausted", False)

        # Quota exhaustion is fatal — no point retrying the same unit
        # against a dead provider; the other pool actors will hit it too.
        if is_quota:
            self._handle_error(message)
            return

        # Drop in-flight bookkeeping for this unit.
        self._detail_dispatch_info.pop(unit_id, None)
        if getattr(self, "_detail_in_flight", 0) > 0:
            self._detail_in_flight -= 1

        attempts = self._detail_retries.get(unit_id, 0) + 1
        self._detail_retries[unit_id] = attempts

        if attempts > MAX_DETAIL_RETRIES:
            # Give up on this unit — keep processing the rest so the
            # operator has a failure to inspect rather than a silent
            # hang.
            self._pending_detail_ids.discard(unit_id)
            self._emit_output(
                "refuel",
                f"Detail unit {unit_id!r} failed after {attempts} attempts: {error_str}",
                level="error",
                source=_SOURCE,
                metadata={"unit_id": unit_id, "attempts": attempts},
            )
            # If the queue is now empty and nothing else is in flight,
            # the remaining pending set will keep _pending_detail_ids
            # non-empty, so continue. If we just gave up on the last
            # unit and no more are in flight or queued, proceed to
            # validation with what we've got.
            if not self._pending_detail_ids:
                self._details = {"details": self._accumulated_details}
                self._specs = self._merge_to_specs()
                self.send(
                    self._validator,
                    {"type": "validate", "specs": self._specs},
                )
            else:
                self._dispatch_pending_details()
            return

        # Still within retry budget — push back onto the queue.
        self._emit_output(
            "refuel",
            f"Detail unit {unit_id!r} failed (attempt {attempts}/"
            f"{MAX_DETAIL_RETRIES + 1}), requeuing: {error_str}",
            level="warning",
            source=_SOURCE,
            metadata={"unit_id": unit_id, "attempts": attempts},
        )
        if unit_id:
            self._detail_queue.append(unit_id)
        self._dispatch_pending_details()

    def _handle_error(self, message):
        """Report error to workflow — shutdown agents first."""
        if isinstance(message, dict):
            phase = message.get("phase", "")
            error_str = message.get("error", "unknown error")
            is_quota = message.get("quota_exhausted", False)
        else:
            # Legacy string path
            phase = ""
            error_str = str(message)
            is_quota = False

        if is_quota:
            from maverick.exceptions.quota import parse_quota_reset

            reset_time = parse_quota_reset(error_str)
            reset_suffix = f" (resets {reset_time})" if reset_time else ""
            error_msg = f"Provider quota exhausted{reset_suffix}"
        else:
            prefix = f"Decomposer error ({phase}): " if phase else ""
            error_msg = f"{prefix}{error_str}"

        self._shutdown_all()
        self._emit_output(
            "refuel",
            f"Decomposition failed: {error_msg}",
            level="error",
            source=_SOURCE,
        )
        self._mark_done(
            {
                "success": False,
                "error": error_msg,
                "specs": self._specs,
                "fix_rounds": self._fix_rounds,
            }
        )

    def _shutdown_all(self):
        """Shutdown all agent actors (decomposer + briefing)."""
        for addr in [self._decomposer] + list(self._decomposer_pool):
            if addr:
                self.send(addr, {"type": "shutdown"})
        for addr in self._briefing_actors.values():
            if addr:
                self.send(addr, {"type": "shutdown"})

    def _emit_agent_completed_with_error(
        self, step_name: str, agent_name: str, duration_seconds: float, error: str
    ) -> None:
        """Emit an AgentCompleted event with failure status."""
        from maverick.events import AgentCompleted

        self._emit(
            AgentCompleted(
                step_name=step_name,
                agent_name=agent_name,
                duration_seconds=duration_seconds,
                success=False,
                error=error,
            )
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _merge_to_specs(self):
        """Merge outline + details into WorkUnitSpec list."""
        from maverick.workflows.refuel_maverick.models import WorkUnitSpec

        work_units = self._outline.get("work_units", []) if self._outline else []
        details = self._details.get("details", []) if self._details else []

        detail_map = {}
        for d in details:
            if isinstance(d, dict):
                detail_map[d.get("id", "")] = d

        specs = []
        for wu in work_units:
            if not isinstance(wu, dict):
                continue
            wu_id = wu.get("id", "")
            detail = detail_map.get(wu_id, {})
            merged = {
                "id": wu_id,
                "task": wu.get("task", ""),
                "sequence": wu.get("sequence", 0),
                "parallel_group": wu.get("parallel_group"),
                "depends_on": wu.get("depends_on", []),
                "file_scope": wu.get("file_scope", {}),
                "instructions": detail.get("instructions", ""),
                "acceptance_criteria": detail.get("acceptance_criteria", []),
                "verification": detail.get("verification", []),
                "test_specification": detail.get("test_specification", ""),
            }
            try:
                specs.append(WorkUnitSpec.model_validate(merged))
            except Exception:
                specs.append(merged)
        return specs

    def _extract_deps(self):
        deps = []
        for spec in self._specs:
            sid = spec.id if hasattr(spec, "id") else spec.get("id", "")
            dep_list = (
                spec.depends_on if hasattr(spec, "depends_on") else spec.get("depends_on", [])
            )
            for dep_id in dep_list:
                deps.append([sid, dep_id])
        return deps

    def _enrich_gaps(self, gaps):
        flight_plan = self._config.get("flight_plan")
        if not flight_plan:
            return gaps

        sc_list = getattr(flight_plan, "success_criteria", [])
        sc_map = {}
        for i, sc in enumerate(sc_list):
            ref = getattr(sc, "ref", None) or f"SC-{i + 1:03d}"
            text = getattr(sc, "text", str(sc))
            sc_map[ref] = text

        enriched = []
        for gap in gaps:
            for ref, text in sc_map.items():
                if ref in gap:
                    gap = f"{gap} — Full text: {text}"
                    break
            enriched.append(gap)
        return enriched
