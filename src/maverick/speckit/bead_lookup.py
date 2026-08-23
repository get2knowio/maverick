"""Shared epic/task <-> bead lookup helpers.

Extracted from ``workflows/refuel_speckit/workflow.py``'s
``_find_existing_epic`` so the delta layer's impact detection
(``speckit/delta/impacts.py``) can resolve the same epic and
task-id-to-bead map without a second implementation (Guardrail 5).
"""

from __future__ import annotations

from typing import Any

from maverick.logging import get_logger
from maverick.speckit.errors import SpeckitError

logger = get_logger(__name__)


async def find_epic_id(client: Any, feature_name: str) -> str | None:
    """Find the open epic (if any) whose ``speckit_feature`` state matches.

    Args:
        client: A :class:`~maverick.beads.client.BeadClient` (or test double).
        feature_name: Spec Kit feature directory basename.

    Returns:
        The epic's bead id, or ``None`` if no open epic claims this feature.

    Raises:
        SpeckitError: More than one open epic claims this feature (corrupt state).
    """
    try:
        epics = await client.query("type=epic AND status=open")
    except Exception as exc:
        logger.debug("speckit_epic_query_failed", error=str(exc))
        return None

    matches = []
    for epic_summary in epics:
        try:
            details = await client.show(epic_summary.id)
        except Exception as exc:
            # Silently skipping here (rather than failing) is deliberate —
            # this loop only ever means "does *this* epic claim the
            # feature", so one epic's transient show() failure must not
            # sink the scan of every other epic. But a caller relying on
            # find_epic_id() to gate a safety check (delta apply's impact
            # detection: no epic found -> skip the refusal check entirely)
            # cannot tell "genuinely no epic" from "lookup degraded" unless
            # this is at least observable — hence the warning rather than
            # a bare `continue`.
            logger.warning("speckit_epic_show_failed", epic_id=epic_summary.id, error=str(exc))
            continue
        if details.state.get("speckit_feature") == feature_name:
            matches.append(details)

    if not matches:
        return None
    if len(matches) > 1:
        ids = ", ".join(d.id for d in matches)
        raise SpeckitError(f"multiple open epics claim speckit_feature={feature_name}: {ids}")
    return matches[0].id


async def build_task_bead_map(
    client: Any, epic_id: str
) -> tuple[dict[str, str], tuple[str, ...], dict[str, str]]:
    """Walk *epic_id*'s children, mapping ``speckit_task_id`` -> bead id.

    Args:
        client: A :class:`~maverick.beads.client.BeadClient` (or test double).
        epic_id: The epic bead id to walk.

    Returns:
        ``(task_id -> bead_id, unstamped_bead_ids, bead_id -> status)``.
        *unstamped_bead_ids* are children with no recorded
        ``speckit_task_id`` at all (the research R7 hazard: a process
        death between ``create_bead`` and ``set_state`` on some prior
        ingestion run). *bead_id -> status* comes from ``bd list``'s own
        summary (``BeadSummary.status``) — free with the ``children()``
        call this function already makes, so a caller classifying a
        withdrawn task's bead status (the delta layer's impact
        detection, and refuel's withdrawal-closing step) needs no extra
        ``bd`` query beyond what building this map already costs
        (research R6).
    """
    existing_task_map: dict[str, str] = {}
    unstamped: list[str] = []
    try:
        children = await client.children(epic_id)
    except Exception as exc:
        logger.warning("speckit_epic_children_failed", epic_id=epic_id, error=str(exc))
        children = []
    bead_status: dict[str, str] = {child.id: child.status for child in children}
    for child in children:
        try:
            child_details = await client.show(child.id)
        except Exception as exc:
            # A dropped child here is invisible to BOTH existing_task_map
            # and unstamped_bead_ids — exactly the class of hazard
            # unstamped_bead_ids exists to catch (research R7). Warn so a
            # transient failure here doesn't silently masquerade as "this
            # bead is fine and stamped".
            logger.warning("speckit_bead_show_failed", bead_id=child.id, error=str(exc))
            continue
        task_id = (child_details.state or {}).get("speckit_task_id")
        if task_id:
            existing_task_map[task_id] = child.id
        else:
            unstamped.append(child.id)
    return existing_task_map, tuple(unstamped), bead_status


__all__ = ["build_task_bead_map", "find_epic_id"]
