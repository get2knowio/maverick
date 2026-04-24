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
from maverick.tools.agent_inbox.models import (
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
    detail_session_max_turns: int = 5
    fix_session_max_turns: int = 1
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

        # Briefing state
        self._briefing_results: dict[str, SupervisorInboxPayload] = {}
        self._briefing_expected: set[str] = set()
        self._briefing_start_times: dict[str, float] = {}
        self._awaiting_fix = False

        # Seed outline from cache if pre-populated by workflow.
        cached_outline = self._inputs.initial_payload.get("outline")
        if isinstance(cached_outline, dict):
            from maverick.tools.agent_inbox.models import (
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
        self._decomposer_pool: list[xo.ActorRef] = []
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
            address=self.address,
            uid=f"{self.uid.decode()}:bead-creator",
        )

        # --- Briefing actors ---
        self._briefing_actors: dict[str, xo.ActorRef] = {}
        if not self._inputs.skip_briefing:
            for name, tool, method in REFUEL_BRIEFING_CONFIG:
                self._briefing_actors[name] = await xo.create_actor(
                    BriefingActor,
                    self_ref,
                    agent_name=name,
                    mcp_tool=tool,
                    forward_method=method,
                    cwd=self._inputs.cwd,
                    config=self._inputs.config,
                    address=self.address,
                    uid=f"{self.uid.decode()}:briefing-{name}",
                )

    async def __pre_destroy__(self) -> None:
        """Destroy all children so their __pre_destroy__ hooks run."""
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

        await asyncio.gather(
            *[
                self._briefing_actors[name].send_briefing(
                    BriefingRequest(agent_name=name, prompt=prompt)
                )
                for name in PARALLEL_BRIEFING_NAMES
                if name in self._briefing_actors
            ]
        )

        missing = self._briefing_expected - set(self._briefing_results.keys())
        if missing:
            raise RuntimeError(f"Briefing agents did not submit tool calls: {sorted(missing)}")

        if "contrarian" in self._briefing_actors:
            await self._run_contrarian_phase()

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

        if "contrarian" not in self._briefing_results:
            raise RuntimeError("Contrarian briefing did not submit its tool call")

    # ------------------------------------------------------------------
    # Decomposition phase
    # ------------------------------------------------------------------

    async def _run_decompose_phase(self) -> None:
        import time as _time

        await self._emit_phase_started("decompose", "Decomposing")
        decompose_start = _time.monotonic()

        # Outline
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
                raise RuntimeError("Decomposer did not submit an outline")
        else:
            unit_ids_seed = [wu.id for wu in self._outline.work_units if wu.id]
            await self._emit_output(
                "refuel",
                f"Outline loaded from cache: {len(unit_ids_seed)} work unit(s)",
                level="success",
                metadata={"unit_count": len(unit_ids_seed)},
            )

        # Details
        unit_ids = [wu.id for wu in self._outline.work_units if wu.id]
        await self._run_detail_fan_out(unit_ids)

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
                "specs": self._specs,
                "fix_rounds": self._fix_rounds,
                "error": beads_result.error or None,
            }
        )

    async def _run_detail_fan_out(self, unit_ids: list[str]) -> None:
        if not unit_ids:
            await self._emit_output(
                "refuel",
                "No units to detail; proceeding to validation",
            )
            return

        pool = self._decomposer_pool or [self._decomposer]
        pool_size = len(pool)

        # Broadcast context once per pool actor so per-unit requests stay tiny.
        context = DecomposerContext(
            outline_json=json.dumps(self._outline_payload()),
            flight_plan_content=self._inputs.initial_payload.get("flight_plan_content", ""),
            verification_properties=self._inputs.initial_payload.get(
                "verification_properties", ""
            ),
        )
        await asyncio.gather(*[ref.set_context(context) for ref in pool])

        self._pending_detail_ids = set(unit_ids)
        await self._emit_output(
            "refuel",
            f"Detailing {len(unit_ids)} unit(s) across {pool_size} actor(s)",
        )

        # Bound concurrency at pool_size * 2 in-flight requests.
        semaphore = asyncio.Semaphore(max(1, pool_size * 2))

        async def _one(index: int, unit_id: str) -> None:
            assigned = pool[index % pool_size]
            for attempt in range(MAX_DETAIL_RETRIES + 1):
                async with semaphore:
                    try:
                        await xo.wait_for(
                            assigned.send_detail(DetailRequest.for_unit(unit_id)),
                            timeout=STALE_IN_FLIGHT_SECONDS,
                        )
                    except TimeoutError:
                        if attempt < MAX_DETAIL_RETRIES:
                            await self._emit_output(
                                "refuel",
                                f"Unit {unit_id!r} timed out (attempt {attempt + 1}), retrying",
                                level="warning",
                            )
                            continue
                        await self._emit_output(
                            "refuel",
                            f"Unit {unit_id!r} timed out after retries — abandoning",
                            level="error",
                        )
                        self._pending_detail_ids.discard(unit_id)
                        return
                # send_detail returned. If the tool call landed, unit has been
                # removed from pending_detail_ids by detail_ready. Otherwise,
                # the agent skipped its tool call; retry once.
                if unit_id not in self._pending_detail_ids:
                    return
                if attempt < MAX_DETAIL_RETRIES:
                    await self._emit_output(
                        "refuel",
                        f"Unit {unit_id!r} prompt completed without tool call, retrying",
                        level="warning",
                    )
                    continue
                await self._emit_output(
                    "refuel",
                    f"Unit {unit_id!r} abandoned after retries",
                    level="error",
                )
                self._pending_detail_ids.discard(unit_id)
                return

        await asyncio.gather(*[_one(i, uid) for i, uid in enumerate(unit_ids)])

    async def _request_fix(self, validation: ValidationResult) -> None:
        self._fix_rounds += 1
        gaps = self._enrich_gaps(list(validation.gaps))
        await self._emit_output(
            "refuel",
            f"Validation found {len(gaps)} gap(s); "
            f"requesting fix (round {self._fix_rounds}/{MAX_FIX_ROUNDS})",
            level="warning",
            metadata={"gap_count": len(gaps), "fix_round": self._fix_rounds},
        )
        self._awaiting_fix = True
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
        for detail in payload.details:
            uid = detail.id
            self._accumulated_details = [d for d in self._accumulated_details if d.id != uid]
            self._accumulated_details.append(detail)
            self._pending_detail_ids.discard(uid)
            # Per-unit cache write so a killed run resumes at N-of-M.
            self._cache_detail(uid, detail)
        remaining = len(self._pending_detail_ids)
        done = len(self._accumulated_details)
        if remaining > 0:
            await self._emit_output(
                "refuel",
                f"Detail {done}/{done + remaining} complete",
            )

    @xo.no_lock
    async def fix_ready(self, payload: SubmitFixPayload) -> None:
        if payload.work_units:
            self._outline = SubmitOutlinePayload(work_units=payload.work_units)
        if payload.details:
            self._details = SubmitDetailsPayload(details=payload.details)
            self._accumulated_details = list(payload.details)
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
        loop — this callback only logs them at debug.
        """
        if error.phase == "detail":
            logger.debug(
                "refuel_supervisor.detail_prompt_error",
                unit_id=error.unit_id,
                error=error.error,
                quota=error.quota_exhausted,
            )
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
        self, step_name: str, agent_name: str, duration_seconds: float
    ) -> None:
        await self._emit(
            AgentCompleted(
                step_name=step_name,
                agent_name=agent_name,
                duration_seconds=duration_seconds,
            )
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
        from maverick.workflows.refuel_maverick.models import WorkUnitSpec

        work_units = self._outline.work_units if self._outline else ()
        details = self._details.details if self._details else ()

        detail_map: dict[str, WorkUnitDetailPayload] = {d.id: d for d in details}
        specs: list[Any] = []
        for wu in work_units:
            detail = detail_map.get(wu.id)
            merged = {
                "id": wu.id,
                "task": wu.task,
                "sequence": wu.sequence,
                "parallel_group": wu.parallel_group,
                "depends_on": list(wu.depends_on),
                "file_scope": dump_supervisor_payload(wu.file_scope),
                "instructions": detail.instructions if detail else "",
                "acceptance_criteria": (
                    [dump_supervisor_payload(ac) for ac in detail.acceptance_criteria]
                    if detail
                    else []
                ),
                "verification": list(detail.verification) if detail else [],
                "test_specification": detail.test_specification if detail else "",
            }
            try:
                specs.append(WorkUnitSpec.model_validate(merged))
            except Exception:  # noqa: BLE001 — fall back to raw dict on parse failure
                specs.append(merged)
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
