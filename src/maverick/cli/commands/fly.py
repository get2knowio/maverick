from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.common import cli_error_handler
from maverick.cli.context import ExitCode, async_command
from maverick.cli.helpers import detect_task_file, validate_branch
from maverick.logging import get_logger
from maverick.workflows.fly import FlyInputs, FlyWorkflow, FlyWorkflowCompleted


@click.command()
@click.argument("branch_name")
@click.option(
    "-t",
    "--task-file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to task file (auto-detect if not specified).",
)
@click.option(
    "--skip-review",
    is_flag=True,
    default=False,
    help="Skip code review stage.",
)
@click.option(
    "--skip-pr",
    is_flag=True,
    default=False,
    help="Skip PR creation stage.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show planned actions without executing.",
)
@click.pass_context
@async_command
async def fly(
    ctx: click.Context,
    branch_name: str,
    task_file: Path | None,
    skip_review: bool,
    skip_pr: bool,
    dry_run: bool,
) -> None:
    """Execute FlyWorkflow for a feature branch.

    Orchestrates the complete spec-based development workflow including setup,
    implementation, code review, validation, convention updates, and PR management.

    Examples:
        maverick fly feature-123
        maverick fly feature-123 --task-file ./tasks.md
        maverick fly feature-123 --skip-review --skip-pr
        maverick fly feature-123 --dry-run
    """
    logger = get_logger(__name__)

    with cli_error_handler():
        # T039: Validate branch exists
        logger.info(f"Validating branch '{branch_name}'...")
        is_valid, error_msg = validate_branch(branch_name)
        if not is_valid:
            click.echo(error_msg, err=True)
            raise SystemExit(ExitCode.FAILURE)

        # T040: Detect/validate task file
        if task_file is None:
            task_file = detect_task_file(branch_name)
            if task_file:
                logger.info(f"Auto-detected task file: {task_file}")

        # T042: If dry_run, just show planned actions
        if dry_run:
            click.echo(f"Dry run: Would execute FlyWorkflow for branch '{branch_name}'")
            click.echo(f"  Task file: {task_file or '(auto-detect)'}")
            click.echo(f"  Skip review: {skip_review}")
            click.echo(f"  Skip PR: {skip_pr}")
            click.echo("\nNo actions performed (dry run mode).")
            raise SystemExit(ExitCode.SUCCESS)

        # Create FlyInputs from CLI options
        inputs = FlyInputs(
            branch_name=branch_name,
            task_file=task_file,
            skip_review=skip_review,
            skip_pr=skip_pr,
        )

        # T041: Run workflow (TUI or headless based on cli_ctx.use_tui)
        logger.info(
            f"Starting fly workflow (branch={branch_name}, "
            f"task_file={task_file}, skip_review={skip_review}, skip_pr={skip_pr})"
        )

        workflow = FlyWorkflow()

        # Execute workflow and consume events
        result = None
        async for event in workflow.execute(inputs):
            if isinstance(event, FlyWorkflowCompleted):
                result = event.result
            # Optionally log progress events here

        # Show summary
        if result:
            click.echo(f"\n{result.summary}")
            if result.success:
                raise SystemExit(ExitCode.SUCCESS)
            else:
                raise SystemExit(ExitCode.FAILURE)
        else:
            click.echo("Workflow did not complete")
            raise SystemExit(ExitCode.FAILURE)
