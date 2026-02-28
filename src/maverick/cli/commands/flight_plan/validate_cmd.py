"""``maverick flight-plan validate`` command.

Validates a flight plan Markdown file against the structural rules V1–V9
and reports any issues found, exiting with a non-zero code when problems
are detected.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.commands.flight_plan._group import flight_plan
from maverick.cli.console import console
from maverick.cli.context import ExitCode


@flight_plan.command("validate")
@click.argument("file_path", metavar="FILE_PATH")
def validate(file_path: str) -> None:
    """Validate a flight plan file for structural issues.

    Checks structural rules V1–V9 and reports all issues found.  Exits with
    code 0 when the file is valid; exits with code 1 if any issues are found
    or the file does not exist.

    Examples:

        maverick flight-plan validate .maverick/flight-plans/my-feature.md
    """
    from maverick.flight.validator import validate_flight_plan_file

    path = Path(file_path)

    try:
        issues = validate_flight_plan_file(path)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] File not found: [bold]{file_path}[/bold]")
        raise SystemExit(ExitCode.FAILURE) from None

    if issues:
        console.print(
            f"[red]Validation failed[/red] — {len(issues)} issue(s) found in "
            f"[bold]{file_path}[/bold]:\n"
        )
        for issue in issues:
            console.print(f"  [yellow]{issue.location}[/yellow]: {issue.message}")
        raise SystemExit(ExitCode.FAILURE)

    console.print(
        f"[green]Valid[/green] — flight plan [bold]{file_path}[/bold] "
        "passed all checks."
    )
