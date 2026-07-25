"""Maverick uninstall command.

Removes the project's ``maverick.yaml`` configuration file and the
packaged ``maverick-review`` Claude Code skill installed by
``maverick init`` (053-assumption-review-console) at
``.claude/skills/maverick-review/SKILL.md``.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.console import console, err_console
from maverick.logging import get_logger
from maverick.skills import REVIEW_SKILL_RELATIVE_PATH

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
    """Remove ``maverick.yaml`` and the maverick-review skill.

    Examples:
        maverick uninstall              # Remove maverick.yaml + skill
        maverick uninstall --dry-run    # Preview what would be removed
        maverick uninstall --force      # Skip confirmation
    """
    config_path = Path.cwd() / "maverick.yaml"
    skill_path = Path.cwd() / REVIEW_SKILL_RELATIVE_PATH
    config_exists = config_path.exists()
    skill_exists = skill_path.exists()

    if not config_exists and not skill_exists:
        console.print("Nothing to remove.")
        if verbose:
            logger.info(
                "cleanup_nothing_to_do",
                config_path=str(config_path),
                skill_path=str(skill_path),
            )
        return

    if dry_run or not force:
        console.print("[bold]The following will be removed:[/]")
        console.print()
        if config_exists:
            console.print("Configuration file:")
            # `soft_wrap` keeps the path on one line: Rich otherwise wraps at
            # the terminal width, splitting a long path mid-segment so it
            # can't be copied out of the terminal.
            console.print(f"  - [dim]{config_path}[/]", soft_wrap=True)
            console.print()
        if skill_exists:
            console.print("Review-console skill:")
            console.print(f"  - [dim]{skill_path}[/]", soft_wrap=True)
            console.print()

    if dry_run:
        console.print("[dim]\\[DRY RUN] No files were removed.[/]")
        return

    if not force and not click.confirm("Do you want to proceed?"):
        console.print("Cleanup canceled.")
        return

    removed_config = False
    if config_exists:
        try:
            config_path.unlink()
            removed_config = True
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

    removed_skill = False
    if skill_exists:
        removed_skill = _remove_review_skill(skill_path, verbose)

    if not removed_config and not removed_skill:
        return

    console.print()
    console.print("[bold]Cleanup complete:[/]")
    if removed_config:
        console.print("  [green]check[/] Removed configuration file")
    if removed_skill:
        console.print("  [green]check[/] Removed maverick-review skill")


def _remove_review_skill(skill_path: Path, verbose: bool) -> bool:
    """Remove the packaged skill file and prune now-empty parent dirs.

    Removes ``<project>/.claude/skills/maverick-review/`` entirely (it's
    Maverick-owned — nothing else lives there), then removes
    ``.claude/skills/`` too, but only if it's empty afterward (a user may
    have other, unrelated skills installed there). ``.claude/`` itself is
    never removed.

    Returns:
        ``True`` on success, ``False`` on a (logged) failure.
    """
    import shutil

    skill_dir = skill_path.parent  # .claude/skills/maverick-review/
    skills_dir = skill_dir.parent  # .claude/skills/

    try:
        shutil.rmtree(skill_dir)
    except Exception as e:
        logger.warning(
            "skill_removal_failed",
            path=str(skill_path),
            error=str(e),
        )
        err_console.print(
            f"[yellow]Warning:[/yellow] Failed to remove {skill_path}: {e}",
        )
        return False

    if verbose:
        logger.info("skill_removed", path=str(skill_path))

    try:
        if skills_dir.is_dir() and not any(skills_dir.iterdir()):
            skills_dir.rmdir()
            if verbose:
                logger.info("skills_dir_removed", path=str(skills_dir))
    except OSError as e:
        # Best-effort — leaving an empty skills/ dir behind is harmless.
        logger.debug(
            "skills_dir_removal_skipped",
            path=str(skills_dir),
            error=str(e),
        )

    return True
