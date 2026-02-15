"""CLI command for maverick brief.

This module provides the ``maverick brief`` command for reviewing
queued beads before executing them with ``maverick fly``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

import click
from rich.live import Live
from rich.table import Table

from maverick.beads.client import BeadClient
from maverick.beads.models import BeadSummary, ReadyBead
from maverick.cli.console import console
from maverick.cli.context import ExitCode, async_command
from maverick.cli.output import format_error, format_table
from maverick.logging import get_logger

logger = get_logger(__name__)

# Maximum beads to fetch for brief display
_BRIEF_LIMIT = 100

_CLOSED_STATUSES = frozenset(("closed", "done"))

_STATUS_STYLES: dict[str, str] = {
    "ready": "green",
    "blocked": "red",
    "open": "yellow",
    "closed": "dim",
    "done": "dim",
}


def _beads_to_rows(beads: Sequence[ReadyBead | BeadSummary]) -> list[list[str]]:
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


def _beads_to_dicts(beads: Sequence[ReadyBead | BeadSummary]) -> list[dict[str, str]]:
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
        result.append(
            {
                "id": bead.id,
                "title": bead.title,
                "priority": str(bead.priority),
                "type": bead_type,
                "status": status,
            }
        )
    return result


_TABLE_HEADERS = ["ID", "Title", "Priority", "Type", "Status"]


def _build_rich_table(
    beads: list[ReadyBead | BeadSummary],
    epic: str | None = None,
) -> Table:
    """Build a Rich Table with color-coded status for watch mode.

    Args:
        beads: Combined list of bead models.
        epic: Epic ID if in epic mode, None for global mode.

    Returns:
        A Rich Table ready for Live display.
    """
    title = f'Brief: Epic "{epic}"' if epic else "Brief: Dashboard"
    table = Table(title=title, show_lines=False)
    for header in _TABLE_HEADERS:
        table.add_column(header)

    for bead in beads:
        bead_type = getattr(bead, "bead_type", "task")
        status = getattr(bead, "status", "ready")
        style = _STATUS_STYLES.get(status, "")
        table.add_row(
            bead.id,
            bead.title,
            str(bead.priority),
            bead_type,
            f"[{style}]{status}[/{style}]" if style else status,
        )

    return table


async def _fetch_beads_global(
    client: BeadClient,
    show_all: bool,
) -> list[ReadyBead | BeadSummary]:
    """Fetch beads for global (non-epic) mode.

    Args:
        client: BeadClient instance.
        show_all: Whether to include closed/done beads.

    Returns:
        Combined list of ready and blocked beads (and closed if show_all).
    """
    ready_beads = await client.ready(limit=_BRIEF_LIMIT)
    blocked_beads = await client.query("status=blocked")

    # Deduplicate by ID, ready beads take precedence
    seen_ids: set[str] = set()
    combined: list[ReadyBead | BeadSummary] = []
    for rb in ready_beads:
        if rb.id not in seen_ids:
            seen_ids.add(rb.id)
            combined.append(rb)
    for bb in blocked_beads:
        if bb.id not in seen_ids:
            seen_ids.add(bb.id)
            combined.append(bb)

    if show_all:
        closed_beads = await client.query("status=closed OR status=done")
        for cb in closed_beads:
            if cb.id not in seen_ids:
                seen_ids.add(cb.id)
                combined.append(cb)

    # Sort by priority (lower number = higher priority)
    combined.sort(key=lambda b: b.priority)
    return combined


async def _fetch_beads_epic(
    client: BeadClient,
    epic: str,
    show_all: bool,
) -> list[ReadyBead | BeadSummary]:
    """Fetch beads for epic mode.

    Args:
        client: BeadClient instance.
        epic: Epic bead ID.
        show_all: Whether to include closed/done beads.

    Returns:
        List of children with statuses enriched (ready beads marked).
    """
    children = await client.children(epic)
    ready_beads = await client.ready(parent_id=epic, limit=_BRIEF_LIMIT)
    ready_ids = {b.id for b in ready_beads}

    result: list[ReadyBead | BeadSummary] = []
    for child in children:
        if not show_all and child.status in _CLOSED_STATUSES:
            continue
        # Enrich status: mark beads in the ready set
        if child.id in ready_ids and child.status not in _CLOSED_STATUSES:
            result.append(
                BeadSummary(
                    id=child.id,
                    title=child.title,
                    priority=child.priority,
                    bead_type=child.bead_type,
                    status="ready",
                )
            )
        else:
            result.append(child)

    return result


async def _watch_loop(
    fetch_fn: Callable[[], Awaitable[list[ReadyBead | BeadSummary]]],
    interval: float,
    epic: str | None,
) -> None:
    """Poll beads and refresh Rich Live display.

    Args:
        fetch_fn: Async callable that returns beads to display.
        interval: Refresh interval in seconds.
        epic: Epic ID if in epic mode, None for global.
    """
    with Live(console=console, refresh_per_second=1) as live:
        try:
            while True:
                beads = await fetch_fn()
                table = _build_rich_table(beads, epic=epic)
                live.update(table)
                await asyncio.sleep(interval)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass  # Clean exit on Ctrl-C


@click.command("brief")
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
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    default=False,
    help="Include closed/completed beads.",
)
@click.option(
    "--watch",
    is_flag=True,
    default=False,
    help="Continuously refresh the display.",
)
@click.option(
    "--interval",
    type=float,
    default=5.0,
    help="Refresh interval in seconds (requires --watch).",
)
@click.pass_context
@async_command
async def brief(
    ctx: click.Context,
    epic: str | None,
    output_format: str,
    show_all: bool,
    watch: bool,
    interval: float,
) -> None:
    """Review queued beads before flying.

    Shows ready and blocked beads by default. Use --epic to see children
    of a specific epic. Use --all to include closed/completed beads.
    Use --watch to continuously refresh the display.

    Examples:

        maverick brief

        maverick brief --epic 001-greet-cli

        maverick brief --format json

        maverick brief --watch --interval 2

        maverick brief --epic my-epic --watch
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

    if watch:

        async def fetch_fn() -> list[ReadyBead | BeadSummary]:
            if epic:
                return await _fetch_beads_epic(client, epic, show_all)
            return await _fetch_beads_global(client, show_all)

        await _watch_loop(fetch_fn, interval, epic)
    elif epic:
        await _brief_epic(client, epic, output_format, show_all)
    else:
        await _brief_ready(client, output_format, show_all)


