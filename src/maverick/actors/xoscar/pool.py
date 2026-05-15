"""xoscar actor-pool lifecycle helpers.

xoscar binds to an ephemeral port instead of the hardcoded 19500 the
legacy Thespian runtime used, so there is no stale-daemon problem and
no port-coordination problem between concurrent workflows.

Single-process model (``n_process=0``) is intentional — all actors run
as coroutines in the pool's event loop, so process isolation comes from
the OpenCode subprocess rather than the actor runtime.

The pool no longer owns the OpenCode server lifecycle — that moved to
:class:`maverick.squadron.Squadron`, which validates tier bindings at
startup and exposes the handle / tier overrides / cost sink that the
pool registers against its address. Pass ``opencode_handle=squadron.handle``
when entering :func:`actor_pool` so actors can keep looking up the
handle via ``opencode_handle_for(self.address)``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import xoscar as xo

from maverick.logging import get_logger
from maverick.runtime.opencode import (
    CostSink,
    OpenCodeServerHandle,
    Tier,
    register_cost_sink,
    register_opencode_handle,
    register_tier_overrides,
    unregister_cost_sink,
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
    opencode_handle: OpenCodeServerHandle | None = None,
    provider_tiers: dict[str, Tier] | None = None,
    cost_sink: CostSink | None = None,
) -> AsyncIterator[tuple[MainActorPoolType, str]]:
    """Context manager for a short-lived actor pool.

    Yields ``(pool, external_address)``. The pool is stopped on exit,
    but actor refs are NOT destroyed automatically — the caller is
    responsible for collecting the refs it creates and passing them to
    ``teardown_pool`` (or calling ``xo.destroy_actor`` in reverse order)
    before the context exits so each actor's ``__pre_destroy__`` runs.

    Args:
        address: xoscar pool bind address. Default picks an ephemeral
            port on loopback.
        opencode_handle: OpenCode server handle to register on the
            pool address so mailbox actors can look it up via
            ``opencode_handle_for(self.address)``. The pool does NOT
            spawn or terminate the server — that's the squadron's
            job. Pass ``squadron.handle``.
        provider_tiers: Optional ``{tier_name: Tier}`` map registered
            on the pool address so agent classes pick up user-config
            tier overrides without each constructor taking it as an
            argument. Pass ``squadron.tier_overrides``.
        cost_sink: Optional async callable invoked with each
            :class:`CostEntry` produced by mailbox sends. Pass
            ``squadron.cost_sink``.

    Typical use::

        async with FlySquadron(cwd=cwd, config=cfg, cost_sink=sink) as squadron:
            async with actor_pool(
                opencode_handle=squadron.handle,
                provider_tiers=squadron.tier_overrides,
                cost_sink=squadron.cost_sink,
            ) as (pool, address):
                sup = await xo.create_actor(FlySupervisor, address=address, ...)
                try:
                    async for event in await sup.run(inputs):
                        yield event
                finally:
                    await xo.destroy_actor(sup)
    """
    pool, external_address = await create_pool(address)

    if opencode_handle is not None:
        register_opencode_handle(external_address, opencode_handle)
        logger.debug(
            "xoscar.opencode_bound",
            pool=external_address,
            opencode=opencode_handle.base_url,
        )

    if provider_tiers:
        register_tier_overrides(external_address, provider_tiers)
        logger.debug(
            "xoscar.tier_overrides_bound",
            pool=external_address,
            tiers=sorted(provider_tiers.keys()),
        )

    if cost_sink is not None:
        register_cost_sink(external_address, cost_sink)
        logger.debug("xoscar.cost_sink_bound", pool=external_address)

    try:
        yield pool, external_address
    finally:
        if cost_sink is not None:
            unregister_cost_sink(external_address)
        if provider_tiers:
            unregister_tier_overrides(external_address)
        if opencode_handle is not None:
            unregister_opencode_handle(external_address)
        try:
            await pool.stop()
        except Exception as exc:  # noqa: BLE001 — context exit must not raise
            logger.debug("xoscar.pool_stop_failed", error=str(exc))
