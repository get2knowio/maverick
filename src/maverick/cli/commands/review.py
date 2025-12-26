from __future__ import annotations

from pathlib import Path

import click

from maverick.agents.code_reviewer import CodeReviewerAgent
from maverick.cli.common import cli_error_handler
from maverick.cli.context import CLIContext, ExitCode, async_command
from maverick.cli.helpers import (
    format_review_markdown,
    format_review_text,
    validate_pr,
)
from maverick.cli.output import OutputFormat, format_json
from maverick.logging import get_logger
from maverick.models.review import ReviewContext


@click.command()
@click.argument("pr_number", type=int)
@click.option(
    "--fix/--no-fix",
    default=False,
    help="Automatically apply suggested fixes.",
)
@click.option(
    "-o",
    "--output",
    type=click.Choice(["tui", "json", "markdown", "text"]),
    default="tui",
    help="Output format.",
)
@click.pass_context
@async_command
async def review(
    ctx: click.Context,
    pr_number: int,
    fix: bool,
    output: str,
) -> None:
    """Review a pull request using AI-powered analysis.

    Analyzes a GitHub pull request for correctness, security, style, performance,
    and testability issues using the CodeReviewerAgent.

    Examples:
        maverick review 123
        maverick review 123 --fix
        maverick review 123 --output json
        maverick review 123 --output markdown
        maverick review 123 --output text
    """
    _cli_ctx: CLIContext = ctx.obj["cli_ctx"]  # Reserved for future use
    logger = get_logger(__name__)

    with cli_error_handler():
        # T064: Validate PR exists using gh pr view
        logger.info(f"Validating PR #{pr_number}...")
        is_valid, error_msg, pr_data = validate_pr(pr_number)
        if not is_valid:
            click.echo(error_msg, err=True)
            raise SystemExit(ExitCode.FAILURE)

        # Extract branch info from pr_data
        branch = pr_data.get("headRefName", "HEAD") if pr_data else "HEAD"
        base_branch = pr_data.get("baseRefName", "main") if pr_data else "main"

        # T065: Create and execute CodeReviewerAgent
        logger.info(f"Starting code review for PR #{pr_number}...")

        agent = CodeReviewerAgent()

        # Create ReviewContext for the review
        context = ReviewContext(
            branch=branch,
            base_branch=base_branch,
            cwd=Path.cwd(),
        )

        # Execute the review
        result = await agent.execute(context)

        # T066-T067: Format output based on --output option
        output_format = OutputFormat(output)

        if output_format == OutputFormat.JSON:
            click.echo(format_json(result.model_dump()))
        elif output_format == OutputFormat.MARKDOWN:
            click.echo(format_review_markdown(result, pr_number))
        else:
            click.echo(format_review_text(result))

        if result.success:
            raise SystemExit(ExitCode.SUCCESS)
        else:
            raise SystemExit(ExitCode.FAILURE)
