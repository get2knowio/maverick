"""Pure frontier/classification/report logic for ``maverick land``.

No Rich/Click concerns and no bd access here — this module operates only
on already-materialized :class:`AssumptionReportEntry` tuples (from
``ledger.report_entries()``), so its rules are unit-testable without a
running bd. See specs/052-conditional-landing/data-model.md and
contracts/cli-land.md and contracts/land-report-schema.md for the
authoritative contract.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from maverick.assumptions.models import (
    RECONCILE_STATUS_NEEDS_REVIEW,
    AssumptionReportEntry,
    LandFrontier,
    LandVerification,
)
from maverick.utils.atomic import atomic_write_json, atomic_write_text

__all__ = [
    "LandReport",
    "SpecReportSection",
    "build_report",
    "classify",
    "frontier",
    "persist_report",
    "render_markdown",
]

_EMPTY_TOTALS: dict[str, int] = {"resolved": 0, "waived": 0, "open": 0, "pending_reconcile": 0}


def frontier(entries: Sequence[AssumptionReportEntry]) -> LandFrontier:
    """Split *entries* into the two buckets that block ``maverick land``.

    Strict gate (Clarifications 2026-07-24): every open entry blocks,
    regardless of severity, including open legacy escalation beads.
    Answered entries pending reconciliation (051's predicate) block too,
    via a separate bucket so the CLI can render a distinct hint
    (``maverick reconcile`` vs ``maverick review <id>``).
    """
    open_entries = tuple(e for e in entries if e.bucket == "open")
    pending_reconcile_entries = tuple(e for e in entries if e.pending_reconcile)
    return LandFrontier(
        open_entries=open_entries,
        pending_reconcile_entries=pending_reconcile_entries,
    )


def classify(entries: Sequence[AssumptionReportEntry]) -> LandVerification:
    """Classify a completed (non-blocked) land evaluation.

    Callers should only trust this classification once
    ``frontier(entries).is_empty`` is True — the ordering below still
    handles a non-empty frontier defensively (returns ``BLOCKED``) so it
    can't misreport a landing that shouldn't have happened.
    """
    if any(e.blocks_landing for e in entries):
        return LandVerification.BLOCKED
    if any(e.bucket == "waived" for e in entries):
        return LandVerification.CONDITIONALLY_VERIFIED
    return LandVerification.VERIFIED


def _bucket_counts(entries: Sequence[AssumptionReportEntry]) -> dict[str, int]:
    counts = dict(_EMPTY_TOTALS)
    for entry in entries:
        counts[entry.bucket] += 1
        if entry.pending_reconcile:
            counts["pending_reconcile"] += 1
    return counts


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


def _entry_to_dict(entry: AssumptionReportEntry) -> dict[str, Any]:
    record = entry.record
    waiver = (
        {"by": entry.waived_by, "at": entry.waived_at, "reason": entry.waive_reason}
        if entry.bucket == "waived"
        else None
    )
    return {
        "bead_id": record.bead_id,
        "bucket": entry.bucket,
        "question": record.question,
        "adopted_answer": record.adopted_answer,
        "final_answer": entry.final_answer,
        "alternatives": list(record.alternatives),
        "severity": record.severity.value,
        "severity_defaulted": record.severity_defaulted,
        "is_legacy": record.is_legacy,
        "source_bead": record.source_bead,
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


@dataclass(frozen=True, slots=True)
class SpecReportSection:
    """One owning spec's grouped entries within a :class:`LandReport`."""

    owner_spec: str
    entries: tuple[AssumptionReportEntry, ...]

    @property
    def counts(self) -> dict[str, int]:
        """Per-bucket counts, plus the cross-cutting ``pending_reconcile`` count."""
        return _bucket_counts(self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner_spec": self.owner_spec,
            "counts": self.counts,
            "entries": [_entry_to_dict(e) for e in self.entries],
        }


@dataclass(frozen=True, slots=True)
class LandReport:
    """The full provenance report for one ``maverick land`` evaluation.

    Persisted as ``land-report.json``/``land-report.md`` under
    ``.maverick/runs/<run_id>/`` on every evaluation (contracts/cli-land.md)
    — a stable public contract (additive evolution only, see
    contracts/land-report-schema.md).
    """

    run_id: str
    created_at: str
    verification: LandVerification | None
    dry_run: bool
    specs: tuple[SpecReportSection, ...]
    degraded: bool = False

    @property
    def totals(self) -> dict[str, int]:
        totals = dict(_EMPTY_TOTALS)
        for section in self.specs:
            counts = section.counts
            for key in totals:
                totals[key] += counts[key]
        return totals

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": 1,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "dry_run": self.dry_run,
            "totals": self.totals,
            "specs": [section.to_dict() for section in self.specs],
            "degraded": self.degraded,
        }
        # `verification` key is absent (not null) when the gate degraded —
        # a degraded evaluation must never assert a false classification.
        if self.verification is not None:
            data["verification"] = self.verification.value
        return data


