"""Workflow search subcommand.

Provides case-insensitive substring search across workflow names
and descriptions.
"""

from __future__ import annotations

import click

from maverick.cli.common import get_discovery_result
from maverick.cli.context import ExitCode
from maverick.cli.output import format_error, format_json, format_table
from maverick.logging import get_logger

from ._group import workflow


@workflow.command("search")
@click.argument("query")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format.",
)
@click.pass_context
def workflow_search(ctx: click.Context, query: str, fmt: str) -> None:
    """Search workflows by name or description.

    QUERY is the search string (case-insensitive substring match).

    Examples:
        maverick workflow search validate
        maverick workflow search "code review"
        maverick workflow search fix --format json
    """
    logger = get_logger(__name__)

    try:
        # Run discovery
        discovery_result = get_discovery_result(ctx)

        # Search workflows
        matches = discovery_result.search_workflows(query)

        if not matches:
            click.echo(f"No workflows found matching '{query}'")
            raise SystemExit(ExitCode.SUCCESS)

        # Build output data
        workflows = []
        for dw in matches:
            wf = dw.workflow
            workflows.append(
                {
                    "name": wf.name,
                    "description": wf.description or "(no description)",
                    "version": wf.version,
                    "source": dw.source,
                    "file": str(dw.file_path),
                }
            )

        # Format output
        if fmt == "json":
            click.echo(format_json(workflows))
        else:
            # Table format
            headers = ["Name", "Version", "Source", "Description"]
            rows = [
                [
                    str(wf["name"]),
                    str(wf["version"]),
                    str(wf["source"]),
                    str(wf["description"])[:50],
                ]
                for wf in workflows
            ]
            click.echo(format_table(headers, rows))

            # Show summary
            click.echo()
            click.echo(f"Found {len(matches)} workflow(s) matching '{query}'")

    except SystemExit:
        raise
    except Exception as e:
        logger.exception("Unexpected error in workflow search command")
        error_msg = format_error(f"Failed to search workflows: {e}")
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e
