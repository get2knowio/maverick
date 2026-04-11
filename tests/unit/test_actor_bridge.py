"""Unit tests for the ActorAsyncBridge mixin."""

from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any

import pytest

from maverick.actors._bridge import ActorAsyncBridge


class _Bridge(ActorAsyncBridge):
    """Minimal concrete subclass for testing — no Thespian dependency."""


def test_start_bridge_creates_running_loop() -> None:
    b = _Bridge()
    b._start_async_bridge()
    try:
        assert b._loop.is_running()
        assert b._thread.is_alive()
        assert b._thread.daemon
    finally:
        b._loop.call_soon_threadsafe(b._loop.stop)


def test_run_coro_returns_result() -> None:
    b = _Bridge()
    b._start_async_bridge()
    try:

        async def double(x: int) -> int:
            await asyncio.sleep(0)
            return x * 2

        assert b._run_coro(double(21), timeout=5) == 42
    finally:
        b._loop.call_soon_threadsafe(b._loop.stop)


def test_run_coro_propagates_exceptions() -> None:
    b = _Bridge()
    b._start_async_bridge()
    try:

        async def fail() -> None:
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            b._run_coro(fail(), timeout=5)
    finally:
        b._loop.call_soon_threadsafe(b._loop.stop)


def test_run_coro_timeout() -> None:
    b = _Bridge()
    b._start_async_bridge()
    try:

        async def slow() -> None:
            await asyncio.sleep(10)

        with pytest.raises(FuturesTimeoutError):
            b._run_coro(slow(), timeout=0.05)
    finally:
        b._loop.call_soon_threadsafe(b._loop.stop)


def test_cleanup_executor_none_is_noop() -> None:
    b = _Bridge()
    b._start_async_bridge()
    try:
        b._cleanup_executor()
    finally:
        b._loop.call_soon_threadsafe(b._loop.stop)


def test_cleanup_executor_missing_attr_is_noop() -> None:
    b = _Bridge()
    b._start_async_bridge()
    try:
        b._cleanup_executor()
    finally:
        b._loop.call_soon_threadsafe(b._loop.stop)


def test_cleanup_executor_invokes_async_cleanup() -> None:
    b = _Bridge()
    b._start_async_bridge()

    class _FakeExecutor:
        def __init__(self) -> None:
            self.cleaned = False

        async def cleanup(self) -> None:
            await asyncio.sleep(0)
            self.cleaned = True

    fake: Any = _FakeExecutor()
    b._executor = fake
    try:
        b._cleanup_executor()
        assert fake.cleaned is True
    finally:
        b._loop.call_soon_threadsafe(b._loop.stop)


def test_cleanup_executor_swallows_errors() -> None:
    b = _Bridge()
    b._start_async_bridge()

    class _BadExecutor:
        async def cleanup(self) -> None:
            raise RuntimeError("teardown failed")

    b._executor = _BadExecutor()
    try:
        b._cleanup_executor()
    finally:
        b._loop.call_soon_threadsafe(b._loop.stop)
