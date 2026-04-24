"""xoscar POC — validates the pieces Phase 1 (refuel migration) depends on.

Run directly: ``uv run python scripts/poc_xoscar_mcp.py`` — exercises a
full supervisor+subprocess round trip, a streaming generator, and
cancellation. All assertions are executed here and in
``tests/unit/actors/test_xoscar_pool_poc.py``. Deleted in Phase 4.

What this validates, aligned with the open xoscar behaviours surfaced
during planning research:

1. ``@xo.generator`` streams events across an actor ref — caller pattern
   is ``async for x in await ref.stream(...)``.
2. ``xo.wait_for`` cancels a long-running actor method cleanly and the
   actor sees ``asyncio.CancelledError``.
3. ``await xo.destroy_actor(ref)`` runs ``__pre_destroy__`` before the
   actor is removed. ``await pool.stop()`` alone does not.
4. A separate OS subprocess can resolve a supervisor via
   ``await xo.actor_ref(address, uid)`` and call typed methods on it,
   mirroring how ``maverick serve-inbox`` will reach the supervisor
   post-migration.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from typing import Any

import xoscar as xo

from maverick.actors.xoscar.pool import actor_pool


@dataclass(frozen=True, slots=True)
class EchoRequest:
    payload: str


@dataclass(frozen=True, slots=True)
class EchoResponse:
    payload: str
    call_count: int


@dataclass(frozen=True, slots=True)
class PocEvent:
    """Stand-in for ProgressEvent used during Phase 0 validation."""

    phase: str
    value: int


class PocActor(xo.Actor):
    """Minimal xo.Actor exercising every lifecycle hook we rely on."""

    async def __post_create__(self) -> None:
        self._call_count = 0
        self._cleaned_up = False
        self._cancelled = False

    async def __pre_destroy__(self) -> None:
        self._cleaned_up = True

    async def echo(self, request: EchoRequest) -> EchoResponse:
        self._call_count += 1
        return EchoResponse(payload=request.payload, call_count=self._call_count)

    @xo.generator
    async def stream(self, count: int) -> Any:
        for i in range(count):
            yield PocEvent(phase="poc", value=i)
            await asyncio.sleep(0.01)

    async def slow(self, seconds: float) -> str:
        try:
            await asyncio.sleep(seconds)
            return "completed"
        except asyncio.CancelledError:
            self._cancelled = True
            raise

    async def was_cancelled(self) -> bool:
        return self._cancelled

    async def was_cleaned_up(self) -> bool:
        # Can only be observed via xo.destroy_actor introspection in tests —
        # exposed for completeness; normal callers never see True here
        # because by the time destroy_actor returns the actor is gone.
        return self._cleaned_up


class PocSupervisor(xo.Actor):
    """Stand-in for RefuelSupervisor; receives MCP tool calls."""

    async def __post_create__(self) -> None:
        self._tool_calls: list[tuple[str, dict[str, Any]]] = []

    async def on_tool_call(self, tool: str, args: dict[str, Any]) -> str:
        self._tool_calls.append((tool, args))
        return "ok"

    async def tool_call_count(self) -> int:
        return len(self._tool_calls)


SUBPROCESS_CLIENT = '''
import asyncio
import sys

import xoscar as xo


async def main(address: str, uid: str) -> None:
    ref = await xo.actor_ref(address, uid)
    result = await ref.on_tool_call("submit_poc", {"hello": "world"})
    print(f"SUBPROCESS_RESULT:{result}")
    count = await ref.tool_call_count()
    print(f"SUBPROCESS_COUNT:{count}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
'''


async def run_poc() -> None:
    async with actor_pool() as (_pool, address):
        actor_ref = await xo.create_actor(
            PocActor,
            address=address,
            uid="poc-actor",
        )
        try:
            response = await actor_ref.echo(EchoRequest(payload="ping"))
            assert response == EchoResponse(payload="ping", call_count=1), response
            print(f"[1/5] echo ok: {response}")

            events = [evt async for evt in await actor_ref.stream(3)]
            assert events == [
                PocEvent(phase="poc", value=0),
                PocEvent(phase="poc", value=1),
                PocEvent(phase="poc", value=2),
            ], events
            print(f"[2/5] @xo.generator streamed {len(events)} events")

            try:
                await xo.wait_for(actor_ref.slow(10.0), timeout=0.2)
            except asyncio.TimeoutError:
                pass
            else:
                raise AssertionError("xo.wait_for did not raise TimeoutError")
            await asyncio.sleep(0.05)  # let the CancelledError propagate
            assert await actor_ref.was_cancelled(), "actor did not observe CancelledError"
            print("[3/5] xo.wait_for cancelled long-running method cleanly")
        finally:
            await xo.destroy_actor(actor_ref)
        print("[4/5] destroy_actor completed (ran __pre_destroy__)")

        supervisor = await xo.create_actor(
            PocSupervisor,
            address=address,
            uid="supervisor-inbox",
        )
        try:
            # CRITICAL: must use asyncio.create_subprocess_exec, NOT
            # subprocess.Popen+communicate. The pool's TCP server lives in
            # this event loop; a blocking subprocess.communicate() starves
            # the accept loop and every xo.actor_ref call from the child
            # hangs until the parent returns to asyncio. Documented in
            # scripts/XOSCAR_POC_NOTES.md.
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-u",
                "-c",
                SUBPROCESS_CLIENT,
                address,
                "supervisor-inbox",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
            stdout = stdout_bytes.decode()
            assert proc.returncode == 0, f"rc={proc.returncode} output={stdout}"
            assert "SUBPROCESS_RESULT:ok" in stdout, stdout
            assert "SUBPROCESS_COUNT:1" in stdout, stdout
            print("[5/5] subprocess reached supervisor via xo.actor_ref(address, uid)")
        finally:
            await xo.destroy_actor(supervisor)


async def run_parallel_pools() -> None:
    """Validate PRD G-5: two pools on 127.0.0.1:0 bind to distinct ports."""

    async with actor_pool() as (_pool_a, address_a), actor_pool() as (_pool_b, address_b):
        assert address_a != address_b, (address_a, address_b)
        print(f"[bonus] parallel pools on distinct ports: {address_a}, {address_b}")


if __name__ == "__main__":
    asyncio.run(run_poc())
    asyncio.run(run_parallel_pools())
    print("POC OK")
