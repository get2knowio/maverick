"""HTTP MCP gateway: one shared server multiplexing N agent tool routes by uid.

Replaces the per-actor stdio MCP subprocess model. A single in-process
uvicorn ASGI app serves MCP over streamable-HTTP; agent actors register a
handler keyed by their xoscar uid and the gateway routes incoming tool calls
to the right per-actor handler via path-based dispatch (``/mcp/<uid>``).

Architecture:

* One :class:`AgentToolGateway` per workflow run, started inside the actor
  pool's lifecycle and reachable via :func:`agent_tool_gateway_for(pool_address)`.
* Each :class:`_ActorRoute` owns a private :class:`mcp.server.lowlevel.Server`
  with the actor's tool subset, an MCP :class:`StreamableHTTPSessionManager`,
  and a background task that runs the manager's lifecycle.
* The gateway is a pure ASGI app: it parses ``scope["path"]`` to extract the
  uid, looks up the matching actor, and forwards the ASGI call directly to
  that actor's session manager.
* Per-tool JSON Schema validation runs in the route handler before invoking
  the actor's handler — same self-correction loop the legacy stdio server
  used.

Encapsulation note: the gateway is *infrastructure*. Agent actors continue to
own their schemas, handler, session state, and ACP executor. Only the MCP
transport moves out of the actor and into this shared service.

Naming note: the package is named ``agent_inbox`` because its sibling files
(``schemas.py``, ``models.py``) define the typed message-shape contract for
agent-to-controller payloads. The gateway itself is RPC, not a mailbox — the
class and helpers reflect that.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

import jsonschema
import uvicorn
from mcp.server.lowlevel import Server as McpServer
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool
from starlette.types import Receive, Scope, Send

from maverick.logging import get_logger
from maverick.tools.agent_inbox.schemas import ALL_TOOL_SCHEMAS

__all__ = [
    "AgentToolGateway",
    "ToolHandler",
    "agent_tool_gateway_for",
    "register_agent_tool_gateway",
    "unregister_agent_tool_gateway",
]

logger = get_logger(__name__)

# Agent handler signature: (tool_name, arguments) -> short status string
ToolHandler = Callable[[str, dict[str, Any]], Awaitable[str]]


_gateway_by_pool: dict[str, AgentToolGateway] = {}


def agent_tool_gateway_for(pool_address: str) -> AgentToolGateway:
    """Return the gateway bound to a given xoscar pool address.

    Raises:
        KeyError: when no gateway is registered for ``pool_address`` —
            typically means the actor was constructed outside of an
            ``actor_pool()`` context, or the gateway failed to start.
    """
    try:
        return _gateway_by_pool[pool_address]
    except KeyError as exc:
        raise KeyError(
            f"No agent tool gateway registered for pool {pool_address!r}. "
            "Was the actor created inside actor_pool()?"
        ) from exc


def register_agent_tool_gateway(
    pool_address: str, gateway: AgentToolGateway
) -> None:
    """Bind a gateway to a pool address. Overwrites any existing binding."""
    _gateway_by_pool[pool_address] = gateway


def unregister_agent_tool_gateway(pool_address: str) -> None:
    """Remove the binding for a pool address. No-op when missing."""
    _gateway_by_pool.pop(pool_address, None)


class _ActorRoute:
    """Per-actor MCP server hosting one or more tools.

    Owns its own :class:`StreamableHTTPSessionManager` running in a background
    task so multiple actor routes can coexist in one ASGI app with
    independent lifetimes.
    """

    def __init__(
        self,
        uid: str,
        tool_names: list[str],
        handler: ToolHandler,
    ) -> None:
        self.uid = uid
        self.handler = handler
        self.tools: dict[str, Tool] = {}
        for name in tool_names:
            schema = ALL_TOOL_SCHEMAS.get(name)
            if schema is None:
                raise ValueError(f"Unknown agent tool: {name!r}")
            self.tools[name] = Tool(
                name=schema["name"],
                description=schema["description"],
                inputSchema=schema["inputSchema"],
            )

        self._mcp_server: McpServer = McpServer(f"agent-tool-gateway-{uid}")

        @self._mcp_server.list_tools()
        async def _list_tools() -> list[Tool]:
            return list(self.tools.values())

        @self._mcp_server.call_tool()
        async def _call_tool(
            name: str, arguments: dict[str, Any] | None
        ) -> list[TextContent]:
            return await self._handle_call(name, arguments or {})

        self._session_manager = StreamableHTTPSessionManager(
            app=self._mcp_server,
            stateless=False,
            json_response=False,
        )
        self._task: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()

    async def _handle_call(
        self, name: str, arguments: dict[str, Any]
    ) -> list[TextContent]:
        if name not in self.tools:
            available = ", ".join(sorted(self.tools)) or "(none)"
            raise ValueError(
                f"Tool {name!r} is not available for actor {self.uid!r}. "
                f"Available tools: {available}"
            )

        schema = self.tools[name].inputSchema
        if schema:
            try:
                jsonschema.validate(instance=arguments, schema=schema)
            except jsonschema.ValidationError as exc:
                error_path = (
                    " → ".join(str(p) for p in exc.absolute_path)
                    if exc.absolute_path
                    else "(root)"
                )
                raise ValueError(
                    f"Schema validation failed for {name!r} at {error_path!r}: "
                    f"{exc.message}. Please fix the arguments and call "
                    f"{name!r} again."
                ) from exc

        logger.debug(
            "agent_tool_gateway.tool_call_received",
            uid=self.uid,
            tool=name,
            arg_keys=sorted(arguments.keys()),
        )
        result = await self.handler(name, arguments)
        logger.debug(
            "agent_tool_gateway.tool_delivered",
            uid=self.uid,
            tool=name,
            result=repr(result),
        )
        return [
            TextContent(
                type="text",
                text=f"Submitted {name} to agent (result: {result}).",
            )
        ]

    async def start(self) -> None:
        """Start the per-actor session manager in a background task."""

        async def _runner() -> None:
            async with self._session_manager.run():
                self._ready.set()
                # Block until cancelled — the session manager handles its
                # own request lifetimes; we just keep the run() context alive.
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.Event().wait()

        self._task = asyncio.create_task(
            _runner(), name=f"agent-tool-route[{self.uid}]"
        )
        await self._ready.wait()

    async def stop(self) -> None:
        """Cancel the background runner and drain pending sessions."""
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def asgi(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI entry point — forward to the session manager."""
        await self._session_manager.handle_request(scope, receive, send)


