"""``maverick refuel flight-plan`` command.

Delegates to the ``RefuelMaverickWorkflow`` Python workflow via shared
helpers in ``_shared``.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.commands.refuel._group import refuel
from maverick.cli.commands.refuel._shared import (
    print_steps_and_exit,
    refuel_flight_plan_options,
    run_refuel_workflow,
)
from maverick.cli.context import async_command


@refuel.command("flight-plan")
@refuel_flight_plan_options
@click.pass_context
@async_command
async def flight_plan_cmd(
    ctx: click.Context,
    flight_plan_path: Path,
    dry_run: bool,
    list_steps: bool,
    session_log: Path | None,
) -> None:
    """Decompose a Flight Plan into work units and beads.

    FLIGHT-PLAN-PATH is the path to the flight plan Markdown file.

    The workflow parses the flight plan, gathers codebase context for
    in-scope files, decomposes into ordered work units via an AI agent,
    writes work unit files, and creates beads for execution by
    ``maverick fly``.

    Examples:

        maverick refuel flight-plan .maverick/flight-plans/add-auth.md

        maverick refuel flight-plan .maverick/flight-plans/add-auth.md --dry-run

        maverick refuel flight-plan .maverick/flight-plans/add-auth.md --list-steps
    """
    if list_steps:
        print_steps_and_exit()

    await run_refuel_workflow(ctx, flight_plan_path, dry_run, session_log)
