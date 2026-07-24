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
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import click
from rich.table import Table

from maverick.cli.common import cli_error_handler, verify_bd_ready
from maverick.cli.console import console, err_console
from maverick.cli.context import ExitCode, async_command
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


@click.command("reconcile")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help=(
        "Preview detection, ordering, and target resolution with zero jj/bd/filesystem mutations."
    ),
)
@click.pass_context
@async_command
async def reconcile(ctx: click.Context, dry_run: bool) -> None:
    """Reconcile changed assumption-ledger answers against the current stack.

    Detects human-answered assumption-ledger entries whose adopted answer
    changed since the entry was last reconciled, re-applies each
    correction to its resolved target change, gates the result (format,
    lint, typecheck, test), and marks each answer terminal — reconciled or
    needs-interactive-review. See
    specs/051-reconcile-changed-answers/contracts/cli-reconcile.md.
    """
    cwd = Path.cwd().resolve()

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
