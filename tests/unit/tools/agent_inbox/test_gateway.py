"""Unit tests for ``maverick.tools.agent_inbox.gateway.AgentToolGateway``.

End-to-end tests exercise the gateway via a real MCP HTTP client (the
streamable-HTTP client from the ``mcp`` SDK) so we get protocol-level
coverage without depending on the ``claude-agent-acp`` Node bridge.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from maverick.tools.agent_inbox.gateway import (
    AgentToolGateway,
    agent_tool_gateway_for,
    register_agent_tool_gateway,
    unregister_agent_tool_gateway,
)


@pytest.fixture
async def gateway():
    """Yield a started :class:`AgentToolGateway` and stop it on teardown."""
    gateway = AgentToolGateway()
    await gateway.start()
    try:
        yield gateway
    finally:
        await gateway.stop()


def _record_handler(sink: list[tuple[str, dict[str, Any]]]):
    async def handler(name: str, args: dict[str, Any]) -> str:
        sink.append((name, args))
        return "ok"

    return handler


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gateway_binds_ephemeral_port():
    gateway = AgentToolGateway()
    try:
        await gateway.start()
        assert gateway.port > 0
        assert gateway.base_url.startswith(f"http://127.0.0.1:{gateway.port}")
    finally:
        await gateway.stop()


@pytest.mark.asyncio
async def test_start_is_idempotent():
    gateway = AgentToolGateway()
    await gateway.start()
    port = gateway.port
    await gateway.start()  # second call should be a no-op
    assert gateway.port == port
    await gateway.stop()


@pytest.mark.asyncio
async def test_url_for_uses_base_url():
    gateway = AgentToolGateway()
    await gateway.start()
    try:
        assert gateway.url_for("foo") == f"{gateway.base_url}/mcp/foo"
    finally:
        await gateway.stop()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_returns_actor_url(gateway: AgentToolGateway):
    received: list[tuple[str, dict[str, Any]]] = []
    url = await gateway.register("actor-1", ["submit_implementation"], _record_handler(received))
    assert url == gateway.url_for("actor-1")


@pytest.mark.asyncio
async def test_register_rejects_duplicate_uid(gateway: AgentToolGateway):
    received: list[tuple[str, dict[str, Any]]] = []
    await gateway.register("dup", ["submit_implementation"], _record_handler(received))
    with pytest.raises(ValueError, match="already registered"):
        await gateway.register("dup", ["submit_review"], _record_handler(received))


@pytest.mark.asyncio
async def test_register_rejects_unknown_tool(gateway: AgentToolGateway):
    received: list[tuple[str, dict[str, Any]]] = []
    with pytest.raises(ValueError, match="Unknown agent tool"):
        await gateway.register("x", ["does_not_exist"], _record_handler(received))


@pytest.mark.asyncio
async def test_unregister_is_idempotent(gateway: AgentToolGateway):
    await gateway.unregister("never-registered")  # no-op, no error


# ---------------------------------------------------------------------------
# MCP protocol round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_initialize_list_call(gateway: AgentToolGateway):
    """End-to-end: real MCP HTTP client → server → handler."""
    received: list[tuple[str, dict[str, Any]]] = []
    url = await gateway.register(
        "echo-actor", ["submit_implementation"], _record_handler(received)
    )

    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            assert init.protocolVersion is not None

            tools = await session.list_tools()
            assert {t.name for t in tools.tools} == {"submit_implementation"}

            result = await session.call_tool(
                "submit_implementation",
                {"summary": "did the thing", "files_changed": ["a.py"]},
            )
            assert result.isError is False
            assert "submit_implementation" in result.content[0].text

    assert received == [
        ("submit_implementation", {"summary": "did the thing", "files_changed": ["a.py"]})
    ]


@pytest.mark.asyncio
async def test_mcp_per_actor_tool_isolation(gateway: AgentToolGateway):
    """Two actors expose disjoint tool sets via distinct URLs."""
    a_seen: list[tuple[str, dict[str, Any]]] = []
    b_seen: list[tuple[str, dict[str, Any]]] = []
    url_a = await gateway.register("a", ["submit_implementation"], _record_handler(a_seen))
    url_b = await gateway.register("b", ["submit_review"], _record_handler(b_seen))

    async with streamablehttp_client(url_a) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            assert {t.name for t in tools.tools} == {"submit_implementation"}

    async with streamablehttp_client(url_b) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            assert {t.name for t in tools.tools} == {"submit_review"}


@pytest.mark.asyncio
async def test_schema_validation_returns_tool_error(gateway: AgentToolGateway):
    """Bad arguments → MCP tool error result, handler not invoked."""
    received: list[tuple[str, dict[str, Any]]] = []
    url = await gateway.register(
        "validate-actor", ["submit_implementation"], _record_handler(received)
    )

    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # Missing required field 'summary'
            result = await session.call_tool("submit_implementation", {})
            assert result.isError is True
            text = result.content[0].text if result.content else ""
            assert "Schema validation failed" in text or "summary" in text

    # Handler must NOT have been invoked
    assert received == []


@pytest.mark.asyncio
async def test_handler_exception_returns_tool_error(gateway: AgentToolGateway):
    async def boom(name: str, args: dict[str, Any]) -> str:
        raise RuntimeError("simulated failure in handler")

    url = await gateway.register("boom-actor", ["submit_implementation"], boom)
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("submit_implementation", {"summary": "x"})
            assert result.isError is True


@pytest.mark.asyncio
async def test_unknown_uid_returns_404(gateway: AgentToolGateway):
    bad_url = gateway.url_for("never-registered")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            bad_url,
            json={"jsonrpc": "2.0", "method": "initialize", "id": 1},
            headers={"Accept": "application/json, text/event-stream"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unregister_then_call_returns_404(gateway: AgentToolGateway):
    received: list[tuple[str, dict[str, Any]]] = []
    url = await gateway.register("ephemeral", ["submit_implementation"], _record_handler(received))
    await gateway.unregister("ephemeral")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json={"jsonrpc": "2.0", "method": "initialize", "id": 1},
            headers={"Accept": "application/json, text/event-stream"},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Module-level pool registry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_and_lookup_by_pool_address():
    gateway = AgentToolGateway()
    await gateway.start()
    try:
        register_agent_tool_gateway("127.0.0.1:99999", gateway)
        assert agent_tool_gateway_for("127.0.0.1:99999") is gateway
    finally:
        unregister_agent_tool_gateway("127.0.0.1:99999")
        await gateway.stop()


@pytest.mark.asyncio
async def test_lookup_unknown_pool_raises_keyerror():
    with pytest.raises(KeyError, match="No agent tool gateway registered"):
        agent_tool_gateway_for("127.0.0.1:0")


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_tool_calls_dispatch_correctly(gateway: AgentToolGateway):
    """Many concurrent tool calls across many actors all land in the right handler."""
    sinks: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    urls: dict[str, str] = {}
    for i in range(5):
        uid = f"concurrent-{i}"
        sinks[uid] = []
        urls[uid] = await gateway.register(
            uid, ["submit_implementation"], _record_handler(sinks[uid])
        )

    async def call_tool_for(uid: str, payload: str) -> None:
        async with streamablehttp_client(urls[uid]) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool("submit_implementation", {"summary": payload})

    await asyncio.gather(*[call_tool_for(uid, f"payload-{uid}") for uid in urls])

    for uid, sink in sinks.items():
        assert len(sink) == 1
        name, args = sink[0]
        assert name == "submit_implementation"
        assert args["summary"] == f"payload-{uid}"


# ---------------------------------------------------------------------------
# SubprocessQuota wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gateway_without_max_subprocesses_has_no_quota():
    """Default construction (no cap) leaves ``subprocess_quota = None``."""
    gateway = AgentToolGateway()
    try:
        assert gateway.subprocess_quota is None
    finally:
        await gateway.stop()


@pytest.mark.asyncio
async def test_gateway_with_max_subprocesses_exposes_quota():
    """When ``max_subprocesses`` is set, the gateway exposes a quota
    sized to that cap. Executors look up this quota via
    ``agent_tool_gateway_for(pool_address).subprocess_quota``."""
    gateway = AgentToolGateway(max_subprocesses=4)
    try:
        quota = gateway.subprocess_quota
        assert quota is not None
        assert quota.max_subprocesses == 4
    finally:
        await gateway.stop()
