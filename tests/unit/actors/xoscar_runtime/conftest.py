"""Shared fixtures for xoscar actor tests.

Both fixtures bind a process-level :class:`AgentToolGateway` (legacy ACP
mailbox transport) and a fake OpenCode :class:`OpenCodeServerHandle`
(new substrate) to the pool's external address. That lets tests run
against either path without re-wiring per-test.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
import xoscar as xo

from maverick.actors.xoscar.pool import create_pool
from maverick.runtime.opencode import (
    OpenCodeServerHandle,
    invalidate_cache,
    register_opencode_handle,
    unregister_opencode_handle,
)
from maverick.tools.agent_inbox.gateway import (
    AgentToolGateway,
    register_agent_tool_gateway,
    unregister_agent_tool_gateway,
)


class _FakeProcess:
    """Stub for asyncio.subprocess.Process inside an OpenCodeServerHandle."""

    pid = 0
    returncode = 0

    def terminate(self) -> None:
        pass

    def kill(self) -> None:
        pass

    async def wait(self) -> int:
        return 0


def _fake_opencode_handle() -> OpenCodeServerHandle:
    return OpenCodeServerHandle(
        base_url="http://fake-opencode",
        password="fake",
        pid=0,
        _process=_FakeProcess(),  # type: ignore[arg-type]
    )


@pytest.fixture
async def pool_address() -> AsyncIterator[str]:
    """Yield a pool's external address with both substrates registered.

    The pool, gateway, and OpenCode handle are torn down on exit. Tests
    that create actors should ``xo.destroy_actor(ref)`` them explicitly so
    ``__pre_destroy__`` runs before the pool stops.
    """
    invalidate_cache()
    pool, address = await create_pool()
    gateway = AgentToolGateway()
    await gateway.start()
    register_agent_tool_gateway(address, gateway)
    register_opencode_handle(address, _fake_opencode_handle())
    try:
        yield address
    finally:
        unregister_opencode_handle(address)
        unregister_agent_tool_gateway(address)
        await gateway.stop()
        await pool.stop()


@pytest.fixture
async def pool() -> AsyncIterator[tuple[xo.Actor, str]]:
    """Yield ``(pool, address)`` with both substrates registered."""

    invalidate_cache()
    pool_obj, address = await create_pool()
    gateway = AgentToolGateway()
    await gateway.start()
    register_agent_tool_gateway(address, gateway)
    register_opencode_handle(address, _fake_opencode_handle())
    try:
        yield pool_obj, address
    finally:
        unregister_opencode_handle(address)
        unregister_agent_tool_gateway(address)
        await gateway.stop()
        await pool_obj.stop()


_ = asyncio  # keep import for downstream test files that subclass via `inspect`
