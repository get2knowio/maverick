"""``maverick fly run`` command.

Runs arbitrary DSL workflows by name or file path — equivalent to the
original ``maverick fly <name>`` before the group restructure.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.commands.fly._group import fly
from maverick.cli.commands.workflow import _execute_workflow_run
from maverick.cli.context import async_command


@fly.command("run")
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
@click.option(
    "--session-log",
    type=click.Path(path_type=Path),
    default=None,
    help="Write session journal (JSONL) to this file path.",
)
@click.pass_context
@async_command
async def run(
    ctx: click.Context,
    name_or_file: str,
    inputs: tuple[str, ...],
    input_file: Path | None,
    dry_run: bool,
    restart: bool,
    no_validate: bool,
    list_steps: bool,
    only_step: str | None,
    session_log: Path | None,
) -> None:
    """Run a DSL workflow by name or file path.

    NAME_OR_FILE can be:
    - A workflow name from the library (e.g., "feature", "cleanup")
    - A path to a workflow file (e.g., "./my-workflow.yaml")

    Examples:
        maverick fly run feature -i branch_name=001-foo -i skip_review=true
        maverick fly run ./custom-workflow.yaml -i branch=main
    """
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
        session_log_path=session_log,
    )
