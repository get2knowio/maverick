"""``maverick fly`` command.

Bead-driven development workflow — picks the next ready bead(s) and
iterates: implement, validate, review, commit, close, repeat.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.context import async_command
from maverick.cli.workflow_executor import execute_workflow_run


@click.command()
@click.option(
    "--epic",
    default=None,
    help="Epic bead ID to iterate over (omit to pick any ready bead).",
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
async def fly(
    ctx: click.Context,
    epic: str | None,
    max_beads: int,
    dry_run: bool,
    skip_review: bool,
    list_steps: bool,
    session_log: Path | None,
) -> None:
    """Run a bead-driven development workflow.

    Iterates over ready beads: selects the next bead, implements it,
    validates, reviews, commits, closes, and repeats until all beads
    are done.

    When --epic is provided, only beads under that epic are considered.
    When omitted, any ready bead across all epics may be selected.

    Examples:
        maverick fly
        maverick fly --epic my-epic
        maverick fly --epic my-epic --dry-run
        maverick fly --skip-review --max-beads 5
    """
    input_parts: list[str] = [
        f"max_beads={max_beads}",
        f"dry_run={str(dry_run).lower()}",
        f"skip_review={str(skip_review).lower()}",
    ]
    if epic:
        input_parts.insert(0, f"epic_id={epic}")
    else:
        # Pass empty string so the workflow receives the input (not missing)
        input_parts.insert(0, "epic_id=")

    await execute_workflow_run(
        ctx,
        "fly-beads",
        tuple(input_parts),
        None,  # input_file
        dry_run,  # CLI-level dry_run
        False,  # restart
        False,  # no_validate
        list_steps,
        None,  # only_step
        session_log_path=session_log,
    )
