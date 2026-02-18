"""``maverick refuel speckit`` command.

Delegates to the ``refuel-speckit`` DSL workflow via ``execute_workflow_run``.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.commands.refuel._group import refuel
from maverick.cli.context import async_command
from maverick.cli.workflow_executor import execute_workflow_run


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
    await execute_workflow_run(
        ctx,
        "refuel-speckit",
        (
            f"spec={spec}",
            f"dry_run={str(dry_run).lower()}",
        ),
        None,  # input_file
        dry_run,  # CLI-level dry_run: show plan and exit (skips preflight)
        False,  # restart
        False,  # no_validate
        list_steps,
        None,  # only_step
        session_log_path=session_log,
    )
