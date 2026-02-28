"""Flight Plan CLI group definition.

Defines the top-level ``maverick flight-plan`` Click group for
creating and validating flight plan files.
"""

from __future__ import annotations

import click


@click.group("flight-plan", invoke_without_command=True)
@click.pass_context
def flight_plan(ctx: click.Context) -> None:
    """Create and validate flight plan files."""
    ctx.ensure_object(dict)
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
