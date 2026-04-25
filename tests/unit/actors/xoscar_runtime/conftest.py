"""Shared fixtures for xoscar actor tests.

Both fixtures bind a process-level :class:`AgentToolGateway` to the pool's
external address so agentic actors (which register with the gateway in
``__post_create__``) work in tests without each test having to wire its own
gateway.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import xoscar as xo

from maverick.actors.xoscar.pool import create_pool
from maverick.tools.agent_inbox.gateway import (
    AgentToolGateway,
    register_agent_tool_gateway,
    unregister_agent_tool_gateway,
)


@pytest.fixture
async def pool_address() -> AsyncIterator[str]:
    """Yield a pool's external address with a bound :class:`AgentToolGateway`.

    The pool and gateway are stopped on teardown. Tests that create actors
    should ``xo.destroy_actor(ref)`` them explicitly so ``__pre_destroy__``
    runs before the pool stops.
    """
    pool, address = await create_pool()
    gateway = AgentToolGateway()
    await gateway.start()
    register_agent_tool_gateway(address, gateway)
    try:
        yield address
    finally:
        unregister_agent_tool_gateway(address)
        await gateway.stop()
        await pool.stop()


@pytest.fixture
async def pool() -> AsyncIterator[tuple[xo.Actor, str]]:
    """Yield ``(pool, address)`` with a bound :class:`AgentToolGateway`."""

    pool_obj, address = await create_pool()
    gateway = AgentToolGateway()
    await gateway.start()
    register_agent_tool_gateway(address, gateway)
    try:
        yield pool_obj, address
    finally:
        unregister_agent_tool_gateway(address)
        await gateway.stop()
        await pool_obj.stop()
