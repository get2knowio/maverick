"""Shared fixtures for xoscar actor tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import xoscar as xo

from maverick.actors.xoscar.pool import create_pool


@pytest.fixture
async def pool_address() -> AsyncIterator[str]:
    """Yield ``(pool, external_address)``-style address for a fresh pool.

    The pool is stopped on teardown. Tests that create actors should
    ``xo.destroy_actor(ref)`` them explicitly so ``__pre_destroy__``
    runs before the pool stops.
    """
    pool, address = await create_pool()
    try:
        yield address
    finally:
        await pool.stop()


@pytest.fixture
async def pool() -> AsyncIterator[tuple[xo.Actor, str]]:
    """Yield the actual pool alongside its address when tests need both."""

    pool_obj, address = await create_pool()
    try:
        yield pool_obj, address
    finally:
        await pool_obj.stop()
