"""Execute DSL workflows with clean syntax.

This module provides 'maverick fly' as the primary way to execute workflows,
making it easy to run workflows from the library or custom workflow files.
"""

from __future__ import annotations

from pathlib import Path

import click

# Import the helper function (not the command)
from maverick.cli.commands.workflow import _execute_workflow_run
from maverick.cli.context import async_command


# Create 'fly' as a standalone command (not a group)
# This makes 'maverick fly <workflow>' work directly
@click.command("fly", context_settings={"ignore_unknown_options": True})
@click.argument("name_or_file")
@click.option(
    "-i",
    "--input",
    "inputs",
    multiple=True,
    help="Workflow input (key=value pairs). Can be specified multiple times.",
)
@click.option(
    "--input-file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Load inputs from JSON/YAML file.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Preview workflow steps without executing.",
)
@click.option(
    "--restart",
    is_flag=True,
    default=False,
    help="Ignore existing checkpoint and restart workflow from the beginning.",
)
@click.option(
    "--no-validate",
    is_flag=True,
    default=False,
    help="Skip semantic validation before execution (not recommended).",
)
@click.option(
    "--list-steps",
    is_flag=True,
    default=False,
    help="List workflow steps and exit without executing.",
)
@click.option(
    "--step",
    "only_step",
    default=None,
    help="Run only specified step (name or number). Use --list-steps to see options.",
)
@click.pass_context
@async_command
async def fly(
    ctx: click.Context,
    name_or_file: str,
    inputs: tuple[str, ...],
    input_file: Path | None,
    dry_run: bool,
    restart: bool,
    no_validate: bool,
    list_steps: bool,
    only_step: str | None,
) -> None:
    """Execute a DSL workflow.

    This command dynamically loads and executes workflows from the library
    or from a file path. Workflows orchestrate complex development tasks
    like feature implementation, tech-debt cleanup, and more.

    NAME_OR_FILE can be:
    - A workflow name from the library (e.g., "feature", "cleanup")
    - A path to a workflow file (e.g., "./my-workflow.yaml")

    By default, workflows resume from the last checkpoint if one exists.
    Use --restart to ignore checkpoints and start fresh.

    By default, workflows are validated before execution. Use --no-validate
    to skip semantic validation (not recommended).

    Examples:
        # Build a feature from spec
        maverick fly feature -i branch_name=001-foo -i skip_review=true

        # Fix tech-debt issues
        maverick fly cleanup -i label=tech-debt -i limit=10

        # Run from a custom workflow file
        maverick fly ./custom-workflow.yaml -i branch=main

        # Use input file
        maverick fly feature --input-file inputs.json

        # Preview without executing
        maverick fly feature -i branch_name=001-foo --dry-run

        # Restart from the beginning (ignore checkpoint)
        maverick fly feature --restart

        # Skip validation (not recommended)
        maverick fly feature --no-validate

        # List workflow steps
        maverick fly feature --list-steps

        # Run only a specific step (skips earlier steps)
        maverick fly feature -i branch_name=001-foo --step init
        maverick fly feature -i branch_name=001-foo --step 3
    """
    # Delegate to shared helper function
    await _execute_workflow_run(
        ctx,
        name_or_file,
        inputs,
        input_file,
        dry_run,
        restart,
        no_validate,
        list_steps,
        only_step,
    )
