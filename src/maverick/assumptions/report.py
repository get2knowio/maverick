"""Per-spec assumption aggregation for ``maverick brief`` and the land gate."""

from __future__ import annotations

from typing import TYPE_CHECKING

from maverick.assumptions.errors import AssumptionLedgerError
from maverick.assumptions.ledger import _legacy_record_from_details, _record_from_details
from maverick.assumptions.models import (
    ASSUMPTION_LABEL,
    ASSUMPTION_REVIEW_LABEL,
    EPIC_KEY_FLIGHT_PLAN_NAME,
    EPIC_KEY_SPECKIT_FEATURE,
    STATUS_ANSWERED,
    STATUS_OPEN,
    STATUS_WAIVED,
    PerSpecAssumptionCounts,
    Severity,
)
from maverick.exceptions.beads import BeadError
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.beads.client import BeadClient

logger = get_logger(__name__)

__all__ = ["per_spec_counts"]

_CLOSED_STATUSES = frozenset(("closed", "done"))


def _empty_severity_counts() -> dict[Severity, int]:
    return {Severity.LOW: 0, Severity.MEDIUM: 0, Severity.HIGH: 0}


async def per_spec_counts(client: BeadClient) -> tuple[PerSpecAssumptionCounts, ...]:
    """Aggregate all ``assumption`` beads (+ legacy) by owning spec.

    Every epic in the store yields a row even at zero counts (FR-010).
    Legacy escalation beads (``assumption-review`` without ``assumption``)
    are counted in a separate ``legacy_open`` bucket. Ordered by owner
    spec identifier.
    """
    try:
        epic_summaries = await client.query("type=epic")
    except BeadError as exc:
        raise AssumptionLedgerError(f"Failed to query epics: {exc}") from exc

    owner_specs: dict[str, None] = {}
    for epic in epic_summaries:
        try:
            details = await client.show(epic.id)
        except BeadError as exc:
            raise AssumptionLedgerError(f"Failed to load epic {epic.id}: {exc}") from exc
        spec = (
            details.state.get(EPIC_KEY_SPECKIT_FEATURE)
            or details.state.get(EPIC_KEY_FLIGHT_PLAN_NAME)
            or epic.id
        )
        owner_specs.setdefault(spec, None)

    try:
        task_summaries = await client.query("type=task")
    except BeadError as exc:
        raise AssumptionLedgerError(f"Failed to query task beads: {exc}") from exc

    open_counts: dict[str, dict[Severity, int]] = {}
    answered_counts: dict[str, dict[Severity, int]] = {}
    waived_counts: dict[str, dict[Severity, int]] = {}
    legacy_counts: dict[str, int] = {}

    for candidate in task_summaries:
        try:
            details = await client.show(candidate.id)
        except BeadError as exc:
            raise AssumptionLedgerError(f"Failed to load bead {candidate.id}: {exc}") from exc
        labels = details.labels or []

        if ASSUMPTION_LABEL in labels:
            record = _record_from_details(details)
            owner_specs.setdefault(record.owner_spec, None)
            if record.status == STATUS_OPEN:
                bucket = open_counts.setdefault(record.owner_spec, _empty_severity_counts())
            elif record.status == STATUS_ANSWERED:
                bucket = answered_counts.setdefault(record.owner_spec, _empty_severity_counts())
            elif record.status == STATUS_WAIVED:
                bucket = waived_counts.setdefault(record.owner_spec, _empty_severity_counts())
            else:
                continue
            bucket[record.severity] += 1
        elif ASSUMPTION_REVIEW_LABEL in labels and details.status not in _CLOSED_STATUSES:
            legacy = _legacy_record_from_details(details)
            spec = legacy.owner_spec or "(unknown)"
            owner_specs.setdefault(spec, None)
            legacy_counts[spec] = legacy_counts.get(spec, 0) + 1

    results = [
        PerSpecAssumptionCounts(
            owner_spec=spec,
            open=open_counts.get(spec, _empty_severity_counts()),
            answered=answered_counts.get(spec, _empty_severity_counts()),
            waived=waived_counts.get(spec, _empty_severity_counts()),
            legacy_open=legacy_counts.get(spec, 0),
        )
        for spec in sorted(owner_specs)
    ]
    return tuple(results)
