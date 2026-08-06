"""Canonical row projection for one :class:`AssumptionReportEntry`.

Extracted from ``land_report._entry_to_dict`` (research R4,
specs/053-assumption-review-console/data-model.md "entry_to_dict") so both
``maverick land``'s provenance report and the new `review --list` listing
share one projection instead of maintaining two copies. ``land_report``'s
``_entry_to_dict`` is now a thin backward-compatible alias for
:func:`entry_to_dict`.
"""

from __future__ import annotations

from maverick.assumptions.models import (
    RECONCILE_STATUS_NEEDS_REVIEW,
    AssumptionReportEntry,
)

__all__ = ["entry_to_dict"]


def _annotations(entry: AssumptionReportEntry) -> tuple[str, ...]:
    """Denormalized, human-facing tags — every one derivable from other fields.

    ``reconcile_status`` only ever persists as the single
    ``RECONCILE_STATUS_NEEDS_REVIEW`` value for both the "skipped" (no
    mutation attempted) and "needs_interactive_review" (rolled back)
    flavours described in data-model.md §2 — the ledger has no
    discriminating field for the two, so both surface identically here.
    """
    tags: list[str] = []
    if entry.record.is_legacy:
        tags.append("legacy")
    if entry.reconcile_status == RECONCILE_STATUS_NEEDS_REVIEW:
        tags.append(f"reconcile: {entry.reconcile_status}")
    if entry.pending_reconcile:
        tags.append("pending reconcile")
    return tuple(tags)


def entry_to_dict(entry: AssumptionReportEntry) -> dict[str, object]:
    """Project *entry* into the JSON-serializable row shared by the land
    report and ``review --list`` (data-model.md "entry_to_dict").

    ``waiver`` is ``None`` unless *entry* is in the waived bucket.
    """
    record = entry.record
    waiver = (
        {"by": entry.waived_by, "at": entry.waived_at, "reason": entry.waive_reason}
        if entry.bucket == "waived"
        else None
    )
    return {
        "bead_id": record.bead_id,
        "owner_spec": record.owner_spec,
        "status": record.status,
        "bucket": entry.bucket,
        "blocks_landing": entry.blocks_landing,
        "question": record.question,
        "adopted_answer": record.adopted_answer,
        "final_answer": entry.final_answer,
        "alternatives": list(record.alternatives),
        "severity": record.severity.value,
        "severity_defaulted": record.severity_defaulted,
        "is_legacy": record.is_legacy,
        "source_bead": record.source_bead,
        "created_at": record.created_at,
        "affected_change_ids": list(entry.affected_change_ids),
        "waiver": waiver,
        "reconcile": {
            "status": entry.reconcile_status,
            "reconciled_answer": entry.reconciled_answer,
            "change_id": entry.reconcile_change_id,
            "reason": entry.reconcile_reason,
        },
        "pending_reconcile": entry.pending_reconcile,
        "annotations": list(_annotations(entry)),
    }
