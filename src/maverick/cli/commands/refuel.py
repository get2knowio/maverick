from __future__ import annotations

import click

from maverick.cli.common import cli_error_handler
from maverick.cli.context import ExitCode, async_command
from maverick.cli.validators import check_git_auth
from maverick.logging import get_logger
from maverick.workflows.refuel import (
    IssueProcessingCompleted,
    IssueProcessingStarted,
    RefuelCompleted,
    RefuelInputs,
    RefuelStarted,
    RefuelWorkflow,
)


@click.command()
@click.option(
    "-l",
    "--label",
    default="tech-debt",
    help="Issue label to filter by.",
)
@click.option(
    "-n",
    "--limit",
    default=5,
    type=click.IntRange(1, 100),
    help="Maximum issues to process (1-100).",
)
@click.option(
    "--parallel/--sequential",
    default=True,
    help="Processing mode (parallel or sequential).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="List matching issues without processing.",
)
@click.pass_context
@async_command
async def refuel(
    ctx: click.Context,
    label: str,
    limit: int,
    parallel: bool,
    dry_run: bool,
) -> None:
    """Execute RefuelWorkflow for tech debt resolution.

    Discovers GitHub issues by label and processes them using IssueFixerAgent.
    Creates branches, fixes issues, and generates pull requests.

    Examples:
        maverick refuel
        maverick refuel --label bug --limit 3
        maverick refuel --sequential
        maverick refuel --dry-run
    """
    logger = get_logger(__name__)

    with cli_error_handler():
        # T053: Check GitHub CLI authentication
        logger.info("Checking GitHub CLI authentication...")
        auth_status = check_git_auth()

        if not auth_status.available:
            error_msg = f"Error: {auth_status.error}"
            if auth_status.install_url:
                error_msg += f"\n\nSuggestion: Visit {auth_status.install_url}"
            click.echo(error_msg, err=True)
            raise SystemExit(ExitCode.FAILURE)

        # Create RefuelInputs from CLI options
        inputs = RefuelInputs(
            label=label,
            limit=limit,
            parallel=parallel,
            dry_run=dry_run,
        )

        # T054: Run workflow (TUI or headless based on cli_ctx.use_tui)
        logger.info(
            f"Starting refuel workflow (label={label}, limit={limit}, "
            f"parallel={parallel}, dry_run={dry_run})"
        )

        workflow = RefuelWorkflow()

        # T055: If dry_run, just list matching issues
        if dry_run:
            click.echo(f"Dry run: Finding issues with label '{label}'...")

        # Execute workflow and consume events
        async for event in workflow.execute(inputs):
            if isinstance(event, RefuelStarted):
                click.echo(f"Found {event.issues_found} issue(s) with label '{label}'")
                if dry_run and event.issues_found == 0:
                    click.echo("No issues found.")

            elif isinstance(event, IssueProcessingStarted):
                msg = (
                    f"[{event.index}/{event.total}] Processing issue "
                    f"#{event.issue.number}: {event.issue.title}"
                )
                click.echo(msg)

            elif isinstance(event, IssueProcessingCompleted):
                issue_result = event.result
                if issue_result.status.value == "fixed":
                    click.echo(f"  ✓ Fixed: {issue_result.pr_url}")
                elif issue_result.status.value == "failed":
                    click.echo(f"  ✗ Failed: {issue_result.error}")
                elif issue_result.status.value == "skipped":
                    click.echo("  ⊘ Skipped")

            elif isinstance(event, RefuelCompleted):
                refuel_result = event.result
                click.echo("\nSummary:")
                click.echo(f"  Total issues: {refuel_result.issues_found}")
                click.echo(f"  Fixed: {refuel_result.issues_fixed}")
                click.echo(f"  Failed: {refuel_result.issues_failed}")
                click.echo(f"  Skipped: {refuel_result.issues_skipped}")

                if refuel_result.total_cost_usd > 0:
                    click.echo(f"  Cost: ${refuel_result.total_cost_usd:.4f}")

                # Determine exit code
                # Success: no failures (dry-run or all skipped)
                if refuel_result.issues_failed == 0:
                    raise SystemExit(ExitCode.SUCCESS)
                # Partial: some fixed, some failed
                elif refuel_result.issues_failed > 0 and refuel_result.issues_fixed > 0:
                    raise SystemExit(ExitCode.PARTIAL)
                # Failure: only failures, no fixes
                else:
                    raise SystemExit(ExitCode.FAILURE)
