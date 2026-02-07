"""Workflow show subcommand.

Displays workflow metadata, inputs, and steps for a named workflow
or a workflow file path.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.common import get_discovery_result
from maverick.cli.context import ExitCode
from maverick.cli.output import format_error
from maverick.dsl.serialization.parser import parse_workflow
from maverick.logging import get_logger

from ._group import workflow
from ._helpers import format_workflow_not_found_error, get_source_label


@workflow.command("show")
@click.argument("name")
@click.pass_context
def workflow_show(ctx: click.Context, name: str) -> None:
    """Display workflow metadata, inputs, and steps.

    NAME can be either a workflow name (from discovery) or a file path.
    Shows source information and any overrides.

    Examples:
        maverick workflow show fly
        maverick workflow show my-workflow
        maverick workflow show ./workflows/my-workflow.yaml
    """
    logger = get_logger(__name__)

    try:
        # Determine if name is a file path or workflow name
        name_path = Path(name)
        discovered_workflow = None
        workflow_obj = None
        source_info = None
        file_path = None
        overrides: list[Path] = []

        if name_path.exists():
            # It's a file path - parse directly
            file_path = name_path
            content = file_path.read_text(encoding="utf-8")
            workflow_obj = parse_workflow(content, validate_only=True)
            source_info = "file"
        else:
            # Look up in discovery (FR-014: use DiscoveryResult for workflow show)
            discovery_result = get_discovery_result(ctx)
            discovered_workflow = discovery_result.get_workflow(name)

            if discovered_workflow is None:
                format_workflow_not_found_error(discovery_result, name)

            workflow_obj = discovered_workflow.workflow
            source_info = discovered_workflow.source
            file_path = discovered_workflow.file_path
            overrides = list(discovered_workflow.overrides)

        # Display workflow information with source (T063)
        click.echo(f"Workflow: {workflow_obj.name}")
        click.echo(f"Version: {workflow_obj.version}")

        # T063: Add source information display
        if source_info:
            source_label = get_source_label(source_info)
            click.echo(f"Source: {source_label}")

        if file_path:
            click.echo(f"File: {file_path}")

        if overrides:
            click.echo(f"Overrides: {len(overrides)} workflow(s)")
            for override_path in overrides:
                click.echo(f"  - {override_path}")

        if workflow_obj.description:
            click.echo(f"Description: {workflow_obj.description}")
        click.echo()

        # Display inputs
        if workflow_obj.inputs:
            click.echo("Inputs:")
            for input_name, input_def in workflow_obj.inputs.items():
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

        # Display steps
        click.echo(f"Steps ({len(workflow_obj.steps)}):")
        for i, step in enumerate(workflow_obj.steps, 1):
            click.echo(f"  {i}. {step.name} ({step.type.value})")
            if step.when:
                click.echo(f"     when: {step.when}")

    except SystemExit:
        raise
    except Exception as e:
        logger.exception("Unexpected error in workflow show command")
        error_msg = format_error(f"Failed to show workflow: {e}")
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e
