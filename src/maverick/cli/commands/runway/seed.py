"""``maverick runway seed`` command."""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.commands.runway._group import runway
from maverick.cli.console import console
from maverick.cli.context import ExitCode, async_command
from maverick.cli.output import format_bytes, format_success, format_warning


@runway.command()
@click.option(
    "--provider",
    type=str,
    default=None,
    help="ACP provider name to use for analysis.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite existing semantic files.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be generated without writing.",
)
@click.pass_context
@async_command
async def seed(
    ctx: click.Context,
    provider: str | None,
    force: bool,
    dry_run: bool,
) -> None:
    """Seed the runway with AI-generated codebase insights."""
    from maverick.runway.seed import gather_seed_context, run_seed

    project_path = Path.cwd().resolve()

    click.echo("Runway Seed")
    click.echo("===========")
    click.echo("")

    # Show context gathering progress
    click.echo("Gathering project context...")
    context = await gather_seed_context(project_path)

    commit_count = len(context.git_log)
    config_count = len(context.config_files)
    file_count = sum(context.file_type_counts.values())
    click.echo(f"  {commit_count} commits, {config_count} config files, {file_count} source files")
    click.echo("")

    if dry_run:
        click.echo("Dry run — would analyze and generate semantic files.")
        raise SystemExit(ExitCode.SUCCESS)

    # Run seed — pass pre-gathered context to avoid re-gathering
    click.echo("Analyzing codebase via ACP provider...")
    result = await run_seed(
        project_path,
        provider=provider,
        force=force,
        context=context,
    )

    if not result.success:
        console.print(
            format_warning(
                f"Seed failed: {result.error}\n"
                "  Runway will build knowledge organically during fly cycles."
            )
        )
        raise SystemExit(ExitCode.FAILURE)

    if not result.files_written:
        # Existing files, no --force
        click.echo(f"  {result.error}")
        click.echo("  Use --force to overwrite.")
        raise SystemExit(ExitCode.SUCCESS)

    # Show results
    click.echo("")
    click.echo("Writing semantic files...")
    for filename in result.files_written:
        # Read back to show size
        fpath = project_path / ".maverick" / "runway" / "semantic" / filename
        size = fpath.stat().st_size if fpath.exists() else 0
        click.echo(f"  ✓ {filename} ({format_bytes(size)})")

    click.echo("")
    console.print(
        format_success(f"Runway seeded with {len(result.files_written)} semantic file(s).")
    )
    raise SystemExit(ExitCode.SUCCESS)
