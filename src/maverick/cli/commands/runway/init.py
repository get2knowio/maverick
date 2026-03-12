"""``maverick runway init`` command."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click

from maverick.cli.commands.runway._group import runway
from maverick.cli.console import console
from maverick.cli.output import format_success


@runway.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize the runway knowledge store in the current project."""
    from maverick.runway.store import RunwayStore

    project_path = Path.cwd().resolve()
    runway_path = project_path / ".maverick" / "runway"
    store = RunwayStore(runway_path)

    if store.is_initialized:
        console.print(format_success("Runway already initialized."))
        console.print(f"  Path: {runway_path}")
        return

    try:
        asyncio.get_event_loop().run_until_complete(store.initialize())
    except RuntimeError:
        asyncio.run(store.initialize())

    console.print(format_success("Runway initialized."))
    console.print(f"  Path: {runway_path}")
