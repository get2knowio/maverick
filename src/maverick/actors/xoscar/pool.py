"""xoscar actor-pool lifecycle helpers.

xoscar binds to an ephemeral port instead of the hardcoded 19500 the
legacy Thespian runtime used, so there is no stale-daemon problem and
no port-coordination problem between concurrent workflows.

Single-process model (``n_process=0``) is intentional — all actors run
as coroutines in the pool's event loop, so process isolation comes from
the OpenCode subprocess rather than the actor runtime.

The actor-pool wrapper spawns one OpenCode HTTP server per workflow run
(via :func:`spawn_opencode_server`) and registers its handle against the
pool address so :class:`OpenCodeAgentMixin`-based actors can look it up
via ``opencode_handle_for(self.address)``. Spawn defaults to ON since
every mailbox actor now uses OpenCode; pass ``with_opencode=False`` for
tests or special workflows that don't need the runtime.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import xoscar as xo

from maverick.logging import get_logger
from maverick.runtime.opencode import (
    OpenCodeServerHandle,
    Tier,
    register_opencode_handle,
    register_tier_overrides,
    spawn_opencode_server,
    unregister_opencode_handle,
    unregister_tier_overrides,
)

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
    (verified against xoscar 0.9.5 source), so agent actors that need
    to release resources must be destroyed explicitly first. Each
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
    *,
    with_opencode: bool = True,
    opencode_handle: OpenCodeServerHandle | None = None,
    provider_tiers: dict[str, Tier] | None = None,
) -> AsyncIterator[tuple[MainActorPoolType, str]]:
    """Context manager for a short-lived actor pool + OpenCode server.

    Yields ``(pool, external_address)``. The pool is stopped on exit,
    but actor refs are NOT destroyed automatically — the caller is
    responsible for collecting the refs it creates and passing them to
    ``teardown_pool`` (or calling ``xo.destroy_actor`` in reverse order)
    before the context exits so each actor's ``__pre_destroy__`` runs.

    Args:
        address: xoscar pool bind address. Default picks an ephemeral
            port on loopback.
        with_opencode: When ``True`` (default), spawn an OpenCode HTTP
            server for this pool's lifetime and register its handle so
            mailbox actors can use it. Set to ``False`` for tests or
            workflows that don't need the runtime.
        opencode_handle: Pre-spawned OpenCode server handle. When given,
            the pool registers it but does not spawn or terminate it
            (caller owns the lifecycle).
        provider_tiers: Optional ``{tier_name: Tier}`` map registered on
            the pool address so :class:`OpenCodeAgentMixin`-based actors
            pick up user-config tier overrides without each constructor
            taking it as an argument. ``None`` (the default) leaves the
            runtime on :data:`DEFAULT_TIERS`.

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

    owns_opencode = False
    bound_opencode: OpenCodeServerHandle | None = opencode_handle
    if bound_opencode is None and with_opencode:
        try:
            bound_opencode = await spawn_opencode_server()
            owns_opencode = True
        except Exception:  # noqa: BLE001 — surface spawn failures to the caller
            try:
                await pool.stop()
            except Exception as stop_exc:  # noqa: BLE001 — diagnostic only
                logger.debug("xoscar.pool_stop_failed_during_unwind", error=str(stop_exc))
            raise
    if bound_opencode is not None:
        register_opencode_handle(external_address, bound_opencode)
        logger.debug(
            "xoscar.opencode_bound",
            pool=external_address,
            opencode=bound_opencode.base_url,
            owns=owns_opencode,
        )

    if provider_tiers:
        register_tier_overrides(external_address, provider_tiers)
        logger.debug(
            "xoscar.tier_overrides_bound",
            pool=external_address,
            tiers=sorted(provider_tiers.keys()),
        )

    try:
        yield pool, external_address
    finally:
        if provider_tiers:
            unregister_tier_overrides(external_address)
        if bound_opencode is not None:
            unregister_opencode_handle(external_address)
            if owns_opencode:
                try:
                    await bound_opencode.stop()
                except Exception as exc:  # noqa: BLE001 — exit must not raise
                    logger.debug("xoscar.opencode_stop_failed", error=str(exc))
        try:
            await pool.stop()
        except Exception as exc:  # noqa: BLE001 — context exit must not raise
            logger.debug("xoscar.pool_stop_failed", error=str(exc))
