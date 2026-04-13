"""``maverick runway seed`` command."""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.commands.runway._group import runway
from maverick.cli.console import console, err_console
from maverick.cli.context import ExitCode, async_command
from maverick.cli.output import format_bytes


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

    console.print("[bold cyan]Runway Seed[/]")
    console.print()

    # Show context gathering progress
    console.print("Gathering project context...")
    context = await gather_seed_context(project_path)

    commit_count = len(context.git_log)
    config_count = len(context.config_files)
    file_count = sum(context.file_type_counts.values())
    console.print(
        f"  {commit_count} commits, {config_count} config files, {file_count} source files"
    )
    console.print()

    if dry_run:
        console.print("[dim]Dry run — would analyze and generate semantic files.[/]")
        raise SystemExit(ExitCode.SUCCESS)

    # Run seed — pass pre-gathered context to avoid re-gathering
    console.print("Analyzing codebase via ACP provider...")
    result = await run_seed(
        project_path,
        provider=provider,
        force=force,
        context=context,
    )

    if not result.success:
        err_console.print(
            f"[yellow]Warning:[/yellow] Seed failed: {result.error}\n"
            "  Runway will build knowledge organically during fly cycles."
        )
        raise SystemExit(ExitCode.FAILURE)

    if not result.files_written:
        # Existing files, no --force
        console.print(f"  [dim]{result.error}[/]")
        console.print("  Use [bold]--force[/] to overwrite.")
        raise SystemExit(ExitCode.SUCCESS)

    # Show results
    console.print()
    console.print("Writing semantic files...")
    for filename in result.files_written:
        fpath = project_path / ".maverick" / "runway" / "semantic" / filename
        size = fpath.stat().st_size if fpath.exists() else 0
        console.print(f"  [green]✓[/] {filename} [dim]({format_bytes(size)})[/]")

    console.print()
    console.print(f"[green]✓[/] Runway seeded with {len(result.files_written)} semantic file(s).")
    raise SystemExit(ExitCode.SUCCESS)
