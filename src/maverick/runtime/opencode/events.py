"""Event-stream helpers built atop :meth:`OpenCodeClient.stream_events`.

The client surfaces individual SSE events; this module adds a small
watcher abstraction for actors that want to forward events to a
supervisor while still benefiting from typed error detection
(Landmine 2). Most actors use :meth:`OpenCodeClient.send_with_event_watch`
for the send path; the helpers here are for long-lived listeners that
want to observe ``message.part.delta`` (token streaming) or
``session.diff`` (workspace edits) outside of a single send.

The OpenCode event taxonomy (from the spike's ``probe_events.py``):

============================== =====================================
event type                      meaning
============================== =====================================
``server.connected``            initial handshake
``message.updated``             message lifecycle (assistant ready)
``message.part.updated``        part lifecycle (tool / text)
``message.part.delta``          token streaming
``session.status``              busy/idle transitions
``session.diff``                file changes (workspace tools)
``session.idle``                **reliable completion signal**
``session.error``               provider/model errors (classify!)
============================== =====================================
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from maverick.logging import get_logger
from maverick.runtime.opencode.client import (
    OpenCodeClient,
    classify_session_error,
)
from maverick.runtime.opencode.errors import OpenCodeError

logger = get_logger(__name__)


EventCallback = Callable[[dict[str, Any]], Awaitable[None]]
"""Async callback invoked with each event yielded by the watcher."""


# Events this module forwards by default. Restrict to a useful subset to
# avoid swamping the supervisor with token-deltas.
DEFAULT_FORWARD_TYPES: frozenset[str] = frozenset(
    {
        "session.idle",
        "session.error",
        "message.updated",
        "message.part.updated",
        "session.diff",
    }
)


class EventWatcher:
    """Background task that reads events for one session and dispatches them.

    Typical use::

        watcher = EventWatcher(client, session_id, on_event=fwd)
        await watcher.start()
        ...
        await watcher.stop()

    The watcher runs until the session reaches ``session.idle`` OR
    :meth:`stop` is called. ``session.error`` events are surfaced via the
    callback; callers that want them as Python exceptions should use
    :meth:`OpenCodeClient.send_with_event_watch` instead.
    """

    def __init__(
        self,
        client: OpenCodeClient,
        session_id: str,
        *,
        on_event: EventCallback | None = None,
        forward_types: frozenset[str] = DEFAULT_FORWARD_TYPES,
        stop_on_idle: bool = True,
    ) -> None:
        self._client = client
        self._session_id = session_id
        self._on_event = on_event
        self._forward_types = forward_types
        self._stop_on_idle = stop_on_idle
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Spawn the background drain task."""
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name=f"opencode-events-{self._session_id}")

    async def stop(self) -> None:
        """Cancel and await the drain task. Idempotent."""
        if self._task is None:
            return
        if not self._task.done():
            self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001
            if not isinstance(exc, asyncio.CancelledError):
                logger.debug(
                    "opencode.events_watcher_stopped_with_error",
                    error=str(exc)[:200],
                )
        finally:
            self._task = None

    async def _run(self) -> None:
        try:
            async for evt in self._client.stream_events(session_id=self._session_id):
                evt_type = evt.get("type") or ""
                if self._on_event is not None and evt_type in self._forward_types:
                    try:
                        await self._on_event(evt)
                    except Exception as cb_exc:  # noqa: BLE001 — callbacks must not break the watcher
                        logger.debug(
                            "opencode.events_callback_error",
                            event_type=evt_type,
                            error=str(cb_exc)[:200],
                        )
                if evt_type == "session.idle" and self._stop_on_idle:
                    return
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001 — surface but never raise
            logger.debug(
                "opencode.events_watcher_stream_failed",
                session_id=self._session_id,
                error=str(exc)[:200],
            )


async def collect_events(
    client: OpenCodeClient,
    session_id: str,
    *,
    until: str = "session.idle",
    timeout: float | None = None,
) -> list[dict[str, Any]]:
    """Drain events for ``session_id`` until the named ``until`` event arrives.

    Useful for tests and one-shot probes. Returns the list of events
    received (including the terminal one). Raises :class:`asyncio.TimeoutError`
    when ``timeout`` elapses.
    """

    async def _read() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        async for evt in client.stream_events(session_id=session_id):
            out.append(evt)
            if (evt.get("type") or "") == until:
                return out
        return out

    if timeout is None:
        return await _read()
    return await asyncio.wait_for(_read(), timeout=timeout)


async def first_error(
    client: OpenCodeClient,
    session_id: str,
    *,
    timeout: float | None = None,
) -> OpenCodeError | None:
    """Return the first classified ``session.error`` for the session, or ``None``.

    Resolves to ``None`` when the session reaches ``session.idle`` cleanly.
    """

    async def _watch() -> OpenCodeError | None:
        async for evt in client.stream_events(session_id=session_id):
            t = evt.get("type") or ""
            if t == "session.error":
                err_obj = (evt.get("properties") or {}).get("error") or {}
                return classify_session_error(err_obj)
            if t == "session.idle":
                return None
        return None

    if timeout is None:
        return await _watch()
    return await asyncio.wait_for(_watch(), timeout=timeout)


async def session_idle_signal(
    client: OpenCodeClient,
    session_id: str,
) -> AsyncIterator[dict[str, Any]]:
    """Async iterator that yields events until ``session.idle`` is observed.

    Convenience wrapper for callers that want to react to events as they
    arrive without writing the loop themselves.
    """
    async for evt in client.stream_events(session_id=session_id):
        yield evt
        if (evt.get("type") or "") == "session.idle":
            return
