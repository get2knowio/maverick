"""Workflow CLI group definition.

Defines the top-level ``maverick workflow`` Click group with shared options.
"""

from __future__ import annotations

from pathlib import Path

import click


@click.group()
@click.option(
    "--registry",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to custom registry file.",
)
@click.option(
    "--lenient/--no-lenient",
    default=False,
    help="Lenient mode for unknown references.",
)
@click.pass_context
def workflow(
    ctx: click.Context,
    registry: Path | None,
    lenient: bool,
) -> None:
    """Manage DSL workflows."""
    # Store workflow-specific options in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["workflow_registry"] = registry
    ctx.obj["workflow_lenient"] = lenient
