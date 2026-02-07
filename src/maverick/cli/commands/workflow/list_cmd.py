"""Workflow list subcommand.

Lists all discovered workflows with optional source filtering and
multiple output formats.
"""

from __future__ import annotations

import click

from maverick.cli.common import get_discovery_result
from maverick.cli.context import ExitCode
from maverick.cli.output import format_error, format_json, format_table
from maverick.logging import get_logger

from ._group import workflow


@workflow.command("list")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json", "yaml"]),
    default="table",
    help="Output format.",
)
@click.option(
    "--source",
    type=click.Choice(["all", "builtin", "user", "project"]),
    default="all",
    help="Filter by source location.",
)
@click.pass_context
def workflow_list(ctx: click.Context, fmt: str, source: str) -> None:
    """List all discovered workflows.

    Discovers workflows from builtin, user, and project locations with
    override precedence (project > user > builtin).

    Examples:
        maverick workflow list
        maverick workflow list --format json
        maverick workflow list --source builtin
    """
    import yaml

    logger = get_logger(__name__)

    try:
        # Run discovery (FR-014: call discover() when CLI initializes)
        discovery_result = get_discovery_result(ctx)

        # Filter workflows by source if specified
        if source == "all":
            discovered_workflows = discovery_result.workflows
        else:
            source_filter = source
            discovered_workflows = tuple(
                w for w in discovery_result.workflows if w.source == source_filter
            )

        if not discovered_workflows:
            if source != "all":
                click.echo(f"No workflows found from source '{source}'")
            else:
                click.echo("No workflows discovered")
            raise SystemExit(ExitCode.SUCCESS)

        # Build output data with source information
        workflows = []
        for dw in discovered_workflows:
            wf = dw.workflow
            workflows.append(
                {
                    "name": wf.name,
                    "description": wf.description or "(no description)",
                    "version": wf.version,
                    "source": dw.source,
                    "file": str(dw.file_path),
                    "overrides": [str(p) for p in dw.overrides] if dw.overrides else [],
                }
            )

        # Sort by name
        workflows.sort(key=lambda w: str(w["name"]))

        # Format output
        if fmt == "json":
            click.echo(format_json(workflows))
        elif fmt == "yaml":
            click.echo(yaml.dump(workflows, default_flow_style=False, sort_keys=False))
        else:
            # Table format with source column
            headers = ["Name", "Version", "Source", "Description"]
            rows = [
                [
                    str(wf["name"]),
                    str(wf["version"]),
                    str(wf["source"]),
                    str(wf["description"])[:40],
                ]
                for wf in workflows
            ]
            click.echo(format_table(headers, rows))

            # Show discovery stats
            click.echo()
            time_ms = discovery_result.discovery_time_ms
            click.echo(f"Discovered {len(workflows)} workflow(s) in {time_ms:.0f}ms")
            if discovery_result.skipped:
                skipped_count = len(discovery_result.skipped)
                click.echo(f"Skipped {skipped_count} file(s) with errors")

    except SystemExit:
        raise
    except Exception as e:
        logger.exception("Unexpected error in workflow list command")
        error_msg = format_error(f"Failed to list workflows: {e}")
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e
