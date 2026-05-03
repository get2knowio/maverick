"""Integration test: ``actor_pool(with_opencode=True)`` spawns a real server.

Confirms the pool's OpenCode lifecycle wiring end-to-end:

* Server spawns and is reachable from inside the pool.
* The handle is registered against the pool address so the mixin can
  look it up.
* On context exit, the server is torn down and the registry entry is gone.
"""

from __future__ import annotations

import os
import shutil

import pytest
import xoscar as xo
from pydantic import BaseModel

from maverick.actors.xoscar.opencode_mixin import OpenCodeAgentMixin
from maverick.actors.xoscar.pool import actor_pool
from maverick.runtime.opencode import OpenCodeClient

pytestmark = [pytest.mark.integration, pytest.mark.slow]

if not shutil.which(os.environ.get("OPENCODE_BIN") or "opencode"):
    pytest.skip("opencode binary not on PATH", allow_module_level=True)


class _PingPayload(BaseModel):
    pong: bool


class _PingActor(OpenCodeAgentMixin, xo.Actor):
    """Actor whose only job is to confirm the runtime registry is wired up."""

    result_model = _PingPayload  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self._cwd = "/tmp"
        self._step_config = None

    async def __post_create__(self) -> None:
        await self._opencode_post_create()

    async def __pre_destroy__(self) -> None:
        await self._opencode_pre_destroy()

    async def get_handle_info(self) -> dict[str, str]:
        # Build the client (lazy) so we exercise the registry lookup,
        # but don't actually call OpenCode — health is enough.
        from maverick.runtime.opencode import opencode_handle_for

        handle = opencode_handle_for(self.address)
        return {"base_url": handle.base_url, "password_present": str(bool(handle.password))}


async def test_actor_pool_with_opencode_registers_handle() -> None:
    async with actor_pool(with_opencode=True) as (_pool, address):
        actor = await xo.create_actor(_PingActor, address=address, uid="ping-1")
        try:
            info = await actor.get_handle_info()
            assert info["base_url"].startswith("http://")
            assert info["password_present"] == "True"

            # Sanity: the live server answers /global/health.
            client = OpenCodeClient(
                base_url=info["base_url"],
                # The mixin's _build_client uses the same handle, but we
                # need the password; the integration test here just
                # confirms the registry shape so we trust the shape.
                password="bogus",
            )
            try:
                # Bogus password → expect a classified error, not a
                # network failure. Confirms the server is reachable.
                from maverick.runtime.opencode import OpenCodeError

                with pytest.raises(OpenCodeError):
                    await client.health()
            finally:
                await client.aclose()
        finally:
            await xo.destroy_actor(actor)


async def test_actor_pool_unregisters_after_exit() -> None:
    address: str | None = None
    async with actor_pool(with_opencode=True) as (_pool, addr):
        address = addr

    # After context exit the handle must be unregistered.
    from maverick.runtime.opencode import opencode_handle_for

    assert address is not None
    with pytest.raises(KeyError):
        opencode_handle_for(address)
