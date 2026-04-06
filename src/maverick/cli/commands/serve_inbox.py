"""CLI command for maverick serve-inbox.

Starts the MCP supervisor inbox server. Discovers the supervisor
Thespian actor via globalName and delivers tool call data as
Thespian messages.

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

    Discovers the supervisor Thespian actor and delivers validated
    MCP tool calls as messages.
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

    # Connect to existing Thespian ActorSystem and discover supervisor
    from thespian.actors import ActorSystem

    from maverick.actors.refuel_supervisor import RefuelSupervisorActor

    asys = ActorSystem("multiprocTCPBase")
    supervisor_addr = asys.createActor(
        RefuelSupervisorActor, globalName="supervisor-inbox"
    )
    _server_module._thespian_system = asys
    _server_module._thespian_inbox = supervisor_addr

    asyncio.run(run_server())
