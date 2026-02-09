"""Fly CLI group definition.

Defines the top-level ``maverick fly`` Click group for executing
DSL workflows and bead-driven development.
"""

from __future__ import annotations

import click


@click.group(invoke_without_command=True)
@click.pass_context
def fly(ctx: click.Context) -> None:
    """Execute DSL workflows.

    Subcommands:
        run    Run a workflow by name or file path
        beads  Run a bead-driven development workflow

    Examples:
        # Build a feature from spec
        maverick fly run feature -i branch_name=001-foo -i skip_review=true

        # Run bead-driven workflow
        maverick fly beads --epic my-epic --branch 001-feature

        # Run from a custom workflow file
        maverick fly run ./custom-workflow.yaml -i branch=main
    """
    ctx.ensure_object(dict)
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
