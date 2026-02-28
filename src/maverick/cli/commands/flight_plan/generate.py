"""``maverick flight-plan generate`` command.

Generates a structured flight plan from a PRD using an AI agent.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import click

from maverick.cli.commands.flight_plan._group import flight_plan
from maverick.cli.console import console
from maverick.cli.context import ExitCode, async_command

# Kebab-case validation (reuse same pattern as create.py)
_KEBAB_CASE_RE = re.compile(r"^[a-z]([a-z0-9-]*[a-z0-9])?$")

_DEFAULT_OUTPUT_DIR = ".maverick/flight-plans"


@flight_plan.command("generate")
@click.argument("name", metavar="NAME")
@click.option(
    "--from-prd",
    required=True,
    help="Path to PRD file, or '-' for STDIN.",
)
@click.option(
    "--interactive",
    is_flag=True,
    default=False,
    help="Agent asks clarifying questions before generating (coming soon).",
)
@click.option(
    "--output-dir",
    default=_DEFAULT_OUTPUT_DIR,
    show_default=True,
    help="Output directory for the flight plan file.",
)
@click.option(
    "--session-log",
    type=click.Path(path_type=Path),
    default=None,
    help="Write session journal (JSONL) to this file path.",
)
@click.pass_context
@async_command
async def generate(
    ctx: click.Context,
    name: str,
    from_prd: str,
    interactive: bool,
    output_dir: str,
    session_log: Path | None,
) -> None:
    """Generate a flight plan from a PRD using an AI agent.

    NAME must be a kebab-case identifier: lowercase letters, digits, and
    hyphens only, starting with a letter and not ending with a hyphen.

    The --from-prd option accepts a file path or '-' for STDIN.

    Examples:

        maverick flight-plan generate my-feature --from-prd spec.md

        cat spec.md | maverick flight-plan generate my-feature --from-prd -
    """
    from maverick.cli.workflow_executor import (
        PythonWorkflowRunConfig,
        execute_python_workflow,
    )
    from maverick.workflows.generate_flight_plan import GenerateFlightPlanWorkflow

    # Validate kebab-case name.
    if not _KEBAB_CASE_RE.match(name):
        console.print(
            f"[red]Error:[/red] Invalid flight plan name '[bold]{name}[/bold]'.\n"
            "Name must be kebab-case: lowercase letters, digits, and hyphens only,\n"
            "starting with a letter and not ending with a hyphen.",
        )
        raise SystemExit(ExitCode.FAILURE)

    # Interactive mode warning
    if interactive:
        console.print(
            "[yellow]Warning:[/yellow] --interactive mode is not yet implemented. "
            "Proceeding in non-interactive mode.",
        )

    # Read PRD content
    if from_prd == "-":
        prd_content = sys.stdin.read()
    else:
        prd_path = Path(from_prd)
        if not prd_path.exists():
            console.print(
                f"[red]Error:[/red] PRD file not found: '[bold]{from_prd}[/bold]'.",
            )
            raise SystemExit(ExitCode.FAILURE)
        prd_content = prd_path.read_text(encoding="utf-8")

    if not prd_content.strip():
        console.print("[red]Error:[/red] PRD content is empty.")
        raise SystemExit(ExitCode.FAILURE)

    output_path = Path(output_dir)

    # Guard: --output-dir must not point to an existing regular file.
    if output_path.exists() and not output_path.is_dir():
        console.print(
            f"[red]Error:[/red] '[bold]{output_dir}[/bold]' exists but"
            " is not a directory.",
        )
        raise SystemExit(ExitCode.FAILURE)

    target_file = output_path / f"{name}.md"

    # Overwrite guard: refuse if file already exists.
    if target_file.exists():
        console.print(
            f"[red]Error:[/red] Flight plan '[bold]{name}[/bold]' already exists at "
            f"[dim]{target_file}[/dim].\n"
            "Delete the file or choose a different name to proceed.",
        )
        raise SystemExit(ExitCode.FAILURE)

    # Execute the workflow
    await execute_python_workflow(
        ctx,
        PythonWorkflowRunConfig(
            workflow_class=GenerateFlightPlanWorkflow,
            inputs={
                "prd_content": prd_content,
                "name": name,
                "output_dir": output_dir,
            },
            session_log_path=session_log,
        ),
    )
