"""``maverick runway status`` command."""

from __future__ import annotations

from pathlib import Path

import click
from rich.table import Table

from maverick.cli.commands.runway._group import runway
from maverick.cli.console import console
from maverick.cli.context import async_command
from maverick.cli.output import format_bytes, format_warning


@runway.command()
@click.pass_context
@async_command
async def status(ctx: click.Context) -> None:
    """Show runway knowledge store status."""
    from maverick.runway.store import RunwayStore

    project_path = Path.cwd().resolve()
    runway_path = project_path / ".maverick" / "runway"
    store = RunwayStore(runway_path)

    if not store.is_initialized:
        console.print(format_warning("Runway not initialized."))
        console.print("  Run: maverick runway init")
        return

    runway_status = await store.get_status()

    table = Table(show_header=False, show_lines=False, padding=(0, 2))
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("Path", str(runway_path))
    table.add_row("Bead outcomes", str(runway_status.bead_outcome_count))
    table.add_row("Review findings", str(runway_status.review_finding_count))
    table.add_row("Fix attempts", str(runway_status.fix_attempt_count))
    table.add_row("Semantic files", str(len(runway_status.semantic_files)))
    table.add_row("Total size", format_bytes(runway_status.total_size_bytes))
    table.add_row(
        "Last consolidated",
        runway_status.last_consolidated or "never",
    )

    console.print(table)
