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
        return

    # ── 3. Runway consolidation (best-effort) ─────────────────────
    await _maybe_consolidate(cwd, no_consolidate)

    # ── 4. Mode-specific next-step hint ───────────────────────────
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
            f"Finalize hint: push to [bold]{target}[/bold] and "
            f"open a PR with [bold]gh pr create[/bold]."
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
        from maverick.executor import create_default_executor
        from maverick.library.actions.curation import (
            build_curator_prompt,
            ensure_refs_trailers,
            parse_curation_plan,
        )

        _executor = create_default_executor()
        try:
            _result = await _executor.execute_named(
                agent="maverick.curator",
                user_prompt=build_curator_prompt(
                    {
                        "commits": curation_ctx["commits"],
                        "log_summary": curation_ctx["log_summary"],
                    }
                ),
                step_name="curate",
                cwd=cwd,
            )
            raw_output = str(_result.output) if _result.output else ""
        finally:
            await _executor.cleanup()
        plan = parse_curation_plan(raw_output)
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
        raise SystemExit(ExitCode.SUCCESS)

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
