"""``maverick review`` command — lightweight human review of assumption beads.

Two flavors of "human-assigned bead" share this command:

* **Ledger entries** (labeled ``assumption``, from the assumption ledger
  feature) — full-context display (question / adopted answer /
  alternatives / severity / owning spec / change stamps / discovered-from
  source) with an answer/waive resolution flow.
* **Legacy escalation beads** (``needs-human-review`` / ``assumption-review``
  without ``assumption``) — the original approve/reject/defer flow.
  Rejected beads spawn a correction bead back into the agent pipeline.

The human provides judgment and direction, not code.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click
from rich.markup import escape

from maverick.cli.console import console
from maverick.cli.context import ExitCode, async_command
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.beads.client import BeadClient
    from maverick.beads.models import BeadDetails

logger = get_logger(__name__)


@click.command("review")
@click.argument("bead_id", required=False, default=None)
@click.option(
    "--approve",
    is_flag=True,
    default=False,
    help="Approve without interactive prompt (legacy escalation beads).",
)
@click.option(
    "--reject",
    "reject_guidance",
    default=None,
    help="Reject with guidance text (non-interactive, legacy escalation beads).",
)
@click.option(
    "--defer",
    is_flag=True,
    default=False,
    help="Defer without interactive prompt (legacy escalation beads).",
)
@click.option(
    "--answer",
    "answer_text",
    default=None,
    help="Answer a ledger entry (non-interactive).",
)
@click.option(
    "--waive",
    "waive_reason",
    default=None,
    help="Waive a ledger entry with a reason (non-interactive).",
)
@click.option(
    "--spec",
    "owner_spec",
    default=None,
    help="Bulk-waive: owning spec selector (matches `owner_spec` attribution).",
)
@click.option(
    "--severity",
    "severities",
    multiple=True,
    type=click.Choice(["low", "medium", "high"]),
    help="Bulk-waive: severity filter, repeatable (default: low only).",
)
@click.pass_context
@async_command
async def review(
    ctx: click.Context,
    bead_id: str | None,
    approve: bool,
    reject_guidance: str | None,
    defer: bool,
    answer_text: str | None,
    waive_reason: str | None,
    owner_spec: str | None,
    severities: tuple[str, ...],
) -> None:
    """Review a human-assigned bead, or bulk-waive a spec's open entries.

    For assumption-ledger entries: displays full context and captures
    answer or waive. For legacy escalation beads: displays the escalation
    context and captures approve, reject (with guidance for the
    correction agent), or defer. ``--spec`` switches to bulk waive: every
    open entry owned by that spec, filtered by ``--severity`` (default
    low only), is waived with a shared reason.

    Examples:

        maverick review dea-ykp.7

        maverick review dea-ykp.7 --answer "Per bead, matches existing scoping."

        maverick review dea-ykp.7 --waive "No longer applicable"

        maverick review dea-ykp.7 --approve

        maverick review dea-ykp.7 --reject "Use Dockerfile generation instead"

        maverick review dea-ykp.7 --defer

        maverick review --spec 052-conditional-landing --waive "accepted for MVP"
    """
    from maverick.beads.client import BeadClient

    if answer_text is not None and waive_reason is not None:
        console.print("[red]Error:[/] --answer and --waive are mutually exclusive")
        raise SystemExit(ExitCode.FAILURE)

    if bead_id is not None and owner_spec is not None:
        console.print("[red]Error:[/] BEAD_ID and --spec are mutually exclusive")
        raise SystemExit(ExitCode.FAILURE)

    if bead_id is None and owner_spec is None:
        console.print("[red]Error:[/] Provide either BEAD_ID or --spec")
        raise SystemExit(ExitCode.FAILURE)

    if owner_spec is None and severities:
        console.print("[red]Error:[/] --severity only applies to bulk waive (--spec)")
        raise SystemExit(ExitCode.FAILURE)

    if owner_spec is not None:
        # Validate up front, matching the single-entry path — otherwise an
        # empty reason sails past this check and surfaces as N identical
        # per-entry "failed to waive" rows from inside `waive()`.
        if waive_reason is None or not waive_reason.strip():
            console.print("[red]Error:[/] --spec requires --waive <reason>")
            raise SystemExit(ExitCode.FAILURE)
        if answer_text is not None or approve or reject_guidance is not None or defer:
            console.print(
                "[red]Error:[/] --spec only supports --waive "
                "(bulk answering is unsupported — answers are per-question)"
            )
            raise SystemExit(ExitCode.FAILURE)

        client = BeadClient(cwd=Path.cwd())
        if not await client.verify_available():
            console.print("[red]Error:[/] bd is not available")
            raise SystemExit(ExitCode.FAILURE)

        await _bulk_waive_flow(
            client,
            owner_spec=owner_spec,
            severities=severities or ("low",),
            reason=waive_reason,
        )
        return

    assert bead_id is not None  # mutual-exclusion checks above guarantee this
    from maverick.assumptions.models import ASSUMPTION_LABEL
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
        raise SystemExit(ExitCode.FAILURE) from exc

    state = details.state or {}
    labels = details.labels or []

    if ASSUMPTION_LABEL in labels:
        await _review_ledger_entry(
            client, bead_id, details, answer_text=answer_text, waive_reason=waive_reason
        )
        return

    # Verify this is a human-assigned review bead
    is_human = "needs-human-review" in labels or "assumption-review" in labels
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
                "[bold]Guidance for the correction agent[/] (brief note — what should change?):"
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
            created = await client.create_bead(correction_def, parent_id=parent_id)
            console.print(f"\n[yellow]→[/] Correction bead created: {created.bd_id}")
        except Exception as exc:
            console.print(f"\n[red]Error:[/] Failed to create correction bead: {exc}")
            console.print("Close the review bead manually when ready.")
            raise SystemExit(ExitCode.FAILURE) from exc

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


async def _bulk_waive_flow(
    client: BeadClient,
    *,
    owner_spec: str,
    severities: tuple[str, ...],
    reason: str,
) -> None:
    """Waive every open entry owned by *owner_spec* matching *severities*.

    Contract (contracts/cli-review-bulk-waive.md): zero matches prints a
    message and exits zero (idempotent); a partial failure waives what it
    can, lists per-entry failures, and exits non-zero.
    """
    from maverick.assumptions.errors import AssumptionLedgerError
    from maverick.assumptions.ledger import bulk_waive
    from maverick.assumptions.models import Severity

    severity_set = frozenset(Severity(s) for s in severities)
    waived_by = _resolve_git_user_name(Path.cwd())

    try:
        result = await bulk_waive(
            client,
            owner_spec=owner_spec,
            severities=severity_set,
            reason=reason,
            waived_by=waived_by,
        )
    except AssumptionLedgerError as exc:
        # `bulk_waive`'s selection sweep raises (only per-entry failures
        # are collected). Without this the CLI dumps a raw traceback,
        # unlike every other ledger path in this command.
        console.print(f"[red]Error:[/] {exc}")
        raise SystemExit(ExitCode.FAILURE) from exc

    if not result.waived and not result.failed:
        severities_label = "/".join(sorted(s.value for s in severity_set))
        console.print(f"No open {severities_label}-severity assumptions for {owner_spec}.")
        return

    if result.waived:
        console.print(
            f"[green]✓[/] Waived {len(result.waived)} assumption"
            f"{'s' if len(result.waived) != 1 else ''} for {owner_spec}:"
        )
        for record in result.waived:
            # Agent-authored text — `escape` keeps Rich from eating `[...]`.
            console.print(f"  {record.bead_id}  {escape(record.question)}")
        console.print(f"Reason: {reason} (waived by {waived_by})")

    if result.failed:
        console.print()
        console.print(f"[red]✗[/] Failed to waive {len(result.failed)} entries:")
        for bead_id, error in result.failed.items():
            console.print(f"  {bead_id}: {error}")
        raise SystemExit(ExitCode.FAILURE)


def _resolve_git_user_name(cwd: Path) -> str:
    """Resolve the git user name via GitPython config (Guardrail 8)."""
    try:
        from git import Repo

        repo = Repo(cwd, search_parent_directories=True)
        with repo.config_reader() as cfg:
            name = cfg.get_value("user", "name", default="unknown")
            return str(name)
    except Exception:  # noqa: BLE001 — best-effort attribution
        return "unknown"


async def _review_ledger_entry(
    client: BeadClient,
    bead_id: str,
    details: BeadDetails,
    *,
    answer_text: str | None,
    waive_reason: str | None,
) -> None:
    """Full-context display + answer/waive flow for an assumption ledger entry."""
    from maverick.assumptions.errors import AssumptionLedgerError
    from maverick.assumptions.ledger import answer as ledger_answer
    from maverick.assumptions.ledger import parse_description
    from maverick.assumptions.ledger import waive as ledger_waive
    from maverick.assumptions.models import (
        KEY_CHANGE_IDS,
        KEY_OWNER_SPEC,
        KEY_SEVERITY,
        KEY_SEVERITY_DEFAULTED,
        KEY_SOURCE_BEAD,
    )

    state = details.state or {}
    question, adopted_answer, alternatives = parse_description(details.description or "")
    severity = state.get(KEY_SEVERITY, "medium")
    defaulted = state.get(KEY_SEVERITY_DEFAULTED) == "true"
    owner_spec = state.get(KEY_OWNER_SPEC, "")
    source_bead = state.get(KEY_SOURCE_BEAD, "")
    stamps = state.get(KEY_CHANGE_IDS) or "unstamped"

    console.print()
    console.print("[bold]━" * 60)
    console.print(f"[bold] Assumption: {question or details.title}")
    console.print("[bold]━" * 60)
    console.print()
    console.print(f"[dim]Question:[/]        {question}")
    console.print(f"[dim]Adopted answer:[/]   {adopted_answer}")
    if alternatives:
        console.print("[dim]Alternatives:[/]")
        for alt in alternatives:
            console.print(f"  - {alt}")
    severity_display = f"{severity}{' (defaulted)' if defaulted else ''}"
    console.print(f"[dim]Severity:[/]         {severity_display}")
    console.print(f"[dim]Owning spec:[/]      {owner_spec}")
    console.print(f"[dim]Change stamps:[/]    {stamps}")
    console.print(f"[dim]Discovered from:[/]  {source_bead}")
    console.print()
    console.print("[bold]━" * 60)
    console.print()

    if answer_text is None and waive_reason is None:
        console.print("[bold]Decision:[/]")
        console.print()
        console.print("  [green]1.[/] Answer — record the resolution and close")
        console.print("  [yellow]2.[/] Waive — record a reason and close")
        console.print()
        choice = click.prompt("Choice", type=click.Choice(["1", "2"]))
        console.print()
        if choice == "1":
            answer_text = click.prompt("Answer")
        else:
            waive_reason = click.prompt("Waive reason")

    if answer_text is not None:
        if not answer_text.strip():
            console.print("[red]Error:[/] Answer text must not be empty")
            raise SystemExit(ExitCode.FAILURE)
        try:
            await ledger_answer(client, bead_id=bead_id, answer_text=answer_text)
        except AssumptionLedgerError as exc:
            console.print(f"[red]Error:[/] {exc}")
            raise SystemExit(ExitCode.FAILURE) from exc
        console.print(f"\n[green]✓[/] Bead {bead_id} answered and closed.")
    else:
        if not waive_reason or not waive_reason.strip():
            console.print("[red]Error:[/] Waive reason must not be empty")
            raise SystemExit(ExitCode.FAILURE)
        waived_by = _resolve_git_user_name(Path.cwd())
        try:
            await ledger_waive(client, bead_id=bead_id, reason=waive_reason, waived_by=waived_by)
        except AssumptionLedgerError as exc:
            console.print(f"[red]Error:[/] {exc}")
            raise SystemExit(ExitCode.FAILURE) from exc
        console.print(f"\n[yellow]⚠[/] Bead {bead_id} waived by {waived_by} and closed.")
