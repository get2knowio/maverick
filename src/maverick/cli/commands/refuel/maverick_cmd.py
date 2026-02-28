"""``maverick refuel maverick`` command.

Delegates to the ``RefuelMaverickWorkflow`` Python workflow.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.commands.refuel._group import refuel
from maverick.cli.console import console
from maverick.cli.context import ExitCode, async_command
from maverick.cli.workflow_executor import (
    PythonWorkflowRunConfig,
    execute_python_workflow,
)
from maverick.workflows.refuel_maverick import RefuelMaverickWorkflow
from maverick.workflows.refuel_maverick.constants import (
    CREATE_BEADS,
    DECOMPOSE,
    GATHER_CONTEXT,
    PARSE_FLIGHT_PLAN,
    VALIDATE,
    WIRE_DEPS,
    WORKFLOW_NAME,
    WRITE_WORK_UNITS,
)

# Ordered list of refuel-maverick steps for --list-steps display.
_REFUEL_MAVERICK_STEPS = [
    PARSE_FLIGHT_PLAN,
    GATHER_CONTEXT,
    DECOMPOSE,
    VALIDATE,
    WRITE_WORK_UNITS,
    CREATE_BEADS,
    WIRE_DEPS,
]


@refuel.command("maverick")
@click.argument(
    "flight_plan_path",
    metavar="FLIGHT-PLAN-PATH",
    type=click.Path(exists=False, path_type=Path),
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Write work unit files but skip bead creation.",
)
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
@click.pass_context
@async_command
async def maverick_cmd(
    ctx: click.Context,
    flight_plan_path: Path,
    dry_run: bool,
    list_steps: bool,
    session_log: Path | None,
) -> None:
    """Decompose a Maverick Flight Plan into work units and beads.

    FLIGHT-PLAN-PATH is the path to the flight plan Markdown file.

    The workflow parses the flight plan, gathers codebase context for
    in-scope files, decomposes into ordered work units via an AI agent,
    writes work unit files, and creates beads for execution by
    ``maverick fly``.

    Examples:

        maverick refuel maverick .maverick/flight-plans/add-auth.md

        maverick refuel maverick .maverick/flight-plans/add-auth.md --dry-run

        maverick refuel maverick .maverick/flight-plans/add-auth.md --list-steps
    """
    if list_steps:
        console.print(f"[bold]Workflow: {WORKFLOW_NAME}[/]")
        console.print()
        console.print("[bold]Steps:[/]")
        for i, step_name in enumerate(_REFUEL_MAVERICK_STEPS, 1):
            step_type = "agent" if step_name == DECOMPOSE else "python"
            console.print(f"  {i}. {step_name} [dim]({step_type})[/]")
        console.print()
        raise SystemExit(ExitCode.SUCCESS)

    await execute_python_workflow(
        ctx,
        PythonWorkflowRunConfig(
            workflow_class=RefuelMaverickWorkflow,
            inputs={
                "flight_plan_path": str(flight_plan_path),
                "dry_run": dry_run,
            },
            session_log_path=session_log,
        ),
    )
