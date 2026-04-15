"""``maverick refuel`` command.

Decomposes a flight plan into beads (work units) using the Thespian
actor system for parallel agent execution.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.commands.flight_plan._group import DEFAULT_PLANS_DIR
from maverick.cli.console import console
from maverick.cli.context import ExitCode, async_command


@click.command()
@click.argument("name")
@click.option(
    "--list-steps",
    is_flag=True,
    default=False,
    help="List workflow steps and exit without executing.",
)
@click.option(
    "--session-log",
    type=click.Path(path_type=Path),
    default=None,
    help="Write session journal (JSONL) to this file path.",
)
@click.option(
    "--skip-briefing",
    is_flag=True,
    default=False,
    help="Skip the briefing room step (parallel agent analysis).",
)
@click.option(
    "--plans-dir",
    default=DEFAULT_PLANS_DIR,
    show_default=True,
    help="Base plans directory.",
)
@click.pass_context
@async_command
async def refuel(
    ctx: click.Context,
    name: str,
    list_steps: bool,
    session_log: Path | None,
    skip_briefing: bool,
    plans_dir: str,
) -> None:
    """Decompose a flight plan into beads.

    NAME is a kebab-case plan name. The flight plan is read from
    .maverick/plans/<name>/flight-plan.md.

    Examples:

        maverick refuel my-feature

        maverick refuel my-feature --skip-briefing
    """
    import shutil

    if shutil.which("bd") is None:
        console.print(
            "[red]Error:[/red] The [bold]bd[/bold] CLI is required but not found on PATH.\n"
            "Install it with: [cyan]cargo install bd-cli[/cyan] "
            "(or see https://github.com/get2knowio/bd)"
        )
        raise SystemExit(ExitCode.FAILURE)

    from maverick.cli.workflow_executor import (
        PythonWorkflowRunConfig,
        execute_python_workflow,
    )
    from maverick.workflows.refuel_maverick import RefuelMaverickWorkflow
    from maverick.workflows.refuel_maverick.constants import (
        BRIEFING,
        CREATE_BEADS,
        DECOMPOSE,
        GATHER_CONTEXT,
        PARSE_FLIGHT_PLAN,
        VALIDATE,
        WIRE_DEPS,
        WORKFLOW_NAME,
        WRITE_WORK_UNITS,
    )

    steps = [
        PARSE_FLIGHT_PLAN,
        GATHER_CONTEXT,
        BRIEFING,
        DECOMPOSE,
        VALIDATE,
        WRITE_WORK_UNITS,
        CREATE_BEADS,
        WIRE_DEPS,
    ]

    if list_steps:
        from maverick.cli.workflow_executor import _display_name

        console.print(f"[bold]Workflow: {WORKFLOW_NAME}[/]")
        console.print()
        console.print("[bold]Steps:[/]")
        for i, step_name in enumerate(steps, 1):
            console.print(f"  {i}. {_display_name(step_name)}")
        console.print()
        raise SystemExit(ExitCode.SUCCESS)

    flight_plan_path = Path(plans_dir) / name / "flight-plan.md"

    await execute_python_workflow(
        ctx,
        PythonWorkflowRunConfig(
            workflow_class=RefuelMaverickWorkflow,
            inputs={
                "flight_plan_path": str(flight_plan_path),
                "skip_briefing": skip_briefing,
            },
            session_log_path=session_log,
        ),
    )
