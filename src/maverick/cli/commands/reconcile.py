"""``maverick reconcile`` — reconcile changed assumption-ledger answers.

See specs/051-reconcile-changed-answers/contracts/cli-reconcile.md for the
full contract (preconditions, output format, exit codes). This module
implements both the real-mutation happy path and the ``--dry-run`` preview
(T035).

The real-run dispatch goes through :func:`~maverick.cli.workflow_executor.
execute_python_workflow` (checkpointing, session journal, standard progress
rendering) and reads the workflow's persisted result back via
:func:`~maverick.workflows.reconcile.state.load_run_state` — that file is
part of the real run's contractual side effects (resumability). ``--dry-run``
cannot use that path: the contract requires "zero jj/bd/filesystem
mutations", and :meth:`~maverick.workflows.reconcile.workflow.
ReconcileWorkflow._run`'s dry-run branch deliberately never writes
``.maverick/runs/<run-id>/reconcile.json`` (T035, ``workflow.py``), so
``load_run_state`` would always come back empty. Instead, the dry-run
branch below drives the workflow directly via its public ``execute()``
template method (reusing :func:`~maverick.cli.workflow_executor.
render_workflow_events` for identical progress output) and reads the
predicted report straight off ``workflow.result.final_output`` — entirely
in-memory, matching the contract's zero-mutation guarantee.

``--json`` (053-assumption-review-console, T013; see
specs/053-assumption-review-console/contracts/cli-reconcile-json.md) adds a
third path, ``_run_reconcile_json``, used for *both* the real run and
``--dry-run``: it never goes through ``execute_python_workflow`` (which
would swallow a ``WorkflowError`` into a stderr message before
``json_error_handler`` ever saw it — see that function's docstring), always
driving ``ReconcileWorkflow.execute()`` directly and reading
``workflow.result.final_output`` the same way the dry-run path above
already does.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import click
from rich.table import Table

from maverick.cli.common import (
    BD_MISSING,
    BD_NOT_INITIALIZED,
    bd_ready_reason,
    cli_error_handler,
    resolve_verbosity,
    verify_bd_ready,
)
from maverick.cli.console import console, err_console
from maverick.cli.context import ExitCode, async_command
from maverick.cli.json_output import JsonEnvelope, emit_json, json_error_handler
from maverick.exceptions import REASON_DIRTY_WORKING_COPY, BeadError, JjError, WorkflowError
from maverick.jj.client import JjClient
from maverick.workflows.reconcile.state import AnswerState, ReconcileRunState

__all__ = ["reconcile"]

#: Python `AnswerOutcome.status` / `AnswerState.terminal_status` spelling ->
#: the CLI summary table's spelling (data-model.md's three-spellings table
#: in workflows/reconcile/models.py — this owns the third, CLI, spelling).
_STATUS_DISPLAY = {
    "reconciled": "reconciled",
    "skipped": "skipped",
    "needs_interactive_review": "needs interactive review",
}

_STATUS_STYLE = {
    "reconciled": "green",
    "skipped": "yellow",
    "needs_interactive_review": "red",
}


def _display_status(status: str | None) -> str:
    if status is None:
        return "unknown"
    return _STATUS_DISPLAY.get(status, status)


def _render_answers_table(answers: list[AnswerState]) -> Table:
    # Columns per the contract's Output contract §3 (ID, Severity, Target,
    # Status, Reason) minus Severity: neither `AnswerState` (state.py) nor
    # `ReconcileReport.to_dict()` (models.py) carries a severity field for
    # a terminal answer, so that column is omitted rather than invented.
    table = Table()
    table.add_column("ID")
    table.add_column("Target")
    table.add_column("Status")
    table.add_column("Reason")

    for answer in answers:
        status = answer.terminal_status
        style = _STATUS_STYLE.get(status or "", "white")
        table.add_row(
            answer.entry_id,
            answer.target_change_id or "",
            f"[{style}]{_display_status(status)}[/{style}]",
            answer.reason or "",
        )
    return table


def _render_summary_and_exit(run_state: ReconcileRunState | None) -> None:
    """Render the final summary table and exit per the contract's exit-code rule.

    ``run_state is None`` means the workflow returned via its zero-changed-
    answers early exit (:meth:`ReconcileWorkflow._run` never persists run
    state on that path) — the only reconcile outcome that skips
    ``save_run_state`` entirely, per ``workflows/reconcile/state.py``.
    """
    if run_state is None:
        console.print("[green]✓[/] No changed answers — nothing to reconcile.")
        raise SystemExit(ExitCode.SUCCESS)

    console.print()
    console.print(_render_answers_table(run_state.answers))

    any_non_reconciled = any(
        answer.terminal_status != "reconciled" for answer in run_state.answers
    )
    if any_non_reconciled:
        console.print()
        console.print("Run: [bold]maverick review <id>[/]  (re-answer to re-arm reconcile)")

    if not any_non_reconciled:
        raise SystemExit(ExitCode.SUCCESS)
    raise SystemExit(ExitCode.FAILURE)


def _dry_run_display(outcome: dict[str, Any]) -> tuple[str, str]:
    """Map a predicted ``AnswerOutcome`` dict to (display text, Rich style).

    Contract's dry-run vocabulary (cli-reconcile.md "Output contract"):
    ``reconciled`` -> ``"would reconcile"``, ``skipped`` ->
    ``"would skip (<reason>)"``. The workflow's dry-run predictor
    (:meth:`~maverick.workflows.reconcile.workflow.ReconcileWorkflow.
    _predict_dry_run_outcomes`) only ever produces these two statuses —
    ``needs_interactive_review`` never occurs in a dry-run report (nothing
    is ever attempted, so nothing is ever rolled back) — but an unknown
    status still falls back to the real-run spelling rather than crashing.
    """
    status = outcome.get("status")
    reason = outcome.get("reason") or ""
    if status == "reconciled":
        return "would reconcile", "green"
    if status == "skipped":
        return f"would skip ({reason})", "yellow"
    return _display_status(status), _STATUS_STYLE.get(status or "", "white")


def _render_dry_run_answers_table(outcomes: list[dict[str, Any]]) -> Table:
    # Same column shape as `_render_answers_table` (ID, Target, Status,
    # Reason); only the Status column's vocabulary differs for dry-run.
    table = Table()
    table.add_column("ID")
    table.add_column("Target")
    table.add_column("Status")
    table.add_column("Reason")

    for outcome in outcomes:
        display, style = _dry_run_display(outcome)
        table.add_row(
            str(outcome.get("entry_id", "")),
            str(outcome.get("target_change_id") or ""),
            f"[{style}]{display}[/{style}]",
            str(outcome.get("reason") or ""),
        )
    return table


def _render_dry_run_summary_and_exit(report: dict[str, Any]) -> None:
    """Render the dry-run preview table and always exit SUCCESS.

    Per the contract's exit-codes table: "``--dry-run`` with valid
    preconditions -> SUCCESS(0) regardless of predicted statuses" — unlike
    the real-run summary, this never inspects the predicted statuses to
    decide the exit code.
    """
    outcomes = report.get("outcomes") or []
    if not outcomes:
        console.print("[green]✓[/] No changed answers — nothing to reconcile.")
        raise SystemExit(ExitCode.SUCCESS)

    console.print()
    console.print(_render_dry_run_answers_table(outcomes))
    console.print()
    console.print("Dry run — no changes made.")
    raise SystemExit(ExitCode.SUCCESS)


async def _run_dry_run_preview(ctx: click.Context, *, run_id: str, cwd: Path) -> None:
    """Drive the reconcile workflow's dry-run branch directly, in-memory.

    Bypasses :func:`~maverick.cli.workflow_executor.execute_python_workflow`
    (whose companion ``load_run_state`` read would always be empty for a
    dry run, per the module docstring above) but reuses its
    ``render_workflow_events`` so progress output (e.g. "Detecting changed
    answers...") looks identical to the real-run path.
    """
    from maverick.cli.workflow_executor import render_workflow_events
    from maverick.config import load_config
    from maverick.workflows.reconcile.workflow import WORKFLOW_NAME, ReconcileWorkflow

    config = (ctx.obj or {}).get("config") if ctx.obj else None
    if config is None:
        config = load_config()

    workflow = ReconcileWorkflow(config=config)
    events = workflow.execute({"run_id": run_id, "cwd": str(cwd), "dry_run": True})

    with cli_error_handler():
        await render_workflow_events(events, console, workflow_name=WORKFLOW_NAME)

    assert workflow.result is not None
    if not workflow.result.success:
        # `execute()` re-raises the underlying exception after yielding
        # WorkflowCompleted(success=False) (base.py) — `render_workflow_events`
        # propagates that, and `cli_error_handler()` above converts it to a
        # SystemExit before we ever get here. This is an unreachable
        # defensive fallback, not a normal exit path.
        raise SystemExit(ExitCode.FAILURE)

    report = workflow.result.final_output
    assert isinstance(report, dict)
    _render_dry_run_summary_and_exit(report)


#: Machine reason (``maverick.cli.common.bd_ready_reason``) -> the message
#: the ``bd-unavailable`` envelope carries.
_BD_REASON_MESSAGES = {
    BD_MISSING: "The bd CLI is required but not found on PATH.",
    BD_NOT_INITIALIZED: (
        "this project hasn't been initialized for Maverick yet — run `maverick init`."
    ),
}


def _require_bd_ready_json(cwd: Path) -> None:
    """JSON-mode sibling of :func:`maverick.cli.common.verify_bd_ready`.

    ``verify_bd_ready`` prints a Rich-formatted message to ``console``
    (stdout) and calls ``SystemExit`` directly rather than raising — see
    ``maverick.cli.json_output``'s module docstring, "Scope note on
    bd-unavailable". That's incompatible with ``--json`` (FR: stdout
    carries exactly one JSON document), so this consumes the same shared
    predicate (:func:`~maverick.cli.common.bd_ready_reason` — the single
    place the conditions live, so the two modes can't drift) and raises
    :class:`~maverick.exceptions.BeadError` instead, letting the caller's
    ``json_error_handler`` build the ``bd-unavailable`` envelope via its
    existing ``BeadError`` mapping. Human mode keeps calling
    ``verify_bd_ready`` unchanged (FR-018 byte-for-byte preservation).
    """
    reason = bd_ready_reason(cwd)
    if reason is None:
        return
    raise BeadError(_BD_REASON_MESSAGES.get(reason, f"bd is not ready ({reason})."))


async def _run_reconcile_json(ctx: click.Context, *, dry_run: bool, cwd: Path) -> None:
    """Drive reconcile end-to-end in ``--json`` mode: one envelope on stdout.

    Bypasses :func:`~maverick.cli.workflow_executor.execute_python_workflow`
    for the real run too (not just dry-run, which already bypassed it —
    see this module's docstring): that helper wraps its dispatch in
    :func:`~maverick.cli.common.cli_error_handler`, which catches
    ``WorkflowError`` (raised by :meth:`ReconcileWorkflow._run` for the
    concurrent-fly-run and reconcile-lockfile preconditions) and converts
    it directly to a stderr message + ``SystemExit`` *before* control ever
    returns here — there would be nothing left for ``json_error_handler``
    to map to ``concurrent-run``/``locked``. Driving the workflow's public
    ``execute()`` template method directly (same mechanism the dry-run
    path already uses) keeps the ``WorkflowError`` intact.

    ``ReconcileWorkflow._run`` returns ``ReconcileReport.to_dict()``
    unconditionally — real run and dry run alike (workflow.py) — so
    ``workflow.result.final_output`` is already the exact JSON result
    shape for both verbs; no separate real-run report needs to be
    assembled from ``load_run_state``.

    All four preconditions (bd-ready, jj-colocated, clean working copy,
    then the workflow's own concurrent-fly/lockfile guards) are expressed
    as raised exceptions inside one ``json_error_handler`` scope, reusing
    its existing ``BeadError`` -> ``bd-unavailable``, ``JjError`` ->
    ``vcs``, and ``WorkflowError`` substring -> ``dirty-working-copy``/
    ``concurrent-run``/``locked`` mappings — no envelope is built by hand
    here. The ``.jj``-missing check has no natural ``JjError`` subclass
    (``JjNotFoundError`` specifically means "the jj binary isn't on
    PATH", a different condition), so it raises the ``JjError`` base
    class directly with this project's own message.
    """
    verb = "reconcile.dry-run" if dry_run else "reconcile.run"

    with json_error_handler(verb):
        _require_bd_ready_json(cwd)

        if not (cwd / ".jj").is_dir():
            raise JjError("this project is not a jj-colocated repository.")

        jj_client = JjClient(cwd=cwd)
        working_copy_stat = await jj_client.diff_stat(revision="@")
        if working_copy_stat.files_changed != 0:
            # Same precondition (and same typed reason) the workflow itself
            # raises — `json_error_handler` dispatches on `reason_code`, so the
            # prose is free to diverge without breaking the mapping.
            raise WorkflowError(
                "working copy is not clean — commit or discard changes before running reconcile",
                reason_code=REASON_DIRTY_WORKING_COPY,
            )

        run_id = uuid.uuid4().hex[:8]

        from maverick.checkpoint.store import FileCheckpointStore
        from maverick.cli.workflow_executor import render_workflow_events
        from maverick.config import load_config
        from maverick.workflows.reconcile.workflow import WORKFLOW_NAME, ReconcileWorkflow

        config = (ctx.obj or {}).get("config") if ctx.obj else None
        if config is None:
            config = load_config()

        # Parity with `execute_python_workflow`'s dispatch, which this path
        # deliberately bypasses (see the docstring above): a real run still
        # gets a checkpoint store, and progress still honours `-v`.
        # `--dry-run` gets neither — it must not touch the filesystem.
        checkpoint_store = (
            None if dry_run else FileCheckpointStore(cwd / ".maverick" / "checkpoints")
        )
        workflow = ReconcileWorkflow(
            config=config,
            checkpoint_store=checkpoint_store,
            workflow_name=WORKFLOW_NAME,
        )
        events = workflow.execute({"run_id": run_id, "cwd": str(cwd), "dry_run": dry_run})

        verbosity = resolve_verbosity(ctx)
        steps_meta = getattr(ReconcileWorkflow, "STEPS", None) or {}
        total_steps = len(steps_meta) if isinstance(steps_meta, dict) else 0

        # Progress narration goes to stderr in JSON mode (contract:
        # stdout carries exactly one JSON document) — `err_console`
        # instead of the human-mode `console`.
        await render_workflow_events(
            events,
            err_console,
            workflow_name=WORKFLOW_NAME,
            verbosity=verbosity,
            total_steps=total_steps,
        )

        assert workflow.result is not None
        if not workflow.result.success:
            # `execute()` re-raises the underlying exception after yielding
            # WorkflowCompleted(success=False) — that exception propagates
            # through `render_workflow_events` into the `json_error_handler`
            # scope above before we ever reach this line. Unreachable
            # defensive fallback, same rationale as `_run_dry_run_preview`'s
            # equivalent branch.
            raise SystemExit(ExitCode.FAILURE)

        report = workflow.result.final_output
        assert isinstance(report, dict)

    # Contract exit codes: dry-run always 0 (barring an error envelope
    # above); real run 0 when nothing to reconcile or every outcome
    # `reconciled` (`report["exit_success"]`), else 1 — `ok: true` either
    # way, the outcomes carry the news.
    exit_code = ExitCode.SUCCESS if (dry_run or report["exit_success"]) else ExitCode.FAILURE
    emit_json(JsonEnvelope.success(verb, report))
    raise SystemExit(exit_code)


@click.command("reconcile")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help=(
        "Preview detection, ordering, and target resolution with zero jj/bd/filesystem mutations."
    ),
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
async def reconcile(ctx: click.Context, dry_run: bool, json_output: bool) -> None:
    """Reconcile changed assumption-ledger answers against the current stack.

    Detects human-answered assumption-ledger entries whose adopted answer
    changed since the entry was last reconciled, re-applies each
    correction to its resolved target change, gates the result (format,
    lint, typecheck, test), and marks each answer terminal — reconciled or
    needs-interactive-review. See
    specs/051-reconcile-changed-answers/contracts/cli-reconcile.md and, for
    ``--json``, specs/053-assumption-review-console/contracts/
    cli-reconcile-json.md.
    """
    cwd = Path.cwd().resolve()

    if json_output:
        await _run_reconcile_json(ctx, dry_run=dry_run, cwd=cwd)
        return

    with cli_error_handler():
        # Preconditions (contract "Preconditions", checked in order).
        verify_bd_ready(cwd)

        if not (cwd / ".jj").is_dir():
            err_console.print("[red]✗[/] this project is not a jj-colocated repository.")
            err_console.print(
                "[yellow]Remediation:[/yellow] run [cyan]maverick init[/cyan] "
                "in this directory first."
            )
            raise SystemExit(ExitCode.FAILURE)

        jj_client = JjClient(cwd=cwd)
        working_copy_stat = await jj_client.diff_stat(revision="@")
        if working_copy_stat.files_changed != 0:
            err_console.print("[red]✗[/] working copy is not clean.")
            err_console.print(
                "[yellow]Remediation:[/yellow] commit or discard changes before running reconcile."
            )
            raise SystemExit(ExitCode.FAILURE)

        # NOTE (T022): precondition 4, "no concurrent run" — the reconcile
        # lockfile (acquire_lock/release_lock, workflows/reconcile/state.py)
        # and the fly-run-flying check — is wired into the workflow itself
        # by a later task, not this CLI layer. Intentionally not
        # implemented here; do not invent lock-acquisition logic in the CLI.

    run_id = uuid.uuid4().hex[:8]

    if dry_run:
        await _run_dry_run_preview(ctx, run_id=run_id, cwd=cwd)
        return

    from maverick.cli.workflow_executor import PythonWorkflowRunConfig, execute_python_workflow
    from maverick.workflows.reconcile.state import load_run_state
    from maverick.workflows.reconcile.workflow import ReconcileWorkflow

    await execute_python_workflow(
        ctx,
        PythonWorkflowRunConfig(
            workflow_class=ReconcileWorkflow,
            inputs={"run_id": run_id, "cwd": str(cwd), "dry_run": dry_run},
        ),
    )

    run_state = await load_run_state(run_id, cwd)
    _render_summary_and_exit(run_state)
