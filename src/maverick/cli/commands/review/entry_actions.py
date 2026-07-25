"""Ledger-entry answer/waive flow and bulk-waive flow for ``maverick review``.

Split out of ``maverick.cli.commands.review`` (T001,
053-assumption-review-console) — behavior-preserving move, no logic changes.
``--json`` support (T007/T011/T012) added on top: every branch either
prints Rich narration to stdout (human mode, unchanged) or emits exactly
one :class:`~maverick.cli.json_output.JsonEnvelope` document (JSON mode) —
never both.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

import click
from rich.markup import escape

from maverick.assumptions.models import STATUS_WAIVED
from maverick.cli.console import console
from maverick.cli.context import ExitCode

if TYPE_CHECKING:
    from maverick.beads.client import BeadClient
    from maverick.beads.models import BeadDetails


async def _project_after_write(client: BeadClient, bead_id: str) -> dict[str, object] | None:
    """Re-read *bead_id* and project it into the canonical entry row.

    **Must be called outside any ``json_error_handler`` scope.** This read
    happens *after* the ledger write has already succeeded; letting a
    transient bd failure here surface as ``ok: false`` would report a
    recorded decision as an unrecorded one — the skill would then tell the
    human their answer wasn't saved while the ledger says otherwise.
    Failing soft (``None``, surfaced as ``degraded: true`` on the success
    envelope) keeps the envelope honest about what actually happened.
    """
    from maverick.assumptions.ledger import report_entry_from_details
    from maverick.assumptions.serialize import entry_to_dict

    try:
        details = await client.show(bead_id)
    except Exception:  # noqa: BLE001 — the write already succeeded; never fail on the read
        return None
    entry = report_entry_from_details(details)
    return entry_to_dict(entry) if entry is not None else None


async def _bulk_waive_flow(
    client: BeadClient,
    *,
    owner_spec: str,
    severities: tuple[str, ...],
    reason: str,
    json_mode: bool = False,
) -> None:
    """Waive every open entry owned by *owner_spec* matching *severities*.

    Contract (contracts/cli-review-json.md "review.bulk-waive"): zero
    matches is success (idempotent, ``ok: true`` with an empty ``waived``
    list); a partial failure waives what it can and reports per-entry
    failures — ``ok: true`` still (the verb ran), but the CLI exits
    non-zero since outcomes say what failed.

    Human mode (``json_mode=False``) is unchanged from the pre-053
    behavior: zero matches prints a message and exits zero; a partial
    failure waives what it can, lists per-entry failures, and exits
    non-zero.
    """
    from maverick.assumptions.errors import AssumptionLedgerError
    from maverick.assumptions.ledger import bulk_waive
    from maverick.assumptions.models import Severity
    from maverick.cli.commands.review import _resolve_git_user_name
    from maverick.cli.json_output import JsonEnvelope, emit_json, json_error_handler

    severity_set = frozenset(Severity(s) for s in severities)
    waived_by = _resolve_git_user_name(Path.cwd())

    if json_mode:
        with json_error_handler("review.bulk-waive"):
            result = await bulk_waive(
                client,
                owner_spec=owner_spec,
                severities=severity_set,
                reason=reason,
                waived_by=waived_by,
            )

        # Post-write projection, deliberately OUTSIDE the handler above:
        # every waive in `result` already succeeded, so a read failure on
        # one row must not discard the record of *all* of them. Each row is
        # re-read independently and fails soft into `unprojected`.
        # (A single repo-wide `report_entries()` sweep would look cheaper
        # but isn't — it queries every task bead and shows each one, which
        # is strictly more work than showing just the entries waived here.)
        waived_rows: list[dict[str, object]] = []
        unprojected: list[str] = []
        for record in result.waived:
            row = await _project_after_write(client, record.bead_id)
            if row is None:
                unprojected.append(record.bead_id)
            else:
                waived_rows.append(row)

        payload: dict[str, object] = {
            "owner_spec": owner_spec,
            "severities": sorted(s.value for s in severity_set),
            "waived": waived_rows,
            "failed": dict(result.failed),
        }
        if unprojected:
            # These entries WERE waived — only their post-write rows
            # couldn't be re-read. Reported separately so a consumer never
            # mistakes a projection gap for a failed waive.
            payload["unprojected"] = unprojected
        emit_json(JsonEnvelope.success("review.bulk-waive", payload))
        if result.failed:
            raise SystemExit(ExitCode.FAILURE)
        return

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


def _emit_or_print_validation(*, json_mode: bool, verb: str, message: str) -> NoReturn:
    """Shared validation-failure exit for the ledger-entry flow.

    JSON mode emits a ``validation`` envelope; human mode keeps the
    existing ``console.print`` + ``SystemExit`` style. Always raises.
    """
    if json_mode:
        from maverick.cli.json_output import ErrorKind, JsonEnvelope, emit_json

        emit_json(JsonEnvelope.failure(verb, ErrorKind.VALIDATION, message))
    else:
        console.print(f"[red]Error:[/] {message}")
    raise SystemExit(ExitCode.FAILURE)


async def _review_ledger_entry(
    client: BeadClient,
    bead_id: str,
    details: BeadDetails,
    *,
    answer_text: str | None,
    waive_reason: str | None,
    json_mode: bool = False,
) -> None:
    """Full-context display + answer/waive flow for an assumption ledger entry.

    JSON mode (research R6, contracts/cli-review-json.md): no prompts, no
    Rich narration on stdout — exactly one envelope document. A pre-check
    (research R6) reads the entry's *current* status from *details*
    (already fetched by the caller moments earlier) before any write: a
    ``waived`` target is ``already-resolved`` in both modes — re-answering
    an ``answered`` entry stays legal (051 FR-017).
    """
    from maverick.assumptions.errors import AssumptionLedgerError
    from maverick.assumptions.ledger import answer as ledger_answer
    from maverick.assumptions.ledger import (
        parse_description,
        report_entry_from_details,
    )
    from maverick.assumptions.ledger import waive as ledger_waive
    from maverick.assumptions.models import (
        KEY_CHANGE_IDS,
        KEY_OWNER_SPEC,
        KEY_SEVERITY,
        KEY_SEVERITY_DEFAULTED,
        KEY_SOURCE_BEAD,
    )
    from maverick.assumptions.serialize import entry_to_dict
    from maverick.cli.commands.review import _resolve_git_user_name
    from maverick.cli.json_output import ErrorKind, JsonEnvelope, emit_json, json_error_handler

    is_waive_only = waive_reason is not None and answer_text is None
    verb = "review.waive" if is_waive_only else "review.answer"

    if json_mode and answer_text is None and waive_reason is None:
        _emit_or_print_validation(
            json_mode=True,
            verb=verb,
            message="Provide --answer or --waive in --json mode (no interactive prompt available)",
        )

    # Already-resolved pre-check (research R6) — applies in both modes.
    # `details` carries the ASSUMPTION_LABEL (the caller only dispatches
    # here for ledger entries), so this never returns None.
    current_entry = report_entry_from_details(details)
    assert current_entry is not None  # ledger entries always project
    if current_entry.record.status == STATUS_WAIVED:
        message = f"Bead {bead_id} is already waived — no further action possible"
        if json_mode:
            emit_json(
                JsonEnvelope.failure(
                    verb,
                    ErrorKind.ALREADY_RESOLVED,
                    message,
                    details={"entry": entry_to_dict(current_entry)},
                )
            )
        else:
            console.print(f"[red]Error:[/] {message}")
        raise SystemExit(ExitCode.FAILURE)

    if not json_mode:
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
            _emit_or_print_validation(
                json_mode=json_mode,
                verb="review.answer",
                message="Answer text must not be empty",
            )

        if json_mode:
            with json_error_handler("review.answer"):
                await ledger_answer(client, bead_id=bead_id, answer_text=answer_text)
            # Projection re-read is outside the handler on purpose — see
            # `_project_after_write`. The write is already committed here.
            row = await _project_after_write(client, bead_id)
            payload: dict[str, object] = {"entry": row, "action": "answered"}
            if row is None:
                payload["degraded"] = True
            emit_json(JsonEnvelope.success("review.answer", payload))
            return

        try:
            await ledger_answer(client, bead_id=bead_id, answer_text=answer_text)
        except AssumptionLedgerError as exc:
            console.print(f"[red]Error:[/] {exc}")
            raise SystemExit(ExitCode.FAILURE) from exc
        console.print(f"\n[green]✓[/] Bead {bead_id} answered and closed.")
    else:
        if not waive_reason or not waive_reason.strip():
            _emit_or_print_validation(
                json_mode=json_mode,
                verb="review.waive",
                message="Waive reason must not be empty",
            )

        waived_by = _resolve_git_user_name(Path.cwd())

        if json_mode:
            with json_error_handler("review.waive"):
                await ledger_waive(
                    client, bead_id=bead_id, reason=waive_reason, waived_by=waived_by
                )
            # Outside the handler — same rationale as the answer path above.
            row = await _project_after_write(client, bead_id)
            payload = {"entry": row, "action": "waived"}
            if row is None:
                payload["degraded"] = True
            emit_json(JsonEnvelope.success("review.waive", payload))
            return

        try:
            await ledger_waive(client, bead_id=bead_id, reason=waive_reason, waived_by=waived_by)
        except AssumptionLedgerError as exc:
            console.print(f"[red]Error:[/] {exc}")
            raise SystemExit(ExitCode.FAILURE) from exc
        console.print(f"\n[yellow]⚠[/] Bead {bead_id} waived by {waived_by} and closed.")
