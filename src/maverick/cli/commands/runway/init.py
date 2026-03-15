"""``maverick runway init`` command."""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.commands.runway._group import runway
from maverick.cli.console import console
from maverick.cli.context import async_command
from maverick.cli.output import format_success


@runway.command()
@click.pass_context
@async_command
async def init(ctx: click.Context) -> None:
    """Initialize the runway knowledge store in the current project."""
    from maverick.runway.store import RunwayStore

    project_path = Path.cwd().resolve()
    runway_path = project_path / ".maverick" / "runway"
    store = RunwayStore(runway_path)

    if store.is_initialized:
        console.print(format_success("Runway already initialized."))
        console.print(f"  Path: {runway_path}")
        return

    await store.initialize()

    console.print(format_success("Runway initialized."))
    console.print(f"  Path: {runway_path}")
