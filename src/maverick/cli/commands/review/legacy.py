"""Legacy escalation-bead review flow (approve/reject/defer).

Split out of ``maverick.cli.commands.review`` (T001,
053-assumption-review-console) — behavior-preserving move, no logic changes.
Handles beads labeled ``needs-human-review`` / ``assumption-review`` that
predate the assumption ledger (i.e. lack the ``assumption`` label).

``--json`` support (T007/T011/T012) added on top: contracts/cli-review-json.md
documents legacy approve/reject/defer under the ``review.answer`` verb
("Legacy escalation beads accept --approve / --reject <guidance> / --defer
instead; result then reports the legacy action taken"). JSON mode never
prompts — no flag and no ``is_human`` label both become ``validation``
errors instead of an interactive confirm/prompt.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn

import click

from maverick.cli.console import console
from maverick.cli.context import ExitCode

if TYPE_CHECKING:
    from maverick.beads.client import BeadClient
    from maverick.beads.models import BeadDetails

#: contracts/cli-review-json.md documents legacy approve/reject/defer under
#: the `review.answer` verb section.
_LEGACY_VERB = "review.answer"


def _fail_validation(*, json_mode: bool, message: str) -> NoReturn:
    if json_mode:
        from maverick.cli.json_output import ErrorKind, JsonEnvelope, emit_json

        emit_json(JsonEnvelope.failure(_LEGACY_VERB, ErrorKind.VALIDATION, message))
    else:
        console.print(f"[red]Error:[/] {message}")
    raise SystemExit(ExitCode.FAILURE)


async def handle_legacy_review(
    client: BeadClient,
    bead_id: str,
    details: BeadDetails,
    *,
    approve: bool,
    reject_guidance: str | None,
    defer: bool,
    json_mode: bool = False,
) -> None:
    """Display legacy escalation context and execute an approve/reject/defer decision.

    Rejected beads spawn a correction bead assigned to the next `maverick fly` run.
    """
    from maverick.beads.models import BeadCategory, BeadDefinition, BeadType

    state = details.state or {}
    labels = details.labels or []

    # Verify this is a human-assigned review bead
    is_human = "needs-human-review" in labels or "assumption-review" in labels
    if not is_human:
        if json_mode:
            _fail_validation(
                json_mode=True,
                message=f"Bead {bead_id} is not flagged for human review (labels: {labels})",
            )
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

    if not json_mode:
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
    elif json_mode:
        _fail_validation(
            json_mode=True,
            message="Provide --approve, --reject, or --defer in --json mode "
            "(no interactive prompt available)",
        )
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
                "[bold]Guidance for the correction agent[/] (brief note — what should change?):"
            )
            guidance = click.prompt(">")
        else:
            decision = "defer"
            guidance = ""

    # Execute the decision
    if decision == "approve":
        await client.close(bead_id, reason="approved")
        if json_mode:
            from maverick.cli.json_output import JsonEnvelope, emit_json

            emit_json(JsonEnvelope.success(_LEGACY_VERB, {"action": "approved"}))
            return
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
            created = await client.create_bead(correction_def, parent_id=parent_id)
        except Exception as exc:
            message = f"Failed to create correction bead: {exc}"
            if json_mode:
                from maverick.cli.json_output import ErrorKind, JsonEnvelope, emit_json

                emit_json(JsonEnvelope.failure(_LEGACY_VERB, ErrorKind.INTERNAL, message))
                raise SystemExit(ExitCode.FAILURE) from exc
            console.print(f"\n[red]Error:[/] {message}")
            console.print("Close the review bead manually when ready.")
            raise SystemExit(ExitCode.FAILURE) from exc

        if not json_mode:
            console.print(f"\n[yellow]→[/] Correction bead created: {created.bd_id}")

        # Close the review bead as rejected
        await client.close(bead_id, reason=f"rejected: {guidance[:200]}")

        if json_mode:
            from maverick.cli.json_output import JsonEnvelope, emit_json

            emit_json(
                JsonEnvelope.success(
                    _LEGACY_VERB,
                    {"action": "rejected", "correction_bead_id": created.bd_id},
                )
            )
            return

        console.print(f"[red]✗[/] Bead {bead_id} closed as rejected.")
        console.print(
            f"\nThe correction bead ({created.bd_id}) will be picked up "
            f"by the next `maverick fly` run."
        )

    elif decision == "defer":
        if json_mode:
            from maverick.cli.json_output import JsonEnvelope, emit_json

            emit_json(JsonEnvelope.success(_LEGACY_VERB, {"action": "deferred"}))
            return
        console.print(f"\n[yellow]⏸[/] Bead {bead_id} deferred — no action taken.")
        console.print("Run `maverick review` again when ready.")