async def _brief_ready(
    client: BeadClient,
    output_format: str,
    show_all: bool,
) -> None:
    """Display ready and blocked beads globally.

    Args:
        client: BeadClient instance.
        output_format: "text" or "json".
        show_all: Whether to include closed/done beads.
    """
    beads = await _fetch_beads_global(client, show_all)

    if output_format == "json":
        click.echo(json.dumps(_beads_to_dicts(beads), indent=2))
        return

    count = len(beads)
    if count == 0:
        click.echo("Brief: No beads ready")
        click.echo("")
        click.echo("All beads are either completed or blocked.")
        return

    click.echo(f"Brief: {count} bead{'s' if count != 1 else ''} ready")
    click.echo("")
    click.echo(format_table(_TABLE_HEADERS, _beads_to_rows(beads)))
    click.echo("")
    click.echo(
        "Use 'maverick fly' to start executing, "
        "or 'maverick fly --epic <id>' to focus on one epic."
    )


async def _brief_epic(
    client: BeadClient,
    epic: str,
    output_format: str,
    show_all: bool,
) -> None:
    """Display children of an epic with status.

    Args:
        client: BeadClient instance.
        epic: Epic bead ID.
        output_format: "text" or "json".
        show_all: Whether to include closed/done beads.
    """
    children = await client.children(epic)
    ready_beads = await client.ready(parent_id=epic, limit=_BRIEF_LIMIT)
    ready_ids = {b.id for b in ready_beads}

    # Filter closed beads unless --all
    if not show_all:
        children = [c for c in children if c.status not in _CLOSED_STATUSES]

    if output_format == "json":
        dicts = _beads_to_dicts(children)
        # Enrich status: mark beads that are in the ready set
        for d in dicts:
            if d["id"] in ready_ids and d["status"] not in _CLOSED_STATUSES:
                d["status"] = "ready"
        click.echo(json.dumps(dicts, indent=2))
        return

    ready_count = len(ready_ids)
    total_count = len(children)

    if total_count == 0:
        click.echo(f'Brief: Epic "{epic}" has no children')
        return

    click.echo(
        f'Brief: Epic "{epic}" — '
        f"{ready_count} of {total_count} bead{'s' if total_count != 1 else ''} ready"
    )
    click.echo("")

    # Build rows, enriching status for ready beads
    rows: list[list[str]] = []
    for child in children:
        status = child.status
        if child.id in ready_ids and status not in _CLOSED_STATUSES:
            status = "ready"
        rows.append(
            [
                child.id,
                child.title,
                str(child.priority),
                child.bead_type,
                status,
            ]
        )

    click.echo(format_table(_TABLE_HEADERS, rows))
