"""CLI command for maverick briefing.

This module provides the ``maverick briefing`` command for reviewing
queued beads before executing them with ``maverick fly``.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from maverick.beads.client import BeadClient
from maverick.beads.models import BeadSummary, ReadyBead
from maverick.cli.context import ExitCode, async_command
from maverick.cli.output import format_error, format_table
from maverick.logging import get_logger

logger = get_logger(__name__)

# Maximum beads to fetch for briefing display
_BRIEFING_LIMIT = 100


def _beads_to_rows(beads: list[ReadyBead] | list[BeadSummary]) -> list[list[str]]:
    """Convert bead models to table rows.

    Args:
        beads: List of ReadyBead or BeadSummary models.

    Returns:
        List of row lists suitable for format_table.
    """
    rows: list[list[str]] = []
    for bead in beads:
        bead_type = getattr(bead, "bead_type", "task")
        status = getattr(bead, "status", "ready")
        priority = str(bead.priority)
        rows.append([bead.id, bead.title, priority, bead_type, status])
    return rows


def _beads_to_dicts(beads: list[ReadyBead] | list[BeadSummary]) -> list[dict[str, str]]:
    """Convert bead models to JSON-serializable dicts.

    Args:
        beads: List of ReadyBead or BeadSummary models.

    Returns:
        List of dicts with bead fields.
    """
    result: list[dict[str, str]] = []
    for bead in beads:
        bead_type = getattr(bead, "bead_type", "task")
        status = getattr(bead, "status", "ready")
        result.append({
            "id": bead.id,
            "title": bead.title,
            "priority": str(bead.priority),
            "type": bead_type,
            "status": status,
        })
    return result


_TABLE_HEADERS = ["ID", "Title", "Priority", "Type", "Status"]


@click.command("briefing")
@click.option(
    "--epic",
    default=None,
    help="Filter to a specific epic's beads.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (text table or JSON).",
)
@click.pass_context
@async_command
async def briefing(
    ctx: click.Context,
    epic: str | None,
    output_format: str,
) -> None:
    """Review queued beads before flying.

    Shows beads that are ready for execution. Use --epic to see all
    children of a specific epic (ready and not-ready).

    Examples:

        maverick briefing

        maverick briefing --epic 001-greet-cli

        maverick briefing --format json
    """
    cwd = Path.cwd()
    client = BeadClient(cwd=cwd)

    # Verify bd is available
    if not await client.verify_available():
        error_msg = format_error(
            "bd is not available",
            suggestion="Install bd from https://github.com/steveyegge/beads",
        )
        click.echo(error_msg, err=True)
        raise SystemExit(ExitCode.FAILURE)

    if epic:
        await _briefing_epic(client, epic, output_format)
    else:
        await _briefing_ready(client, output_format)


async def _briefing_ready(client: BeadClient, output_format: str) -> None:
    """Display all globally ready beads.

    Args:
        client: BeadClient instance.
        output_format: "text" or "json".
    """
    beads = await client.ready(limit=_BRIEFING_LIMIT)

    if output_format == "json":
        click.echo(json.dumps(_beads_to_dicts(beads), indent=2))
        return

    count = len(beads)
    if count == 0:
        click.echo("Briefing: No beads ready")
        click.echo("")
        click.echo("All beads are either completed or blocked.")
        return

    click.echo(f"Briefing: {count} bead{'s' if count != 1 else ''} ready")
    click.echo("")
    click.echo(format_table(_TABLE_HEADERS, _beads_to_rows(beads)))
    click.echo("")
    click.echo(
        "Use 'maverick fly' to start executing, "
        "or 'maverick fly --epic <id>' to focus on one epic."
    )


async def _briefing_epic(
    client: BeadClient,
    epic: str,
    output_format: str,
) -> None:
    """Display all children of an epic with status.

    Args:
        client: BeadClient instance.
        epic: Epic bead ID.
        output_format: "text" or "json".
    """
    children = await client.children(epic)
    ready_beads = await client.ready(parent_id=epic, limit=_BRIEFING_LIMIT)
    ready_ids = {b.id for b in ready_beads}

    if output_format == "json":
        dicts = _beads_to_dicts(children)
        # Enrich status: mark beads that are in the ready set
        for d in dicts:
            if d["id"] in ready_ids and d["status"] not in ("closed", "done"):
                d["status"] = "ready"
        click.echo(json.dumps(dicts, indent=2))
        return

    ready_count = len(ready_ids)
    total_count = len(children)

    if total_count == 0:
        click.echo(f'Briefing: Epic "{epic}" has no children')
        return

    click.echo(
        f'Briefing: Epic "{epic}" — '
        f"{ready_count} of {total_count} bead{'s' if total_count != 1 else ''} ready"
    )
    click.echo("")

    # Build rows, enriching status for ready beads
    rows: list[list[str]] = []
    for child in children:
        status = child.status
        if child.id in ready_ids and status not in ("closed", "done"):
            status = "ready"
        rows.append([
            child.id,
            child.title,
            str(child.priority),
            child.bead_type,
            status,
        ])

    click.echo(format_table(_TABLE_HEADERS, rows))
