"""Burr ``Application`` driver — wraps ``arun()`` into an event stream.

The driver follows the producer/consumer pattern verified in the Phase 0
spikes:

* ``Application.arun()`` runs as a background ``asyncio.Task``.
* Actions and a :class:`~maverick.burr.hooks.ProgressEventHook` push
  :class:`maverick.events.ProgressEvent` instances into an
  ``asyncio.Queue``; the hook enqueues a ``None`` sentinel after the
  terminal action's ``post_run_step`` to signal end-of-stream.
* :meth:`BurrWorkflowDriver.events` drains the queue, yielding each
  event to the consumer in real time (Spike 3 measured sub-millisecond
  emit→consume lag).
* After the consumer finishes iterating, ``result`` exposes the tuple
  returned by ``Application.arun()`` for downstream use.

This is the airframe-side analogue of the xoscar supervisor's
``@xo.generator run()`` drain (see
:meth:`maverick.workflows.base.PythonWorkflow._drain_xoscar_supervisor`).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from burr.core import Application

    from maverick.events import ProgressEvent

__all__ = ["BurrWorkflowDriver"]


class BurrWorkflowDriver:
    """Run a Burr ``Application`` and stream its ProgressEvents.

    Usage::

        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        app = build_plan_application(squadron, queue)
        driver = BurrWorkflowDriver(
            app, halt_after=["write_plan"], event_queue=queue,
        )
        async for event in driver.events():
            ...
        last_action, result, state = driver.result

    Args:
        app: A built :class:`burr.core.Application`.
        halt_after: Action names that, when completed, terminate the
            run. Forwarded to ``app.arun(halt_after=...)``.
        event_queue: The same queue the application's hook and actions
            push :class:`ProgressEvent` instances into. The driver
            drains it until it receives a ``None`` sentinel.
    """

    def __init__(
        self,
        app: Application,
        *,
        halt_after: Sequence[str],
        event_queue: asyncio.Queue[ProgressEvent | None],
    ) -> None:
        if not halt_after:
            raise ValueError("halt_after must name at least one terminal action")
        self._app = app
        self._halt_after = list(halt_after)
        self._queue = event_queue
        self._result: tuple[Any, Any, Any] | None = None
        self._exception: BaseException | None = None

    async def events(self) -> AsyncIterator[ProgressEvent]:
        """Drive the application and yield emitted events.

        The application task runs concurrently with this iterator. When
        a terminal action completes, the hook enqueues ``None``; the
        iterator returns and the application task is awaited so any
        exception surfaces to :attr:`result`. Cancelling the wrapping
        task propagates through Burr cleanly (Spike 4).

        On natural exit (sentinel received) we *do not* cancel the
        application task — cancelling races with Burr's in-flight
        exception propagation and replaces the underlying error with
        ``CancelledError``. We only cancel when the consumer bails out
        without draining (consumer-side break, exception, GeneratorExit).
        """
        app_task: asyncio.Task[tuple[Any, Any, Any]] = asyncio.create_task(
            self._app.arun(halt_after=self._halt_after)
        )
        saw_sentinel = False
        try:
            while True:
                evt = await self._queue.get()
                if evt is None:
                    saw_sentinel = True
                    break
                yield evt
        finally:
            if not saw_sentinel and not app_task.done():
                app_task.cancel()
            try:
                self._result = await app_task
            except BaseException as exc:  # noqa: BLE001
                self._exception = exc

    @property
    def result(self) -> tuple[Any, Any, Any]:
        """The ``(last_action, result, state)`` tuple ``app.arun()`` returned.

        Raises:
            BaseException: If the application task raised. The original
                exception is re-raised here (including
                ``asyncio.CancelledError`` on cancelled runs).
            RuntimeError: If ``events()`` hasn't been drained yet.
        """
        if self._exception is not None:
            raise self._exception
        if self._result is None:
            raise RuntimeError(
                "BurrWorkflowDriver.events() must be drained before reading .result"
            )
        return self._result
