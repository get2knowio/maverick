"""CLI command for ``maverick serve-inbox``.

Starts the MCP inbox server and connects it to an agent actor so the
agent's MCP tool calls land on that actor's ``on_tool_call`` method.

Per Design Decision #3 of the xoscar migration, the target is the
**agent** actor (not a single supervisor inbox). The actor's uid and
the pool's external address are passed at spawn time:

    maverick serve-inbox --tools submit_outline,submit_details \\
        --inbox-address 127.0.0.1:12345 --inbox-uid decomposer-primary
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import click

from maverick.cli.console import err_console
from maverick.cli.context import ExitCode
from maverick.logging import get_logger

logger = get_logger(__name__)


@click.command("serve-inbox")
@click.option(
    "--tools",
    required=True,
    help="Comma-separated tool names to expose to the agent.",
)
@click.option(
    "--inbox-address",
    required=True,
    help="xoscar pool address HOST:PORT of the agent whose inbox we serve.",
)
@click.option(
    "--inbox-uid",
    required=True,
    help="xoscar uid of the agent actor whose inbox we serve.",
)
def serve_inbox(tools: str, inbox_address: str, inbox_uid: str) -> None:
    """Start the MCP inbox server (internal)."""
    import asyncio

    from maverick.tools.agent_inbox import server as _server_module
    from maverick.tools.agent_inbox.server import _build_mcp_tools, run_server

    requested = {t.strip() for t in tools.split(",") if t.strip()}
    _server_module._active_tools = _build_mcp_tools(requested)

    if not _server_module._active_tools:
        from maverick.tools.agent_inbox.schemas import ALL_TOOL_SCHEMAS

        err_console.print(
            f"[red]Error:[/red] no valid tools in '{tools}'. "
            f"Available: {', '.join(sorted(ALL_TOOL_SCHEMAS))}"
        )
        raise SystemExit(ExitCode.FAILURE)

    asyncio.run(_run_xoscar(inbox_address, inbox_uid, _server_module, run_server))


async def _run_xoscar(
    address: str,
    uid: str,
    server_module: Any,
    run_server: Callable[[], Awaitable[None]],
) -> None:
    import xoscar as xo

    ref = await xo.actor_ref(address, uid)
    server_module._inbox_ref = ref
    await run_server()
