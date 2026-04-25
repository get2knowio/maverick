"""AgenticActorMixin — boilerplate for actors that own an ACP session + MCP tools.

Encapsulation contract: an agentic actor still owns:

1. **Schemas** — declared via the ``mcp_tools`` class attribute (or returned
   from ``_mcp_tools()``).
2. **Handler** — the actor implements ``on_tool_call(name, args) -> str``;
   when an agent calls one of its tools, the gateway forwards the call here.
3. **Session/turn state** — ACP session ID, mode, turn count.
4. **The ACP executor** — lazy-created via ``_ensure_executor`` in the
   subclass.

This mixin removes the per-actor MCP subprocess entirely. The shared
:class:`AgentToolGateway` (started by the actor pool) handles transport. The
mixin's responsibility is to register on ``__post_create__`` and unregister
on ``__pre_destroy__`` so the gateway always knows where to dispatch.

Subclasses use :meth:`mcp_server_config` when building an ACP session: it
returns the ``HttpMcpServer`` config that points the agent's MCP client at
``/mcp/<actor-uid>`` on the shared gateway.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import xoscar as xo
from acp.schema import HttpMcpServer

from maverick.logging import get_logger
from maverick.tools.agent_inbox.gateway import (
    AgentToolGateway,
    agent_tool_gateway_for,
)

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class AgenticActorMixin:
    """Mixin providing :class:`AgentToolGateway` registration for ACP-backed agent actors.

    Subclass requirements:

    * Declare ``mcp_tools: ClassVar[tuple[str, ...]]`` listing the tool names
      this actor owns, OR override :meth:`_mcp_tools` to compute the list
      dynamically (e.g., when the tool depends on constructor args).
    * Implement ``async def on_tool_call(self, name: str, args: dict) -> str``;
      it receives parsed tool arguments and is expected to forward a typed
      result to the supervisor.
    * Have ``self.address`` and an actor uid (provided by ``xo.Actor``).

    Subclasses MUST call :meth:`_register_with_gateway` from
    ``__post_create__`` and :meth:`_unregister_from_gateway` from
    ``__pre_destroy__``. This mixin does not override those hooks itself
    because real subclasses already use them for their own state.
    """

    # Default — subclasses override.
    mcp_tools: ClassVar[tuple[str, ...]] = ()

    # Set by _register_with_gateway.
    _gateway_url: str | None = None
    _gateway: AgentToolGateway | None = None
    _registered_uid: str | None = None

    # ------------------------------------------------------------------
    # Subclass-overridable hooks
    # ------------------------------------------------------------------

    def _mcp_tools(self) -> tuple[str, ...]:
        """Return the tool names this actor exposes.

        Default: returns the class-level ``mcp_tools`` attribute. Subclasses
        with per-instance variation (e.g., :class:`BriefingActor` whose tool
        is set at construction time) should override.
        """
        return tuple(self.mcp_tools)

    @xo.no_lock
    async def on_tool_call(self, name: str, args: dict[str, Any]) -> str:
        """Handle a tool call delivered by the gateway. Subclass MUST override.

        Decorated ``@xo.no_lock`` to prevent the deadlock between
        ``send_*`` (which holds the actor lock while awaiting an ACP
        prompt) and the gateway dispatch (which arrives while that prompt
        is in flight). Subclasses overriding this method MUST also
        decorate their override — see
        ``test_on_tool_call_is_no_lock`` in
        ``tests.unit.actors.xoscar_runtime.test_super_init``.
        """
        raise NotImplementedError(f"{type(self).__name__} must implement on_tool_call(name, args)")

    # ------------------------------------------------------------------
    # Registration helpers — call from __post_create__ / __pre_destroy__
    # ------------------------------------------------------------------

    async def _register_with_gateway(self) -> None:
        """Register this actor with the pool's :class:`AgentToolGateway`.

        Stores ``_gateway_url`` for use in :meth:`mcp_server_config`. Idempotent:
        a second call is a no-op.
        """
        if self._gateway_url is not None:
            return

        pool_address: str = self.address  # type: ignore[attr-defined]
        # The actor uid is always ``bytes`` on xoscar — see
        # ``test_actor_module_decodes_self_uid``. Decode for the gateway
        # registry / URL path.
        uid = self.uid.decode()  # type: ignore[attr-defined]

        tools = list(self._mcp_tools())
        if not tools:
            raise ValueError(
                f"{type(self).__name__} declares no MCP tools — "
                "set the `mcp_tools` class attribute or override `_mcp_tools()`."
            )

        gateway = agent_tool_gateway_for(pool_address)
        url = await gateway.register(uid, tools, self.on_tool_call)
        self._gateway = gateway
        self._gateway_url = url
        self._registered_uid = uid
        logger.debug(
            "agentic_actor.registered",
            actor=type(self).__name__,
            uid=uid,
            url=url,
            tools=tools,
        )

    async def _unregister_from_gateway(self) -> None:
        """Remove this actor's gateway registration. Best-effort, no-op when missing."""
        if self._gateway is None or self._registered_uid is None:
            return
        try:
            await self._gateway.unregister(self._registered_uid)
        except Exception as exc:  # noqa: BLE001 — teardown must not raise
            logger.debug(
                "agentic_actor.unregister_failed",
                actor=type(self).__name__,
                uid=self._registered_uid,
                error=str(exc),
            )
        finally:
            self._gateway = None
            self._gateway_url = None
            self._registered_uid = None

    # ------------------------------------------------------------------
    # ACP session helper
    # ------------------------------------------------------------------

    def mcp_server_config(self) -> HttpMcpServer:
        """Return the ACP HttpMcpServer pointing at this actor's gateway URL.

        Pass into ``executor.create_session(mcp_servers=[self.mcp_server_config()])``.
        Raises :class:`RuntimeError` if called before registration.
        """
        if self._gateway_url is None:
            raise RuntimeError(
                f"{type(self).__name__}: mcp_server_config() called before "
                "_register_with_gateway(). Did you forget to call "
                "self._register_with_gateway() in __post_create__?"
            )
        return HttpMcpServer(
            type="http",
            name="agent-tool-gateway",
            url=self._gateway_url,
            headers=[],
        )
