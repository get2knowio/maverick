"""CLI entry point for Maverick.

This module defines the Click-based command-line interface for Maverick.
"""

from __future__ import annotations

import logging

import click

from maverick import __version__
from maverick.config import load_config
from maverick.exceptions import ConfigError


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="maverick")
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Increase verbosity (-v for INFO, -vv for DEBUG).",
)
@click.pass_context
def cli(ctx: click.Context, verbose: int) -> None:
    """Maverick - AI-powered development workflow orchestration."""
    # Ensure ctx.obj exists for subcommands
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    # Load configuration first (before logging setup)
    try:
        config = load_config()
        ctx.obj["config"] = config
    except ConfigError as e:
        # Can't use logging yet, just output error
        error_parts = [f"Error: {e.message}"]
        if e.field:
            error_parts.append(f"  Field: {e.field}")
        if e.value is not None:
            error_parts.append(f"  Value: {e.value}")
        error_msg = "\n".join(error_parts)
        click.echo(error_msg, err=True)
        ctx.exit(1)

    # Determine verbosity: CLI flags override config
    verbosity_map = {"error": 40, "warning": 30, "info": 20, "debug": 10}
    if verbose > 0:
        # CLI flag takes precedence
        # 1 (-v): INFO (20)
        # 2+ (-vv): DEBUG (10)
        level = max(10, 30 - (verbose * 10))
    else:
        # Use config file setting
        level = verbosity_map.get(config.verbosity, 30)

    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        force=True,  # Reconfigure if already configured
    )

    # If no command is given, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


if __name__ == "__main__":
    cli()
