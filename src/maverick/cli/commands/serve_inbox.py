"""CLI command for maverick serve-inbox.

Starts the MCP supervisor inbox server. This is an internal command
used by the actor-mailbox architecture — the orchestrator spawns it
as a subprocess that agent processes connect to via stdio.

Not intended to be run manually, but available for debugging:
    maverick serve-inbox --tools submit_outline,submit_details --output /tmp/inbox.json
"""

from __future__ import annotations

import click

from maverick.logging import get_logger

logger = get_logger(__name__)


@click.command("serve-inbox")
@click.option(
    "--tools",
    required=True,
    help="Comma-separated tool names to expose to the agent.",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(),
    help="Path to write inbox messages (JSON file).",
)
def serve_inbox(tools: str, output: str) -> None:
    """Start the MCP supervisor inbox server (internal).

    Exposes a filtered set of MCP tools for an agent to call.
    Each tool call writes structured data to the output file
    for the supervisor to read.
    """
    from maverick.tools.supervisor_inbox.server import (
        _build_mcp_tools,
        _output_path,
        run_server,
        server,
    )
    from maverick.tools.supervisor_inbox import server as _server_module

    import asyncio
    from pathlib import Path

    requested = {t.strip() for t in tools.split(",") if t.strip()}
    _server_module._active_tools = _build_mcp_tools(requested)
    _server_module._output_path = Path(output)

    if not _server_module._active_tools:
        from maverick.tools.supervisor_inbox.schemas import ALL_TOOL_SCHEMAS

        click.echo(
            f"Error: no valid tools in '{tools}'. "
            f"Available: {', '.join(sorted(ALL_TOOL_SCHEMAS))}",
            err=True,
        )
        raise SystemExit(1)

    asyncio.run(run_server())
