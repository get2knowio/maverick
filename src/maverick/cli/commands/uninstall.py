"""Maverick uninstall command.

Removes the project's ``maverick.yaml`` configuration file. The legacy
``~/.claude/skills/maverick-*`` cleanup was retired with the OpenCode
substrate migration — those skills were never installed by ``maverick
init`` so there is nothing to clean up there.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.console import console, err_console
from maverick.logging import get_logger

logger = get_logger(__name__)


@click.command("uninstall")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be removed without actually removing",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Skip confirmation prompts",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed output",
)
def uninstall(
    dry_run: bool,
    force: bool,
    verbose: bool,
) -> None:
    """Remove ``maverick.yaml`` from the current directory.

    Examples:
        maverick uninstall              # Remove maverick.yaml
        maverick uninstall --dry-run    # Preview what would be removed
        maverick uninstall --force      # Skip confirmation
    """
    config_path = Path.cwd() / "maverick.yaml"
    config_exists = config_path.exists()

    if not config_exists:
        console.print("Nothing to remove.")
        if verbose:
            logger.info("cleanup_nothing_to_do", config_path=str(config_path))
        return

    if dry_run or not force:
        console.print("[bold]The following will be removed:[/]")
        console.print()
        console.print("Configuration file:")
        console.print(f"  - [dim]{config_path}[/]")
        console.print()

    if dry_run:
        console.print("[dim]\\[DRY RUN] No files were removed.[/]")
        return

    if not force and not click.confirm("Do you want to proceed?"):
        console.print("Cleanup canceled.")
        return

    try:
        config_path.unlink()
        if verbose:
            logger.info("config_removed", path=str(config_path))
    except Exception as e:
        logger.warning(
            "config_removal_failed",
            path=str(config_path),
            error=str(e),
        )
        err_console.print(
            f"[yellow]Warning:[/yellow] Failed to remove {config_path}: {e}",
        )
        return

    console.print()
    console.print("[bold]Cleanup complete:[/]")
    console.print("  [green]check[/] Removed configuration file")
