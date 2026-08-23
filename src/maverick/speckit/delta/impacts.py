"""Task entry -> bead impact detection.

See ``specs/059-spec-delta-layer/research.md`` R6/R7 for the bead ↔ task
join this module resolves against, and
``specs/059-spec-delta-layer/data-model.md``'s "Impact layer" for the
classification rules.

Read-only: this module never creates, updates, or closes a bead (FR-011)
— it only reads bd state to decide whether ``delta apply`` may proceed.
"""

from __future__ import annotations

from maverick.beads.client import BeadClient
from maverick.speckit.bead_lookup import build_task_bead_map
from maverick.speckit.delta.models import DeltaDocument, Impact

#: bd's closed-bead vocabulary (mirrors ``assumptions.ledger._CLOSED_STATUSES``
#: — duplicated rather than imported to keep ``speckit`` decoupled from
#: ``assumptions``).
_CLOSED_STATUSES = frozenset(("closed", "done"))

#: The one status that means "open and unstarted" — every other status
#: (``in_progress``, ``blocked``, anything else bd reports) is in-flight.
_OPEN_UNSTARTED_STATUS = "open"


async def detect_impacts(
    document: DeltaDocument,
    *,
    client: BeadClient,
    epic_id: str,
) -> tuple[Impact, ...]:
    """Resolve every ``WITHDRAWN`` task entry to its bead and classify it.

    Only ``WITHDRAWN`` entries can collide with existing work — an
    ``ADDED`` entry creates a task that has no bead yet. Also scans every
    bead under *epic_id* for the research R7 hazard: a bead recorded with
    no ``speckit_task_id`` at all (a process death between ``create_bead``
    and ``set_state`` on some prior ingestion run). That hazard is
    reported regardless of whether this delta names any withdrawn tasks —
    it means the epic's task->bead map cannot be trusted to be complete.

    Args:
        document: The parsed, already-validated delta document.
        client: Bead client (read-only use only — ``show``/``children``).
        epic_id: The target feature's epic bead id.

    Returns:
        Every blocking :class:`Impact`, in a stable order (withdrawn
        tasks in document order, then unstamped beads). A withdrawn task
        whose bead is open and unstarted is **not** included — that is
        the clean case a later ``refuel --speckit`` closes without any
        fuss.
    """
    withdrawn_ids = [entry.task_id for entry in document.task_entries if entry.kind == "withdrawn"]

    task_id_to_bead, unstamped_bead_ids, bead_status = await build_task_bead_map(client, epic_id)

    impacts: list[Impact] = []
    for task_id in withdrawn_ids:
        bead_id = task_id_to_bead.get(task_id)
        if bead_id is None:
            # No bead was ever created for this task (e.g. delta applied
            # before any refuel ran) — nothing in flight to refuse on.
            continue
        status = bead_status.get(bead_id, "")
        if status in _CLOSED_STATUSES:
            impacts.append(
                Impact(task_id=task_id, bead_id=bead_id, bead_status=status, reason="closed")
            )
        elif status != _OPEN_UNSTARTED_STATUS:
            impacts.append(
                Impact(task_id=task_id, bead_id=bead_id, bead_status=status, reason="in-flight")
            )

    for bead_id in unstamped_bead_ids:
        impacts.append(
            Impact(bead_id=bead_id, bead_status=bead_status.get(bead_id, ""), reason="unstamped")
        )

    return tuple(impacts)


__all__ = ["detect_impacts"]
