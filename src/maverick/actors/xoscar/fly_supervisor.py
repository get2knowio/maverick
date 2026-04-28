"""xoscar FlySupervisor — async-native fly (bead-loop) orchestrator.

Per-bead state machine (linearised now that every step is awaitable):

    implement → gate (with fix loop) → AC (with fix loop)
             → spec (with fix loop) → review (with fix loop) → commit

Aggregate review runs once after the bead loop if more than one bead
was processed successfully. Per-bead runway recording feeds future
briefings; review-round exhaustion creates a human-assigned review
bead and commits with a ``needs-human-review`` tag so the epic history
reflects the escalation. Watch mode polls for new ready beads at a
configurable interval.

Stale-in-flight watchdog behaviour from the Thespian supervisor is
replaced by per-step ``xo.wait_for`` around long-running agent calls.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import xoscar as xo

from maverick.actors.xoscar.ac_check import ACCheckActor
from maverick.actors.xoscar.committer import CommitterActor
from maverick.actors.xoscar.gate import GateActor
from maverick.actors.xoscar.implementer import ImplementerActor
from maverick.actors.xoscar.messages import (
    ACRequest,
    AggregateReviewRequest,
    CommitRequest,
    FlyFixRequest,
    GateRequest,
    ImplementRequest,
    NewBeadRequest,
    PromptError,
    ReviewRequest,
    SpecRequest,
)
from maverick.actors.xoscar.reviewer import ReviewerActor
from maverick.actors.xoscar.spec_check import SpecCheckActor
from maverick.events import ProgressEvent, StepOutput
from maverick.logging import get_logger
from maverick.tools.agent_inbox.models import (
    ReviewFindingPayload,
    SubmitFixResultPayload,
    SubmitImplementationPayload,
    SubmitReviewPayload,
)

logger = get_logger(__name__)

MAX_REVIEW_ROUNDS = 3
MAX_GATE_FIX_ATTEMPTS = 2
MAX_SPEC_FIX_ATTEMPTS = 2
AGGREGATE_REVIEW_THRESHOLD = 2  # run aggregate review when ≥ this many beads done
_SOURCE = "fly-supervisor"

#: Ordered tier names (low → high intelligence). Matches WorkUnitComplexity.
TIER_ORDER: tuple[str, ...] = ("trivial", "simple", "moderate", "complex")
#: Sentinel name for the single-actor fallback when no tiers are configured.
_DEFAULT_TIER = "_default"
#: Where unclassified beads (decomposer didn't classify, or older runs) route.
_FALLBACK_COMPLEXITY = "moderate"


def _extract_complexity_from_md(work_unit_md: str) -> str | None:
    """Read ``complexity:`` from a work-unit markdown's YAML frontmatter.

    Returns the value when it parses as a known tier name, else ``None``.
    Robust against missing frontmatter, missing key, or unknown values —
    callers treat ``None`` as "unclassified" and fall back to the default
    tier in :meth:`_resolve_implementer_tier`.
    """
    if not work_unit_md or not work_unit_md.lstrip().startswith("---"):
        return None
    # Split on the second `---` to bound the frontmatter scan.
    body = work_unit_md.lstrip()
    parts = body.split("---", 2)
    if len(parts) < 3:
        return None
    fm_block = parts[1]
    for line in fm_block.split("\n"):
        stripped = line.strip()
        if stripped.startswith("complexity:"):
            value = stripped.split(":", 1)[1].strip().strip("\"'")
            if value in TIER_ORDER:
                return value
            return None
    return None


@dataclass(frozen=True)
class FlyInputs:
    """Construction payload for ``FlySupervisor``."""

    cwd: str
    epic_id: str = ""
    config: Any = None  # Base StepConfig — implementer when reviewer_config is set.
    # Reviewer's own resolved StepConfig (from actors.fly.reviewer / steps.review
    # / agents.reviewer). When set, the no-tiers ReviewerActor uses this instead
    # of falling back to ``config`` (which is the implementer's config). When
    # tiers are configured, this is the per-tier base before override merging.
    # ``None`` preserves the legacy single-config behaviour for older callers.
    reviewer_config: Any = None
    # 0 = unlimited; see fly_beads.constants.MAX_BEADS for the rationale.
    max_beads: int = 0
    validation_commands: dict[str, tuple[str, ...]] | None = None
    project_type: str = "rust"
    completed_bead_ids: tuple[str, ...] = ()
    # Bead-context enrichment: the supervisor loads work-unit markdown
    # and briefing from `.maverick/plans/<flight_plan_name>/` when set.
    flight_plan_name: str = ""
    # Watch mode: when true, the bead loop polls for new ready beads
    # every ``watch_interval`` seconds, up to ``max_idle_polls`` times.
    watch: bool = False
    watch_interval: int = 30
    max_idle_polls: int = 60
    # Per-bead complexity tier routing. When set, the supervisor spawns
    # one ImplementerActor per defined tier (each with its own ACP
    # subprocess) and dispatches each bead to the actor matching the
    # decomposer-assigned ``complexity``. None = single-actor fallback
    # (the legacy behaviour).
    implementer_tiers: Any = None  # ImplementerTiersConfig | None
    # Same shape for the reviewer (FUTURE.md §2.10 Phase 3). When set,
    # one ReviewerActor per defined tier; the bead's complexity routes
    # the review prompt. No escalation (review is one-shot per round).
    reviewer_tiers: Any = None  # ReviewerTiersConfig | None


class FlySupervisor(xo.Actor):
    """Orchestrates the fly bead loop."""

    def __init__(self, inputs: FlyInputs) -> None:
        super().__init__()
        if not inputs.cwd:
            raise ValueError("FlySupervisor requires 'cwd'")
        self._inputs = inputs

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def __post_create__(self) -> None:
        self._event_queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        self._done = False
        self._terminal_result: dict[str, Any] | None = None
        self._driver_task: asyncio.Task[None] | None = None

        # Per-bead "result landed" slots — set by agent callbacks during
        # the awaited ACP call, read by the driver right after the call
        # returns. Reset at the start of each bead / fix round.
        self._last_implementation: SubmitImplementationPayload | None = None
        self._last_fix_result: SubmitFixResultPayload | None = None
        self._last_review: SubmitReviewPayload | None = None
        self._last_aggregate_review: SubmitReviewPayload | None = None
        self._last_parse_error: tuple[str, str] | None = None

        # Accumulators. ``_completed_beads`` is cumulative across runs —
        # it starts seeded with ``_inputs.completed_bead_ids`` (loaded
        # from the checkpoint) so the loop's "skip already-done" guard
        # works on resume. ``_processed_this_run`` is the new-work
        # counter that ``--max-beads`` caps and that the terminal report
        # surfaces, so resuming with ``--max-beads 2`` against a
        # checkpoint with 10 prior IDs reports 2, not 12.
        self._completed_beads: list[str] = list(self._inputs.completed_bead_ids)
        self._completed_titles: list[str] = []
        self._processed_this_run: int = 0
        self._current_bead_id: str | None = None
        # Reference to the in-flight bead dict (with ``complexity``,
        # ``work_unit_md``, etc.) for tier routing during fix loops.
        self._current_bead: dict[str, Any] | None = None
        self._review_findings_for_bead: list[SubmitReviewPayload] = []
        self._last_review_findings: tuple[ReviewFindingPayload, ...] = ()

        # Bead-context enrichment (populated lazily by _load_bead_context).
        self._briefing_context: str = ""
        self._work_units_cache: dict[str, dict[str, str]] = {}

        self_ref = self.ref()

        # Implementer wiring — either single actor (legacy) or per-tier
        # actors when complexity routing is configured. ``self._implementers``
        # is a tier-name → ActorRef map either way; legacy mode uses the
        # ``_DEFAULT_TIER`` sentinel.
        self._implementers: dict[str, xo.ActorRef] = {}
        if self._inputs.implementer_tiers is None:
            self._implementers[_DEFAULT_TIER] = await xo.create_actor(
                ImplementerActor,
                self_ref,
                cwd=self._inputs.cwd,
                config=self._inputs.config,
                address=self.address,
                uid=f"{self.uid.decode()}:implementer",
            )
        else:
            tiers = self._inputs.implementer_tiers
            for tier_name in TIER_ORDER:
                tier_override = getattr(tiers, tier_name, None)
                if tier_override is None:
                    continue
                tier_config = self._merge_tier_config(
                    base=self._inputs.config,
                    override=tier_override,
                )
                self._implementers[tier_name] = await xo.create_actor(
                    ImplementerActor,
                    self_ref,
                    cwd=self._inputs.cwd,
                    config=tier_config,
                    address=self.address,
                    uid=f"{self.uid.decode()}:implementer:{tier_name}",
                )
            if not self._implementers:
                # Safety: empty tiers config is treated as "no tiers".
                self._implementers[_DEFAULT_TIER] = await xo.create_actor(
                    ImplementerActor,
                    self_ref,
                    cwd=self._inputs.cwd,
                    config=self._inputs.config,
                    address=self.address,
                    uid=f"{self.uid.decode()}:implementer",
                )

        # Backward-compat alias used by code paths that don't care about
        # tier routing (e.g. fix loops with no escalation pending).
        self._implementer = next(iter(self._implementers.values()))

        # Per-bead escalation tracking: how many fix rounds have run at
        # the bead's current tier. Reset when a new bead starts. Read by
        # _resolve_implementer_tier when escalation_threshold is reached.
        self._bead_escalation_level: int = 0
        # Reviewer wiring — mirrors the implementer tier pattern. When
        # ``reviewer_tiers`` is None, one ReviewerActor under the
        # _DEFAULT_TIER sentinel; when set, one per defined tier.
        # Reviewer base config defaults to its own resolved StepConfig
        # (``inputs.reviewer_config``) so it doesn't inherit the
        # implementer's provider/model. Older callers that only populate
        # ``inputs.config`` keep the legacy shared-config behaviour.
        reviewer_base = (
            self._inputs.reviewer_config
            if self._inputs.reviewer_config is not None
            else self._inputs.config
        )
        self._reviewers: dict[str, xo.ActorRef] = {}
        if self._inputs.reviewer_tiers is None:
            self._reviewers[_DEFAULT_TIER] = await xo.create_actor(
                ReviewerActor,
                self_ref,
                cwd=self._inputs.cwd,
                config=reviewer_base,
                address=self.address,
                uid=f"{self.uid.decode()}:reviewer",
            )
        else:
            r_tiers = self._inputs.reviewer_tiers
            for tier_name in TIER_ORDER:
                tier_override = getattr(r_tiers, tier_name, None)
                if tier_override is None:
                    continue
                tier_config = self._merge_tier_config(
                    base=reviewer_base,
                    override=tier_override,
                )
                self._reviewers[tier_name] = await xo.create_actor(
                    ReviewerActor,
                    self_ref,
                    cwd=self._inputs.cwd,
                    config=tier_config,
                    address=self.address,
                    uid=f"{self.uid.decode()}:reviewer:{tier_name}",
                )
            if not self._reviewers:
                # Empty tiers config — same safety net as implementer.
                self._reviewers[_DEFAULT_TIER] = await xo.create_actor(
                    ReviewerActor,
                    self_ref,
                    cwd=self._inputs.cwd,
                    config=reviewer_base,
                    address=self.address,
                    uid=f"{self.uid.decode()}:reviewer",
                )

        # Backward-compat alias for code paths that don't care about
        # tier routing (e.g. the aggregate review which uses any reviewer).
        self._reviewer = next(iter(self._reviewers.values()))
        self._gate = await xo.create_actor(
            GateActor,
            validation_commands=self._inputs.validation_commands,
            address=self.address,
            uid=f"{self.uid.decode()}:gate",
        )
        self._ac = await xo.create_actor(
            ACCheckActor,
            address=self.address,
            uid=f"{self.uid.decode()}:ac",
        )
        self._spec = await xo.create_actor(
            SpecCheckActor,
            project_type=self._inputs.project_type,
            address=self.address,
            uid=f"{self.uid.decode()}:spec",
        )
        self._committer = await xo.create_actor(
            CommitterActor,
            address=self.address,
            uid=f"{self.uid.decode()}:committer",
        )

    async def __pre_destroy__(self) -> None:
        for ref in (
            *self._implementers.values(),
            *self._reviewers.values(),
            self._gate,
            self._ac,
            self._spec,
            self._committer,
        ):
            try:
                await xo.destroy_actor(ref)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "fly_supervisor.destroy_child_failed",
                    uid=getattr(ref, "uid", "?"),
                    error=str(exc),
                )

    # ------------------------------------------------------------------
    # Tier routing (FUTURE.md §2.10 Phase 2)
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_tier_config(base: Any, override: Any) -> Any:
        """Merge an ImplementerTierConfig override over a base StepConfig.

        Each field set on the override replaces the base. Fields left as
        None on the override fall through to base. Returns a new StepConfig
        (StepConfig is frozen, so this is a model_copy).
        """
        if base is None:
            # No base — synthesize a minimal StepConfig from the override.
            from maverick.executor.config import StepConfig

            return StepConfig(
                provider=override.provider,
                model_id=override.model_id,
                timeout=override.timeout,
                max_tokens=override.max_tokens,
                temperature=override.temperature,
            )
        updates: dict[str, Any] = {}
        for field_name in (
            "provider",
            "model_id",
            "timeout",
            "max_tokens",
            "temperature",
        ):
            value = getattr(override, field_name, None)
            if value is not None:
                updates[field_name] = value
        if not updates:
            return base
        return base.model_copy(update=updates)

    @staticmethod
    def _resolve_tier_in(
        actors_by_tier: dict[str, xo.ActorRef],
        complexity: str | None,
        escalation_level: int = 0,
    ) -> str:
        """Pick the tier name for ``complexity`` in ``actors_by_tier``.

        Generalized version of the implementer tier resolver — used for
        every actor type that participates in tier routing (implementer,
        reviewer, decomposer-detail).

        Two-step resolution:

        1. **Base tier from complexity.** ``trivial / simple / moderate /
           complex`` map to their like-named tier when defined; missing
           tiers round DOWN to the nearest cheaper defined tier (and
           round UP only when nothing at-or-below exists). Unrecognised
           or ``None`` complexity defaults to ``moderate``.
        2. **Escalation walks defined tiers upward.** Each escalation
           step jumps to the *next-defined* tier above the current one,
           skipping any undefined gaps. Caps at the highest defined
           tier. ``escalation_level=0`` (the default) means "no
           escalation"; reviewers and decomposers always pass 0.

        Returns ``_DEFAULT_TIER`` when ``actors_by_tier`` is in legacy
        single-actor mode (``_DEFAULT_TIER`` is the only key).
        """
        if _DEFAULT_TIER in actors_by_tier:
            return _DEFAULT_TIER

        base = complexity if complexity in TIER_ORDER else _FALLBACK_COMPLEXITY
        base_idx = TIER_ORDER.index(base)

        # Step 1: round-down to nearest defined tier at-or-below base.
        current_idx: int | None = None
        for idx in range(base_idx, -1, -1):
            if TIER_ORDER[idx] in actors_by_tier:
                current_idx = idx
                break
        if current_idx is None:
            # Nothing at-or-below; round UP to first defined tier above.
            for idx in range(base_idx + 1, len(TIER_ORDER)):
                if TIER_ORDER[idx] in actors_by_tier:
                    current_idx = idx
                    break
        if current_idx is None:
            # Defensive — every tier map should have at least one entry.
            return next(iter(actors_by_tier))

        # Step 2: apply escalation_level by walking defined tiers up.
        for _ in range(max(0, escalation_level)):
            next_idx: int | None = None
            for idx in range(current_idx + 1, len(TIER_ORDER)):
                if TIER_ORDER[idx] in actors_by_tier:
                    next_idx = idx
                    break
            if next_idx is None:
                break  # already at top defined tier
            current_idx = next_idx
        return TIER_ORDER[current_idx]

    def _resolve_implementer_tier(
        self,
        complexity: str | None,
        escalation_level: int = 0,
    ) -> str:
        """Backward-compat wrapper — see :meth:`_resolve_tier_in`."""
        return self._resolve_tier_in(self._implementers, complexity, escalation_level)

    def _resolve_reviewer_tier(self, complexity: str | None) -> str:
        """Pick the reviewer tier for a bead. No escalation."""
        return self._resolve_tier_in(self._reviewers, complexity, 0)

    def _implementer_for(
        self,
        complexity: str | None,
        escalation_level: int = 0,
    ) -> tuple[str, xo.ActorRef]:
        """Return ``(tier_name, actor_ref)`` for routing a bead's prompt."""
        tier_name = self._resolve_implementer_tier(complexity, escalation_level)
        return tier_name, self._implementers[tier_name]

    def _reviewer_for(self, complexity: str | None) -> tuple[str, xo.ActorRef]:
        """Return ``(tier_name, actor_ref)`` for routing a bead's review."""
        tier_name = self._resolve_reviewer_tier(complexity)
        return tier_name, self._reviewers[tier_name]

    # ------------------------------------------------------------------
    # Workflow entry point
    # ------------------------------------------------------------------

    @xo.generator
    async def run(self) -> AsyncGenerator[ProgressEvent, None]:
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
        try:
            await self._bead_loop()
            if len(self._completed_beads) >= AGGREGATE_REVIEW_THRESHOLD:
                await self._maybe_aggregate_review()
        except Exception as exc:  # noqa: BLE001
            logger.exception("fly_supervisor.drive_failed", error=str(exc))
            await self._emit_output(
                "fly",
                f"Fly loop failed: {exc}",
                level="error",
            )
            self._mark_done(
                {
                    "success": False,
                    "error": str(exc),
                    "beads_completed": self._processed_this_run,
                    "completed_bead_ids": list(self._completed_beads),
                }
            )
            return

        self._mark_done(
            {
                "success": True,
                "beads_completed": self._processed_this_run,
                "completed_bead_ids": list(self._completed_beads),
            }
        )

    async def _bead_loop(self) -> None:
        processed = 0
        idle_polls = 0
        max_idle = self._inputs.max_idle_polls if self._inputs.watch else 0
        # ``max_beads <= 0`` means unlimited — drain whatever's ready.
        # The loop still terminates naturally when ``_select_next_bead``
        # returns nothing (and watch mode hits ``max_idle`` polls).
        unlimited = self._inputs.max_beads <= 0
        await self._emit_output(
            "fly",
            f"Starting bead loop (epic: {self._inputs.epic_id or 'any'})",
        )
        while unlimited or processed < self._inputs.max_beads:
            bead = await self._select_next_bead()
            if bead is None or not bead.get("found"):
                if self._inputs.watch and idle_polls < max_idle:
                    idle_polls += 1
                    await self._emit_output(
                        "fly",
                        f"No beads ready; waiting ({idle_polls}/{max_idle})",
                    )
                    await asyncio.sleep(self._inputs.watch_interval)
                    continue
                await self._emit_output("fly", "No more beads to process")
                return
            idle_polls = 0
            bead_id = bead.get("bead_id", "")
            if not bead_id or bead_id in self._completed_beads:
                continue
            ok = await self._process_bead(bead)
            if ok:
                self._completed_beads.append(bead_id)
                self._completed_titles.append(bead.get("title", ""))
                processed += 1
                self._processed_this_run = processed
            # If a bead failed (ok=False), the escalation path already
            # emitted a warning and recorded the outcome. Move on.

    async def _select_next_bead(self) -> dict[str, Any] | None:
        from maverick.library.actions.beads import select_next_bead

        try:
            result = await select_next_bead(epic_id=self._inputs.epic_id)
            return result.to_dict()
        except Exception as exc:  # noqa: BLE001
            await self._emit_output(
                "fly",
                f"Bead selection failed: {exc}",
                level="error",
            )
            return None

    async def _process_bead(self, bead: dict[str, Any]) -> bool:
        bead_id = bead["bead_id"]
        title = bead.get("title", "")
        self._current_bead_id = bead_id
        self._current_bead = bead
        self._last_implementation = None
        self._last_review = None
        self._review_findings_for_bead = []
        self._last_review_findings = ()

        await self._emit_output(
            "fly",
            f"Processing bead {bead_id}: {title[:80]}",
            metadata={"bead_id": bead_id, "title": title},
        )

        # Enrich bead with work-unit markdown + briefing (best-effort).
        # Sets bead["complexity"] from the work-unit YAML frontmatter when
        # the decomposer classified it (Phase 1 always does, older beads
        # may not).
        await self._load_bead_context(bead)

        # Reset per-bead escalation tracker for tier routing.
        self._bead_escalation_level = 0

        # Pick the implementer tier based on bead complexity. In legacy
        # (no-tiers) mode this always returns the single fallback actor;
        # in tier mode it picks the matching tier actor.
        tier_name, implementer = self._implementer_for(
            bead.get("complexity"),
            escalation_level=0,
        )
        if tier_name != _DEFAULT_TIER:
            await self._emit_output(
                "fly",
                f"Routing bead {bead_id} (complexity={bead.get('complexity') or 'unclassified'}) "
                f"to implementer tier '{tier_name}'",
                metadata={
                    "bead_id": bead_id,
                    "complexity": bead.get("complexity"),
                    "implementer_tier": tier_name,
                    "escalation_level": 0,
                },
            )

        # Rotate sessions for the new bead. Only the *selected* tier
        # actors need a session rotation — the others are idle until a
        # bead routes to them.
        complexity = bead.get("complexity")
        _, reviewer = self._reviewer_for(complexity)
        await implementer.new_bead(NewBeadRequest(bead_id=bead_id))
        await reviewer.new_bead(NewBeadRequest(bead_id=bead_id))

        # ---- Implement ----
        prompt = self._build_implement_prompt(bead)
        await implementer.send_implement(ImplementRequest(bead_id=bead_id, prompt=prompt))
        if self._last_implementation is None:
            await self._escalate(bead, "Implementer did not submit results")
            return False

        # ---- Gate fix loop ----
        if not await self._gate_loop(bead):
            return False

        # ---- AC fix loop ----
        if not await self._ac_loop(bead):
            return False

        # ---- Spec fix loop ----
        if not await self._spec_loop(bead):
            return False

        # ---- Review fix loop ----
        review_rounds, approved = await self._review_loop(bead)
        if not approved and review_rounds == 0:
            # Reviewer didn't submit at all (prompt failed, MCP dropped).
            return False

        # ---- Commit ----
        # If review rounds were exhausted without approval, commit with the
        # needs-human-review tag and create the escalation bead. The epic
        # still captures the work; a human can follow up via the bead.
        tag: str | None = None
        if not approved:
            tag = "needs-human-review"
            await self._escalate(
                bead,
                "Review rounds exhausted",
                findings=[f.issue for f in self._last_review_findings],
                commit_after=False,
            )

        commit_result = await self._committer.commit(
            CommitRequest(
                bead_id=bead_id,
                title=title,
                cwd=self._inputs.cwd,
                tag=tag,
            )
        )
        if not commit_result.success:
            await self._emit_output(
                "fly",
                f"Commit failed for {bead_id}: {commit_result.error}",
                level="error",
            )
            return False

        await self._record_bead_outcome(bead, commit_success=True, review_rounds=review_rounds)

        await self._emit_output(
            "fly",
            f"Bead {bead_id} complete ({commit_result.commit_sha or '?'})",
            level="success",
            metadata={
                "bead_id": bead_id,
                "commit_sha": commit_result.commit_sha,
                "needs_human_review": tag is not None,
            },
        )
        return True

    # ------------------------------------------------------------------
    # Per-phase fix loops
    # ------------------------------------------------------------------

    async def _gate_loop(self, bead: dict[str, Any]) -> bool:
        bead_id = bead["bead_id"]
        for attempt in range(MAX_GATE_FIX_ATTEMPTS + 1):
            result = await self._gate.gate(GateRequest(cwd=self._inputs.cwd))
            if result.passed:
                return True
            if attempt >= MAX_GATE_FIX_ATTEMPTS:
                await self._escalate(
                    bead,
                    "Gate fix attempts exhausted",
                    findings=[result.summary],
                )
                return False
            await self._emit_output(
                "fly",
                f"Gate failed (attempt {attempt + 1}): {result.summary}",
                level="warning",
            )
            if not await self._send_fix(
                bead_id, phase="gate", context=result.summary, round=attempt + 1
            ):
                return False
        return False

    async def _ac_loop(self, bead: dict[str, Any]) -> bool:
        bead_id = bead["bead_id"]
        description = bead.get("description", bead.get("title", ""))
        # AC has a single fix-attempt retry in the legacy supervisor.
        result = await self._ac.ac_check(ACRequest(description=description, cwd=self._inputs.cwd))
        if result.passed:
            return True
        await self._emit_output(
            "fly",
            f"AC check failed: {'; '.join(result.reasons)}",
            level="warning",
        )
        if not await self._send_fix(
            bead_id,
            phase="ac",
            context="\n".join(result.reasons),
            round=1,
        ):
            return False
        result = await self._ac.ac_check(ACRequest(description=description, cwd=self._inputs.cwd))
        if not result.passed:
            await self._escalate(
                bead,
                "AC check failed after fix attempt",
                findings=list(result.reasons),
            )
            return False
        return True

    async def _spec_loop(self, bead: dict[str, Any]) -> bool:
        bead_id = bead["bead_id"]
        for attempt in range(MAX_SPEC_FIX_ATTEMPTS + 1):
            result = await self._spec.spec_check(SpecRequest(cwd=self._inputs.cwd))
            if result.passed:
                return True
            if attempt >= MAX_SPEC_FIX_ATTEMPTS:
                await self._escalate(
                    bead,
                    "Spec compliance fix attempts exhausted",
                    findings=list(result.findings),
                )
                return False
            await self._emit_output(
                "fly",
                f"Spec check failed (attempt {attempt + 1}): {result.details}",
                level="warning",
            )
            if not await self._send_fix(
                bead_id,
                phase="spec",
                context="\n".join(result.findings),
                round=attempt + 1,
            ):
                return False
        return False

    async def _review_loop(self, bead: dict[str, Any]) -> tuple[int, bool]:
        """Run the review fix loop.

        Returns ``(review_rounds, approved)``. ``review_rounds`` counts
        how many non-approved reviews landed (i.e., fix rounds needed).
        ``approved`` is true when the last review was approved. When the
        reviewer never submits a payload at all, returns ``(0, False)``
        so the caller can distinguish "no result" from "findings".
        """
        bead_id = bead["bead_id"]
        complexity = bead.get("complexity")
        _, reviewer = self._reviewer_for(complexity)
        rounds_with_findings = 0
        for round_n in range(1, MAX_REVIEW_ROUNDS + 1):
            self._last_review = None
            await reviewer.send_review(
                ReviewRequest(
                    bead_id=bead_id,
                    bead_description=bead.get("description", ""),
                    work_unit_md=bead.get("work_unit_md", ""),
                    briefing_context=bead.get("briefing_context", ""),
                )
            )
            if self._last_review is None:
                await self._emit_output(
                    "fly",
                    f"Reviewer did not submit for {bead_id} (round {round_n})",
                    level="warning",
                )
                return (rounds_with_findings, False)
            self._last_review_findings = self._last_review.findings
            if self._last_review.approved:
                return (rounds_with_findings, True)
            rounds_with_findings += 1
            self._review_findings_for_bead.append(self._last_review)
            # Record findings to runway for future briefings.
            await self._record_review_findings(self._last_review.findings)
            if round_n >= MAX_REVIEW_ROUNDS:
                return (rounds_with_findings, False)
            finding_text = "\n".join(
                f"- [{f.severity}] {f.issue} ({f.file}:{f.line})"
                for f in self._last_review.findings
            )
            if not await self._send_fix(
                bead_id, phase="review", context=finding_text, round=round_n
            ):
                return (rounds_with_findings, False)
        return (rounds_with_findings, False)

    async def _send_fix(self, bead_id: str, *, phase: str, context: str, round: int) -> bool:
        prompt = (
            f"## {phase.title()} findings (round {round})\n\n"
            f"{context}\n\n"
            "Address each issue and re-verify your changes."
        )

        # Tier escalation (FUTURE.md §2.10 Phase 2). When tiers are
        # configured and the bead has burned through `escalation_threshold`
        # fix rounds at its current tier with findings still pending,
        # promote one tier up. Re-rotate the higher-tier actor's session
        # for this bead so it starts fresh with the failing context.
        bead = self._current_bead_for_fix(bead_id)
        complexity = bead.get("complexity") if bead else None
        tier_name = _DEFAULT_TIER
        implementer = self._implementer
        if self._inputs.implementer_tiers is not None:
            threshold = getattr(self._inputs.implementer_tiers, "escalation_threshold", 0)
            if (
                threshold > 0
                and round > threshold
                and self._can_escalate(complexity, self._bead_escalation_level)
            ):
                self._bead_escalation_level += 1
                new_tier, new_implementer = self._implementer_for(
                    complexity, self._bead_escalation_level
                )
                old_tier, _ = self._implementer_for(complexity, self._bead_escalation_level - 1)
                if new_tier != old_tier:
                    await self._emit_output(
                        "fly",
                        f"Escalating bead {bead_id} from tier '{old_tier}' "
                        f"to '{new_tier}' after {round - 1} fix rounds with "
                        "findings",
                        level="warning",
                        metadata={
                            "bead_id": bead_id,
                            "complexity": complexity,
                            "from_tier": old_tier,
                            "to_tier": new_tier,
                            "fix_round": round,
                        },
                    )
                    # Rotate the higher-tier actor's session for this
                    # bead so it starts with a clean context.
                    await new_implementer.new_bead(NewBeadRequest(bead_id=bead_id))
                    tier_name, implementer = new_tier, new_implementer
                else:
                    # Couldn't actually escalate (already at top tier or
                    # no higher tier defined). Fall through with current.
                    tier_name, implementer = self._implementer_for(
                        complexity, self._bead_escalation_level
                    )
            else:
                tier_name, implementer = self._implementer_for(
                    complexity, self._bead_escalation_level
                )

        self._last_fix_result = None
        await implementer.send_fix(FlyFixRequest(bead_id=bead_id, prompt=prompt))
        if self._last_fix_result is None:
            await self._emit_output(
                "fly",
                f"Implementer did not submit fix for {bead_id} ({phase}, tier={tier_name})",
                level="error",
            )
            return False
        return True

    def _can_escalate(self, complexity: str | None, current_level: int) -> bool:
        """True when escalating one more level reaches a higher defined tier."""
        if _DEFAULT_TIER in self._implementers:
            return False  # legacy mode has no tiers
        next_tier = self._resolve_implementer_tier(complexity, current_level + 1)
        cur_tier = self._resolve_implementer_tier(complexity, current_level)
        if next_tier == cur_tier:
            return False
        # Only "true" escalation when next is strictly higher.
        return TIER_ORDER.index(next_tier) > TIER_ORDER.index(cur_tier)

    def _current_bead_for_fix(self, bead_id: str) -> dict[str, Any] | None:
        """Best-effort lookup of the current bead dict by id.

        Used by ``_send_fix`` to read the bead's complexity for tier
        routing without changing the existing call signature. Returns
        ``None`` when the bead context isn't available — callers fall
        back to legacy single-tier behaviour.
        """
        if self._current_bead_id == bead_id:
            return self._current_bead
        return None

    # ------------------------------------------------------------------
    # Aggregate review
    # ------------------------------------------------------------------

    async def _maybe_aggregate_review(self) -> None:
        if len(self._completed_beads) < AGGREGATE_REVIEW_THRESHOLD:
            return
        self._last_aggregate_review = None
        bead_list = "\n".join(
            f"- {bid}: {title}"
            for bid, title in zip(self._completed_beads, self._completed_titles, strict=False)
        )
        diff_stat = await self._safe_diff_stat()
        await self._emit_output("fly", "Running epic aggregate review")
        await self._reviewer.send_aggregate_review(
            AggregateReviewRequest(
                objective=self._inputs.epic_id or "epic",
                bead_list=bead_list,
                diff_stat=diff_stat,
                bead_count=len(self._completed_beads),
            )
        )
        if self._last_aggregate_review and not self._last_aggregate_review.approved:
            await self._emit_output(
                "fly",
                f"Aggregate review flagged {len(self._last_aggregate_review.findings)} "
                "cross-bead issue(s)",
                level="warning",
            )

    async def _safe_diff_stat(self) -> str:
        from pathlib import Path

        from maverick.runners.command import CommandRunner

        try:
            runner = CommandRunner(cwd=Path(self._inputs.cwd))
            result = await runner.run(["git", "diff", "--stat", "HEAD~1..HEAD"])
            return result.stdout if result.returncode == 0 else ""
        except Exception:  # noqa: BLE001
            return ""

    # ------------------------------------------------------------------
    # Bead-context enrichment
    # ------------------------------------------------------------------

    async def _load_bead_context(self, bead: dict[str, Any]) -> None:
        """Populate ``bead`` with ``work_unit_md`` and ``briefing_context``.

        Ported from the Thespian supervisor's ``_load_bead_context``.
        Best-effort: any filesystem or parsing error is logged at debug
        and the bead proceeds with whatever context it had.
        """
        flight_plan = self._inputs.flight_plan_name
        if not flight_plan or not self._inputs.cwd:
            return

        plans_dir = Path(self._inputs.cwd) / ".maverick" / "plans" / flight_plan

        # Work-unit matching — cached across beads keyed by flight_plan.
        work_units = self._work_units_cache.get(flight_plan)
        if work_units is None:
            work_units = {}
            try:
                for md_file in sorted(plans_dir.glob("[0-9]*.md")):
                    content = md_file.read_text(encoding="utf-8")
                    wu_id = ""
                    for line in content.split("\n"):
                        if line.startswith("work-unit:"):
                            wu_id = line.split(":", 1)[1].strip()
                            break
                    if wu_id:
                        work_units[wu_id] = content
            except Exception as exc:  # noqa: BLE001
                logger.debug("fly_supervisor.work_units_load_failed", error=str(exc))
            self._work_units_cache[flight_plan] = work_units

        bead_title = bead.get("title", "")
        work_unit_md = ""
        for content in work_units.values():
            task_line = ""
            in_task = False
            for line in content.split("\n"):
                if line.startswith("## Task"):
                    in_task = True
                    continue
                if in_task and line.strip():
                    task_line = line.strip()
                    break
            if task_line and bead_title:
                if bead_title[:60] in task_line or task_line[:60] in bead_title:
                    work_unit_md = content
                    break
        if not work_unit_md and work_units:
            # Fallback: concatenate so the agent can pick the right one.
            work_unit_md = "\n\n---\n\n".join(work_units.values())
        bead["work_unit_md"] = work_unit_md
        bead["complexity"] = _extract_complexity_from_md(work_unit_md)

        # Briefing context — loaded once per run.
        if not self._briefing_context:
            for briefing_name in ("refuel-briefing.md", "briefing.md"):
                briefing_path = plans_dir / briefing_name
                if briefing_path.exists():
                    try:
                        self._briefing_context = briefing_path.read_text(encoding="utf-8")[:8000]
                    except Exception:  # noqa: BLE001
                        pass
                    break
        bead["briefing_context"] = self._briefing_context

    # ------------------------------------------------------------------
    # Runway recording
    # ------------------------------------------------------------------

    async def _record_bead_outcome(
        self,
        bead: dict[str, Any],
        *,
        commit_success: bool,
        review_rounds: int,
    ) -> None:
        try:
            from maverick.library.actions.runway import record_bead_outcome

            await record_bead_outcome(
                bead_id=bead.get("bead_id", ""),
                epic_id=self._inputs.epic_id,
                title=bead.get("title", ""),
                flight_plan=self._inputs.flight_plan_name,
                validation_result={"passed": True},
                review_result={
                    "issues_found": review_rounds,
                    "issues_fixed": review_rounds if commit_success else 0,
                },
                mistakes_caught=[
                    f.issue
                    for f in self._last_review_findings
                    if f.severity in ("critical", "major")
                ]
                or None,
                cwd=self._inputs.cwd,
            )
        except Exception as exc:  # noqa: BLE001 — runway is best-effort
            logger.warning("fly_supervisor.runway_record_failed", error=str(exc))

    async def _record_review_findings(self, findings: tuple[ReviewFindingPayload, ...]) -> None:
        if not findings:
            return
        try:
            from maverick.library.actions.runway import record_review_findings

            await record_review_findings(
                bead_id=self._current_bead_id or "",
                review_result={
                    "findings": [
                        {
                            "severity": f.severity,
                            "category": "code_review",
                            "file_path": f.file,
                            "description": f.issue,
                        }
                        for f in findings
                    ],
                },
                cwd=self._inputs.cwd,
            )
        except Exception as exc:  # noqa: BLE001 — runway is best-effort
            logger.warning("fly_supervisor.runway_review_record_failed", error=str(exc))

    # ------------------------------------------------------------------
    # Human-in-the-loop escalation
    # ------------------------------------------------------------------

    async def _escalate(
        self,
        bead: dict[str, Any],
        reason: str,
        findings: list[str] | None = None,
        *,
        commit_after: bool = True,
    ) -> None:
        """Create a human-assigned review bead. When ``commit_after`` is
        true, also commit with the ``needs-human-review`` tag so the
        epic history records the escalation and the partial work lands
        in the workspace."""
        try:
            await self._create_human_bead(bead, reason, findings)
        except Exception as exc:  # noqa: BLE001
            await self._emit_output(
                "fly",
                f"Human bead creation failed: {exc}",
                level="error",
            )
        if commit_after:
            await self._committer.commit(
                CommitRequest(
                    bead_id=bead.get("bead_id", ""),
                    title=bead.get("title", ""),
                    cwd=self._inputs.cwd,
                    tag="needs-human-review",
                )
            )

    async def _create_human_bead(
        self,
        bead: dict[str, Any],
        reason: str,
        findings: list[str] | None,
    ) -> None:
        from maverick.beads.client import BeadClient
        from maverick.beads.models import BeadCategory, BeadDefinition, BeadType

        client = BeadClient(cwd=Path(self._inputs.cwd))
        bead_id = bead.get("bead_id", "")
        bead_title = bead.get("title", bead_id)
        findings_text = "\n".join(f"- {f}" for f in (findings or [])) if findings else "None"
        review_def = BeadDefinition(
            title=f"Review: {bead_title[:150]}",
            bead_type=BeadType.TASK,
            priority=1,
            category=BeadCategory.REVIEW,
            description=(f"## Escalation Reason\n\n{reason}\n\n## Findings\n\n{findings_text}"),
            assignee="human",
            labels=["assumption-review", "needs-human-review"],
        )

        created = await client.create_bead(review_def, parent_id=self._inputs.epic_id)
        await client.set_state(
            created.bd_id,
            {
                "source_bead": bead_id,
                "escalation_type": "fix_exhaustion",
                "flight_plan": self._inputs.flight_plan_name,
            },
            reason=f"Escalated from {bead_id}",
        )
        await self._emit_output(
            "fly",
            f"Created human review bead {created.bd_id} for {bead_id}",
            level="warning",
            metadata={"human_bead_id": created.bd_id, "source_bead": bead_id},
        )

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_implement_prompt(self, bead: dict[str, Any]) -> str:
        desc = bead.get("description", bead.get("title", ""))
        work_unit_md = bead.get("work_unit_md", "")
        runway_hint = (
            "\n\n## Historical Context (Runway)\n\n"
            "The `.maverick/runway/` directory contains project knowledge:\n"
            "- `episodic/bead-outcomes.jsonl` — outcomes from previous beads\n"
            "- `episodic/review-findings.jsonl` — review findings and resolutions\n"
            "- `episodic/fix-attempts.jsonl` — what was tried and whether it worked\n"
            "- `semantic/` — architecture notes and decision records\n"
            "- `index.json` — store metadata and suppressed patterns\n\n"
            "Read these files if they exist — they contain lessons learned "
            "that may prevent repeating past mistakes."
        )
        if work_unit_md:
            return (
                f"## Work Unit Specification\n\n{work_unit_md}\n\n"
                f"Implement this task. Read the relevant files, make changes, "
                f"and run tests to verify.{runway_hint}"
            )
        return (
            f"## Task\n\n{desc}\n\n"
            f"Implement this task. Read the relevant files, make changes, "
            f"and run tests to verify.{runway_hint}"
        )

    # ------------------------------------------------------------------
    # Typed domain methods (called by children via in-pool RPC)
    # ------------------------------------------------------------------

    @xo.no_lock
    async def implementation_ready(self, payload: SubmitImplementationPayload) -> None:
        self._last_implementation = payload
        await self._emit_output(
            "fly",
            f"Implementation submitted: {payload.summary[:80]}",
        )

    @xo.no_lock
    async def fix_result_ready(self, payload: SubmitFixResultPayload) -> None:
        self._last_fix_result = payload
        await self._emit_output(
            "fly",
            f"Fix submitted: {payload.summary[:80]}",
        )

    @xo.no_lock
    async def review_ready(self, payload: SubmitReviewPayload) -> None:
        self._last_review = payload
        approved = "approved" if payload.approved else "findings"
        await self._emit_output(
            "fly",
            f"Review submitted ({approved}, {len(payload.findings)} finding(s))",
        )

    @xo.no_lock
    async def aggregate_review_ready(self, payload: SubmitReviewPayload) -> None:
        self._last_aggregate_review = payload
        await self._emit_output(
            "fly",
            f"Aggregate review submitted ({'approved' if payload.approved else 'findings'})",
        )

    @xo.no_lock
    async def prompt_error(self, error: PromptError) -> None:
        """Handle an ACP prompt failure.

        Fatal across the board for fly (unlike refuel's detail-phase
        retry): there's no per-unit retry loop here — bead-level
        failures should surface loud and let the bead fail.
        """
        await self._emit_output(
            "fly",
            f"{error.phase} prompt failed: {error.error}",
            level="error",
            metadata={"phase": error.phase, "quota": error.quota_exhausted},
        )
        self._mark_done(
            {
                "success": False,
                "error": error.error,
                "phase": error.phase,
                "quota_exhausted": error.quota_exhausted,
                "beads_completed": self._processed_this_run,
                "completed_bead_ids": list(self._completed_beads),
            }
        )

    @xo.no_lock
    async def payload_parse_error(self, tool: str, message: str) -> None:
        self._last_parse_error = (tool, message)
        await self._emit_output(
            "fly",
            f"Tool {tool!r} payload rejected: {message}",
            level="warning",
        )

    # ------------------------------------------------------------------
    # Event bus (asyncio.Queue-backed)
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

    def _mark_done(self, result: dict[str, Any] | None) -> None:
        self._terminal_result = result
        self._done = True
        self._event_queue.put_nowait(None)

    @xo.no_lock
    async def get_terminal_result(self) -> dict[str, Any] | None:
        return self._terminal_result

    # ------------------------------------------------------------------
    # Test-only inspection surface (FUTURE.md §2.10 Phase 2 verification)
    # ------------------------------------------------------------------
    #
    # xoscar actors don't expose direct attribute access from refs, so
    # these tiny wrappers let tier-routing tests poke at the internals
    # without spinning up a full bead loop. They're prefixed with
    # ``_test_`` so it's obvious from a call site that they're not part
    # of the supervisor's public contract.

    @xo.no_lock
    async def t_peek_implementers(self) -> dict[str, Any]:
        return dict(self._implementers)

    @xo.no_lock
    async def t_resolve_tier(self, complexity: str | None, escalation_level: int) -> str:
        return self._resolve_implementer_tier(complexity, escalation_level)

    @xo.no_lock
    async def t_can_escalate(self, complexity: str | None, current_level: int) -> bool:
        return self._can_escalate(complexity, current_level)

    @xo.no_lock
    async def t_peek_reviewers(self) -> dict[str, Any]:
        return dict(self._reviewers)

    @xo.no_lock
    async def t_resolve_reviewer_tier(self, complexity: str | None) -> str:
        return self._resolve_reviewer_tier(complexity)
