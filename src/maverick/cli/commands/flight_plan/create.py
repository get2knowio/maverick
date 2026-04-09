"""``maverick plan create`` command.

Creates a new flight plan skeleton Markdown file in the specified output
directory, validating the name and guarding against accidental overwrites.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import click

from maverick.cli.commands.flight_plan._group import (
    DEFAULT_PLANS_DIR,
    KEBAB_CASE_RE,
    flight_plan,
)
from maverick.cli.console import console
from maverick.cli.context import ExitCode


@flight_plan.command("create")
@click.argument("name", metavar="NAME")
@click.option(
    "--output-dir",
    "plans_dir",
    default=DEFAULT_PLANS_DIR,
    show_default=True,
    help="Base plans directory.",
)
def create(name: str, plans_dir: str) -> None:
    """Create a new flight plan from a template.

    NAME must be a kebab-case identifier: lowercase letters, digits, and
    hyphens only, starting with a letter and not ending with a hyphen.

    Examples:

        maverick plan create my-feature

        maverick plan create api-gateway --output-dir .maverick/plans
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

    plans_path = Path(plans_dir)

    # Guard: --output-dir must not point to an existing regular file.
    if plans_path.exists() and not plans_path.is_dir():
        console.print(
            f"[red]Error:[/red] '[bold]{plans_dir}[/bold]' exists but is not a directory.",
        )
        raise SystemExit(ExitCode.FAILURE)

    plan_dir = plans_path / name
    target_file = plan_dir / "flight-plan.md"

    # Overwrite guard: refuse if file already exists.
    if target_file.exists():
        console.print(
            f"[red]Error:[/red] Flight plan '[bold]{name}[/bold]' already exists at "
            f"[dim]{target_file}[/dim].\n"
            "Delete the file or choose a different name to proceed.",
        )
        raise SystemExit(ExitCode.FAILURE)

    # Auto-create plan directory (and parents) if it doesn't exist.
    try:
        plan_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        console.print(
            f"[red]Error:[/red] Permission denied creating directory '[bold]{plan_dir}[/bold]'.",
        )
        raise SystemExit(ExitCode.FAILURE) from None

    # Generate and write the skeleton.
    skeleton = generate_skeleton(name, date.today())
    try:
        target_file.write_text(skeleton, encoding="utf-8")
    except PermissionError:
        console.print(
            f"[red]Error:[/red] Permission denied writing to '[bold]{target_file}[/bold]'.",
        )
        raise SystemExit(ExitCode.FAILURE) from None

    console.print(
        f"[green]Created[/green] flight plan '[bold]{name}[/bold]' at [dim]{target_file}[/dim]",
    )
