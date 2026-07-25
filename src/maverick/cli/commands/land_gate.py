"""Assumption-frontier gate + provenance report — shared by ``land`` verbs.

``maverick land`` (the apply path, ``land.py``) and ``maverick land
--status`` (the read-only query, ``land_status.py``) evaluate the exact
same gate and render/persist the exact same report; only what they do
*afterwards* differs. That shared half lives here so neither command
imports the other's private surface — an earlier revision had
``land_status`` reaching into five underscore-prefixed ``land`` helpers
while ``land`` lazily imported ``land_status`` back to dodge the resulting
cycle.

Gate semantics (052-conditional-landing, strict / no bypass flag): any
open entry of any severity — including low, including legacy escalation
beads — or any answered entry pending reconciliation blocks landing.
The gate degrades *open* (never blocks) when bd is unavailable or the
ledger query fails, but reports ``verification=None`` so callers never
advertise a false "verified" classification.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from maverick.cli.console import console, err_console
from maverick.cli.output import format_warning

if TYPE_CHECKING:
    from pathlib import Path

    from maverick.assumptions.land_report import LandReport
    from maverick.assumptions.models import (
        AssumptionReportEntry,
        LandFrontier,
        LandVerification,
    )

__all__ = [
    "build_report",
    "check_assumption_gate",
    "display_verification",
    "persist_report_json",
    "render_and_persist_land_report",
    "render_land_report_terminal",
]


async def check_assumption_gate(
    cwd: Path,
    *,
    quiet: bool = False,
) -> tuple[bool, tuple[AssumptionReportEntry, ...], LandVerification | None]:
    """Evaluate the strict, repo-wide assumption frontier gate.

    Returns ``(blocks, entries, verification)``. The gate blocks on any
    open entry (any severity, incl. legacy) or any answered entry pending
    reconciliation (051's predicate) — strict, no bypass flag
    (Clarifications 2026-07-24). ``entries`` is the full repo-wide
    materialization (empty when degraded); ``verification`` is ``None``
    when bd is unavailable or the ledger query failed — the gate degrades
    open (never blocks) but must not report a false "verified"
    classification. Prints the blocking table (grouped by owning spec,
    per-row action hints) as a side effect when the gate blocks, unless
    ``quiet`` is set (JSON modes, and any caller that renders the full
    provenance report itself — the blocking rows appear there too, so
    printing both duplicates every row).
    """
    from maverick.assumptions.land_report import classify, frontier
    from maverick.assumptions.ledger import report_entries
    from maverick.beads.client import BeadClient

    client = BeadClient(cwd=cwd)
    if not await client.verify_available():
        return False, (), None

    try:
        entries = await report_entries(client)
    except Exception as exc:  # noqa: BLE001 — non-fatal; gate passes on query failure
        out = err_console if quiet else console
        out.print(format_warning(f"Assumption gate check failed: {exc}"))
        return False, (), None

    land_frontier = frontier(entries)
    verification = classify(entries)

    if not land_frontier.is_empty:
        if not quiet:
            _display_assumption_gate_table(land_frontier)
        return True, entries, verification

    return False, entries, verification


def _display_assumption_gate_table(land_frontier: LandFrontier) -> None:
    """Render blocking entries (open + pending-reconcile) grouped by spec.

    Open entries and pending-reconciliation entries get distinct
    resolution hints (research R4 — one detection predicate, two
    actions) printed below the table rather than a per-row column, to
    keep the table readable at typical terminal widths.
    """
    entries = tuple(land_frontier.open_entries) + tuple(land_frontier.pending_reconcile_entries)

    table = Table(show_header=True, header_style="bold red")
    table.add_column("ID", width=20)
    table.add_column("Severity", width=10)
    table.add_column("Spec", width=25)
    table.add_column("Question")

    for entry in sorted(entries, key=lambda e: (e.record.owner_spec, e.record.bead_id)):
        question = entry.record.question
        question = question[:80] + "..." if len(question) > 80 else question
        # Agent-authored free text: `escape` it, or Rich silently eats any
        # `[...]` run as a style tag.
        table.add_row(
            entry.record.bead_id,
            entry.record.severity.value,
            escape(entry.record.owner_spec),
            escape(question),
        )

    console.print()
    panel = Panel(
        table,
        title=f"Blocking Assumptions ({len(entries)})",
        border_style="red",
    )
    console.print(panel)
    console.print()
    if land_frontier.open_entries:
        console.print("Resolve open entries with: [bold]maverick review <id>[/bold]")
    if land_frontier.pending_reconcile_entries:
        console.print("Resolve pending reconciliation with: [bold]maverick reconcile[/bold]")
    console.print()


def display_verification(
    verification: LandVerification | None,
    entries: tuple[AssumptionReportEntry, ...],
) -> None:
    """Print the land classification line (contracts/cli-land.md "Output" §2).

    No-op when *verification* is ``None`` (bd unavailable / query failed —
    the degraded gate must never report a false classification).
    """
    from maverick.assumptions.models import LandVerification

    if verification is LandVerification.CONDITIONALLY_VERIFIED:
        waived_count = sum(1 for e in entries if e.bucket == "waived")
        console.print(
            f"[yellow]✓ Conditionally verified on unresolved assumptions "
            f"({waived_count} waived)[/yellow]"
        )
    elif verification is LandVerification.VERIFIED:
        console.print("[green]✓ Verified[/green]")


# =====================================================================
# Assumption land report (US2 — provenance + persistence)
# =====================================================================


def render_and_persist_land_report(
    entries: tuple[AssumptionReportEntry, ...],
    verification: LandVerification | None,
    *,
    run_id: str,
    dry_run: bool,
    cwd: Path,
) -> Path | None:
    """Build, render (terminal), and persist the land provenance report.

    Runs for every evaluation (blocked, dry-run, successful) — the report
    is the audit trail of what land saw, even for a refused attempt
    (contracts/cli-land.md). Persistence failure degrades to a warning
    and never affects the gate's exit code.

    Returns:
        The persisted markdown artifact's path, or ``None`` when
        persistence failed (so callers don't advertise a missing file).
    """
    from maverick.assumptions.land_report import persist_report

    report = build_report(entries, verification, run_id=run_id, dry_run=dry_run)

    if report.degraded:
        console.print(format_warning("Assumption ledger unavailable — report may be incomplete."))

    render_land_report_terminal(report)

    try:
        json_path, md_path = persist_report(report, cwd=cwd)
    except OSError as exc:
        console.print(format_warning(f"Failed to persist land report: {exc}"))
        return None
    console.print(f"Report: {json_path}")
    console.print()
    return md_path


def build_report(
    entries: tuple[AssumptionReportEntry, ...],
    verification: LandVerification | None,
    *,
    run_id: str,
    dry_run: bool,
) -> LandReport:
    """Build the land provenance report with no terminal rendering (JSON paths).

    Counterpart to :func:`render_and_persist_land_report` for ``--json``
    callers (``land_status.run_status`` and ``land``'s own JSON apply
    path) — same ``build_report`` call, no Rich output.
    """
    from maverick.assumptions.land_report import build_report as _build

    degraded = verification is None
    return _build(entries, verification, run_id=run_id, dry_run=dry_run, degraded=degraded)


def persist_report_json(
    report: LandReport,
    *,
    cwd: Path,
) -> tuple[dict[str, str | None], bool]:
    """Persist *report*, routing any failure warning to stderr (JSON paths).

    Returns ``(report_paths, degraded_persistence)`` — ``report_paths``
    values are ``None`` when persistence failed (never a gate failure —
    the caller still lands/reports, just without the artifact paths).
    """
    from maverick.assumptions.land_report import persist_report

    try:
        json_path, md_path = persist_report(report, cwd=cwd)
    except OSError as exc:
        err_console.print(format_warning(f"Failed to persist land report: {exc}"))
        return {"json": None, "md": None}, True
    return {"json": str(json_path), "md": str(md_path)}, False


def render_land_report_terminal(report: LandReport) -> None:
    """Render the grouped provenance report to the terminal.

    Walks ``report.to_dict()`` (not raw entries) so the terminal view can
    never drift from the persisted JSON — one source of truth.
    """
    data = report.to_dict()
    if not data["specs"]:
        console.print("No assumptions adopted.")
        return

    bucket_style = {"resolved": "green", "waived": "yellow", "open": "red"}
    bucket_heading = {"resolved": "Resolved", "waived": "Waived", "open": "Open"}

    for spec in data["specs"]:
        console.print(f"[bold]{escape(spec['owner_spec'] or '(unattributed)')}[/bold]")
        by_bucket: dict[str, list[dict[str, Any]]] = {"resolved": [], "waived": [], "open": []}
        for entry in spec["entries"]:
            by_bucket[entry["bucket"]].append(entry)

        for bucket_key in ("resolved", "waived", "open"):
            bucket_entries = by_bucket[bucket_key]
            if not bucket_entries:
                continue
            style = bucket_style[bucket_key]
            console.print(
                f"  [{style}]{bucket_heading[bucket_key]}[/{style}] ({len(bucket_entries)})"
            )
            for entry in bucket_entries:
                # Every free-text field below is agent- or human-authored,
                # so it goes through `escape`: Rich parses `[...]` as a
                # style tag and silently drops it otherwise.
                console.print(f"    {entry['bead_id']}  {escape(entry['question'])}")
                if entry["waiver"]:
                    waiver = entry["waiver"]
                    console.print(
                        f"      waived by {escape(str(waiver['by']))} at "
                        f"{escape(str(waiver['at']))}: {escape(str(waiver['reason']))}"
                    )
                if entry["affected_change_ids"]:
                    console.print(f"      changes: {', '.join(entry['affected_change_ids'])}")
                if entry["annotations"]:
                    # Literally bracketed — `escape` is what keeps the whole
                    # line from rendering as blank whitespace.
                    console.print(f"      {escape('[' + ', '.join(entry['annotations']) + ']')}")
        console.print()
