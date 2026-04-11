"""Async bridge mixin for Thespian actors that run async ACP work.

Thespian's ``receiveMessage`` is synchronous, but ACP's ``prompt_session``
and executor cleanup are async. The CLAUDE.md guidance is to keep a
persistent background event loop + daemon thread per actor and hand
coroutines to it via ``asyncio.run_coroutine_threadsafe``. Using
``asyncio.run()`` instead tears down async generators (ACP's stdio
transport) on every call.

This mixin centralizes that pattern so actors don't each reimplement it.

Usage:

    class MyActor(ActorAsyncBridge, Actor):
        def receiveMessage(self, message, sender):
            if message.get("type") == "init":
                self._start_async_bridge()
                self._executor = None
                self._session_id = None
                self.send(sender, {"type": "init_ok"})
            elif message.get("type") == "work":
                try:
                    self._run_coro(self._do_async_work(message), timeout=1800)
                    self.send(sender, {"type": "ok"})
                except Exception as exc:
                    self.send(sender, {"type": "error", "error": str(exc)})
            elif message.get("type") == "shutdown":
                self._cleanup_executor()
                self.send(sender, {"type": "shutdown_ok"})
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

from maverick.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class ActorAsyncBridge:
    """Mixin providing a persistent asyncio loop for Thespian actors.

    Subclasses must call :meth:`_start_async_bridge` once (typically
    during their ``init`` message handler). They may set
    ``self._executor`` to an ACP executor; :meth:`_cleanup_executor`
    will call ``executor.cleanup()`` on the bridge loop.
    """

    _loop: asyncio.AbstractEventLoop
    _thread: threading.Thread
    _executor: Any

    def _start_async_bridge(self) -> None:
        """Create the background event loop + daemon thread."""
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    def _run_coro(self, coro: Coroutine[Any, Any, T], *, timeout: float) -> T:
        """Schedule ``coro`` on the bridge loop and block until it finishes.

        Raises whatever the coroutine raises, plus
        :class:`concurrent.futures.TimeoutError` if it doesn't complete
        within ``timeout`` seconds.
        """
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def _cleanup_executor(self, *, timeout: float = 5.0) -> None:
        """Best-effort cleanup of ``self._executor`` on the bridge loop.

        Safe to call when no executor was ever created. Never raises —
        errors are logged at debug level because this runs on the
        shutdown path.
        """
        executor = getattr(self, "_executor", None)
        if executor is None:
            return
        try:
            self._run_coro(executor.cleanup(), timeout=timeout)
        except Exception as exc:
            logger.debug("actor_bridge.cleanup_failed", error=str(exc))
