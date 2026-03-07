"""Flight Plan CLI group definition.

Defines the top-level ``maverick plan`` Click group for
creating and validating flight plan files.
"""

from __future__ import annotations

import re

import click

# Kebab-case validation: must start with a lowercase letter, then allow
# lowercase letters, digits, and hyphens, ending with a letter or digit.
KEBAB_CASE_RE = re.compile(r"^[a-z]([a-z0-9-]*[a-z0-9])?$")

DEFAULT_PLANS_DIR = ".maverick/plans"


@click.group("plan", invoke_without_command=True)
@click.pass_context
def flight_plan(ctx: click.Context) -> None:
    """Create and validate flight plan files."""
    ctx.ensure_object(dict)
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
