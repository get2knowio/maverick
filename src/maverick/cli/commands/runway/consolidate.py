"""``maverick runway consolidate`` command."""

from __future__ import annotations

import click

from maverick.cli.commands.runway._group import runway
from maverick.cli.console import console
from maverick.cli.context import async_command
from maverick.cli.output import format_success, format_warning


@runway.command()
@click.option("--force", is_flag=True, default=False, help="Run even if below thresholds.")
@click.pass_context
@async_command
async def consolidate(ctx: click.Context, force: bool) -> None:
    """Consolidate runway episodic records into semantic summaries."""
    from maverick.config import load_config
    from maverick.library.actions.consolidation import consolidate_runway

    config = load_config()

    result = await consolidate_runway(
        force=force,
        max_age_days=config.runway.consolidation.max_episodic_age_days,
        max_records=config.runway.consolidation.max_episodic_records,
    )

    if result.skipped:
        console.print(f"Skipped: {result.skip_reason}")
    elif result.success:
        msg = f"Pruned {result.records_pruned} old records."
        if result.summary_updated:
            msg += " Updated consolidated-insights.md."
        console.print(format_success(msg))
    else:
        console.print(format_warning(f"Consolidation failed: {result.error}"))
