from __future__ import annotations

import click

from maverick.cli.context import ExitCode
from maverick.cli.helpers import (
    count_tasks,
    detect_task_file,
    format_status_json,
    format_status_text,
    get_git_branch,
    get_workflow_history,
)
from maverick.logging import get_logger


@click.command()
@click.option(
    "-f",
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format.",
)
@click.pass_context
def status(ctx: click.Context, fmt: str) -> None:
    """Display project status information.

    Shows current git branch, pending tasks, recent workflow runs, and
    configuration status.

    Examples:
        maverick status
        maverick status --format json
    """
    logger = get_logger(__name__)

    try:
        # Get git branch
        branch, error_msg = get_git_branch()
        if error_msg:
            click.echo(error_msg, err=True)
            raise SystemExit(ExitCode.FAILURE)

        # Ensure we have a valid branch name
        if not branch:
            branch = "(unknown)"

        # Detect pending tasks from tasks.md
        task_file_found = False
        pending_tasks = 0
        completed_tasks = 0

        task_file_path = detect_task_file(
            branch
            if branch and branch not in ("(unknown)", "(detached HEAD)")
            else None
        )

        if task_file_path:
            task_file_found = True
            pending_tasks, completed_tasks = count_tasks(task_file_path)

        # Get recent workflow history
        recent_workflows = get_workflow_history(count=5)

        # Format output
        if fmt == "json":
            output = format_status_json(
                branch,
                task_file_found,
                pending_tasks,
                completed_tasks,
                recent_workflows,
            )
        else:
            output = format_status_text(
                branch,
                task_file_found,
                pending_tasks,
                completed_tasks,
                recent_workflows,
            )

        click.echo(output)

    except SystemExit:
        raise
    except Exception as e:
        # Unexpected error
        logger.exception("Unexpected error in status command")
        click.echo(f"Error: {e!s}", err=True)
        raise SystemExit(ExitCode.FAILURE) from e
