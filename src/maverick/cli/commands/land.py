"""``maverick land`` command.

Curate commit history and push after ``maverick fly`` finishes.
Uses an AI agent to intelligently reorganize commits, with user
approval before applying changes.
"""

from __future__ import annotations

from typing import Any

import click
from rich.panel import Panel
from rich.table import Table

from maverick.cli.console import console, err_console
from maverick.cli.context import ExitCode, async_command
from maverick.cli.output import format_error, format_success
from maverick.logging import get_logger

logger = get_logger(__name__)


@click.command()
@click.option(
    "--no-curate",
    is_flag=True,
    default=False,
    help="Skip curation, just push.",
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
@click.pass_context
@async_command
async def land(
    ctx: click.Context,
    no_curate: bool,
    dry_run: bool,
    yes: bool,
    base: str,
    heuristic_only: bool,
) -> None:
    """Curate commit history and push.

    Finalizes work from 'maverick fly' by reorganizing commits into
    clean history and pushing to remote. Run this when you're ready
    to ship.

    By default, an AI agent analyzes commits and proposes a curation
    plan (squash fix commits, improve messages, reorder for logical
    flow). You review and approve the plan before it's applied.

    Examples:

        maverick land

        maverick land --dry-run

        maverick land --no-curate

        maverick land --heuristic-only

        maverick land --base feature-branch

        maverick land --yes
    """
    from maverick.library.actions.git import git_push
    from maverick.library.actions.jj import (
        curate_history,
        gather_curation_context,
    )

    # ── 1. Check there are commits to land ──────────────────────────
    curation_ctx = await gather_curation_context(base)
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

    # ── 2. Curation ────────────────────────────────────────────────
    if no_curate:
        console.print("Skipping curation (--no-curate).")
    elif heuristic_only:
        console.print("Running heuristic curation...")
        result = await curate_history(base)
        if result["success"]:
            absorb = "yes" if result["absorb_ran"] else "no"
            squashed = result["squashed_count"]
            console.print(
                f"Heuristic curation: absorb={absorb}, squashed={squashed} commits."
            )
        else:
            err_console.print(
                format_error(
                    f"Heuristic curation failed: {result['error']}",
                )
            )
            raise SystemExit(ExitCode.FAILURE)
    else:
        # Agent-driven curation
        await _agent_curate(
            curation_ctx=curation_ctx,
            base=base,
            dry_run=dry_run,
            auto_approve=yes,
        )

    # ── 3. Push ────────────────────────────────────────────────────
    if dry_run:
        console.print("Dry run — skipping push.")
        return

    console.print("Pushing...")
    push_result = await git_push(set_upstream=True)
    if push_result["success"]:
        console.print(
            format_success(
                f"Landed {len(commits)} commit(s).",
            )
        )
    else:
        err_console.print(
            format_error(
                f"Push failed: {push_result['error']}",
                suggestion="You can retry with 'maverick land --no-curate'.",
            )
        )
        raise SystemExit(ExitCode.FAILURE)


async def _agent_curate(
    curation_ctx: dict[str, Any],
    base: str,
    dry_run: bool,
    auto_approve: bool,
) -> None:
    """Run agent-driven curation with interactive approval.

    Args:
        curation_ctx: Output of gather_curation_context().
        base: Base revision.
        dry_run: If True, show plan and exit.
        auto_approve: If True, skip the approval prompt.

    Raises:
        SystemExit: On failure or user rejection.
    """
    from maverick.library.actions.jj import execute_curation_plan

    console.print("Analyzing commits with curator agent...")

    try:
        from maverick.agents.curator import CuratorAgent

        agent = CuratorAgent()
        raw_output = await agent.generate(
            {
                "commits": curation_ctx["commits"],
                "log_summary": curation_ctx["log_summary"],
            }
        )
        # generate returns str when return_usage=False
        assert isinstance(raw_output, str)
        plan = agent.parse_plan(raw_output)
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
    result = await execute_curation_plan(plan)
    if result["success"]:
        console.print(
            f"Curation complete: {result['executed_count']}/{result['total_count']} "
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
                suggestion="Repository was rolled back to pre-curation state.",
            )
        )
        raise SystemExit(ExitCode.FAILURE)


def _display_plan(plan: list[dict[str, Any]]) -> None:
    """Render the curation plan as a Rich table inside a panel.

    Args:
        plan: List of plan step dicts.
    """
    table = Table(show_header=True, header_style="bold", show_lines=False)
    table.add_column("#", style="dim", width=3)
    table.add_column("Command", width=30)
    table.add_column("Reason")

    for i, step in enumerate(plan, 1):
        cmd_str = f"jj {step['command']} {' '.join(step.get('args', []))}"
        table.add_row(str(i), cmd_str, step.get("reason", ""))

    panel = Panel(
        table,
        title=f"Curation Plan ({len(plan)} operation{'s' if len(plan) != 1 else ''})",
        border_style="cyan",
    )
    console.print(panel)
