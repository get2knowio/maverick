"""CLI command for maverick serve-inbox.

Starts the MCP supervisor inbox server. This is an internal command
used by the actor-mailbox architecture — the agent subprocess spawns
it and connects via stdio.

The server validates tool call arguments against JSON Schema and
delivers them to the supervisor's Thespian inbox actor.

    maverick serve-inbox --tools submit_outline,submit_details
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
def serve_inbox(tools: str) -> None:
    """Start the MCP supervisor inbox server (internal).

    Exposes a filtered set of MCP tools for an agent to call.
    Each tool call is validated against the schema and delivered
    to the supervisor's Thespian inbox actor.
    """
    from maverick.tools.supervisor_inbox import server as _server_module
    from maverick.tools.supervisor_inbox.server import (
        _build_mcp_tools,
        run_server,
    )

    import asyncio

    requested = {t.strip() for t in tools.split(",") if t.strip()}
    _server_module._active_tools = _build_mcp_tools(requested)

    if not _server_module._active_tools:
        from maverick.tools.supervisor_inbox.schemas import ALL_TOOL_SCHEMAS

        click.echo(
            f"Error: no valid tools in '{tools}'. "
            f"Available: {', '.join(sorted(ALL_TOOL_SCHEMAS))}",
            err=True,
        )
        raise SystemExit(1)

    # Connect to existing Thespian ActorSystem and discover supervisor inbox
    from thespian.actors import ActorSystem

    from maverick.actors.inbox import InboxActor

    asys = ActorSystem("multiprocTCPBase")
    inbox_addr = asys.createActor(
        InboxActor, globalName="supervisor-inbox"
    )
    _server_module._thespian_system = asys
    _server_module._thespian_inbox = inbox_addr

    asyncio.run(run_server())
