"""Per-actor-pool registry of running OpenCode server handles.

Mirrors :func:`maverick.tools.agent_inbox.gateway.agent_tool_gateway_for` so
:class:`OpenCodeAgentMixin` can look up the server handle by the pool's
external address (which actors expose as ``self.address``). Plays the same
role: actors don't construct the runtime themselves; they receive it via
the pool's lifecycle.
"""

from __future__ import annotations

from maverick.runtime.opencode.server import OpenCodeServerHandle

__all__ = [
    "opencode_handle_for",
    "register_opencode_handle",
    "unregister_opencode_handle",
]


_handle_by_pool: dict[str, OpenCodeServerHandle] = {}


def opencode_handle_for(pool_address: str) -> OpenCodeServerHandle:
    """Return the handle bound to ``pool_address``.

    Raises:
        KeyError: when no handle is registered — typically means the actor
            was constructed outside an ``actor_pool(with_opencode=True)``
            context, or the spawn failed.
    """
    try:
        return _handle_by_pool[pool_address]
    except KeyError as exc:
        raise KeyError(
            f"No OpenCode server registered for pool {pool_address!r}. "
            "Was the actor created inside actor_pool(with_opencode=True)?"
        ) from exc


def register_opencode_handle(pool_address: str, handle: OpenCodeServerHandle) -> None:
    """Bind a server handle to a pool address. Overwrites any existing binding."""
    _handle_by_pool[pool_address] = handle


def unregister_opencode_handle(pool_address: str) -> None:
    """Remove the binding for a pool address. No-op when missing."""
    _handle_by_pool.pop(pool_address, None)
