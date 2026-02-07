"""Shared helpers for workflow CLI subcommands.

Provides common utilities used across multiple workflow commands,
including error formatting and source label mapping.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn

import click

from maverick.cli.context import ExitCode
from maverick.cli.output import format_error

if TYPE_CHECKING:
    from maverick.dsl.discovery import DiscoveryResult


def format_workflow_not_found_error(
    discovery_result: DiscoveryResult,
    workflow_name: str,
) -> NoReturn:
    """Format and display a 'workflow not found' error with suggestions.

    Shows the available workflows and exits with a failure code.

    Args:
        discovery_result: The discovery result to pull available names from.
        workflow_name: The workflow name that was not found.

    Raises:
        SystemExit: Always raises with FAILURE exit code.
    """
    available = discovery_result.workflow_names
    if available:
        available_str = ", ".join(available[:5])
        if len(available) > 5:
            available_str += f", ... ({len(available)} total)"
        suggestion = f"Available workflows: {available_str}"
    else:
        suggestion = "No workflows discovered. Check your workflow directories."

    error_msg = format_error(
        f"Workflow '{workflow_name}' not found",
        suggestion=suggestion,
    )
    click.echo(error_msg, err=True)
    raise SystemExit(ExitCode.FAILURE)


def get_source_label(source: str) -> str:
    """Map a workflow source identifier to a human-readable label.

    Args:
        source: The source identifier (e.g., "builtin", "user", "project", "file").

    Returns:
        A descriptive label for the source.
    """
    return {
        "builtin": "Built-in (packaged with Maverick)",
        "user": "User (~/.config/maverick/workflows/)",
        "project": "Project (.maverick/workflows/)",
        "file": "Direct file path",
    }.get(source, source)
