"""xoscar actor-pool lifecycle helpers.

These helpers replace ``create_actor_system`` / ``cleanup_stale_admin``
from ``src/maverick/actors/__init__.py``: xoscar binds to an ephemeral
port instead of the hardcoded 19500, so there is no stale-daemon problem
and no port-coordination problem between concurrent workflows.

Single-process model (``n_process=0``) is intentional — all actors run
as coroutines in the pool's event loop, which skips pickling ACP
executors and matches the in-process semantics already used by
``src/maverick/workflows/fly_beads/actors/``. Process isolation
continues to come from the ACP agent subprocess each agent actor owns,
not from the actor runtime.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import xoscar as xo

from maverick.logging import get_logger

if TYPE_CHECKING:
    from xoscar.backends.pool import MainActorPoolType

logger = get_logger(__name__)

DEFAULT_POOL_ADDRESS = "127.0.0.1:0"


async def create_pool(address: str = DEFAULT_POOL_ADDRESS) -> tuple[MainActorPoolType, str]:
    """Create a single-process xoscar actor pool bound to an ephemeral port.

    Returns the pool and its resolved external address (host:port). The
    caller passes ``external_address`` to
    ``xo.create_actor(..., address=...)`` when creating actors, and to
    ``xo.actor_ref(address, uid)`` from subprocesses that need to reach
    the pool.
    """
    pool = await xo.create_actor_pool(address, n_process=0)
    external_address = pool.external_address
    logger.debug("xoscar.pool_created", address=external_address)
    return pool, external_address


async def teardown_pool(
    pool: MainActorPoolType,
    refs: Sequence[xo.ActorRef] = (),
) -> None:
    """Tear down an actor pool, running ``__pre_destroy__`` for each ref.

    ``pool.stop()`` alone does not invoke ``__pre_destroy__`` per actor
    (verified against xoscar 0.9.5 source), so agent actors that need to
    reap ACP subprocesses must be destroyed explicitly first. Each
    ``destroy_actor`` failure is logged and swallowed so teardown is
    always best-effort.
    """
    for ref in refs:
        try:
            await xo.destroy_actor(ref)
        except Exception as exc:  # noqa: BLE001 — teardown must not raise
            logger.debug(
                "xoscar.destroy_actor_failed",
                uid=getattr(ref, "uid", "?"),
                error=str(exc),
            )
    try:
        await pool.stop()
    except Exception as exc:  # noqa: BLE001 — teardown must not raise
        logger.debug("xoscar.pool_stop_failed", error=str(exc))


@asynccontextmanager
async def actor_pool(
    address: str = DEFAULT_POOL_ADDRESS,
) -> AsyncIterator[tuple[MainActorPoolType, str]]:
    """Context manager for a short-lived actor pool.

    Yields ``(pool, external_address)``. The pool is stopped on exit,
    but actor refs are NOT destroyed automatically — the caller is
    responsible for collecting the refs it creates and passing them to
    ``teardown_pool`` (or calling ``xo.destroy_actor`` in reverse order)
    before the context exits so each actor's ``__pre_destroy__`` runs.

    Typical use::

        async with actor_pool() as (pool, address):
            sup = await xo.create_actor(RefuelSupervisor, address=address, ...)
            try:
                async for event in await sup.run(inputs):
                    yield event
            finally:
                await xo.destroy_actor(sup)
    """
    pool, external_address = await create_pool(address)
    try:
        yield pool, external_address
    finally:
        try:
            await pool.stop()
        except Exception as exc:  # noqa: BLE001 — context exit must not raise
            logger.debug("xoscar.pool_stop_failed", error=str(exc))