class AgentToolGateway:
    """Shared HTTP MCP gateway routing agent tool calls to per-actor handlers.

    One instance per xoscar pool / workflow run. Started by the pool wrapper
    after the pool is up; stopped before the pool is torn down.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self._host = host
        self._requested_port = port
        self._port: int | None = None
        self._routes: dict[str, _ActorRoute] = {}
        self._uvicorn_config = uvicorn.Config(
            self,  # AgentToolGateway is itself an ASGI callable (see __call__)
            host=self._host,
            port=self._requested_port,
            log_level="warning",
            lifespan="off",
            access_log=False,
        )
        self._uvicorn_server: uvicorn.Server | None = None
        self._serve_task: asyncio.Task[None] | None = None

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        if self._port is None:
            raise RuntimeError("AgentToolGateway not started — port not yet bound")
        return self._port

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self.port}"

    def url_for(self, uid: str) -> str:
        """Return the URL an actor with ``uid`` should pass to ``HttpMcpServer``."""
        return f"{self.base_url}/mcp/{uid}"

    async def start(self) -> None:
        """Start the uvicorn server and discover the bound port."""
        if self._uvicorn_server is not None:
            return  # already running

        server = uvicorn.Server(self._uvicorn_config)
        self._uvicorn_server = server
        self._serve_task = asyncio.create_task(
            server.serve(), name="agent-tool-gateway-uvicorn"
        )

        # Wait until uvicorn has finished startup and bound a real port.
        for _ in range(500):  # up to ~5s
            if server.started and getattr(server, "servers", None):
                break
            await asyncio.sleep(0.01)
        else:  # pragma: no cover — defensive timeout
            raise RuntimeError("AgentToolGateway: uvicorn failed to start within 5s")

        # Discover the actual bound port (handles port=0 ephemeral binding).
        for srv in server.servers:
            socks = getattr(srv, "sockets", None) or []
            for sock in socks:
                self._port = sock.getsockname()[1]
                break
            if self._port is not None:
                break
        if self._port is None:  # pragma: no cover — defensive
            raise RuntimeError("AgentToolGateway: could not discover bound port")

        logger.debug(
            "agent_tool_gateway.started", host=self._host, port=self._port
        )

    async def stop(self) -> None:
        """Stop all per-actor routes and shut the HTTP server down cleanly."""
        # Drain registered routes first so their session managers exit cleanly
        # before we cancel the uvicorn loop.
        for uid in list(self._routes):
            await self.unregister(uid)

        if self._uvicorn_server is not None:
            self._uvicorn_server.should_exit = True
            if self._serve_task is not None:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.wait_for(self._serve_task, timeout=5.0)
            self._uvicorn_server = None
            self._serve_task = None
        logger.debug("agent_tool_gateway.stopped")

    async def register(
        self,
        uid: str,
        tool_names: list[str],
        handler: ToolHandler,
    ) -> str:
        """Register an actor's tool handlers and return the actor's URL.

        The URL should be passed verbatim as ``HttpMcpServer.url`` when the
        actor configures its ACP session.
        """
        if uid in self._routes:
            raise ValueError(f"Actor {uid!r} already registered with the gateway")
        route = _ActorRoute(uid, tool_names, handler)
        await route.start()
        self._routes[uid] = route
        url = self.url_for(uid)
        logger.debug(
            "agent_tool_gateway.actor_registered",
            uid=uid,
            tools=sorted(tool_names),
            url=url,
        )
        return url

    async def unregister(self, uid: str) -> None:
        """Remove an actor's route. No-op when missing."""
        route = self._routes.pop(uid, None)
        if route is None:
            return
        await route.stop()
        logger.debug("agent_tool_gateway.actor_unregistered", uid=uid)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI entry point.

        Path layout: ``/mcp/<uid>`` (and ``/mcp/<uid>/``). Anything else 404s.
        """
        if scope["type"] != "http":
            await self._send_404(send, "only HTTP scope supported")
            return

        path = scope.get("path", "")
        uid = self._parse_uid(path)
        if uid is None:
            await self._send_404(send, f"path {path!r} does not match /mcp/<uid>")
            return

        route = self._routes.get(uid)
        if route is None:
            await self._send_404(send, f"unknown actor uid {uid!r}")
            return

        # Rewrite the scope to put the per-actor mount at "/mcp/<uid>" so the
        # underlying StreamableHTTP transport sees a clean root-relative path.
        mount_prefix = f"/mcp/{uid}"
        new_scope = dict(scope)
        new_scope["root_path"] = scope.get("root_path", "") + mount_prefix
        new_scope["path"] = path[len(mount_prefix) :] or "/"
        await route.asgi(new_scope, receive, send)

    @staticmethod
    def _parse_uid(path: str) -> str | None:
        """Extract ``<uid>`` from ``/mcp/<uid>`` or ``/mcp/<uid>/`` paths."""
        if not path.startswith("/mcp/"):
            return None
        rest = path[len("/mcp/") :]
        # Trailing-slash / sub-path support: take the first segment.
        if not rest:
            return None
        uid, _, _ = rest.partition("/")
        return uid or None

    @staticmethod
    async def _send_404(send: Send, message: str) -> None:
        body = message.encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [
                    (b"content-type", b"text/plain; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})
