"""Shared helpers for ``maverick refuel`` subcommands.

Extracts the common Click options, step listing, and workflow execution
logic used by the ``flight-plan`` subcommand.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click

from maverick.cli.console import console
from maverick.cli.context import ExitCode
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

if TYPE_CHECKING:
    from collections.abc import Callable

# Canonical ordered step list for all refuel-maverick-based commands.
REFUEL_STEPS: list[str] = [
    PARSE_FLIGHT_PLAN,
    GATHER_CONTEXT,
    BRIEFING,
    DECOMPOSE,
    VALIDATE,
    WRITE_WORK_UNITS,
    CREATE_BEADS,
    WIRE_DEPS,
]

# Steps that use agents (for display purposes).
_AGENT_STEPS: dict[str, str] = {
    BRIEFING: "agent (parallel)",
    DECOMPOSE: "agent",
}


def print_steps_and_exit() -> None:
    """Print the workflow step list and exit with success.

    Displays the workflow name and each step with its type indicator
    (``agent`` for the decompose step, ``python`` for all others).

    Raises:
        SystemExit: Always raises with ``ExitCode.SUCCESS``.
    """
    console.print(f"[bold]Workflow: {WORKFLOW_NAME}[/]")
    console.print()
    console.print("[bold]Steps:[/]")
    for i, step_name in enumerate(REFUEL_STEPS, 1):
        step_type = _AGENT_STEPS.get(step_name, "python")
        console.print(f"  {i}. {step_name} [dim]({step_type})[/]")
    console.print()
    raise SystemExit(ExitCode.SUCCESS)


async def run_refuel_workflow(
    ctx: click.Context,
    flight_plan_path: Path,
    dry_run: bool,
    session_log: Path | None,
    skip_briefing: bool = False,
) -> None:
    """Execute the RefuelMaverickWorkflow with the given parameters.

    Args:
        ctx: Click context for workflow execution.
        flight_plan_path: Path to the flight plan Markdown file.
        dry_run: If True, write work unit files but skip bead creation.
        session_log: Optional path for session journal output.
        skip_briefing: If True, skip the briefing room step.
    """
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


def refuel_flight_plan_options(fn: Callable[..., object]) -> Callable[..., object]:
    """Apply the shared Click options for refuel flight-plan commands.

    Decorates a Click command with the ``FLIGHT-PLAN-PATH`` argument and
    ``--dry-run``, ``--list-steps``, and ``--session-log`` options.

    Args:
        fn: The Click command function to decorate.

    Returns:
        The decorated function with all shared options applied.
    """
    fn = click.argument(
        "flight_plan_path",
        metavar="FLIGHT-PLAN-PATH",
        type=click.Path(exists=False, path_type=Path),
    )(fn)
    fn = click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Write work unit files but skip bead creation.",
    )(fn)
    fn = click.option(
        "--list-steps",
        is_flag=True,
        default=False,
        help="List workflow steps and exit without executing.",
    )(fn)
    fn = click.option(
        "--session-log",
        type=click.Path(path_type=Path),
        default=None,
        help="Write session journal (JSONL) to this file path.",
    )(fn)
    fn = click.option(
        "--skip-briefing",
        is_flag=True,
        default=False,
        help="Skip the briefing room step (parallel agent analysis).",
    )(fn)
    return fn
