"""``maverick fly`` command.

Bead-driven development workflow — picks the next ready bead(s) and
iterates: implement, validate, review, commit, close, repeat.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.console import console
from maverick.cli.context import ExitCode, async_command
from maverick.cli.workflow_executor import (
    PythonWorkflowRunConfig,
    _display_name,
    execute_python_workflow,
)
from maverick.workflows.fly_beads import FlyBeadsWorkflow
from maverick.workflows.fly_beads.constants import (
    COMMIT,
    CREATE_WORKSPACE,
    GATE_CHECK,
    GATE_REMEDIATION,
    IMPLEMENT_AND_VALIDATE,
    PREFLIGHT,
    REVIEW,
    SELECT_BEAD,
    SNAPSHOT_UNCOMMITTED,
    WORKFLOW_NAME,
)

# Ordered list of fly-beads steps for --list-steps display.
_FLY_BEADS_STEPS = [
    PREFLIGHT,
    SNAPSHOT_UNCOMMITTED,
    CREATE_WORKSPACE,
    SELECT_BEAD,
    IMPLEMENT_AND_VALIDATE,
    GATE_CHECK,
    GATE_REMEDIATION,
    REVIEW,
    COMMIT,
]


@click.command()
@click.option(
    "--epic",
    default=None,
    help="Epic bead ID to iterate over (omit to pick any ready bead).",
)
@click.option(
    "--max-beads",
    default=0,
    show_default=True,
    type=int,
    help="Maximum number of beads to process (0 = unlimited; drain the queue).",
)
@click.option(
    "--list-steps",
    is_flag=True,
    default=False,
    help="List workflow steps and exit without executing.",
)
@click.option(
    "--auto-commit",
    is_flag=True,
    default=False,
    help="Automatically commit uncommitted changes before cloning workspace.",
)
@click.option(
    "--session-log",
    type=click.Path(path_type=Path),
    default=None,
    help="Write session journal (JSONL) to this file path.",
)
@click.option(
    "--watch",
    is_flag=True,
    default=False,
    help="Keep running and poll for new beads when queue is empty.",
)
@click.option(
    "--watch-interval",
    type=int,
    default=30,
    show_default=True,
    help="Seconds between polls when no beads are ready (requires --watch).",
)
@click.option(
    "--skip-preflight",
    is_flag=True,
    default=False,
    help=(
        "Skip the pre-flight checks (provider health, git config, etc.). "
        "Testing only — runtime failures will surface mid-flight instead."
    ),
)
@click.pass_context
@async_command
async def fly(
    ctx: click.Context,
    epic: str | None,
    max_beads: int,
    list_steps: bool,
    auto_commit: bool,
    session_log: Path | None,
    watch: bool,
    watch_interval: int,
    skip_preflight: bool,
) -> None:
    """Run a bead-driven development workflow.

    Iterates over ready beads: selects the next bead, implements it,
    validates, reviews, commits, closes, and repeats until all beads
    are done.

    When --epic is provided, only beads under that epic are considered.
    When omitted, any ready bead across all epics may be selected.

    With --watch, fly keeps running and polls for new beads when the
    queue is empty. This enables concurrent plan/refuel in another
    terminal while fly continuously drains work.

    Examples:
        maverick fly
        maverick fly --epic my-epic
        maverick fly --max-beads 5
        maverick fly --watch
    """
    if list_steps:
        console.print(f"[bold]Workflow: {WORKFLOW_NAME}[/]")
        console.print()
        console.print("[bold]Steps:[/]")
        for i, step_name in enumerate(_FLY_BEADS_STEPS, 1):
            console.print(f"  {i}. {_display_name(step_name)}")
        console.print()
        raise SystemExit(ExitCode.SUCCESS)

    # Preflight: bd installed AND .beads initialized. Fly closes beads
    # at the end of every successful round, so a missing bd setup would
    # only surface mid-workflow (after expensive implementer + reviewer
    # work) without this check. ``--skip-preflight`` bypasses both this
    # CLI-level check and the in-workflow PREFLIGHT step.
    if skip_preflight:
        console.print(
            "[yellow]Warning:[/yellow] --skip-preflight is set; "
            "provider/git/jj/bd checks will not run. "
            "Failures will surface mid-flight."
        )
    else:
        from maverick.cli.common import verify_bd_ready

        verify_bd_ready()

    await execute_python_workflow(
        ctx,
        PythonWorkflowRunConfig(
            workflow_class=FlyBeadsWorkflow,
            inputs={
                "epic_id": epic or "",
                "max_beads": max_beads,
                "auto_commit": auto_commit,
                "watch": watch,
                "watch_interval": watch_interval,
                "skip_preflight": skip_preflight,
            },
            session_log_path=session_log,
        ),
    )
