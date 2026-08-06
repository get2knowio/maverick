"""``maverick notify`` — evaluate and deliver due assumption-ledger notifications.

See ``specs/054-assumption-batch-scheduler/contracts/cli-notify-json.md`` for
the full contract (verbs, envelope shape, error mapping, exit codes) and
``specs/054-assumption-batch-scheduler/quickstart.md`` for the acceptance
scenarios this command implements (Scenarios 1-3, the MVP checkpoint).

This module is the effects layer sitting downstream of three pure/typed
building blocks that already exist and are never mutated by this file:

* :func:`maverick.assumptions.schedule.evaluate.evaluate` — pure decision
  engine (no disk/network reads); this module is the only caller responsible
  for turning its decisions into ntfy pushes and persisted state.
* :class:`maverick.assumptions.schedule.deliver.NtfyDeliverer` — the sole
  ntfy wrapper (Guardrail 5).
* :mod:`maverick.assumptions.schedule.state` — persisted delivery state
  (``<cwd>/.maverick/notify/state.json``) plus the pid-stamped lockfile.
* :func:`maverick.assumptions.schedule.clock.now_local` — the injected clock
  seam (research R6). This module is where "now" enters the evaluation, bound
  to the machine's real IANA zone so window/quiet-hours wall-clock arithmetic
  stays correct across DST transitions.

Write-after-success (FR-012): :func:`evaluate` returns a candidate
``state_after`` that *assumes* every delivery decision succeeds (see that
module's docstring).
:func:`~maverick.assumptions.schedule.state.finalize_state` strips the
mutations belonging to any decision whose ntfy push actually failed before
the state is persisted, so a failed batch stays due for the next
evaluation — a partial-success run (some due decisions deliver, others
fail) persists exactly the successes, individually.

Concurrency (research R7): unlike ``reconcile``, a held lock is a *benign*
skip for this command — cron overlap is expected operation, not a fault —
so contention exits ``SUCCESS`` with ``result.skipped: "concurrent-evaluation"``
rather than the ``locked`` error kind.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

import click

from maverick.assumptions.errors import AssumptionLedgerError
from maverick.assumptions.ledger import report_entries
from maverick.assumptions.ledger import waive as ledger_waive
from maverick.assumptions.models import Severity
from maverick.assumptions.schedule.clock import now_local
from maverick.assumptions.schedule.deliver import DeliveryFailedError, NtfyDeliverer
from maverick.assumptions.schedule.evaluate import evaluate
from maverick.assumptions.schedule.models import (
    AutoWaiveDecision,
    BatchSummary,
    DecisionKind,
    DeliveryDecision,
    SkipDecision,
    WindowOccurrence,
    format_age_hours,
    format_utc,
)
from maverick.assumptions.schedule.state import (
    DeliveryState,
    TerminalOutcome,
    acquire_lock,
    finalize_state,
    load_state,
    release_lock,
    save_state,
)
from maverick.beads.client import BeadClient
from maverick.cli.common import BD_MISSING, BD_NOT_INITIALIZED, bd_ready_reason, cli_error_handler
from maverick.cli.console import console, err_console
from maverick.cli.context import ExitCode, async_command
from maverick.cli.json_output import ErrorKind, JsonEnvelope, emit_json, json_error_handler
from maverick.config import (
    AssumptionScheduleConfig,
    MaverickConfig,
    NotificationConfig,
    load_config,
)
from maverick.exceptions import BeadError
from maverick.logging import get_logger

__all__ = ["notify"]

logger = get_logger(__name__)

#: ``waived_by`` value stamped on every scheduler-initiated auto-waive
#: (research R10) — distinguishes it from a human waiver in ledger
#: reporting (FR-015).
_AUTO_WAIVE_ACTOR: Final = "maverick-scheduler"

#: Machine reason (``maverick.cli.common.bd_ready_reason``) -> the message
#: the ``bd-unavailable`` envelope/console line carries. Mirrors
#: ``maverick.cli.commands.reconcile._BD_REASON_MESSAGES``.
_BD_REASON_MESSAGES = {
    BD_MISSING: "The bd CLI is required but not found on PATH.",
    BD_NOT_INITIALIZED: (
        "this project hasn't been initialized for Maverick yet — run `maverick init`."
    ),
}

#: Human-mode label per :class:`DecisionKind` (contract's completion-line example).
_KIND_HUMAN: dict[DecisionKind, str] = {
    DecisionKind.WINDOW_BATCH: "window batch",
    DecisionKind.INTERRUPT: "interrupt",
    DecisionKind.ESCALATION: "escalation",
    DecisionKind.RENOTIFY: "renotification",
}


@dataclass(slots=True)
class _DeliveryOutcome:
    """One ntfy delivery attempt that failed, with its position in
    ``EvaluationOutcome.deliveries`` (used to locate the matching
    ``state_after`` mutations to strip — see
    :func:`~maverick.assumptions.schedule.state.finalize_state`)."""

    decision: DeliveryDecision
    index: int
    error: str


@dataclass(slots=True)
class _NotifyRun:
    """The outcome of one evaluate-deliver-save pass, or a benign lock skip."""

    configured: bool
    skipped: str | None
    evaluated_at: datetime | None
    delivered: list[DeliveryDecision]
    failed: list[_DeliveryOutcome]
    skips: list[SkipDecision]
    auto_waives: list[AutoWaiveDecision]
    dry_run: bool


def _notifications_usability_error(notif: NotificationConfig) -> str | None:
    """FR-009: an ``assumptions.schedule`` block requires a usable ntfy endpoint.

    ``NotificationConfig``'s own validator only *warns* when enabled-but-
    topicless (it doesn't know a schedule block is asking it to actually
    deliver something) — this is the enforcement point. Returns a message
    naming the exact missing/misconfigured key, or ``None`` when usable.
    """
    if not notif.enabled:
        return (
            "assumptions.schedule is configured but notifications.enabled is "
            "false in maverick.yaml — set `notifications.enabled: true` to use "
            "`maverick notify`."
        )
    if not notif.topic:
        return (
            "assumptions.schedule is configured but notifications.topic is not "
            "set in maverick.yaml — set `notifications.topic` to use `maverick "
            "notify`."
        )
    return None


async def _bd_preflight_error(cwd: Path, client: BeadClient) -> str | None:
    """Return a bd-unavailable message, or ``None`` when bd is ready.

    Combines the two existing bd-readiness checks — :func:`bd_ready_reason`
    (bd on PATH + ``.beads/`` initialized) and
    :meth:`BeadClient.verify_available` (``bd --version`` actually
    succeeds) — so either failure mode maps to the same ``bd-unavailable``
    error kind (contracts/cli-notify-json.md).
    """
    reason = bd_ready_reason(cwd)
    if reason is not None:
        return _BD_REASON_MESSAGES.get(reason, f"bd is not ready ({reason}).")
    if not await client.verify_available():
        return "The `bd` CLI is on PATH but is not responding (`bd --version` failed)."
    return None


async def _evaluate_and_effect(
    *,
    cwd: Path,
    client: BeadClient,
    schedule: AssumptionScheduleConfig,
    notif: NotificationConfig,
    dry_run: bool,
) -> _NotifyRun:
    """Evaluate the schedule against the ledger and apply effects.

    ``--dry-run`` never acquires the lock, never delivers, and never
    persists state (contract: "zero ntfy calls, zero bd writes, zero state
    writes"). A real run acquires the lockfile around the whole
    evaluate-deliver-save sequence (research R7); contention is a benign
    skip, not a failure.

    Raises:
        AssumptionLedgerError: The ledger sweep (``report_entries``) failed.
    """
    if not dry_run:
        acquired = await acquire_lock(cwd)
        if not acquired:
            return _NotifyRun(
                configured=True,
                skipped="concurrent-evaluation",
                evaluated_at=None,
                delivered=[],
                failed=[],
                skips=[],
                auto_waives=[],
                dry_run=dry_run,
            )

    try:
        entries = await report_entries(client)
        state = await load_state(cwd)
        now = now_local()
        outcome = evaluate(entries, schedule, state, now)

        delivered: list[DeliveryDecision] = []
        failed: list[_DeliveryOutcome] = []

        if dry_run:
            delivered = list(outcome.deliveries)
        elif outcome.deliveries:
            topic = notif.topic
            if topic is None:
                # Unreachable in practice: callers validate notifications
                # usability (`_notifications_usability_error`) before ever
                # reaching this point. Guards mypy's narrowing and fails
                # loudly instead of silently, if that invariant ever slips.
                raise AssertionError(
                    "notify: notifications.topic must be validated before delivery"
                )
            async with NtfyDeliverer(server=notif.server, topic=topic) as deliverer:
                for index, decision in enumerate(outcome.deliveries):
                    try:
                        await deliverer.deliver(decision.kind, decision.summary)
                        delivered.append(decision)
                    except DeliveryFailedError as exc:
                        failed.append(
                            _DeliveryOutcome(decision=decision, index=index, error=str(exc))
                        )

        auto_waived: list[AutoWaiveDecision] = []
        if dry_run:
            auto_waived = list(outcome.auto_waives)
        elif outcome.auto_waives:
            auto_waived = await _execute_auto_waives(client=client, decisions=outcome.auto_waives)

        if not dry_run:
            final_state = finalize_state(
                outcome=outcome,
                prior_state=state,
                failed_indices={f.index for f in failed},
                now=now,
            )
            final_state = _apply_auto_waive_terminal(final_state, auto_waived, now)
            await save_state(final_state, cwd)

        return _NotifyRun(
            configured=True,
            skipped=None,
            evaluated_at=now,
            delivered=delivered,
            failed=failed,
            skips=list(outcome.skips),
            auto_waives=auto_waived,
            dry_run=dry_run,
        )
    finally:
        if not dry_run:
            await release_lock(cwd)


async def _execute_auto_waives(
    *, client: BeadClient, decisions: Sequence[AutoWaiveDecision]
) -> list[AutoWaiveDecision]:
    """Execute auto-waive decisions via the ledger (research R10, FR-015).

    Never called in ``--dry-run`` mode (the contract's "zero bd calls").
    Each waive is attempted independently — Principle III ("one agent
    failing must not crash the workflow") applies equally to this
    effects loop: a bd failure waiving one entry must not prevent the
    rest of the run's due decisions (deliveries, other auto-waives) from
    completing, and must not fabricate a persisted terminal outcome for
    an entry that was never actually waived.

    Args:
        client: The bead client to waive through.
        decisions: Auto-waive candidates from
            :func:`~maverick.assumptions.schedule.evaluate.evaluate`.

    Returns:
        Only the decisions whose ``ledger.waive`` call actually
        succeeded, in the same order — the caller stamps a
        :class:`~maverick.assumptions.schedule.state.TerminalOutcome`
        for exactly these.
    """
    succeeded: list[AutoWaiveDecision] = []
    for decision in decisions:
        try:
            await ledger_waive(
                client,
                bead_id=decision.entry_id,
                reason=decision.reason_text,
                waived_by=_AUTO_WAIVE_ACTOR,
            )
        except AssumptionLedgerError as exc:
            logger.warning("notify_auto_waive_failed", bead_id=decision.entry_id, error=str(exc))
            continue
        succeeded.append(decision)
    return succeeded


def _apply_auto_waive_terminal(
    state: DeliveryState, waived: Sequence[AutoWaiveDecision], now: datetime
) -> DeliveryState:
    """Stamp a :class:`TerminalOutcome` for each successfully auto-waived entry.

    FR-016 ("nothing leaves tracking without a persisted outcome") applies
    to the auto-waive path exactly as it does to human resolution — this
    is where the scheduler records who/what/why for FR-023's 90-day
    retention clock (``TerminalOutcome.at``) and audit (``detail`` carries
    the full rationale).

    Args:
        state: The state ``finalize_state`` already produced for this
            run's delivery decisions.
        waived: The auto-waive decisions that actually succeeded
            (:func:`_execute_auto_waives`'s return value).
        now: The same evaluation clock passed to ``evaluate()``.

    Returns:
        *state* unchanged if *waived* is empty, otherwise a new
        :class:`DeliveryState` with each waived entry's tracking row
        carrying its terminal outcome.
    """
    if not waived:
        return state
    at = format_utc(now)
    tracking = dict(state.entry_tracking)
    for decision in waived:
        record = tracking.get(decision.entry_id)
        if record is None:
            continue
        tracking[decision.entry_id] = record.model_copy(
            update={
                "terminal": TerminalOutcome(kind="auto-waived", at=at, detail=decision.reason_text)
            }
        )
    return state.model_copy(update={"entry_tracking": tracking})


# --- JSON projection -------------------------------------------------------


def _delivery_trigger(decision: DeliveryDecision) -> str:
    if decision.occurrence is not None:
        return decision.occurrence.key
    return decision.rule


def _delivery_to_dict(decision: DeliveryDecision) -> dict[str, Any]:
    return {
        "kind": decision.kind.value,
        "trigger": _delivery_trigger(decision),
        "entry_ids": list(decision.entry_ids),
        "summary": decision.summary.to_dict(),
        "rule": decision.rule,
    }


def _occurrence_to_dict(occurrence: WindowOccurrence | None) -> dict[str, Any] | None:
    if occurrence is None:
        return None
    return {
        "date": occurrence.date.isoformat(),
        "window": occurrence.window,
        "due_at": occurrence.due_at.isoformat(),
    }


def _skip_to_dict(skip: SkipDecision) -> dict[str, Any]:
    return {
        "reason": skip.reason.value,
        "entry_ids": list(skip.entry_ids),
        "occurrence": _occurrence_to_dict(skip.occurrence),
        "rule": skip.rule,
    }


def _auto_waive_to_dict(decision: AutoWaiveDecision) -> dict[str, Any]:
    return {"entry_id": decision.entry_id, "reason": decision.reason_text}


def _failed_delivery_to_dict(outcome: _DeliveryOutcome) -> dict[str, Any]:
    payload = _delivery_to_dict(outcome.decision)
    payload["error"] = outcome.error
    return payload


def _no_op_result(*, dry_run: bool) -> dict[str, Any]:
    """FR-021: the inert, no-``assumptions.schedule`` result shape."""
    return {
        "configured": False,
        "skipped": "not-configured",
        "evaluated_at": None,
        "deliveries": [],
        "skips": [],
        "auto_waives": [],
        "dry_run": dry_run,
    }


def _run_to_dict(run: _NotifyRun) -> dict[str, Any]:
    return {
        "configured": run.configured,
        "skipped": run.skipped,
        "evaluated_at": (
            run.evaluated_at.isoformat(timespec="seconds")
            if run.evaluated_at is not None
            else None
        ),
        "deliveries": [_delivery_to_dict(d) for d in run.delivered],
        "skips": [_skip_to_dict(s) for s in run.skips],
        "auto_waives": [_auto_waive_to_dict(w) for w in run.auto_waives],
        "dry_run": run.dry_run,
    }


async def _run_notify_json(*, dry_run: bool, cwd: Path, config: MaverickConfig) -> None:
    """Drive notify end-to-end in ``--json`` mode: one envelope on stdout."""
    verb = "notify.dry-run" if dry_run else "notify.run"

    schedule = config.assumptions.schedule
    if schedule is None:
        emit_json(JsonEnvelope.success(verb, _no_op_result(dry_run=dry_run)))
        raise SystemExit(ExitCode.SUCCESS)

    notif = config.notifications
    usability_error = _notifications_usability_error(notif)
    if usability_error is not None:
        emit_json(JsonEnvelope.failure(verb, ErrorKind.VALIDATION, usability_error))
        raise SystemExit(ExitCode.FAILURE)

    run: _NotifyRun | None = None
    with json_error_handler(verb):
        client = BeadClient(cwd=cwd)
        bd_error = await _bd_preflight_error(cwd, client)
        if bd_error is not None:
            raise BeadError(bd_error)

        run = await _evaluate_and_effect(
            cwd=cwd, client=client, schedule=schedule, notif=notif, dry_run=dry_run
        )

    assert run is not None  # json_error_handler() already exited on any exception above

    if run.failed:
        details: dict[str, object] = {
            "failed_deliveries": [_failed_delivery_to_dict(f) for f in run.failed]
        }
        message = f"{len(run.failed)} delivery(ies) failed; the affected batch(es) remain due."
        emit_json(JsonEnvelope.failure(verb, ErrorKind.DELIVERY_FAILED, message, details))
        raise SystemExit(ExitCode.FAILURE)

    emit_json(JsonEnvelope.success(verb, _run_to_dict(run)))
    raise SystemExit(ExitCode.SUCCESS)


# --- Human-mode rendering ---------------------------------------------------


def _counts_phrase(summary: BatchSummary) -> str:
    high = summary.counts.get(Severity.HIGH, 0)
    medium = summary.counts.get(Severity.MEDIUM, 0)
    low = summary.counts.get(Severity.LOW, 0)
    parts = [f"{high} high"] if high else []
    parts.append(f"{medium} medium")
    parts.append(f"{low} low")
    return f"{', '.join(parts)}; oldest {format_age_hours(summary.oldest_age_hours)}h"


def _occurrence_phrase(decision: DeliveryDecision) -> str:
    if decision.occurrence is not None:
        return f"{decision.occurrence.window} window"
    return decision.rule


def _render_human_result(run: _NotifyRun, *, dry_run: bool) -> None:
    """Render one evaluation's outcome per the contract's "Human-mode output"
    section, then exit with the matching code."""
    if run.skipped == "concurrent-evaluation":
        console.print("Another `maverick notify` evaluation is already in progress — skipped.")
        raise SystemExit(ExitCode.SUCCESS)

    verb_word = "Would deliver" if dry_run else "Delivered"
    for decision in run.delivered:
        console.print(
            f"[green]✓[/] {verb_word} {_KIND_HUMAN[decision.kind]} "
            f"({_counts_phrase(decision.summary)}) for {_occurrence_phrase(decision)}"
        )

    waive_verb = "Would auto-waive" if dry_run else "Auto-waived"
    for waived in run.auto_waives:
        console.print(f"[green]✓[/] {waive_verb} {waived.entry_id} ({waived.reason_text})")

    if run.failed:
        for failure in run.failed:
            console.print(f"[red]✗[/] Delivery failed: {failure.error}")
        console.print(
            "[yellow]Warning:[/yellow] the batch remains due — it will be "
            "retried on the next evaluation."
        )
        raise SystemExit(ExitCode.FAILURE)

    if not run.delivered and not run.auto_waives:
        console.print("Nothing due.")

    raise SystemExit(ExitCode.SUCCESS)


async def _run_notify_human(*, dry_run: bool, cwd: Path, config: MaverickConfig) -> None:
    """Drive notify end-to-end in human (Rich console) mode."""
    schedule = config.assumptions.schedule
    if schedule is None:
        console.print(
            "Assumption delivery is not configured (no assumptions.schedule "
            "block in maverick.yaml)."
        )
        raise SystemExit(ExitCode.SUCCESS)

    notif = config.notifications
    usability_error = _notifications_usability_error(notif)
    if usability_error is not None:
        err_console.print(f"[red]Error:[/red] {usability_error}")
        raise SystemExit(ExitCode.FAILURE)

    run: _NotifyRun | None = None
    with cli_error_handler():
        client = BeadClient(cwd=cwd)
        bd_error = await _bd_preflight_error(cwd, client)
        if bd_error is not None:
            err_console.print(f"[red]Error:[/red] {bd_error}")
            raise SystemExit(ExitCode.FAILURE)

        run = await _evaluate_and_effect(
            cwd=cwd, client=client, schedule=schedule, notif=notif, dry_run=dry_run
        )

    assert run is not None  # cli_error_handler() already exited on any exception above
    _render_human_result(run, dry_run=dry_run)


@click.command("notify")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Evaluate and report every decision; zero ntfy calls, zero bd writes, zero state writes.",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Emit a single machine-readable JSON envelope to stdout instead of Rich console output.",
)
@click.pass_context
@async_command
async def notify(ctx: click.Context, dry_run: bool, json_output: bool) -> None:
    """Evaluate the assumption-ledger delivery schedule and deliver anything due.

    Batches medium-severity assumption-ledger entries into ntfy pushes at
    configured review windows (respecting quiet hours and the minimum
    batch size), counts low-severity entries without ever pushing for them
    on their own, and is safe to run repeatedly from cron: a window
    occurrence delivers at most once, and overlapping invocations produce
    one evaluation plus a benign skip rather than a duplicate push. Inert
    (exit 0, no-op) when no ``assumptions.schedule`` block is configured
    (FR-021). See specs/054-assumption-batch-scheduler/contracts/cli-notify-json.md.

    Examples:

        maverick notify

        maverick notify --dry-run --json
    """
    cwd = Path.cwd().resolve()
    config = (ctx.obj or {}).get("config") if ctx.obj else None
    if config is None:
        config = load_config()

    if json_output:
        await _run_notify_json(dry_run=dry_run, cwd=cwd, config=config)
        return

    await _run_notify_human(dry_run=dry_run, cwd=cwd, config=config)
