"""CLI entry point for Maverick.

This module defines the Click-based command-line interface for Maverick.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import click
from dotenv import load_dotenv

from maverick.logging import configure_logging

# Load environment variables from .env file in current directory
# This must happen early, before any code reads environment variables
# Use explicit path and verbose mode to debug loading issues
_dotenv_path = Path.cwd() / ".env"
_dotenv_loaded = load_dotenv(dotenv_path=_dotenv_path, override=False)
if _dotenv_loaded:
    # Verify key variables are set
    _has_key = bool(
        os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    )
    if not _has_key:
        import sys

        print(
            f"Warning: .env loaded from {_dotenv_path} but no API key found",
            file=sys.stderr,
        )

from maverick import __version__  # noqa: E402
from maverick.cli.commands.config import config  # noqa: E402
from maverick.cli.commands.fly import fly  # noqa: E402
from maverick.cli.commands.init import init  # noqa: E402
from maverick.cli.commands.refuel import refuel  # noqa: E402
from maverick.cli.commands.review import review  # noqa: E402
from maverick.cli.commands.status import status  # noqa: E402
from maverick.cli.commands.uninstall import uninstall  # noqa: E402
from maverick.cli.commands.workflow import workflow  # noqa: E402
from maverick.cli.context import CLIContext, ExitCode  # noqa: E402
from maverick.cli.output import format_error  # noqa: E402
from maverick.cli.validators import check_dependencies  # noqa: E402
from maverick.config import load_config  # noqa: E402
from maverick.exceptions import ConfigError  # noqa: E402


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="maverick")
@click.option(
    "-c",
    "--config",
    "config_file",
    type=click.Path(exists=False, path_type=str),
    default=None,
    help="Path to config file (overrides project/user config).",
)
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Increase verbosity (-v for INFO, -vv for DEBUG, -vvv for DEBUG+trace).",
)
@click.option(
    "-q",
    "--quiet",
    is_flag=True,
    default=False,
    help="Suppress non-essential output (ERROR level only).",
)
@click.option(
    "--no-tui",
    is_flag=True,
    default=False,
    help="Disable TUI mode (headless operation).",
)
@click.pass_context
def cli(
    ctx: click.Context,
    config_file: str | None,
    verbose: int,
    quiet: bool,
    no_tui: bool,
) -> None:
    """Maverick - AI-powered development workflow orchestration."""
    # Ensure ctx.obj exists for subcommands
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet
    ctx.obj["no_tui"] = no_tui

    # Load configuration first (before logging setup)
    try:
        # If --config specified, load from that path
        config_path = Path(config_file) if config_file else None
        config = load_config(config_path)
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

    # Create CLIContext and store in Click context
    cli_ctx = CLIContext(
        config=config,
        config_path=Path(config_file) if config_file else None,
        verbosity=verbose,
        quiet=quiet,
        no_tui=no_tui,
    )
    ctx.obj["cli_ctx"] = cli_ctx

    # Determine logging level with precedence rules
    # Priority: quiet > verbose > config
    verbosity_map = {
        "error": logging.ERROR,
        "warning": logging.WARNING,
        "info": logging.INFO,
        "debug": logging.DEBUG,
    }

    if quiet:
        # Quiet takes precedence - ERROR level only (40)
        level = logging.ERROR
    elif verbose > 0:
        # CLI verbose flag takes precedence over config
        # 0: WARNING (30) - default
        # 1 (-v): INFO (20)
        # 2+ (-vv, -vvv): DEBUG (10)
        level = logging.INFO if verbose == 1 else logging.DEBUG
    else:
        # Use config file setting
        level = verbosity_map.get(config.verbosity, logging.WARNING)

    configure_logging(level=level)

    # FR-013: Validate required dependencies at startup
    # Only validate when a command is being invoked (not for --help/--version)
    if ctx.invoked_subcommand is not None:
        # Define which commands need which dependencies
        commands_needing_git_gh = {"fly", "review", "status"}

        if ctx.invoked_subcommand in commands_needing_git_gh:
            # Check for git and gh CLI tools
            dep_statuses = check_dependencies(["git", "gh"])

            # Report any missing dependencies
            missing_deps = [dep for dep in dep_statuses if not dep.available]
            if missing_deps:
                for dep in missing_deps:
                    suggestion = (
                        f"Install from {dep.install_url}" if dep.install_url else None
                    )
                    error_msg = format_error(
                        dep.error or f"{dep.name} is not available",
                        suggestion=suggestion,
                    )
                    click.echo(error_msg, err=True)
                ctx.exit(ExitCode.FAILURE)

            # Require maverick.yaml for workflow commands
            project_config_path = (
                Path(config_file) if config_file else Path.cwd() / "maverick.yaml"
            )
            if not project_config_path.exists():
                error_msg = format_error(
                    f"Project configuration not found: {project_config_path}",
                    suggestion="Run 'maverick init' to create maverick.yaml",
                )
                click.echo(error_msg, err=True)
                ctx.exit(ExitCode.FAILURE)

    # If no command is given, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# Register commands
cli.add_command(fly)
cli.add_command(review)
cli.add_command(config)
cli.add_command(workflow)
cli.add_command(status)
cli.add_command(init)
cli.add_command(refuel)
cli.add_command(uninstall)

if __name__ == "__main__":
    cli()
