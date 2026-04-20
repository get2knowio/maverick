"""Tests for :mod:`maverick.actors._bridge`.

The bridge provides the persistent asyncio event loop that Thespian
actors use to run async ACP work. The key behaviors under test:

* ``_run_coro`` runs a coroutine to completion and returns its value.
* On timeout, ``_run_coro`` cancels the underlying task so the loop
  does not accumulate leaked coroutines across retries.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import time

import pytest

from maverick.actors._bridge import ActorAsyncBridge


class _Bridge(ActorAsyncBridge):
    """Bare subclass so the mixin can be instantiated in tests."""


@pytest.fixture
def bridge() -> _Bridge:
    b = _Bridge()
    b._start_async_bridge()
    try:
        yield b
    finally:
        b._stop_async_bridge()


def test_run_coro_returns_value(bridge: _Bridge) -> None:
    async def _work() -> int:
        return 42

    assert bridge._run_coro(_work(), timeout=5.0) == 42


def test_run_coro_propagates_exceptions(bridge: _Bridge) -> None:
    async def _work() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        bridge._run_coro(_work(), timeout=5.0)


def test_run_coro_cancels_task_on_timeout(bridge: _Bridge) -> None:
    cancelled = {"flag": False}
    ready = asyncio.Event()

    async def _hung() -> None:
        # Signal that the coroutine is running, then await an event
        # that will never fire so we depend on cancellation to exit.
        ready.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled["flag"] = True
            raise

    async def _armed() -> None:
        # Wait for _hung to actually enter its await before we let
        # the timeout path trigger. Running on the same loop means
        # the event is the right synchronization primitive.
        await ready.wait()

    # Arm the readiness wait on the bridge loop first. We don't need its
    # result — we just need to make sure _hung is running when we time
    # out.
    future_arm = asyncio.run_coroutine_threadsafe(_armed(), bridge._loop)

    with pytest.raises((TimeoutError, concurrent.futures.TimeoutError)):
        bridge._run_coro(_hung(), timeout=0.3)

    # Give the loop a beat to observe the cancellation.
    deadline = time.monotonic() + 2.0
    while not cancelled["flag"] and time.monotonic() < deadline:
        time.sleep(0.05)

    assert cancelled["flag"], "hung coroutine was not cancelled on timeout"

    # Clean up the arming future so stopping the loop is clean.
    future_arm.cancel()
