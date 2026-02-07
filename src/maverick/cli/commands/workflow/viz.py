"""Workflow viz subcommand.

Generates ASCII or Mermaid diagram visualizations of workflow steps
and their dependencies.
"""

from __future__ import annotations

from pathlib import Path

import click

from maverick.cli.common import get_discovery_result
from maverick.cli.context import ExitCode
from maverick.cli.output import format_error
from maverick.dsl.serialization.parser import parse_workflow
from maverick.dsl.visualization import to_ascii, to_mermaid
from maverick.logging import get_logger

from ._group import workflow
from ._helpers import format_workflow_not_found_error


@workflow.command("viz")
@click.argument("name_or_file")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["ascii", "mermaid"]),
    default="ascii",
    help="Diagram format.",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file (stdout if not specified).",
)
@click.option(
    "--direction",
    type=click.Choice(["TD", "LR"]),
    default="TD",
    help="Mermaid diagram direction (TD=top-down, LR=left-right).",
)
@click.pass_context
def workflow_viz(
    ctx: click.Context,
    name_or_file: str,
    fmt: str,
    output: Path | None,
    direction: str,
) -> None:
    """Generate ASCII or Mermaid diagram of workflow.

    NAME_OR_FILE can be either a workflow name (from discovery) or a file path.

    Examples:
        maverick workflow viz fly
        maverick workflow viz my-workflow.yaml --format mermaid
        maverick workflow viz my-workflow --output diagram.md
        maverick workflow viz my-workflow --format mermaid --direction LR
    """
    logger = get_logger(__name__)

    try:
        # Determine if name_or_file is a file path or workflow name
        name_path = Path(name_or_file)
        workflow_obj = None

        if name_path.exists():
            # It's a file path - parse directly
            content = name_path.read_text(encoding="utf-8")
            workflow_obj = parse_workflow(content, validate_only=True)
        else:
            # Look up in discovery (FR-014: use DiscoveryResult for workflow viz)
            discovery_result = get_discovery_result(ctx)
            discovered_workflow = discovery_result.get_workflow(name_or_file)

            if discovered_workflow is not None:
                workflow_obj = discovered_workflow.workflow
            else:
                format_workflow_not_found_error(discovery_result, name_or_file)

        # Generate diagram
        if fmt == "mermaid":
            diagram = to_mermaid(workflow_obj, direction=direction)
        else:
            # ASCII format
            diagram = to_ascii(workflow_obj, width=80)

        # Output diagram
        if output:
            output.write_text(diagram, encoding="utf-8")
            click.echo(f"Diagram written to {output}")
        else:
            click.echo(diagram)

    except SystemExit:
        raise
    except Exception as e:
        logger.exception("Unexpected error in workflow viz command")
        error_msg = format_error(f"Failed to generate diagram: {e}")
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE) from e
