"""``maverick refuel`` command.

Single command that loads work into beads from various sources.
Default source is a flight plan (``--from plan``); use ``--from speckit``
to load from a SpecKit specification.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click

from maverick.cli.commands.flight_plan._group import DEFAULT_PLANS_DIR
from maverick.cli.console import console
from maverick.cli.context import ExitCode, async_command

if TYPE_CHECKING:
    pass


@click.command()
@click.argument("name_or_path")
@click.option(
    "--from",
    "source_type",
    type=click.Choice(["plan", "speckit"]),
    default="plan",
    show_default=True,
    help="Source type: 'plan' (flight plan) or 'speckit' (SpecKit spec).",
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
    help="Base plans directory (only used with --from plan).",
)
@click.pass_context
@async_command
async def refuel(
    ctx: click.Context,
    name_or_path: str,
    source_type: str,
    dry_run: bool,
    list_steps: bool,
    session_log: Path | None,
    skip_briefing: bool,
    plans_dir: str,
) -> None:
    """Load work into beads from a flight plan or SpecKit specification.

    NAME_OR_PATH is the plan name (default) or speckit spec path.

    With --from plan (default), NAME_OR_PATH is a kebab-case plan name.
    The flight plan is read from .maverick/plans/<name>/flight-plan.md.

    With --from speckit, NAME_OR_PATH is the spec identifier (branch name
    and directory under specs/).

    Examples:

        maverick refuel my-feature

        maverick refuel my-feature --dry-run

        maverick refuel my-feature --skip-briefing

        maverick refuel --from speckit 001-greet-cli

        maverick refuel --from speckit 001-greet-cli --dry-run
    """
    if source_type == "plan":
        await _refuel_from_plan(
            ctx, name_or_path, plans_dir, dry_run, list_steps, session_log, skip_briefing
        )
    else:
        await _refuel_from_speckit(
            ctx, name_or_path, dry_run, list_steps, session_log
        )


async def _refuel_from_plan(
    ctx: click.Context,
    name: str,
    plans_dir: str,
    dry_run: bool,
    list_steps: bool,
    session_log: Path | None,
    skip_briefing: bool,
) -> None:
    """Refuel from a flight plan."""
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
    agent_steps = {BRIEFING: "agent (parallel)", DECOMPOSE: "agent"}

    if list_steps:
        console.print(f"[bold]Workflow: {WORKFLOW_NAME}[/]")
        console.print()
        console.print("[bold]Steps:[/]")
        for i, step_name in enumerate(steps, 1):
            step_type = agent_steps.get(step_name, "python")
            console.print(f"  {i}. {step_name} [dim]({step_type})[/]")
        console.print()
        raise SystemExit(ExitCode.SUCCESS)

    flight_plan_path = Path(plans_dir) / name / "flight-plan.md"

    await execute_python_workflow(
        ctx,
        PythonWorkflowRunConfig(
            workflow_class=RefuelMaverickWorkflow,
            inputs={
                "flight_plan_path": str(flight_plan_path),
                "dry_run": dry_run,
                "skip_briefing": skip_briefing,
            },
            session_log_path=session_log,
        ),
    )


async def _refuel_from_speckit(
    ctx: click.Context,
    spec: str,
    dry_run: bool,
    list_steps: bool,
    session_log: Path | None,
) -> None:
    """Refuel from a SpecKit specification."""
    from maverick.cli.workflow_executor import (
        PythonWorkflowRunConfig,
        execute_python_workflow,
    )
    from maverick.workflows.refuel_speckit import RefuelSpeckitWorkflow
    from maverick.workflows.refuel_speckit.constants import (
        CHECKOUT,
        CHECKOUT_MAIN,
        COMMIT,
        CREATE_BEADS,
        ENRICH_BEADS,
        EXTRACT_DEPS,
        MERGE,
        PARSE_SPEC,
        WIRE_DEPS,
        WORKFLOW_NAME,
    )

    steps = [
        CHECKOUT,
        PARSE_SPEC,
        EXTRACT_DEPS,
        ENRICH_BEADS,
        CREATE_BEADS,
        WIRE_DEPS,
        COMMIT,
        CHECKOUT_MAIN,
        MERGE,
    ]

    if list_steps:
        console.print(f"[bold]Workflow: {WORKFLOW_NAME}[/]")
        console.print()
        console.print("[bold]Steps:[/]")
        for i, step_name in enumerate(steps, 1):
            console.print(f"  {i}. {step_name} [dim](python)[/]")
        console.print()
        raise SystemExit(ExitCode.SUCCESS)

    await execute_python_workflow(
        ctx,
        PythonWorkflowRunConfig(
            workflow_class=RefuelSpeckitWorkflow,
            inputs={
                "spec": spec,
                "dry_run": dry_run,
            },
            session_log_path=session_log,
        ),
    )
