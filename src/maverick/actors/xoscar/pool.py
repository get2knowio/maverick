"""xoscar actor-pool lifecycle helpers.

xoscar binds to an ephemeral port instead of the hardcoded 19500 the
legacy Thespian runtime used, so there is no stale-daemon problem and
no port-coordination problem between concurrent workflows.

Single-process model (``n_process=0``) is intentional — all actors run
as coroutines in the pool's event loop, which skips pickling ACP
executors and matches the in-process semantics used by
``src/maverick/workflows/fly_beads/actors/``. Process isolation
continues to come from the ACP agent subprocess each agent actor owns,
not from the actor runtime.

The actor-pool wrapper also owns a process-level
:class:`AgentToolGateway`: a single shared HTTP MCP server that fronts
every agent actor's tool calls via ``/mcp/<uid>`` routing. Agent actors
register with the gateway in ``__post_create__`` (via
:class:`AgenticActorMixin`) and unregister in ``__pre_destroy__``. The
gateway lifetime brackets the pool's: it starts after the pool is up
and stops before the pool tears down.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import xoscar as xo

from maverick.logging import get_logger
from maverick.tools.agent_inbox.gateway import (
    AgentToolGateway,
    register_agent_tool_gateway,
    unregister_agent_tool_gateway,
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
    *,
    max_subprocesses: int | None = None,
) -> AsyncIterator[tuple[MainActorPoolType, str]]:
    """Context manager for a short-lived actor pool with shared MCP gateway.

    Yields ``(pool, external_address)``. The pool is stopped on exit,
    but actor refs are NOT destroyed automatically — the caller is
    responsible for collecting the refs it creates and passing them to
    ``teardown_pool`` (or calling ``xo.destroy_actor`` in reverse order)
    before the context exits so each actor's ``__pre_destroy__`` runs.

    A pool-scoped :class:`AgentToolGateway` is started before the body
    and bound to the pool's external address via
    ``register_agent_tool_gateway``; agentic actors look it up via
    ``agent_tool_gateway_for(self.address)`` and register their tool
    subset on creation. The gateway is shut down after the body, after
    the pool has stopped.

    Args:
        address: xoscar pool bind address. Default picks an ephemeral
            port on loopback.
        max_subprocesses: Optional global cap on live ACP agent
            subprocesses across the pool. When set, the gateway's
            :class:`SubprocessQuota` enforces it via LRU eviction of
            idle actors. ``None`` disables enforcement (legacy
            behaviour — each actor spawns freely).

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

    gateway = AgentToolGateway(max_subprocesses=max_subprocesses)
    try:
        await gateway.start()
    except Exception:  # noqa: BLE001 — surface gateway failures to the caller
        try:
            await pool.stop()
        except Exception as stop_exc:  # noqa: BLE001 — diagnostic only
            logger.debug("xoscar.pool_stop_failed_during_unwind", error=str(stop_exc))
        raise
    register_agent_tool_gateway(external_address, gateway)
    logger.debug("xoscar.gateway_bound", pool=external_address, gateway=gateway.base_url)

    try:
        yield pool, external_address
    finally:
        unregister_agent_tool_gateway(external_address)
        try:
            await gateway.stop()
        except Exception as exc:  # noqa: BLE001 — exit must not raise
            logger.debug("xoscar.gateway_stop_failed", error=str(exc))
        try:
            await pool.stop()
        except Exception as exc:  # noqa: BLE001 — context exit must not raise
            logger.debug("xoscar.pool_stop_failed", error=str(exc))
