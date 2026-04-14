"""Maverick uninstall command.

Removes Maverick-installed skills and optionally the project configuration.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import click

from maverick.cli.console import console, err_console
from maverick.logging import get_logger

logger = get_logger(__name__)


@click.command("uninstall")
@click.option(
    "--config",
    is_flag=True,
    help="Also remove maverick.yaml from the current directory",
)
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
    config: bool,
    dry_run: bool,
    force: bool,
    verbose: bool,
) -> None:
    """Remove Maverick-installed skills and optionally the configuration file.

    By default, removes all maverick-* skills from ~/.claude/skills/.
    Use --config to also remove maverick.yaml from the current directory.

    Examples:
        maverick uninstall                    # Remove skills only
        maverick uninstall --config           # Remove skills and config
        maverick uninstall --dry-run          # Preview what would be removed
        maverick uninstall --config --force   # Skip confirmation
    """
    _run_cleanup(
        remove_config=config,
        dry_run=dry_run,
        force=force,
        verbose=verbose,
    )


def _run_cleanup(
    remove_config: bool,
    dry_run: bool,
    force: bool,
    verbose: bool,
) -> None:
    """Execute cleanup operations.

    Args:
        remove_config: Whether to remove maverick.yaml.
        dry_run: If True, only show what would be removed.
        force: If True, skip confirmation prompts.
        verbose: If True, show detailed output.
    """
    # Determine what will be removed
    user_skills_dir = Path.home() / ".claude" / "skills"
    maverick_skills: list[Path] = []

    if user_skills_dir.exists():
        # Find all maverick-* skill directories
        for skill_dir in user_skills_dir.iterdir():
            if skill_dir.is_dir() and skill_dir.name.startswith("maverick-"):
                maverick_skills.append(skill_dir)

    config_path = Path.cwd() / "maverick.yaml"
    config_exists = config_path.exists()

    # Check if there's anything to remove
    if not maverick_skills and not (remove_config and config_exists):
        console.print("Nothing to remove.")
        if verbose:
            logger.info(
                "cleanup_nothing_to_do",
                skills_dir=str(user_skills_dir),
                config_path=str(config_path),
            )
        return

    # Show what will be removed
    if dry_run or not force:
        console.print("[bold]The following will be removed:[/]")
        console.print()

        if maverick_skills:
            console.print(f"Skills from [dim]{user_skills_dir}[/]:")
            for skill_dir in sorted(maverick_skills):
                console.print(f"  - {skill_dir.name}")
            console.print()

        if remove_config and config_exists:
            console.print("Configuration file:")
            console.print(f"  - [dim]{config_path}[/]")
            console.print()

    # Dry run: exit early
    if dry_run:
        console.print("[dim]\\[DRY RUN] No files were removed.[/]")
        return

    # Confirm if not forced
    if not force and not click.confirm("Do you want to proceed?"):
        console.print("Cleanup canceled.")
        return

    # Remove skills
    skills_removed = 0
    for skill_dir in maverick_skills:
        try:
            shutil.rmtree(skill_dir)
            skills_removed += 1
            if verbose:
                logger.info("skill_removed", skill=skill_dir.name)
        except Exception as e:
            logger.warning(
                "skill_removal_failed",
                skill=skill_dir.name,
                error=str(e),
            )
            err_console.print(
                f"[yellow]Warning:[/yellow] Failed to remove {skill_dir.name}: {e}",
            )

    # Remove config if requested
    config_removed = False
    if remove_config and config_exists:
        try:
            config_path.unlink()
            config_removed = True
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

    # Summary
    console.print()
    console.print("[bold]Cleanup complete:[/]")
    if skills_removed > 0:
        console.print(f"  [green]✓[/] Removed {skills_removed} skill(s)")
    if config_removed:
        console.print("  [green]✓[/] Removed configuration file")

    if verbose:
        logger.info(
            "cleanup_complete",
            skills_removed=skills_removed,
            config_removed=config_removed,
        )
