"""Runway CLI group definition.

Defines the top-level ``maverick runway`` Click group for
inspecting and managing the runway knowledge store.
"""

from __future__ import annotations

import click


@click.group(invoke_without_command=True)
@click.pass_context
def runway(ctx: click.Context) -> None:
    """Manage the runway knowledge store."""
    ctx.ensure_object(dict)
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
