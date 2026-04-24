"""xoscar FlySupervisor — async-native fly (bead-loop) orchestrator.

Per-bead state machine (linearised now that every step is awaitable):

    implement → gate (with fix loop) → AC (with fix loop)
             → spec (with fix loop) → review (with fix loop) → commit

Aggregate review runs once after the bead loop if more than one bead
was processed successfully.

Scope notes (Phase 2 MVP):

* Watch mode (``--watch`` with idle polling) is deferred to a follow-up.
* Bead-context enrichment (work-unit matching, briefing markdown load)
  is minimal — the supervisor passes whatever the workflow seeds it
  with through to the prompt builders.
* Stale-in-flight watchdog replaced with per-step ``xo.wait_for``
  around long-running agent calls.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
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
from maverick.tools.supervisor_inbox.models import (
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


@dataclass(frozen=True)
class FlyInputs:
    """Construction payload for ``FlySupervisor``."""

    cwd: str
    epic_id: str = ""
    config: Any = None  # StepConfig for agent sessions
    max_beads: int = 30
    validation_commands: dict[str, tuple[str, ...]] | None = None
    project_type: str = "rust"
    completed_bead_ids: tuple[str, ...] = ()


class FlySupervisor(xo.Actor):
    """Orchestrates the fly bead loop."""

    def __init__(self, inputs: FlyInputs) -> None:
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

        # Accumulators
        self._completed_beads: list[str] = list(self._inputs.completed_bead_ids)
        self._completed_titles: list[str] = []
        self._current_bead_id: str | None = None
        self._review_findings_for_bead: list[SubmitReviewPayload] = []

        self_ref = self.ref

        self._implementer = await xo.create_actor(
            ImplementerActor,
            self_ref,
            cwd=self._inputs.cwd,
            config=self._inputs.config,
            address=self.address,
            uid=f"{self.uid}:implementer",
        )
        self._reviewer = await xo.create_actor(
            ReviewerActor,
            self_ref,
            cwd=self._inputs.cwd,
            config=self._inputs.config,
            address=self.address,
            uid=f"{self.uid}:reviewer",
        )
        self._gate = await xo.create_actor(
            GateActor,
            validation_commands=self._inputs.validation_commands,
            address=self.address,
            uid=f"{self.uid}:gate",
        )
        self._ac = await xo.create_actor(
            ACCheckActor,
            address=self.address,
            uid=f"{self.uid}:ac",
        )
        self._spec = await xo.create_actor(
            SpecCheckActor,
            project_type=self._inputs.project_type,
            address=self.address,
            uid=f"{self.uid}:spec",
        )
        self._committer = await xo.create_actor(
            CommitterActor,
            address=self.address,
            uid=f"{self.uid}:committer",
        )

    async def __pre_destroy__(self) -> None:
        for ref in (
            self._implementer,
            self._reviewer,
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
                    "beads_completed": len(self._completed_beads),
                    "completed_bead_ids": list(self._completed_beads),
                }
            )
            return

        self._mark_done(
            {
                "success": True,
                "beads_completed": len(self._completed_beads),
                "completed_bead_ids": list(self._completed_beads),
            }
        )

    async def _bead_loop(self) -> None:
        processed = 0
        await self._emit_output(
            "fly",
            f"Starting bead loop (epic: {self._inputs.epic_id or 'any'})",
        )
        while processed < self._inputs.max_beads:
            bead = await self._select_next_bead()
            if bead is None or not bead.get("found"):
                await self._emit_output("fly", "No more beads to process")
                return
            bead_id = bead.get("bead_id", "")
            if not bead_id or bead_id in self._completed_beads:
                continue
            ok = await self._process_bead(bead)
            if not ok:
                # Escalation already emitted. Move on to next bead so the
                # loop doesn't stall on one failure.
                continue
            self._completed_beads.append(bead_id)
            self._completed_titles.append(bead.get("title", ""))
            processed += 1

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
        self._last_implementation = None
        self._last_review = None
        self._review_findings_for_bead = []

        await self._emit_output(
            "fly",
            f"Processing bead {bead_id}: {title[:80]}",
            metadata={"bead_id": bead_id, "title": title},
        )

        # Rotate sessions for the new bead.
        await self._implementer.new_bead(NewBeadRequest(bead_id=bead_id))
        await self._reviewer.new_bead(NewBeadRequest(bead_id=bead_id))

        # ---- Implement ----
        prompt = self._build_implement_prompt(bead)
        await self._implementer.send_implement(
            ImplementRequest(bead_id=bead_id, prompt=prompt)
        )
        if self._last_implementation is None:
            await self._emit_output(
                "fly",
                f"Implementer did not submit results for {bead_id}",
                level="error",
            )
            return False

        # ---- Gate fix loop ----
        if not await self._gate_loop(bead_id):
            return False

        # ---- AC fix loop ----
        if not await self._ac_loop(bead_id, bead):
            return False

        # ---- Spec fix loop ----
        if not await self._spec_loop(bead_id):
            return False

        # ---- Review fix loop ----
        if not await self._review_loop(bead_id, bead):
            return False

        # ---- Commit ----
        commit_result = await self._committer.commit(
            CommitRequest(
                bead_id=bead_id,
                title=title,
                cwd=self._inputs.cwd,
                tag=None,
            )
        )
        if not commit_result.success:
            await self._emit_output(
                "fly",
                f"Commit failed for {bead_id}: {commit_result.error}",
                level="error",
            )
            return False

        await self._emit_output(
            "fly",
            f"Bead {bead_id} complete ({commit_result.commit_sha or '?'})",
            level="success",
            metadata={
                "bead_id": bead_id,
                "commit_sha": commit_result.commit_sha,
            },
        )
        return True

    # ------------------------------------------------------------------
    # Per-phase fix loops
    # ------------------------------------------------------------------

    async def _gate_loop(self, bead_id: str) -> bool:
        for attempt in range(MAX_GATE_FIX_ATTEMPTS + 1):
            result = await self._gate.gate(GateRequest(cwd=self._inputs.cwd))
            if result.passed:
                return True
            if attempt >= MAX_GATE_FIX_ATTEMPTS:
                await self._emit_output(
                    "fly",
                    f"Gate failed after {attempt + 1} attempts: {result.summary}",
                    level="error",
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

    async def _ac_loop(self, bead_id: str, bead: dict[str, Any]) -> bool:
        description = bead.get("description", bead.get("title", ""))
        # AC has no retry loop in the legacy supervisor beyond a single
        # fix-attempt — preserve that.
        result = await self._ac.ac_check(
            ACRequest(description=description, cwd=self._inputs.cwd)
        )
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
        result = await self._ac.ac_check(
            ACRequest(description=description, cwd=self._inputs.cwd)
        )
        if not result.passed:
            await self._emit_output(
                "fly",
                f"AC check still failing after fix: {'; '.join(result.reasons)}",
                level="error",
            )
            return False
        return True

    async def _spec_loop(self, bead_id: str) -> bool:
        for attempt in range(MAX_SPEC_FIX_ATTEMPTS + 1):
            result = await self._spec.spec_check(SpecRequest(cwd=self._inputs.cwd))
            if result.passed:
                return True
            if attempt >= MAX_SPEC_FIX_ATTEMPTS:
                await self._emit_output(
                    "fly",
                    f"Spec check failed after {attempt + 1} attempts: {result.details}",
                    level="error",
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

    async def _review_loop(self, bead_id: str, bead: dict[str, Any]) -> bool:
        for round_n in range(1, MAX_REVIEW_ROUNDS + 1):
            self._last_review = None
            await self._reviewer.send_review(
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
                return False
            if self._last_review.approved:
                return True
            self._review_findings_for_bead.append(self._last_review)
            if round_n >= MAX_REVIEW_ROUNDS:
                await self._emit_output(
                    "fly",
                    f"Review rounds exhausted for {bead_id}",
                    level="warning",
                )
                return True  # Proceed to commit despite findings
            finding_text = "\n".join(
                f"- [{f.severity}] {f.issue} ({f.file}:{f.line})"
                for f in self._last_review.findings
            )
            if not await self._send_fix(
                bead_id, phase="review", context=finding_text, round=round_n
            ):
                return False
        return True

    async def _send_fix(
        self, bead_id: str, *, phase: str, context: str, round: int
    ) -> bool:
        prompt = (
            f"## {phase.title()} findings (round {round})\n\n"
            f"{context}\n\n"
            "Address each issue and re-verify your changes."
        )
        self._last_fix_result = None
        await self._implementer.send_fix(
            FlyFixRequest(bead_id=bead_id, prompt=prompt)
        )
        if self._last_fix_result is None:
            await self._emit_output(
                "fly",
                f"Implementer did not submit fix for {bead_id} ({phase})",
                level="error",
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Aggregate review
    # ------------------------------------------------------------------

    async def _maybe_aggregate_review(self) -> None:
        if len(self._completed_beads) < AGGREGATE_REVIEW_THRESHOLD:
            return
        self._last_aggregate_review = None
        bead_list = "\n".join(
            f"- {bid}: {title}"
            for bid, title in zip(
                self._completed_beads, self._completed_titles, strict=False
            )
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

    async def implementation_ready(self, payload: SubmitImplementationPayload) -> None:
        self._last_implementation = payload
        await self._emit_output(
            "fly",
            f"Implementation submitted: {payload.summary[:80]}",
        )

    async def fix_result_ready(self, payload: SubmitFixResultPayload) -> None:
        self._last_fix_result = payload
        await self._emit_output(
            "fly",
            f"Fix submitted: {payload.summary[:80]}",
        )

    async def review_ready(self, payload: SubmitReviewPayload) -> None:
        self._last_review = payload
        approved = "approved" if payload.approved else "findings"
        await self._emit_output(
            "fly",
            f"Review submitted ({approved}, {len(payload.findings)} finding(s))",
        )

    async def aggregate_review_ready(self, payload: SubmitReviewPayload) -> None:
        self._last_aggregate_review = payload
        await self._emit_output(
            "fly",
            f"Aggregate review submitted "
            f"({'approved' if payload.approved else 'findings'})",
        )

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
                "beads_completed": len(self._completed_beads),
                "completed_bead_ids": list(self._completed_beads),
            }
        )

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

    async def get_terminal_result(self) -> dict[str, Any] | None:
        return self._terminal_result
