from __future__ import annotations

import logging
from pathlib import Path

import click

from maverick.cli.context import CLIContext, ExitCode
from maverick.cli.output import format_error
from maverick.config import load_config
from maverick.exceptions import ConfigError


@click.group()
def config() -> None:
    """Manage Maverick configuration."""
    pass


@config.command("init")
@click.option("--force", is_flag=True, help="Overwrite existing config file.")
@click.pass_context
def config_init(ctx: click.Context, force: bool) -> None:
    """Initialize a new configuration file.

    Creates a default maverick.yaml configuration file in the current directory.

    Examples:
        maverick config init
        maverick config init --force
    """
    import yaml

    logger = logging.getLogger(__name__)
    config_file = Path.cwd() / "maverick.yaml"

    # Check if file exists and --force not specified
    if config_file.exists() and not force:
        error_msg = format_error(
            f"Config file already exists: {config_file}",
            suggestion="Use --force to overwrite existing file",
        )
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE)

    # Create default config template
    default_config = {
        "github": {
            "owner": None,
            "repo": None,
            "default_branch": "main",
        },
        "notifications": {
            "enabled": False,
            "server": "https://ntfy.sh",
            "topic": None,
        },
        "validation": {
            "format_cmd": ["ruff", "format", "."],
            "lint_cmd": ["ruff", "check", "--fix", "."],
            "typecheck_cmd": ["mypy", "."],
            "test_cmd": ["pytest", "-x", "--tb=short"],
            "timeout_seconds": 300,
            "max_errors": 50,
        },
        "model": {
            "model_id": "claude-sonnet-4-20250514",
            "max_tokens": 8192,
            "temperature": 0.0,
        },
        "parallel": {
            "max_agents": 3,
            "max_tasks": 5,
        },
        "verbosity": "warning",
    }

    try:
        # Write config file
        yaml_content = yaml.dump(
            default_config, default_flow_style=False, sort_keys=False
        )
        config_file.write_text(yaml_content, encoding="utf-8")

        logger.info(f"Config file created: {config_file}")
        click.echo(f"Configuration file created: {config_file}")

    except Exception as e:
        error_msg = format_error(f"Failed to create config file: {e}")
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e


@config.command("show")
@click.option(
    "-f",
    "--format",
    "fmt",
    type=click.Choice(["yaml", "json"]),
    default="yaml",
    help="Output format (yaml or json).",
)
@click.pass_context
def config_show(ctx: click.Context, fmt: str) -> None:
    """Display current configuration.

    Shows the merged configuration from all sources (defaults, user config,
    project config, environment variables).

    Examples:
        maverick config show
        maverick config show --format json
    """
    import yaml

    from maverick.cli.output import format_json

    cli_ctx: CLIContext = ctx.obj["cli_ctx"]
    config = cli_ctx.config

    # Convert config to dict for output
    config_dict = config.model_dump(mode="python")

    if fmt == "json":
        # Output as JSON
        click.echo(format_json(config_dict))
    else:
        # Output as YAML
        yaml_output = yaml.dump(config_dict, default_flow_style=False, sort_keys=False)
        click.echo(yaml_output)


@config.command("edit")
@click.option(
    "--user",
    is_flag=True,
    help="Edit user config (~/.config/maverick/config.yaml).",
)
@click.option(
    "--project",
    is_flag=True,
    default=True,
    help="Edit project config (./maverick.yaml).",
)
@click.pass_context
def config_edit(ctx: click.Context, user: bool, project: bool) -> None:
    """Open configuration file in default editor.

    Opens the specified config file in $EDITOR or the default system editor.

    Examples:
        maverick config edit
        maverick config edit --user
    """
    logger = logging.getLogger(__name__)

    # Determine which config to edit
    if user:
        from maverick.config import get_user_config_path

        config_file = get_user_config_path()
        # Ensure user config directory exists
        config_file.parent.mkdir(parents=True, exist_ok=True)
    else:
        config_file = Path.cwd() / "maverick.yaml"

    # Read existing content if file exists
    content = config_file.read_text(encoding="utf-8") if config_file.exists() else ""

    try:
        # Open editor
        result = click.edit(content)

        # If result is None, user cancelled
        if result is None:
            logger.info("Edit cancelled by user")
            click.echo("Edit cancelled.")
            return

        # Write back if changed
        if result != content:
            config_file.write_text(result, encoding="utf-8")
            logger.info(f"Config file updated: {config_file}")
            click.echo(f"Configuration file updated: {config_file}")
        else:
            click.echo("No changes made.")

    except Exception as e:
        error_msg = format_error(f"Failed to edit config file: {e}")
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e


@config.command("validate")
@click.option(
    "-f",
    "--file",
    "config_file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Config file to validate (auto-detect if not specified).",
)
@click.pass_context
def config_validate(ctx: click.Context, config_file: Path | None) -> None:
    """Validate configuration file.

    Checks configuration file for syntax errors and validation issues.

    Examples:
        maverick config validate
        maverick config validate --file custom.yaml
    """
    logger = logging.getLogger(__name__)

    try:
        # Load and validate config
        load_config(config_file)

        # If we get here, validation succeeded
        logger.info("Configuration is valid")
        click.echo("Configuration is valid.")

    except ConfigError as e:
        # Validation failed
        error_parts = [f"Error: Invalid configuration - {e.message}"]
        if e.field:
            error_parts.append(f"  Field: {e.field}")
        if e.value is not None:
            error_parts.append(f"  Value: {e.value}")
        error_msg = "\n".join(error_parts)
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e

    except Exception as e:
        error_msg = format_error(f"Error validating config: {e}")
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e
