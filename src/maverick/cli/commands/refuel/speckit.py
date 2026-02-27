"""``maverick refuel speckit`` command.

Delegates to the ``RefuelSpeckitWorkflow`` Python workflow.
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

# Ordered list of refuel-speckit steps for --list-steps display.
_REFUEL_SPECKIT_STEPS = [
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


@refuel.command()
@click.argument("spec")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what beads would be created without calling bd.",
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
async def speckit(
    ctx: click.Context,
    spec: str,
    dry_run: bool,
    list_steps: bool,
    session_log: Path | None,
) -> None:
    """Generate beads from a SpecKit specification.

    SPEC is the spec identifier (branch name and directory under specs/).

    The workflow checks out the spec branch, parses specs/<SPEC>/tasks.md,
    creates beads, commits them, and merges back into main.

    Examples:
        maverick refuel speckit 001-greet-cli
        maverick refuel speckit 001-greet-cli --dry-run
        maverick refuel speckit 001-greet-cli --list-steps
    """
    if list_steps:
        console.print(f"[bold]Workflow: {WORKFLOW_NAME}[/]")
        console.print()
        console.print("[bold]Steps:[/]")
        for i, step_name in enumerate(_REFUEL_SPECKIT_STEPS, 1):
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
