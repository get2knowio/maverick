"""Integration test: pool registers a Squadron-spawned OpenCode handle.

Confirms the Squadron + actor_pool composition end-to-end:

* The Squadron spawns the OpenCode server and is reachable.
* The handle is registered against the pool address so actors can
  look it up.
* On context exit, both the registry entry and the server are gone.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
import xoscar as xo

from maverick.actors.xoscar.pool import actor_pool
from maverick.config import MaverickConfig
from maverick.runtime.opencode import OpenCodeClient
from maverick.squadron.fly import FlySquadron

pytestmark = [pytest.mark.integration, pytest.mark.slow]

if not shutil.which(os.environ.get("OPENCODE_BIN") or "opencode"):
    pytest.skip("opencode binary not on PATH", allow_module_level=True)


class _PingActor(xo.Actor):
    """Actor whose only job is to confirm the runtime registry is wired up."""

    async def get_handle_info(self) -> dict[str, str]:
        from maverick.runtime.opencode import opencode_handle_for

        handle = opencode_handle_for(self.address)
        return {"base_url": handle.base_url, "password_present": str(bool(handle.password))}


async def test_squadron_handle_registered_on_pool(tmp_path: Path) -> None:
    config = MaverickConfig()
    async with FlySquadron(cwd=tmp_path, config=config) as squadron:
        async with actor_pool(opencode_handle=squadron.handle) as (_pool, address):
            actor = await xo.create_actor(_PingActor, address=address, uid="ping-1")
            try:
                info = await actor.get_handle_info()
                assert info["base_url"].startswith("http://")
                assert info["password_present"] == "True"

                # Sanity: the live server answers /global/health (with bogus
                # password we expect a classified error, not a network failure).
                client = OpenCodeClient(base_url=info["base_url"], password="bogus")
                try:
                    from maverick.runtime.opencode import AgentRuntimeError

                    with pytest.raises(AgentRuntimeError):
                        await client.health()
                finally:
                    await client.aclose()
            finally:
                await xo.destroy_actor(actor)


async def test_pool_unregisters_handle_after_exit(tmp_path: Path) -> None:
    address: str | None = None
    config = MaverickConfig()
    async with FlySquadron(cwd=tmp_path, config=config) as squadron:
        async with actor_pool(opencode_handle=squadron.handle) as (_pool, addr):
            address = addr

        # Inside the squadron but outside the pool: handle is unregistered.
        from maverick.runtime.opencode import opencode_handle_for

        assert address is not None
        with pytest.raises(KeyError):
            opencode_handle_for(address)
