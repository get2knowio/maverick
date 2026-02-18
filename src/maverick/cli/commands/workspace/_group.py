"""Workspace CLI group definition.

Defines the top-level ``maverick workspace`` Click group for
inspecting and managing hidden jj workspaces.
"""

from __future__ import annotations

import click


@click.group(invoke_without_command=True)
@click.pass_context
def workspace(ctx: click.Context) -> None:
    """Manage hidden jj workspaces."""
    ctx.ensure_object(dict)
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
