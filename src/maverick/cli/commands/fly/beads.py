"""``maverick fly beads`` command.

Delegates to the ``fly-beads`` DSL workflow via ``_execute_workflow_run``.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.commands.fly._group import fly
from maverick.cli.commands.workflow import _execute_workflow_run
from maverick.cli.context import async_command


@fly.command()
@click.option(
    "--epic",
    required=True,
    help="Epic bead ID to iterate over.",
)
@click.option(
    "--branch",
    required=True,
    help="Git branch for all bead work.",
)
@click.option(
    "--max-beads",
    default=30,
    show_default=True,
    type=int,
    help="Maximum number of beads to process.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Preview mode — skip git and bd mutations.",
)
@click.option(
    "--skip-review",
    is_flag=True,
    default=False,
    help="Skip code review step for each bead.",
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
async def beads(
    ctx: click.Context,
    epic: str,
    branch: str,
    max_beads: int,
    dry_run: bool,
    skip_review: bool,
    list_steps: bool,
    session_log: Path | None,
) -> None:
    """Run a bead-driven development workflow.

    Iterates over ready beads in an epic: selects the next bead,
    implements it, validates, reviews, commits, closes, and repeats
    until all beads are done.

    Examples:
        maverick fly beads --epic my-epic --branch 001-feature
        maverick fly beads --epic my-epic --branch 001-feature --dry-run
        maverick fly beads --epic my-epic --branch 001-feature --skip-review
        maverick fly beads --epic my-epic --branch 001-feature --max-beads 5
    """
    await _execute_workflow_run(
        ctx,
        "fly-beads",
        (
            f"epic_id={epic}",
            f"branch_name={branch}",
            f"max_beads={max_beads}",
            f"dry_run={str(dry_run).lower()}",
            f"skip_review={str(skip_review).lower()}",
        ),
        None,  # input_file
        dry_run,  # CLI-level dry_run
        False,  # restart
        False,  # no_validate
        list_steps,
        None,  # only_step
        session_log_path=session_log,
    )
