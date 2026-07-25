"""Mid-flight reconcile pass — fly's bead-boundary integration with reconcile.

052-conditional-landing (User Story 3): a running ``maverick fly`` detects
newly-answered assumption-ledger entries at every bead boundary and, when
any are found, runs the transactional reconcile workflow in-process — all
without ever stopping the drain loop. This closes the human-latency gap
that today requires a manual ``maverick reconcile`` after answering a
question mid-flight.

See ``specs/052-conditional-landing/contracts/mid-flight-reconcile.md`` for
the full contract. :func:`run_mid_flight_pass` is invoked by the thin
``reconcile_answers``/``reconcile_answers_final`` Burr actions in
:mod:`maverick.workflows.fly_beads.actions` — this module holds all the
logic so those actions stay pure delegation (no branching, no state beyond
what the action wrapper itself threads through Burr).

Contract order (each precondition short-circuits to a skipped outcome):

1. ``config.reconcile.mid_flight`` is False -> ``skipped_reason="disabled"``.
2. Graceful stop requested -> ``skipped_reason="graceful-stop"`` (answers
   stay detectable by a later pass or a standalone ``maverick reconcile``
   run — FR-014).
3. :func:`~maverick.assumptions.ledger.answered_unreconciled_entries` is
   empty -> ``skipped_reason="none-detected"``. A bd-layer query failure
   (``AssumptionLedgerError``) is treated identically to empty, plus a
   warning event — detection failures must never propagate into the Burr
   loop.

Only when detection is non-empty does this invoke ``ReconcileWorkflow``
in-process, passing ``active_fly_run_id=fly_run_id`` so the concurrent-fly
guard (research R7) excludes the calling run — it is, by construction,
parked at a safe boundary (an empty ``@`` child, per ``commit()``'s
postcondition) awaiting this pass. The child workflow's own
``ProgressEvent``s are forwarded into ``event_sink`` verbatim (mirroring
the CLI's own dry-run drain in ``cli/commands/reconcile.py``) so the pass
gets its own progress grouping in fly's stream.

Any ``MaverickError`` (``WorkflowError`` for a genuinely concurrent other
fly run, the clean-working-copy guard, the lockfile, or any other
reconcile-internal failure) is caught here and turned into a warning event
plus ``MidFlightOutcome(error=...)`` — the action **never** raises into the
Burr application (FR-013: the drain loop must survive a failed pass).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from maverick.assumptions.errors import AssumptionLedgerError
from maverick.assumptions.ledger import answered_unreconciled_entries
from maverick.beads.client import BeadClient
from maverick.exceptions import MaverickError
from maverick.logging import get_logger
from maverick.workflows.fly_beads.actions import _put_output
from maverick.workflows.fly_beads.graceful_stop import is_graceful_stop_requested
from maverick.workflows.reconcile.workflow import ReconcileWorkflow

if TYPE_CHECKING:
    import asyncio
    from pathlib import Path

    from maverick.config import MaverickConfig
    from maverick.events import ProgressEvent

__all__ = ["MidFlightOutcome", "run_mid_flight_pass"]

logger = get_logger(__name__)

_STEP_NAME = "reconcile"


@dataclass(frozen=True, slots=True)
class MidFlightOutcome:
    """Typed result of one mid-flight reconcile pass (data-model.md).

    Attributes:
        detected: Answers matching detection at this boundary.
        processed: Reconciled successfully this pass.
        escalated: Terminal-marked (``skipped`` or
            ``needs_interactive_review``) outcomes this pass.
        skipped_reason: ``"disabled"``, ``"graceful-stop"``,
            ``"none-detected"``, or ``None`` when a pass actually ran.
        error: Non-``None`` when the pass failed as a whole (the drain
            loop continued regardless).
    """

    detected: int
    processed: int
    escalated: int
    skipped_reason: str | None
    error: str | None


def _skip(reason: str) -> MidFlightOutcome:
    return MidFlightOutcome(
        detected=0, processed=0, escalated=0, skipped_reason=reason, error=None
    )


async def run_mid_flight_pass(
    *,
    cwd: Path,
    config: MaverickConfig | None,
    fly_run_id: str,
    event_sink: asyncio.Queue[ProgressEvent | None],
) -> MidFlightOutcome:
    """Detect changed answers at a bead boundary and reconcile them in-process.

    Args:
        cwd: The user checkout fly is running in.
        config: Project configuration — ``config.reconcile.mid_flight`` is
            the kill-switch; the reconcile round budgets are inherited
            unchanged from ``config.reconcile``. ``None`` is treated the
            same as ``mid_flight=False`` (deliberate defensive default for
            callers — production and tests alike — that haven't threaded
            a config through; every real ``maverick fly`` invocation
            always supplies one).
        fly_run_id: The calling fly run's own ``run_id`` — threaded to
            ``ReconcileWorkflow`` as ``active_fly_run_id`` so its
            concurrent-fly guard excludes this run.
        event_sink: The same event queue fly's other Burr actions push
            ``ProgressEvent``s into; the child ``ReconcileWorkflow``'s own
            events are forwarded here verbatim.

    Returns:
        A :class:`MidFlightOutcome` summarizing what happened. Never
        raises — every failure mode is captured in the returned outcome.
    """
    if config is None or not config.reconcile.mid_flight:
        return _skip("disabled")

    if is_graceful_stop_requested():
        return _skip("graceful-stop")

    bead_client = BeadClient(cwd=cwd)
    try:
        entries = await answered_unreconciled_entries(bead_client)
    except AssumptionLedgerError as exc:
        logger.warning("mid_flight_detection_failed", error=str(exc))
        await _put_output(
            event_sink,
            _STEP_NAME,
            f"Mid-flight reconcile detection failed (treating as none-detected): {exc}",
            level="warning",
        )
        return _skip("none-detected")

    if not entries:
        return _skip("none-detected")

    detected = len(entries)
    await _put_output(
        event_sink,
        _STEP_NAME,
        f"Mid-flight: {detected} changed answer(s) detected — running reconcile",
        metadata={"detected": detected},
    )

    reconcile_run_id = uuid.uuid4().hex[:8]
    inputs: dict[str, Any] = {
        "run_id": reconcile_run_id,
        "cwd": str(cwd),
        "dry_run": False,
        "active_fly_run_id": fly_run_id,
    }
    workflow = ReconcileWorkflow(config=config)
    try:
        async for event in workflow.execute(inputs):
            await event_sink.put(event)
    except MaverickError as exc:
        logger.warning("mid_flight_reconcile_failed", error=str(exc))
        await _put_output(
            event_sink,
            _STEP_NAME,
            f"Mid-flight reconcile pass failed: {exc}",
            level="warning",
        )
        return MidFlightOutcome(
            detected=detected,
            processed=0,
            escalated=0,
            skipped_reason=None,
            error=str(exc),
        )

    assert workflow.result is not None
    report = workflow.result.final_output or {}
    outcomes: list[dict[str, Any]] = list(report.get("outcomes") or ())
    processed = sum(1 for o in outcomes if o.get("status") == "reconciled")
    escalated = sum(1 for o in outcomes if o.get("status") != "reconciled")

    await _put_output(
        event_sink,
        _STEP_NAME,
        f"Mid-flight reconcile pass complete: {processed} reconciled, {escalated} escalated",
        metadata={"processed": processed, "escalated": escalated},
    )

    return MidFlightOutcome(
        detected=detected,
        processed=processed,
        escalated=escalated,
        skipped_reason=None,
        error=None,
    )
