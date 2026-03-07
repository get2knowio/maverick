"""``maverick flight-plan create`` command.

Creates a new flight plan skeleton Markdown file in the specified output
directory, validating the name and guarding against accidental overwrites.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import click

from maverick.cli.commands.flight_plan._group import (
    DEFAULT_OUTPUT_DIR,
    KEBAB_CASE_RE,
    flight_plan,
)
from maverick.cli.console import console
from maverick.cli.context import ExitCode


@flight_plan.command("create")
@click.argument("name", metavar="NAME")
@click.option(
    "--output-dir",
    default=DEFAULT_OUTPUT_DIR,
    show_default=True,
    help="Output directory for the flight plan file.",
)
def create(name: str, output_dir: str) -> None:
    """Create a new flight plan from a template.

    NAME must be a kebab-case identifier: lowercase letters, digits, and
    hyphens only, starting with a letter and not ending with a hyphen.

    Examples:

        maverick flight-plan create my-feature

        maverick flight-plan create api-gateway --output-dir plans/
    """
    from maverick.flight.template import generate_skeleton

    # Validate kebab-case name.
    if not KEBAB_CASE_RE.match(name):
        console.print(
            f"[red]Error:[/red] Invalid flight plan name '[bold]{name}[/bold]'.\n"
            "Name must be kebab-case: lowercase letters, digits, and hyphens only,\n"
            "starting with a letter and not ending with a hyphen.",
        )
        raise SystemExit(ExitCode.FAILURE)

    output_path = Path(output_dir)

    # Guard: --output-dir must not point to an existing regular file.
    if output_path.exists() and not output_path.is_dir():
        console.print(
            f"[red]Error:[/red] '[bold]{output_dir}[/bold]' exists but"
            " is not a directory.",
        )
        raise SystemExit(ExitCode.FAILURE)

    # Auto-create output directory (and parents) if it doesn't exist.
    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        console.print(
            f"[red]Error:[/red] Permission denied creating directory "
            f"'[bold]{output_dir}[/bold]'.",
        )
        raise SystemExit(ExitCode.FAILURE) from None

    target_file = output_path / f"{name}.md"

    # Overwrite guard: refuse if file already exists.
    if target_file.exists():
        console.print(
            f"[red]Error:[/red] Flight plan '[bold]{name}[/bold]' already exists at "
            f"[dim]{target_file}[/dim].\n"
            "Delete the file or choose a different name to proceed.",
        )
        raise SystemExit(ExitCode.FAILURE)

    # Generate and write the skeleton.
    skeleton = generate_skeleton(name, date.today())
    try:
        target_file.write_text(skeleton, encoding="utf-8")
    except PermissionError:
        console.print(
            f"[red]Error:[/red] Permission denied writing to "
            f"'[bold]{target_file}[/bold]'.",
        )
        raise SystemExit(ExitCode.FAILURE) from None

    console.print(
        f"[green]Created[/green] flight plan '[bold]{name}[/bold]' at "
        f"[dim]{target_file}[/dim]",
    )
