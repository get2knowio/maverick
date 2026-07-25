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

This package splits the command's implementation across:

* ``entry_actions.py`` — ledger-entry answer/waive flow and bulk-waive flow.
* ``legacy.py`` — the legacy escalation-bead approve/reject/defer flow.
* ``listing.py`` — ``--list`` mode (053-assumption-review-console).

``--json`` (053-assumption-review-console) makes every path emit exactly
one :class:`~maverick.cli.json_output.JsonEnvelope` document on stdout
instead of Rich narration — see
``specs/053-assumption-review-console/contracts/cli-review-json.md``.
Human-mode behavior (no ``--json``) is unchanged (FR-018).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

import click

from maverick.cli.console import console
from maverick.cli.context import ExitCode, async_command
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.cli.json_output import ErrorKind

logger = get_logger(__name__)


def _fail(
    *,
    json_mode: bool,
    verb: str,
    message: str,
    kind: ErrorKind | None = None,
) -> NoReturn:
    """Shared top-level failure exit: JSON envelope or console print.

    *kind* defaults to ``validation`` — right for the flag-combination
    guards that dominate this command — but must be passed explicitly for
    anything else (notably the ``verify_available()`` precondition, which
    is ``bd-unavailable``; ``json_error_handler`` can't classify a check
    that never raises, so that translation is the caller's job — see
    ``maverick.cli.json_output``'s module docstring).

    Always raises ``SystemExit(ExitCode.FAILURE)``.
    """
    if json_mode:
        from maverick.cli.json_output import ErrorKind as _ErrorKind
        from maverick.cli.json_output import JsonEnvelope, emit_json

        emit_json(JsonEnvelope.failure(verb, kind or _ErrorKind.VALIDATION, message))
    else:
        console.print(f"[red]Error:[/] {message}")
    raise SystemExit(ExitCode.FAILURE)


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
    "--list",
    "list_mode",
    is_flag=True,
    default=False,
    help="List assumption-ledger entries instead of reviewing one.",
)
@click.option(
    "--status",
    "statuses",
    multiple=True,
    type=click.Choice(["open", "answered", "waived"]),
    help="--list filter: entry status, repeatable (default: open only).",
)
@click.option(
    "--spec",
    "owner_specs",
    multiple=True,
    help=(
        "Bulk-waive: owning spec selector (matches `owner_spec` attribution). "
        "Also usable with --list to filter by owner spec; repeatable."
    ),
)
@click.option(
    "--severity",
    "severities",
    multiple=True,
    type=click.Choice(["low", "medium", "high"]),
    help=(
        "Bulk-waive: severity filter, repeatable (default: low only). "
        "Also usable with --list to filter by severity."
    ),
)
@click.option(
    "--json",
    "json_mode",
    is_flag=True,
    default=False,
    help="Emit a machine-readable JSON envelope instead of Rich output.",
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
    list_mode: bool,
    statuses: tuple[str, ...],
    owner_specs: tuple[str, ...],
    severities: tuple[str, ...],
    json_mode: bool,
) -> None:
    """Review a human-assigned bead, list ledger entries, or bulk-waive a spec.

    For assumption-ledger entries: displays full context and captures
    answer or waive. For legacy escalation beads: displays the escalation
    context and captures approve, reject (with guidance for the
    correction agent), or defer. ``--list`` lists ledger entries instead
    of reviewing one. ``--spec`` (without ``--list``) switches to bulk
    waive: every open entry owned by that spec, filtered by ``--severity``
    (default low only), is waived with a shared reason. ``--json`` emits
    a machine-readable envelope instead of Rich output on every path.

    Examples:

        maverick review dea-ykp.7

        maverick review dea-ykp.7 --answer "Per bead, matches existing scoping."

        maverick review dea-ykp.7 --waive "No longer applicable"

        maverick review dea-ykp.7 --approve

        maverick review dea-ykp.7 --reject "Use Dockerfile generation instead"

        maverick review dea-ykp.7 --defer

        maverick review --spec 052-conditional-landing --waive "accepted for MVP"

        maverick review --list --status open --json
    """
    from maverick.beads.client import BeadClient
    from maverick.cli.commands.review.entry_actions import (
        _bulk_waive_flow,
        _review_ledger_entry,
    )
    from maverick.cli.commands.review.legacy import handle_legacy_review
    from maverick.cli.commands.review.listing import run_list

    if list_mode:
        if bead_id is not None:
            _fail(
                json_mode=json_mode,
                verb="review.list",
                message="--list and BEAD_ID are mutually exclusive",
            )
        decision_flags_given = (
            answer_text is not None
            or waive_reason is not None
            or approve
            or reject_guidance is not None
            or defer
        )
        if decision_flags_given:
            _fail(
                json_mode=json_mode,
                verb="review.list",
                message=(
                    "--list is mutually exclusive with --answer/--waive/--approve/--reject/--defer"
                ),
            )

        await run_list(
            statuses=frozenset(statuses),
            owner_specs=frozenset(owner_specs),
            severities=frozenset(severities),
            json_mode=json_mode,
        )
        return

    if answer_text is not None and waive_reason is not None:
        _fail(
            json_mode=json_mode,
            verb="review.answer",
            message="--answer and --waive are mutually exclusive",
        )

    if bead_id is not None and owner_specs:
        _fail(
            json_mode=json_mode,
            verb="review.bulk-waive",
            message="BEAD_ID and --spec are mutually exclusive",
        )

    if bead_id is None and not owner_specs:
        _fail(
            json_mode=json_mode,
            verb="review.answer",
            message="Provide either BEAD_ID or --spec",
        )

    if not owner_specs and severities:
        _fail(
            json_mode=json_mode,
            verb="review.bulk-waive",
            message="--severity only applies to bulk waive (--spec)",
        )

    if owner_specs:
        if len(owner_specs) > 1:
            _fail(
                json_mode=json_mode,
                verb="review.bulk-waive",
                message="--spec accepts only one value for bulk waive",
            )
        owner_spec = owner_specs[0]
        # Validate up front, matching the single-entry path — otherwise an
        # empty reason sails past this check and surfaces as N identical
        # per-entry "failed to waive" rows from inside `waive()`.
        if waive_reason is None or not waive_reason.strip():
            _fail(
                json_mode=json_mode,
                verb="review.bulk-waive",
                message="--spec requires --waive <reason>",
            )
        if answer_text is not None or approve or reject_guidance is not None or defer:
            _fail(
                json_mode=json_mode,
                verb="review.bulk-waive",
                message="--spec only supports --waive "
                "(bulk answering is unsupported — answers are per-question)",
            )

        client = BeadClient(cwd=Path.cwd())
        if not await client.verify_available():
            from maverick.cli.json_output import ErrorKind

            _fail(
                json_mode=json_mode,
                verb="review.bulk-waive",
                message="bd is not available",
                kind=ErrorKind.BD_UNAVAILABLE,
            )

        await _bulk_waive_flow(
            client,
            owner_spec=owner_spec,
            severities=severities or ("low",),
            reason=waive_reason,
            json_mode=json_mode,
        )
        return

    assert bead_id is not None  # mutual-exclusion checks above guarantee this
    from maverick.assumptions.models import ASSUMPTION_LABEL
    from maverick.cli.json_output import ErrorKind
    from maverick.exceptions.beads import BeadQueryError

    client = BeadClient(cwd=Path.cwd())

    default_verb = "review.waive" if waive_reason is not None else "review.answer"

    if not await client.verify_available():
        _fail(
            json_mode=json_mode,
            verb=default_verb,
            message="bd is not available",
            kind=ErrorKind.BD_UNAVAILABLE,
        )

    # Fetch bead details
    try:
        details = await client.show(bead_id)
    except BeadQueryError as exc:
        # A `show()` failure on an already-verified-available bd means an
        # unknown/bad bead id, not "bd unavailable" — handle it directly
        # rather than letting it fall through to `json_error_handler`'s
        # generic BeadError->bd-unavailable mapping.
        message = f"Could not fetch bead {bead_id}: {exc}"
        if json_mode:
            from maverick.cli.json_output import JsonEnvelope, emit_json

            emit_json(
                JsonEnvelope.failure(
                    default_verb, ErrorKind.NOT_FOUND, message, details={"bead_id": bead_id}
                )
            )
        else:
            console.print(f"[red]Error:[/] {message}")
        raise SystemExit(ExitCode.FAILURE) from exc
    except Exception as exc:
        message = f"Could not fetch bead {bead_id}: {exc}"
        if json_mode:
            from maverick.cli.json_output import JsonEnvelope, emit_json

            emit_json(JsonEnvelope.failure(default_verb, ErrorKind.INTERNAL, message))
        else:
            console.print(f"[red]Error:[/] {message}")
        raise SystemExit(ExitCode.FAILURE) from exc

    labels = details.labels or []

    if ASSUMPTION_LABEL in labels:
        await _review_ledger_entry(
            client,
            bead_id,
            details,
            answer_text=answer_text,
            waive_reason=waive_reason,
            json_mode=json_mode,
        )
        return

    await handle_legacy_review(
        client,
        bead_id,
        details,
        approve=approve,
        reject_guidance=reject_guidance,
        defer=defer,
        json_mode=json_mode,
    )


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


__all__ = ["review"]