def build_report(
    entries: Sequence[AssumptionReportEntry],
    verification: LandVerification | None,
    *,
    run_id: str,
    dry_run: bool,
    degraded: bool = False,
) -> LandReport:
    """Group *entries* by owning spec and assemble the full report."""
    by_spec: dict[str, list[AssumptionReportEntry]] = {}
    for entry in entries:
        by_spec.setdefault(entry.record.owner_spec, []).append(entry)

    specs = tuple(
        SpecReportSection(owner_spec=owner_spec, entries=tuple(spec_entries))
        for owner_spec, spec_entries in sorted(by_spec.items())
    )
    return LandReport(
        run_id=run_id,
        created_at=datetime.now(UTC).isoformat(),
        verification=verification,
        dry_run=dry_run,
        specs=specs,
        degraded=degraded,
    )


_VERIFICATION_BANNER: dict[LandVerification, str] = {
    LandVerification.VERIFIED: "✓ Verified",
    LandVerification.CONDITIONALLY_VERIFIED: "✓ Conditionally verified on unresolved assumptions",
    LandVerification.BLOCKED: "✗ Blocked",
}

_BUCKET_HEADINGS: tuple[tuple[str, str], ...] = (
    ("resolved", "Resolved"),
    ("waived", "Waived"),
    ("open", "Open"),
)


def _render_entry_line(entry: AssumptionReportEntry) -> list[str]:
    record = entry.record
    lines = [
        f"- **{record.bead_id}** ({record.severity.value}"
        f"{', defaulted' if record.severity_defaulted else ''}): {record.question}"
    ]
    lines.append(f"  - Adopted answer: {record.adopted_answer}")
    if entry.final_answer is not None:
        lines.append(f"  - Final answer: {entry.final_answer}")
    if entry.affected_change_ids:
        lines.append(f"  - Affected changes: {', '.join(entry.affected_change_ids)}")
    if entry.bucket == "waived":
        lines.append(f"  - Waived by {entry.waived_by} at {entry.waived_at}: {entry.waive_reason}")
    # Keyed off ``blocks_landing``, not ``bucket``: a pending-reconcile
    # entry is always ``assumption_status=answered`` (051's predicate), so
    # its bucket is "resolved" — gating the hint on ``bucket == "open"``
    # made the ``maverick reconcile`` branch unreachable and left the one
    # row that blocks the land with no instruction on how to clear it.
    if entry.blocks_landing:
        hint = (
            "maverick reconcile"
            if entry.pending_reconcile
            else f"maverick review {record.bead_id}"
        )
        lines.append(f"  - Resolve with: `{hint}`")
    annotations = _annotations(entry)
    if annotations:
        lines.append(f"  - Annotations: {', '.join(annotations)}")
    return lines


def render_markdown(report: LandReport) -> str:
    """Render *report* as PR-ready markdown (contracts/land-report-schema.md)."""
    lines: list[str] = ["# Maverick Land Report", ""]

    banner = (
        _VERIFICATION_BANNER[report.verification]
        if report.verification is not None
        else "Assumption gate degraded (bd unavailable)"
    )
    marker = " (DRY RUN)" if report.dry_run else ""
    lines.append(f"**{banner}**{marker}")
    lines.append("")
    lines.append(f"Run: `{report.run_id}` — {report.created_at}")
    lines.append("")

    totals = report.totals
    lines.append(
        f"Totals: {totals['resolved']} resolved, {totals['waived']} waived, "
        f"{totals['open']} open, {totals['pending_reconcile']} pending reconciliation."
    )
    lines.append("")

    if not report.specs:
        lines.append("No assumptions adopted.")
        lines.append("")
    else:
        for section in report.specs:
            lines.append(f"## {section.owner_spec}")
            lines.append("")
            by_bucket: dict[str, list[AssumptionReportEntry]] = {
                "resolved": [],
                "waived": [],
                "open": [],
            }
            for entry in section.entries:
                by_bucket[entry.bucket].append(entry)
            for bucket_key, heading in _BUCKET_HEADINGS:
                bucket_entries = by_bucket[bucket_key]
                if not bucket_entries:
                    continue
                lines.append(f"### {heading}")
                lines.append("")
                for entry in bucket_entries:
                    lines.extend(_render_entry_line(entry))
                lines.append("")

    from maverick import __version__

    lines.append(f"Generated by maverick land {__version__}")
    return "\n".join(lines) + "\n"


def persist_report(report: LandReport, *, cwd: Path) -> tuple[Path, Path]:
    """Atomically write both report artifacts under ``.maverick/runs/<run_id>/``.

    Raises:
        OSError: On write failure — callers degrade this to a warning
            (contracts/cli-land.md: "Persistence failure → warning, never
            a gate failure").
    """
    run_dir = cwd / ".maverick" / "runs" / report.run_id
    json_path = run_dir / "land-report.json"
    md_path = run_dir / "land-report.md"
    atomic_write_json(json_path, report.to_dict())
    atomic_write_text(md_path, render_markdown(report))
    return json_path, md_path
