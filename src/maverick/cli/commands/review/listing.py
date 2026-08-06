"""``maverick review --list [--json]`` — list assumption-ledger entries.

Split out of ``maverick.cli.commands.review`` (T006/T010,
053-assumption-review-console). One bd sweep via
``assumptions.ledger.report_entries``, filtered in-process by
status/spec/severity, sorted into the canonical presentation order, and
rendered either as a JSON envelope (``verb`` ``review.list``) or a minimal
Rich table.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from rich.markup import escape
from rich.table import Table

from maverick.assumptions.models import STATUS_OPEN
from maverick.cli.console import console
from maverick.cli.context import ExitCode
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.assumptions.models import AssumptionReportEntry
    from maverick.beads.client import BeadClient

__all__ = ["run_list"]

logger = get_logger(__name__)

#: Presentation-order rank — high severity sorts first (data-model.md
#: "canonical ordering": owner_spec asc, then severity high->low, then
#: stable ledger order).
_SEVERITY_RANK: dict[str, int] = {"high": 2, "medium": 1, "low": 0}


def _filter_and_sort(
    entries: tuple[AssumptionReportEntry, ...],
    *,
    statuses: frozenset[str],
    owner_specs: frozenset[str],
    severities: frozenset[str],
) -> list[AssumptionReportEntry]:
    """Apply the AND-across/OR-within status/spec/severity filters, then sort.

    Sort key: ``(owner_spec, -severity_rank, original_index)`` — Python's
    ``sorted`` is stable, so capturing ``original_index`` before sorting
    preserves ``report_entries()``'s ledger order as the final tiebreak
    without needing any special-casing.
    """
    indexed = list(enumerate(entries))
    selected = [
        (idx, entry)
        for idx, entry in indexed
        if entry.record.status in statuses
        and (not owner_specs or entry.record.owner_spec in owner_specs)
        and (not severities or entry.record.severity.value in severities)
    ]
    selected.sort(
        key=lambda pair: (
            pair[1].record.owner_spec,
            -_SEVERITY_RANK[pair[1].record.severity.value],
            pair[0],
        )
    )
    return [entry for _, entry in selected]


async def _backfill_entries(
    client: BeadClient,
    entries: list[AssumptionReportEntry],
) -> list[AssumptionReportEntry]:
    """Back-fill suggestions for the *open* entries among *entries*.

    Restricted to open entries with no stored suggestion, deliberately:
    back-fill persists what it computes with a ``bd set-state`` write, and
    an answered/waived entry will never be reviewed again, so writing a
    suggestion onto one is pure cost on a read-only verb (the
    ``maverick-review`` skill calls ``review --list`` on every sweep).
    Callers pass the already-filtered, already-sorted selection so the
    write set is exactly what the caller will render.

    Best-effort (FR-021): a runway store that isn't initialized degrades
    silently inside :func:`backfill_suggestions` itself; any other failure
    raised at this call site is caught here and also degrades to a
    debug-logged no-op — the original *entries* are returned unchanged, in
    their original order.
    """
    from maverick.assumptions.suggestions import backfill_suggestions
    from maverick.runway.store import RunwayStore, runway_path_for

    targets = [e for e in entries if e.record.status == STATUS_OPEN and e.suggestion is None]
    if not targets:
        return entries

    # No `is_initialized` short-circuit here: `backfill_suggestions` already
    # treats an uninitialized store as a debug-logged no-op (FR-021), so
    # that single check stays in one place.
    store = RunwayStore(runway_path_for(Path.cwd()))
    try:
        updated = await backfill_suggestions(client, store, targets)
    except Exception:
        logger.debug("review_list_backfill_failed", exc_info=True)
        return entries

    by_id = {entry.record.bead_id: entry for entry in updated}
    return [by_id.get(entry.record.bead_id, entry) for entry in entries]


def _build_counts(entries: list[AssumptionReportEntry]) -> dict[str, object]:
    """The ``counts`` object — reflects the filtered selection (contract)."""
    by_status = {"open": 0, "answered": 0, "waived": 0}
    by_severity = {"low": 0, "medium": 0, "high": 0}
    pending_reconcile = 0
    for entry in entries:
        status = entry.record.status
        if status in by_status:
            by_status[status] += 1
        by_severity[entry.record.severity.value] += 1
        if entry.pending_reconcile:
            pending_reconcile += 1
    return {
        "total": len(entries),
        "by_status": by_status,
        "by_severity": by_severity,
        "pending_reconcile": pending_reconcile,
    }


def _render_table(entries: list[AssumptionReportEntry], counts: dict[str, object]) -> None:
    """Minimal human table (contract: "new, minimal; reuses the same data")."""
    if not entries:
        console.print("No assumption-ledger entries match.")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Status")
    table.add_column("Severity")
    table.add_column("Spec")
    table.add_column("Question")
    table.add_column("Suggestion")

    for entry in entries:
        question = entry.record.question or entry.record.bead_id
        question = question[:80] + "..." if len(question) > 80 else question
        # Agent/human-authored free text: `escape` it, or Rich silently
        # eats any `[...]` run as a style tag.
        table.add_row(
            entry.record.bead_id,
            entry.record.status,
            entry.record.severity.value,
            escape(entry.record.owner_spec),
            escape(question),
            "suggested" if entry.suggestion is not None else "",
        )

    console.print(table)
    console.print(f"Total: {counts['total']}")


async def run_list(
    *,
    statuses: frozenset[str],
    owner_specs: frozenset[str],
    severities: frozenset[str],
    json_mode: bool,
) -> None:
    """List assumption-ledger entries, filtered and canonically ordered.

    Verifies bd availability first (contract: ``bd-unavailable`` /
    exit 1), then runs one ``report_entries()`` sweep and filters/sorts/
    projects in-process — no second bd call.
    """
    from maverick.assumptions.ledger import report_entries
    from maverick.assumptions.serialize import entry_to_dict
    from maverick.beads.client import BeadClient
    from maverick.cli.json_output import ErrorKind, JsonEnvelope, emit_json, json_error_handler

    client = BeadClient(cwd=Path.cwd())
    if not await client.verify_available():
        message = "bd is not available"
        if json_mode:
            emit_json(JsonEnvelope.failure("review.list", ErrorKind.BD_UNAVAILABLE, message))
        else:
            console.print(f"[red]Error:[/] {message}")
        raise SystemExit(ExitCode.FAILURE)

    effective_statuses = statuses or frozenset({STATUS_OPEN})

    if json_mode:
        with json_error_handler("review.list"):
            entries = await report_entries(client)
    else:
        from maverick.assumptions.errors import AssumptionLedgerError

        try:
            entries = await report_entries(client)
        except AssumptionLedgerError as exc:
            console.print(f"[red]Error:[/] {exc}")
            raise SystemExit(ExitCode.FAILURE) from exc

    # Back-fill runs on the filtered selection, never the whole repo sweep:
    # it writes what it computes, so evaluating rows the caller filtered out
    # would turn this read verb into a repo-wide write.
    selected = _filter_and_sort(
        entries,
        statuses=effective_statuses,
        owner_specs=owner_specs,
        severities=severities,
    )
    selected = await _backfill_entries(client, selected)
    counts = _build_counts(selected)

    if json_mode:
        result: dict[str, object] = {
            "entries": [entry_to_dict(entry) for entry in selected],
            "counts": counts,
        }
        emit_json(JsonEnvelope.success("review.list", result))
        return

    _render_table(selected, counts)
