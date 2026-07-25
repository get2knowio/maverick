"""``maverick land --status`` — read-only frontier/landability query.

The read-only counterpart to the ``land`` apply path (053-assumption-
review-console, contracts/cli-land-json.md "land --status"): evaluates the
assumption frontier gate, builds and persists the same provenance report
``land`` would, and stops — no curation, no consolidation, no manifest
display, no history mutation. A blocked frontier is an *answer* for a
status query, not a failure, so this always exits 0 unless a real error
(``internal``/``vcs``) occurs.

Shares its gate-evaluation/report-building/persisting logic with
``maverick.cli.commands.land`` via the common
``maverick.cli.commands.land_gate`` module rather than duplicating it (or
reaching into the other command's private surface) — this module only
assembles the status-specific result document and renders/emits it.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from maverick.cli.commands.land_gate import (
    build_report,
    check_assumption_gate,
    display_verification,
    persist_report_json,
    render_land_report_terminal,
)
from maverick.cli.console import console
from maverick.cli.json_output import JsonEnvelope, emit_json, json_error_handler
from maverick.cli.output import format_warning

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["run_status"]

_VERB = "land.status"


async def run_status(*, base: str, cwd: Path, json_mode: bool) -> None:
    """Evaluate the assumption frontier gate read-only and report status.

    ``base`` is accepted for CLI symmetry with the apply path but ignored:
    the gate evaluates the whole repo-wide ledger, not a base-revision
    scoped commit range (contracts/cli-land-json.md).
    """
    del base

    from maverick.assumptions.land_report import frontier

    run_id = uuid.uuid4().hex[:8]

    # `quiet=True` on both paths: this function renders the full grouped
    # provenance report itself (or emits it inside the envelope), which
    # already lists every blocking row. Letting the gate print its own
    # blocking panel too would duplicate all of them.
    if json_mode:
        with json_error_handler(_VERB):
            _blocks, entries, verification = await check_assumption_gate(cwd, quiet=True)
            report = build_report(entries, verification, run_id=run_id, dry_run=False)
            report_paths, degraded_persistence = persist_report_json(report, cwd=cwd)
            land_frontier = frontier(entries)

            result: dict[str, object] = {
                # `degraded` means the ledger could not be read at all (bd
                # unavailable / query failure), so `frontier_clear: true`
                # below reflects an *empty* evaluation, not a verified one.
                # Consumers must treat `frontier_clear && !degraded` as the
                # landable condition — this is the top-level signal for
                # that, distinct from `degraded_persistence` (which is only
                # about writing the artifact).
                "degraded": report.degraded,
                "frontier_clear": land_frontier.is_empty,
                "verification": (verification.value if verification is not None else None),
                "blocking": {
                    "open": [e.record.bead_id for e in land_frontier.open_entries],
                    "pending_reconcile": [
                        e.record.bead_id for e in land_frontier.pending_reconcile_entries
                    ],
                },
                "report": report.to_dict(),
                "report_paths": report_paths,
            }
            if degraded_persistence:
                result["degraded_persistence"] = True
            emit_json(JsonEnvelope.success(_VERB, result))
        return

    # Human mode: same evaluation, rendered to the terminal.
    from maverick.assumptions.land_report import persist_report

    _blocks, entries, verification = await check_assumption_gate(cwd, quiet=True)
    report = build_report(entries, verification, run_id=run_id, dry_run=False)
    if report.degraded:
        console.print(format_warning("Assumption ledger unavailable — report may be incomplete."))
    render_land_report_terminal(report)
    try:
        json_path, _md_path = persist_report(report, cwd=cwd)
        console.print(f"Report: {json_path}")
    except OSError as exc:
        console.print(format_warning(f"Failed to persist land report: {exc}"))
    console.print()
    display_verification(verification, entries)
