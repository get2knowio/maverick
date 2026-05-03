"""Shared fixtures for xoscar actor tests.

Provides ``pool_address`` and ``pool`` fixtures with a fake OpenCode
:class:`OpenCodeServerHandle` registered against the pool address so
mailbox actors built on :class:`OpenCodeAgentMixin` work in tests
without each test wiring its own handle.
"""

from __future__ import annotations

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
    """Yield a pool's external address with a fake OpenCode handle.

    The pool and handle binding are torn down on exit. Tests that create
    actors should ``xo.destroy_actor(ref)`` them explicitly so
    ``__pre_destroy__`` runs before the pool stops.
    """
    invalidate_cache()
    pool, address = await create_pool()
    register_opencode_handle(address, _fake_opencode_handle())
    try:
        yield address
    finally:
        unregister_opencode_handle(address)
        await pool.stop()


@pytest.fixture
async def pool() -> AsyncIterator[tuple[xo.Actor, str]]:
    """Yield ``(pool, address)`` with a fake OpenCode handle registered."""

    invalidate_cache()
    pool_obj, address = await create_pool()
    register_opencode_handle(address, _fake_opencode_handle())
    try:
        yield pool_obj, address
    finally:
        unregister_opencode_handle(address)
        await pool_obj.stop()
