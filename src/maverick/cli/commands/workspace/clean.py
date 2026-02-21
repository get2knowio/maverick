"""``maverick workspace clean`` command."""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.commands.workspace._group import workspace
from maverick.cli.console import console
from maverick.cli.context import async_command
from maverick.cli.output import format_success, format_warning


@workspace.command()
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Skip confirmation prompt.",
)
@click.pass_context
@async_command
async def clean(ctx: click.Context, yes: bool) -> None:
    """Remove the workspace for the current project."""
    from maverick.workspace.manager import WorkspaceManager

    user_repo = Path.cwd().resolve()
    manager = WorkspaceManager(user_repo_path=user_repo)

    if not manager.exists:
        console.print(format_warning("No workspace to clean up."))
        return

    if not yes:
        console.print(f"Will remove workspace at: {manager.workspace_path}")
        answer = console.input("Continue? [y/N] ")
        if not answer.strip().lower().startswith("y"):
            console.print("Cancelled.")
            return

    await manager.teardown()
    console.print(format_success("Workspace cleaned up."))
