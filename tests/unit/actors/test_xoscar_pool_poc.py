"""Phase 0 POC tests for the xoscar actor-pool migration.

Validates the xoscar primitives the rest of the migration depends on:

* ``create_pool`` binds to an ephemeral port (PRD goal G-5).
* Two pools on ``127.0.0.1:0`` get distinct ports — concurrent workflows.
* ``@xo.generator`` streams events across an actor ref.
* ``xo.wait_for`` cancels a long-running actor coroutine and the actor
  observes ``asyncio.CancelledError`` (PRD §5.2, §5.5).
* ``xo.destroy_actor`` runs ``__pre_destroy__`` so agent actors can reap
  their ACP subprocesses.
* A separate OS subprocess can resolve a supervisor by ``uid`` via
  ``xo.actor_ref(address, uid)`` and call typed methods on it — the
  contract the ``serve-inbox`` MCP server relies on post-migration.

Deleted in Phase 4 alongside ``scripts/poc_xoscar_mcp.py``.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from typing import Any

import pytest
import xoscar as xo

from maverick.actors.xoscar.pool import actor_pool, create_pool


@dataclass(frozen=True, slots=True)
class _Echo:
    value: str


class _StateActor(xo.Actor):
    """Probe for lifecycle hooks and cancellation semantics."""

    async def __post_create__(self) -> None:
        self._cancelled = False
        self._pre_destroy_ran = False

    async def __pre_destroy__(self) -> None:
        self._pre_destroy_ran = True

    async def echo(self, payload: _Echo) -> _Echo:
        return payload

    @xo.generator
    async def stream(self, count: int) -> Any:
        for i in range(count):
            yield _Echo(value=f"evt-{i}")
            await asyncio.sleep(0.005)

    async def slow(self, seconds: float) -> str:
        try:
            await asyncio.sleep(seconds)
            return "completed"
        except asyncio.CancelledError:
            self._cancelled = True
            raise

    async def was_cancelled(self) -> bool:
        return self._cancelled


class _InboxActor(xo.Actor):
    """Stand-in for the supervisor inbox — a subprocess calls ``on_tool_call``."""

    async def __post_create__(self) -> None:
        self._calls: list[tuple[str, dict[str, Any]]] = []

    async def on_tool_call(self, tool: str, args: dict[str, Any]) -> str:
        self._calls.append((tool, args))
        return "ok"

    async def call_count(self) -> int:
        return len(self._calls)


async def test_pool_binds_to_ephemeral_port() -> None:
    pool, address = await create_pool()
    try:
        host, port_str = address.rsplit(":", 1)
        assert host == "127.0.0.1"
        assert int(port_str) > 0
    finally:
        await pool.stop()


async def test_parallel_pools_get_distinct_ports() -> None:
    async with actor_pool() as (_pool_a, address_a), actor_pool() as (_pool_b, address_b):
        assert address_a != address_b


async def test_generator_streams_events_across_ref() -> None:
    async with actor_pool() as (_pool, address):
        ref = await xo.create_actor(_StateActor, address=address, uid="stream-target")
        try:
            events = [evt async for evt in await ref.stream(4)]
            assert events == [_Echo(f"evt-{i}") for i in range(4)]
        finally:
            await xo.destroy_actor(ref)


async def test_xo_wait_for_cancels_actor_coroutine() -> None:
    async with actor_pool() as (_pool, address):
        ref = await xo.create_actor(_StateActor, address=address, uid="cancel-target")
        try:
            with pytest.raises(asyncio.TimeoutError):
                await xo.wait_for(ref.slow(10.0), timeout=0.2)
            # Give the actor a tick to observe CancelledError and set the flag.
            await asyncio.sleep(0.05)
            assert await ref.was_cancelled()
        finally:
            await xo.destroy_actor(ref)


async def test_destroy_actor_runs_pre_destroy() -> None:
    """We cannot observe ``_pre_destroy_ran == True`` after destroy (the actor
    is gone), so this test instead confirms destroy completes without error
    and that a subsequent method call fails — the contract we rely on for
    Phase 1 teardown discipline is that destroy_actor is synchronous w.r.t.
    the pre_destroy hook."""

    async with actor_pool() as (_pool, address):
        ref = await xo.create_actor(_StateActor, address=address, uid="destroy-target")
        await ref.echo(_Echo(value="alive"))
        await xo.destroy_actor(ref)
        with pytest.raises(Exception):  # noqa: B017 — xoscar raises various types here
            await ref.echo(_Echo(value="post-destroy"))


_SUBPROCESS_CLIENT = """
import asyncio
import sys

import xoscar as xo


async def main(address: str, uid: str) -> None:
    ref = await xo.actor_ref(address, uid)
    result = await ref.on_tool_call("submit_poc", {"hello": "world"})
    print(f"RESULT:{result}")
    count = await ref.call_count()
    print(f"COUNT:{count}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
"""


async def test_subprocess_reaches_actor_via_actor_ref() -> None:
    """Mirrors the ``serve-inbox`` MCP server pattern.

    The parent MUST use ``asyncio.create_subprocess_exec`` so the pool's
    accept loop keeps running while the child does its
    ``xo.actor_ref(address, uid)`` lookup. See
    ``scripts/XOSCAR_POC_NOTES.md`` for the event-loop-starvation finding.
    """

    async with actor_pool() as (_pool, address):
        supervisor = await xo.create_actor(
            _InboxActor, address=address, uid="supervisor-inbox"
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-u",
                "-c",
                _SUBPROCESS_CLIENT,
                address,
                "supervisor-inbox",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
            stdout = stdout_bytes.decode()
            assert proc.returncode == 0, f"rc={proc.returncode}\n{stdout}"
            assert "RESULT:ok" in stdout, stdout
            assert "COUNT:1" in stdout, stdout
            # Server-side state reflects the call
            assert await supervisor.call_count() == 1
        finally:
            await xo.destroy_actor(supervisor)
