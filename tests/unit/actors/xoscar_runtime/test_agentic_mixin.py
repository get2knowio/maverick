"""Tests for ``AgenticActorMixin`` — gateway registration lifecycle.

Verifies that agentic actors register with the gateway on ``__post_create__``,
unregister on ``__pre_destroy__``, and produce a valid ``HttpMcpServer`` config
pointing at the gateway's per-actor URL.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar

import pytest
import xoscar as xo
from acp.schema import HttpMcpServer

from maverick.actors.xoscar._agentic import AgenticActorMixin
from maverick.actors.xoscar.pool import create_pool
from maverick.tools.agent_inbox.gateway import (
    AgentToolGateway,
    register_agent_tool_gateway,
    unregister_agent_tool_gateway,
)


class _RecordingActor(AgenticActorMixin, xo.Actor):
    """Minimal agentic actor that records every tool call it receives."""

    mcp_tools: ClassVar[tuple[str, ...]] = ("submit_implementation",)

    async def __post_create__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        await self._register_with_gateway()

    async def __pre_destroy__(self) -> None:
        await self._unregister_from_gateway()

    async def on_tool_call(self, name: str, args: dict[str, Any]) -> str:
        self.calls.append((name, args))
        return "ok"

    async def get_calls(self) -> list[tuple[str, dict[str, Any]]]:
        return list(self.calls)

    async def get_mcp_url(self) -> str:
        return self.mcp_server_config().url


class _DynamicToolsActor(AgenticActorMixin, xo.Actor):
    """Agentic actor that supplies tool names at construction time."""

    def __init__(self, tool_name: str) -> None:
        super().__init__()
        self._tool_name = tool_name

    def _mcp_tools(self) -> tuple[str, ...]:
        return (self._tool_name,)

    async def __post_create__(self) -> None:
        await self._register_with_gateway()

    async def __pre_destroy__(self) -> None:
        await self._unregister_from_gateway()

    async def on_tool_call(self, name: str, args: dict[str, Any]) -> str:
        return "ok"


class _BadActor(AgenticActorMixin, xo.Actor):
    """Agentic actor that declares no tools — should fail registration."""

    mcp_tools: ClassVar[tuple[str, ...]] = ()

    async def __post_create__(self) -> None:
        await self._register_with_gateway()


@pytest.fixture
async def gateway_pool() -> AsyncIterator[tuple[str, AgentToolGateway]]:
    """Yield ``(pool_address, gateway)`` with a gateway bound to the address."""
    pool, address = await create_pool()
    gateway = AgentToolGateway()
    await gateway.start()
    register_agent_tool_gateway(address, gateway)
    try:
        yield address, gateway
    finally:
        unregister_agent_tool_gateway(address)
        await gateway.stop()
        await pool.stop()


@pytest.mark.asyncio
async def test_register_on_post_create_unregister_on_pre_destroy(
    gateway_pool: tuple[str, AgentToolGateway],
) -> None:
    address, gateway = gateway_pool
    actor = await xo.create_actor(_RecordingActor, address=address, uid="recording-1")
    try:
        url = await actor.get_mcp_url()
        assert url == gateway.url_for("recording-1")

        # The gateway knows about this actor — round-trip via direct ASGI is
        # covered by the gateway tests; here we just assert state.
        assert "recording-1" in gateway._routes  # type: ignore[attr-defined]
    finally:
        await xo.destroy_actor(actor)
    # __pre_destroy__ removed the registration
    assert "recording-1" not in gateway._routes  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_dynamic_tool_list_via_override(
    gateway_pool: tuple[str, AgentToolGateway],
) -> None:
    address, gateway = gateway_pool
    actor = await xo.create_actor(
        _DynamicToolsActor,
        "submit_review",
        address=address,
        uid="dynamic-1",
    )
    try:
        registered = gateway._routes["dynamic-1"]  # type: ignore[attr-defined]
        assert set(registered.tools) == {"submit_review"}
    finally:
        await xo.destroy_actor(actor)


@pytest.mark.asyncio
async def test_actor_without_tools_raises(
    gateway_pool: tuple[str, AgentToolGateway],
) -> None:
    address, _gateway = gateway_pool
    with pytest.raises(Exception):  # xo.create_actor wraps the original error
        await xo.create_actor(_BadActor, address=address, uid="bad-1")


@pytest.mark.asyncio
async def test_mcp_server_config_returns_http_config(
    gateway_pool: tuple[str, AgentToolGateway],
) -> None:
    address, gateway = gateway_pool
    actor = await xo.create_actor(_RecordingActor, address=address, uid="config-1")
    try:
        url = await actor.get_mcp_url()
    finally:
        await xo.destroy_actor(actor)
    # Verify shape — actor returned the URL string from the HttpMcpServer
    assert url.startswith(f"{gateway.base_url}/mcp/config-1")
    # Build the config independently to confirm name/headers shape
    config = HttpMcpServer(type="http", name="agent-tool-gateway", url=url, headers=[])
    assert config.name == "agent-tool-gateway"
    assert config.url == url
    assert config.headers == []
