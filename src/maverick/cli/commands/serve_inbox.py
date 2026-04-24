"""CLI command for ``maverick serve-inbox``.

Starts the MCP inbox server and connects it to an agent actor so the
agent's MCP tool calls land on that actor's ``on_tool_call`` method.

Two discovery modes during the Thespian→xoscar migration:

* **xoscar (default going forward)** — ``--inbox-address HOST:PORT
  --inbox-uid <agent_uid>``. The target is the AGENT actor per Design
  Decision #3: the agent owns its own MCP inbox.

* **Thespian (legacy)** — ``--admin-port <port>``. The target is the
  refuel supervisor, discovered by the hardcoded ``supervisor-inbox``
  globalName. Preserved until Phase 4 so the legacy runtime path stays
  live during review.

Passing flags from both modes is rejected so a miswired caller doesn't
silently pick the wrong discovery path.

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
    default=None,
    help="xoscar pool address HOST:PORT of the agent whose inbox we serve.",
)
@click.option(
    "--inbox-uid",
    default=None,
    help="xoscar uid of the agent actor whose inbox we serve.",
)
@click.option(
    "--admin-port",
    type=int,
    default=None,
    help="(Legacy) Thespian admin port to connect to. Mutually exclusive with --inbox-*.",
)
def serve_inbox(
    tools: str,
    inbox_address: str | None,
    inbox_uid: str | None,
    admin_port: int | None,
) -> None:
    """Start the MCP inbox server (internal)."""
    import asyncio

    from maverick.tools.supervisor_inbox import server as _server_module
    from maverick.tools.supervisor_inbox.server import _build_mcp_tools, run_server

    xoscar_mode = inbox_address is not None or inbox_uid is not None
    legacy_mode = admin_port is not None

    if xoscar_mode and legacy_mode:
        err_console.print(
            "[red]Error:[/red] --inbox-address/--inbox-uid and --admin-port are "
            "mutually exclusive. Pass one discovery mode, not both."
        )
        raise SystemExit(ExitCode.FAILURE)

    if xoscar_mode and (not inbox_address or not inbox_uid):
        err_console.print(
            "[red]Error:[/red] xoscar mode requires both --inbox-address "
            "and --inbox-uid."
        )
        raise SystemExit(ExitCode.FAILURE)

    requested = {t.strip() for t in tools.split(",") if t.strip()}
    _server_module._active_tools = _build_mcp_tools(requested)

    if not _server_module._active_tools:
        from maverick.tools.supervisor_inbox.schemas import ALL_TOOL_SCHEMAS

        err_console.print(
            f"[red]Error:[/red] no valid tools in '{tools}'. "
            f"Available: {', '.join(sorted(ALL_TOOL_SCHEMAS))}"
        )
        raise SystemExit(ExitCode.FAILURE)

    if xoscar_mode:
        assert inbox_address is not None
        assert inbox_uid is not None
        asyncio.run(_run_xoscar(inbox_address, inbox_uid, _server_module, run_server))
    else:
        # Legacy Thespian path — default admin port 19500 preserves
        # behaviour of pre-xoscar callers.
        port = admin_port if admin_port is not None else 19500
        _run_thespian(port, _server_module)
        asyncio.run(run_server())


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


def _run_thespian(admin_port: int, server_module: Any) -> None:
    from thespian.actors import ActorSystem

    from maverick.actors.refuel_supervisor import RefuelSupervisorActor

    asys = ActorSystem(
        "multiprocTCPBase",
        capabilities={"Admin Port": admin_port},
    )
    supervisor_addr = asys.createActor(
        RefuelSupervisorActor, globalName="supervisor-inbox"
    )
    server_module._thespian_system = asys
    server_module._thespian_inbox = supervisor_addr
