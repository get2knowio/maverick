"""``maverick review`` command — lightweight human review of assumption beads.

Displays the escalation context for a human-assigned bead and captures
a structured decision: approve, reject (with guidance), or defer.

Rejected beads spawn a correction bead back into the agent pipeline.
The human provides judgment and direction, not code.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.console import console
from maverick.cli.context import ExitCode, async_command
from maverick.logging import get_logger

logger = get_logger(__name__)


@click.command("review")
@click.argument("bead_id")
@click.option(
    "--approve",
    is_flag=True,
    default=False,
    help="Approve without interactive prompt.",
)
@click.option(
    "--reject",
    "reject_guidance",
    default=None,
    help="Reject with guidance text (non-interactive).",
)
@click.option(
    "--defer",
    is_flag=True,
    default=False,
    help="Defer without interactive prompt.",
)
@click.pass_context
@async_command
async def review(
    ctx: click.Context,
    bead_id: str,
    approve: bool,
    reject_guidance: str | None,
    defer: bool,
) -> None:
    """Review a human-assigned assumption bead.

    Displays the escalation context and captures your decision:
    approve, reject (with guidance for the correction agent), or defer.

    Examples:

        maverick review dea-ykp.7

        maverick review dea-ykp.7 --approve

        maverick review dea-ykp.7 --reject "Use Dockerfile generation instead"

        maverick review dea-ykp.7 --defer
    """
    from maverick.beads.client import BeadClient
    from maverick.beads.models import (
        BeadCategory,
        BeadDefinition,
        BeadType,
    )

    client = BeadClient(cwd=Path.cwd())

    if not await client.verify_available():
        console.print("[red]Error:[/] bd is not available")
        raise SystemExit(ExitCode.FAILURE)

    # Fetch bead details
    try:
        details = await client.show(bead_id)
    except Exception as exc:
        console.print(f"[red]Error:[/] Could not fetch bead {bead_id}: {exc}")
        raise SystemExit(ExitCode.FAILURE)

    state = details.state or {}
    labels = details.labels or []

    # Verify this is a human-assigned review bead
    is_human = (
        "needs-human-review" in labels
        or "assumption-review" in labels
    )
    if not is_human:
        console.print(
            f"[yellow]Warning:[/] Bead {bead_id} is not flagged for "
            f"human review (labels: {labels})"
        )
        if not click.confirm("Review anyway?", default=False):
            return

    # Display the review context
    source_bead = state.get("source_bead", "unknown")
    escalation_type = state.get("escalation_type", "unknown")
    flight_plan = state.get("flight_plan", "unknown")

    console.print()
    console.print("[bold]━" * 60)
    console.print(f"[bold] Assumption Review: {details.title}")
    console.print("[bold]━" * 60)
    console.print()
    console.print(f"[dim]Source bead:[/]  {source_bead}")
    console.print(f"[dim]Flight plan:[/]  {flight_plan}")
    console.print(f"[dim]Escalation:[/]   {escalation_type}")
    console.print()

    if details.description:
        console.print(details.description)
        console.print()

    console.print("[bold]━" * 60)
    console.print()

    # Determine decision — from flags or interactive prompt
    if approve:
        decision = "approve"
        guidance = ""
    elif reject_guidance is not None:
        decision = "reject"
        guidance = reject_guidance
    elif defer:
        decision = "defer"
        guidance = ""
    else:
        # Interactive mode
        console.print("[bold]Decision:[/]")
        console.print()
        console.print("  [green]1.[/] Approve — the current implementation is acceptable")
        console.print("  [red]2.[/] Reject — needs correction (you'll provide guidance)")
        console.print("  [yellow]3.[/] Defer — not enough information, skip for now")
        console.print()

        choice = click.prompt("Choice", type=click.Choice(["1", "2", "3"]))

        if choice == "1":
            decision = "approve"
            guidance = ""
        elif choice == "2":
            decision = "reject"
            console.print()
            console.print(
                "[bold]Guidance for the correction agent[/] "
                "(brief note — what should change?):"
            )
            guidance = click.prompt(">")
        else:
            decision = "defer"
            guidance = ""

    # Execute the decision
    if decision == "approve":
        await client.close(bead_id, reason="approved")
        console.print(f"\n[green]✓[/] Bead {bead_id} closed as approved.")

    elif decision == "reject":
        # Create a correction bead assigned to an agent
        correction_title = f"Correction: {details.title[:150]}"
        correction_desc = (
            f"## Human Guidance\n\n{guidance}\n\n"
            f"## Original Escalation\n\n{details.description or 'N/A'}\n\n"
            f"## Source Bead\n\n{source_bead}"
        )

        correction_def = BeadDefinition(
            title=correction_title,
            bead_type=BeadType.TASK,
            priority=1,
            category=BeadCategory.VALIDATION,
            description=correction_desc,
            labels=["correction", f"corrects:{bead_id}"],
        )

        # Resolve parent epic from source bead
        parent_id = None
        try:
            source_details = await client.show(source_bead)
            parent_id = source_details.parent_id
        except Exception:
            pass

        try:
            created = await client.create_bead(
                correction_def, parent_id=parent_id
            )
            console.print(
                f"\n[yellow]→[/] Correction bead created: {created.bd_id}"
            )
        except Exception as exc:
            console.print(
                f"\n[red]Error:[/] Failed to create correction bead: {exc}"
            )
            console.print("Close the review bead manually when ready.")
            raise SystemExit(ExitCode.FAILURE)

        # Close the review bead as rejected
        await client.close(bead_id, reason=f"rejected: {guidance[:200]}")
        console.print(f"[red]✗[/] Bead {bead_id} closed as rejected.")
        console.print(
            f"\nThe correction bead ({created.bd_id}) will be picked up "
            f"by the next `maverick fly` run."
        )

    elif decision == "defer":
        console.print(f"\n[yellow]⏸[/] Bead {bead_id} deferred — no action taken.")
        console.print("Run `maverick review` again when ready.")
