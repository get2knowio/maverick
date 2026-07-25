"""``maverick land`` command.

Curate the commit history written by ``maverick fly``.

Single-repo (CWD) workflow model: fly commits land directly on the user's
current branch, so land just curates that history in place. Earlier
revisions bridged a hidden jj workspace into the user repo via
``WorkspaceManager`` — that path is retired (see
plans/cryptic-napping-waffle.md).

Three modes (kept for compatibility, all curate the same way; differ
only in the post-curation hint):

* ``--approve`` (default): curate, leave the user to push/PR manually.
* ``--eject``: curate, then print push/PR instructions for an
  ``maverick/preview/<project>`` branch.
* ``--finalize``: curate, then print push/PR instructions for an
  ``maverick/<project>`` branch.

PR opening + remote pushing is intentionally not automated in this
slice. The full architecture (see
``.claude/scratchpads/architecture-pull-work-push.md``) re-introduces
those automations once the underlying state machine lands.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import click
from rich.panel import Panel
from rich.table import Table

from maverick.cli.console import console, err_console
from maverick.cli.context import ExitCode, async_command
from maverick.cli.output import format_error, format_success, format_warning
from maverick.logging import get_logger

logger = get_logger(__name__)


@click.command()
@click.option(
    "--no-curate",
    is_flag=True,
    default=False,
    help="Skip curation, just emit the next-step hint.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show curation plan without executing.",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Auto-approve curation plan.",
)
@click.option(
    "--base",
    default="main",
    show_default=True,
    help="Base revision for curation scope.",
)
@click.option(
    "--heuristic-only",
    is_flag=True,
    default=False,
    help="Use heuristic curation (no agent).",
)
@click.option(
    "--eject",
    is_flag=True,
    default=False,
    help="Curate and emit push/PR instructions for an eject preview branch.",
)
@click.option(
    "--finalize",
    is_flag=True,
    default=False,
    help="Curate and emit push/PR instructions for the maverick branch.",
)
@click.option(
    "--no-consolidate",
    is_flag=True,
    default=False,
    help="Skip runway consolidation.",
)
@click.option(
    "--branch",
    default=None,
    help="Branch label suggested in the next-step hint.",
)
@click.pass_context
@async_command
async def land(
    ctx: click.Context,
    no_curate: bool,
    dry_run: bool,
    yes: bool,
    base: str,
    heuristic_only: bool,
    eject: bool,
    finalize: bool,
    no_consolidate: bool,
    branch: str | None,
) -> None:
    """Curate commit history written by ``maverick fly``.

    Examples:

    \b
        maverick land
        maverick land --dry-run
        maverick land --no-curate
        maverick land --heuristic-only
        maverick land --eject
        maverick land --finalize
        maverick land --yes
    """
    from maverick.library.actions.jj import (
        curate_history,
        gather_curation_context,
    )

    cwd = Path.cwd().resolve()
    project_name = cwd.name
    run_id = uuid.uuid4().hex[:8]

    # ── 1. Check there are commits to land ──────────────────────────
    curation_ctx = await gather_curation_context(base, cwd=cwd)
    if not curation_ctx["success"]:
        err_console.print(
            format_error(
                f"Failed to gather commit context: {curation_ctx['error']}",
            )
        )
        raise SystemExit(ExitCode.FAILURE)

    commits = curation_ctx["commits"]
    if not commits:
        console.print("Nothing to land — no commits found above base revision.")
        return

    console.print(f"Found {len(commits)} commit(s) above [bold]{base}[/bold].")

    # ── 1b. Display human review manifest if present ─────────────
    _display_human_review_manifest(cwd)

    # ── 1c. Assumption ledger gate + provenance report. Blocks unless
    # every entry (any severity, incl. legacy) has been answered or
    # waived via `maverick review`, and no answered entry is pending
    # reconciliation. No bypass flag exists. Every evaluation (blocked,
    # dry-run, successful) renders and persists the grouped provenance
    # report (contracts/cli-land.md); `--dry-run` still evaluates and
    # renders, but only exits non-zero at the end (after the rest of the
    # preview runs) rather than short-circuiting immediately.
    gate_blocks, gate_entries, verification = await _check_assumption_gate(cwd)
    report_md_path = cwd / ".maverick" / "runs" / run_id / "land-report.md"
    _render_and_persist_land_report(
        gate_entries, verification, run_id=run_id, dry_run=dry_run, cwd=cwd
    )
    if gate_blocks and not dry_run:
        raise SystemExit(ExitCode.FAILURE)

    # ── 2. Curation ────────────────────────────────────────────────
    if no_curate:
        console.print("Skipping curation (--no-curate).")
    elif heuristic_only:
        console.print("Running heuristic curation...")
        result = await curate_history(base, cwd=cwd)
        if result["success"]:
            absorb = "yes" if result["absorb_ran"] else "no"
            squashed = result["squashed_count"]
            console.print(f"Heuristic curation: absorb={absorb}, squashed={squashed} commits.")
        else:
            err_console.print(
                format_error(
                    f"Heuristic curation failed: {result['error']}",
                )
            )
            raise SystemExit(ExitCode.FAILURE)
    else:
        await _agent_curate(
            curation_ctx=curation_ctx,
            base=base,
            dry_run=dry_run,
            auto_approve=yes,
            cwd=cwd,
        )

    if dry_run:
        console.print("Dry run — skipping next-step hint.")
        if gate_blocks:
            raise SystemExit(ExitCode.FAILURE)
        return

    # ── 3. Runway consolidation (best-effort) ─────────────────────
    await _maybe_consolidate(cwd, no_consolidate)

    # ── 4. Mode-specific next-step hint ───────────────────────────
    _display_verification(verification, gate_entries)
    console.print(format_success(f"Curated {len(commits)} commit(s) on the current branch."))
    if eject:
        preview = branch or f"maverick/preview/{project_name}"
        console.print()
        console.print(
            f"Eject hint: push to a preview branch with "
            f"[bold]git push origin HEAD:{preview}[/bold]."
        )
    elif finalize:
        target = branch or f"maverick/{project_name}"
        console.print()
        console.print(
            f"Finalize hint: push to [bold]{target}[/bold] and open a PR with "
            f"[bold]gh pr create --base {base} --body-file {report_md_path}[/bold]."
        )
    else:
        console.print()
        console.print("Next: push the curated branch to your remote and open a PR.")


# =====================================================================
# Runway consolidation
# =====================================================================


async def _maybe_consolidate(
    cwd: Path,
    no_consolidate: bool,
) -> None:
    """Best-effort runway consolidation.

    Single-repo model: runway data lives in ``<cwd>/.maverick/runway/``
    and survives across runs without any sync step. Consolidation is the
    only operation worth running here — it prunes stale episodic records
    and updates the semantic summary.
    """
    if no_consolidate:
        return

    try:
        from maverick.config import load_config

        config = load_config()
        if not config.runway.enabled or not config.runway.consolidation.auto:
            return

        from maverick.library.actions.consolidation import consolidate_runway

        console.print("Consolidating runway knowledge store...")
        result = await consolidate_runway(
            cwd=cwd,
            max_age_days=config.runway.consolidation.max_episodic_age_days,
            max_records=config.runway.consolidation.max_episodic_records,
            force=False,
        )
        if result.skipped:
            logger.debug("runway_consolidation_skipped", reason=result.skip_reason)
        elif result.success:
            msg = f"  Pruned {result.records_pruned} old records."
            if result.summary_updated:
                msg += " Updated consolidated-insights.md."
            console.print(msg)
        else:
            console.print(format_warning(f"Runway consolidation failed: {result.error}"))
    except Exception as exc:
        # Best-effort — never block landing
        console.print(format_warning(f"Runway consolidation failed: {exc}"))
        logger.debug("runway_consolidation_error", error=str(exc))


# =====================================================================
# Agent curation
# =====================================================================


async def _agent_curate(
    curation_ctx: dict[str, Any],
    base: str,
    dry_run: bool,
    auto_approve: bool,
    cwd: Path,
) -> None:
    """Run agent-driven curation with interactive approval."""
    from maverick.library.actions.jj import execute_curation_plan

    console.print("Analyzing commits with curator agent...")

    try:
        from maverick.agents.personas import CuratorAgent
        from maverick.config import load_config
        from maverick.library.actions.curation import (
            build_curator_prompt,
            ensure_refs_trailers,
        )
        from maverick.runtime.agent_factory import runtime_for_agent

        config = load_config()
        runtime, _ = runtime_for_agent("review", agents_config=config.agents)
        async with CuratorAgent(runtime=runtime, cwd=str(cwd)) as agent:
            payload = await agent.curate(
                build_curator_prompt(
                    {
                        "commits": curation_ctx["commits"],
                        "log_summary": curation_ctx["log_summary"],
                    }
                )
            )
        plan = [
            {"command": step.command, "args": list(step.args), "reason": step.reason}
            for step in payload.steps
        ]
        # Safety net: guarantee every ``describe`` carries a ``Refs:``
        # trailer so eval tooling can join landed commits to runway
        # state even if the curator skipped the prompt instruction
        # (FUTURE.md §3.9).
        plan = ensure_refs_trailers(plan, curation_ctx["commits"])
    except SystemExit:
        raise
    except Exception as e:
        err_console.print(
            format_error(
                f"Curator agent failed: {e}",
                suggestion="Try --heuristic-only as a fallback.",
            )
        )
        raise SystemExit(ExitCode.FAILURE) from e

    if not plan:
        console.print("Curator: no curation needed — history looks clean.")
        return

    # Display plan
    _display_plan(plan)

    if dry_run:
        console.print("Dry run — plan not applied.")
        # Do NOT raise SystemExit here — the caller (`land()`) decides the
        # final exit code from the assumption gate (`gate_blocks`), which
        # this branch must not pre-empt (T012 fix; analysis I1).
        return

    # Approval gate
    if not auto_approve:
        answer = console.input("\nApply this plan? [y/N] ")
        if not answer.strip().lower().startswith("y"):
            console.print("Curation cancelled.")
            raise SystemExit(ExitCode.SUCCESS)

    # Execute
    console.print("Applying curation plan...")
    result = await execute_curation_plan(plan, cwd=cwd)
    if result["success"]:
        console.print(
            f"Curation complete: "
            f"{result['executed_count']}/{result['total_count']} "
            f"operations applied."
        )
    else:
        err_console.print(
            format_error(
                f"Curation failed: {result['error']}",
                details=[
                    f"Executed {result['executed_count']}/{result['total_count']} steps.",
                    f"Snapshot ID: {result['snapshot_id']} (for manual recovery).",
                ],
                suggestion=("Repository was rolled back to pre-curation state."),
            )
        )
        raise SystemExit(ExitCode.FAILURE)


def _display_plan(plan: list[dict[str, Any]]) -> None:
    """Render the curation plan as a Rich table inside a panel."""
    table = Table(
        show_header=True,
        header_style="bold",
        show_lines=False,
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Command", width=30)
    table.add_column("Reason")

    for i, step in enumerate(plan, 1):
        cmd_str = f"jj {step['command']} {' '.join(step.get('args', []))}"
        table.add_row(str(i), cmd_str, step.get("reason", ""))

    panel = Panel(
        table,
        title=(f"Curation Plan ({len(plan)} operation{'s' if len(plan) != 1 else ''})"),
        border_style="cyan",
    )
    console.print(panel)


# =====================================================================
# Assumption ledger gate
# =====================================================================


async def _check_assumption_gate(cwd: Path) -> tuple[bool, tuple[Any, ...], Any]:
    """Evaluate the strict, repo-wide assumption frontier gate.

    Returns ``(blocks, entries, verification)``. The gate blocks on any
    open entry (any severity, incl. legacy) or any answered entry pending
    reconciliation (051's predicate) — strict, no bypass flag
    (Clarifications 2026-07-24). ``entries`` is the full repo-wide
    materialization (empty when degraded); ``verification`` is ``None``
    when bd is unavailable or the ledger query failed — the gate degrades
    open (never blocks) but must not report a false "verified"
    classification. Prints the blocking table (grouped by owning spec,
    per-row action hints) as a side effect when the gate blocks.
    """
    from maverick.assumptions.land_report import classify, frontier
    from maverick.assumptions.ledger import report_entries
    from maverick.assumptions.models import LandVerification
    from maverick.beads.client import BeadClient

    client = BeadClient(cwd=cwd)
    if not await client.verify_available():
        return False, (), None

    try:
        entries = await report_entries(client)
    except Exception as exc:  # noqa: BLE001 — non-fatal; gate passes on query failure
        console.print(format_warning(f"Assumption gate check failed: {exc}"))
        return False, (), None

    land_frontier = frontier(entries)
    verification: LandVerification = classify(entries)

    if not land_frontier.is_empty:
        _display_assumption_gate_table(land_frontier)
        return True, entries, verification

    return False, entries, verification


def _display_assumption_gate_table(land_frontier: Any) -> None:
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
        table.add_row(
            entry.record.bead_id,
            entry.record.severity.value,
            entry.record.owner_spec,
            question,
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


def _display_verification(verification: Any, entries: tuple[Any, ...]) -> None:
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


def _render_and_persist_land_report(
    entries: tuple[Any, ...],
    verification: Any,
    *,
    run_id: str,
    dry_run: bool,
    cwd: Path,
) -> None:
    """Build, render (terminal), and persist the land provenance report.

    Runs for every evaluation (blocked, dry-run, successful) — the report
    is the audit trail of what land saw, even for a refused attempt
    (contracts/cli-land.md). Persistence failure degrades to a warning
    and never affects the gate's exit code.
    """
    from maverick.assumptions.land_report import build_report, persist_report

    degraded = verification is None
    report = build_report(entries, verification, run_id=run_id, dry_run=dry_run, degraded=degraded)

    if degraded:
        console.print(format_warning("Assumption ledger unavailable — report may be incomplete."))

    _render_land_report_terminal(report)

    try:
        json_path, _md_path = persist_report(report, cwd=cwd)
    except OSError as exc:
        console.print(format_warning(f"Failed to persist land report: {exc}"))
        return
    console.print(f"Report: {json_path}")
    console.print()


def _render_land_report_terminal(report: Any) -> None:
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
        console.print(f"[bold]{spec['owner_spec']}[/bold]")
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
                console.print(f"    {entry['bead_id']}  {entry['question']}")
                if entry["waiver"]:
                    waiver = entry["waiver"]
                    console.print(
                        f"      waived by {waiver['by']} at {waiver['at']}: {waiver['reason']}"
                    )
                if entry["affected_change_ids"]:
                    console.print(f"      changes: {', '.join(entry['affected_change_ids'])}")
                if entry["annotations"]:
                    console.print(f"      [{', '.join(entry['annotations'])}]")
        console.print()


def _display_human_review_manifest(cwd: Path) -> None:
    """Display human review manifest if one exists from the fly phase."""
    import json as _json

    plans_dir = cwd / ".maverick" / "plans"
    if not plans_dir.is_dir():
        return

    manifest_path = plans_dir / "human-review-manifest.json"
    if not manifest_path.is_file():
        return

    try:
        items = _json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return

    if not items:
        return

    needs_review = [i for i in items if i.get("status") == "needs-human-review"]
    if not needs_review:
        console.print(format_success("All beads passed review cleanly."))
        return

    console.print()
    table = Table(show_header=True, header_style="bold yellow")
    table.add_column("Bead", width=20)
    table.add_column("Title", width=40)
    table.add_column("Key Findings")

    for item in needs_review:
        findings_str = (
            "\n".join(
                f"  - {f[:100]}..." if len(f) > 100 else f"  - {f}"
                for f in item.get("key_findings", [])
            )
            or "(no findings captured)"
        )
        table.add_row(
            item.get("bead_id", "?"),
            item.get("title", "?")[:40],
            findings_str,
        )

    panel = Panel(
        table,
        title=f"Human Review Required ({len(needs_review)} bead{'s' if len(needs_review) != 1 else ''})",  # noqa: E501
        border_style="yellow",
    )
    console.print(panel)
    console.print()
