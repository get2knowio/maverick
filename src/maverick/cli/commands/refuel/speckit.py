"""``maverick refuel speckit`` command.

Delegates to the ``refuel-speckit`` DSL workflow via ``_execute_workflow_run``.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.commands.refuel._group import refuel
from maverick.cli.commands.workflow import _execute_workflow_run
from maverick.cli.context import async_command


@refuel.command()
@click.argument(
    "spec_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
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
    spec_dir: Path,
    dry_run: bool,
    list_steps: bool,
    session_log: Path | None,
) -> None:
    """Generate beads from a SpecKit specification directory.

    SPEC_DIR is the path to a spec directory containing tasks.md.

    This command delegates to the refuel-speckit DSL workflow, providing
    event streaming, checkpointing, and preflight prerequisite checks.

    Examples:
        maverick refuel speckit /path/to/spec
        maverick refuel speckit /path/to/spec --dry-run
        maverick refuel speckit /path/to/spec --list-steps
    """
    await _execute_workflow_run(
        ctx,
        "refuel-speckit",
        (
            f"spec_dir={spec_dir.resolve()}",
            f"dry_run={dry_run}",
        ),
        None,  # input_file
        False,  # dry_run (workflow-level, not bead-level)
        False,  # restart
        False,  # no_validate
        list_steps,
        None,  # only_step
        session_log_path=session_log,
    )
