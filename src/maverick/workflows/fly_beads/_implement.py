"""Implement helpers for fly-beads.

Snapshot/describe operations and verification-only detection.
Agent implementation is now handled by ImplementerActor in the
Thespian actor system.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from maverick.library.actions.jj import jj_describe, jj_snapshot_operation
from maverick.logging import get_logger
from maverick.workflows.fly_beads.models import BeadContext

if TYPE_CHECKING:
    from maverick.workflows.fly_beads.workflow import FlyBeadsWorkflow

logger = get_logger(__name__)


async def snapshot_and_describe(wf: FlyBeadsWorkflow, ctx: BeadContext) -> None:
    """Snapshot uncommitted changes and describe the bead in jj."""
    if ctx.cwd is None:
        return

    try:
        snap = await jj_snapshot_operation(cwd=str(ctx.cwd))
        if snap.success:
            logger.debug("snapshot_ok", bead_id=ctx.bead_id)
    except Exception as exc:
        logger.debug("snapshot_failed", bead_id=ctx.bead_id, error=str(exc))

    try:
        await jj_describe(
            message=f"bead({ctx.bead_id}): {ctx.title}",
            cwd=str(ctx.cwd),
        )
    except Exception as exc:
        logger.debug("describe_failed", bead_id=ctx.bead_id, error=str(exc))


def _is_verification_only(ctx: BeadContext) -> bool:
    """Detect verification-only beads that should not modify files.

    Verification beads only read and report — they check that existing
    code meets certain criteria without changing anything.
    """
    text = f"{ctx.title} {ctx.description}".lower()
    verification_signals = (
        "verification-only",
        "verify that",
        "check that",
        "audit",
        "validate existing",
    )
    return any(signal in text for signal in verification_signals)
