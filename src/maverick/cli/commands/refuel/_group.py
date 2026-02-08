"""Refuel CLI group definition.

Defines the top-level ``maverick refuel`` Click group for loading
work into beads from various sources.
"""

from __future__ import annotations

import click


@click.group()
@click.pass_context
def refuel(ctx: click.Context) -> None:
    """Load work into beads from various sources."""
    ctx.ensure_object(dict)
