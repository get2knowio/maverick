"""Workflow info subcommand.

Displays detailed information about a workflow including all discovered
versions and override chains.
"""

from __future__ import annotations

import click

from maverick.cli.common import get_discovery_result
from maverick.cli.context import ExitCode
from maverick.cli.output import format_error
from maverick.logging import get_logger

from ._group import workflow
from ._helpers import format_workflow_not_found_error, get_source_label


@workflow.command("info")
@click.argument("name")
@click.pass_context
def workflow_info(ctx: click.Context, name: str) -> None:
    """Display detailed workflow information including all versions.

    NAME is the workflow name to look up.

    Shows the active workflow (highest precedence) and any overridden versions.

    Examples:
        maverick workflow info fly
        maverick workflow info validate
    """
    logger = get_logger(__name__)

    try:
        # Run discovery
        discovery_result = get_discovery_result(ctx)

        # Get the active workflow
        discovered = discovery_result.get_workflow(name)

        if discovered is None:
            format_workflow_not_found_error(discovery_result, name)

        # Get all versions of the workflow
        all_versions = discovery_result.get_all_with_name(name)

        # Display active workflow (first in precedence order)
        wf = discovered.workflow

        click.echo(click.style(f"Workflow: {wf.name}", bold=True))
        click.echo(f"Version: {wf.version}")
        click.echo(f"Description: {wf.description or '(no description)'}")
        click.echo()

        # Display source information
        click.echo(click.style("Active Version:", bold=True))
        source_label = get_source_label(discovered.source)
        click.echo(f"  Source: {source_label}")
        click.echo(f"  File: {discovered.file_path}")
        click.echo()

        # Display all versions if there are overrides
        if len(all_versions) > 1:
            click.echo(click.style("All Versions:", bold=True))
            for i, (source, path) in enumerate(all_versions, 1):
                status = "ACTIVE" if i == 1 else "overridden"
                click.echo(f"  {i}. [{status}] {source}: {path}")
            click.echo()

        # Display inputs
        if wf.inputs:
            click.echo(click.style("Inputs:", bold=True))
            for input_name, input_def in wf.inputs.items():
                required_str = "required" if input_def.required else "optional"
                default_str = (
                    f", default: {input_def.default}"
                    if input_def.default is not None
                    else ""
                )
                desc_str = (
                    f" - {input_def.description}" if input_def.description else ""
                )
                click.echo(
                    f"  {input_name} ({input_def.type.value}, "
                    f"{required_str}{default_str}){desc_str}"
                )
            click.echo()

        # Display step summary
        click.echo(click.style(f"Steps ({len(wf.steps)}):", bold=True))
        for i, step in enumerate(wf.steps, 1):
            click.echo(f"  {i}. {step.name} ({step.type.value})")
            if step.when:
                click.echo(f"     when: {step.when}")

    except SystemExit:
        raise
    except Exception as e:
        logger.exception("Unexpected error in workflow info command")
        error_msg = format_error(f"Failed to show workflow info: {e}")
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e
