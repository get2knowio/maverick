"""``maverick workspace status`` command."""

from __future__ import annotations

from pathlib import Path

import click
from rich.table import Table

from maverick.cli.commands.workspace._group import workspace
from maverick.cli.console import console
from maverick.cli.output import format_warning


@workspace.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show workspace status for the current project."""
    from maverick.workspace.manager import WorkspaceManager

    user_repo = Path.cwd().resolve()
    manager = WorkspaceManager(user_repo_path=user_repo)

    if not manager.exists:
        console.print(format_warning("No workspace found for this project."))
        console.print(f"  Expected path: {manager.workspace_path}")
        return

    state = manager.get_state()

    table = Table(show_header=False, show_lines=False, padding=(0, 2))
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("Project", user_repo.name)
    table.add_row("Workspace", str(manager.workspace_path))
    table.add_row("State", state.value if state else "unknown")
    table.add_row("User repo", str(user_repo))

    console.print(table)
