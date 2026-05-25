"""Burr lifecycle hooks that translate to maverick :mod:`events`.

:class:`ProgressEventHook` is wired into a Burr ``Application`` via
``ApplicationBuilder().with_hooks(hook)``. It converts every action's
``pre_run_step`` / ``post_run_step`` into a :class:`StepStarted` /
:class:`StepCompleted` push onto an ``asyncio.Queue`` shared with the
driver. After the terminal action's ``post_run_step``, the hook enqueues
a ``None`` sentinel to signal end-of-stream.

Async hooks are required: Burr's sync ``PreRunStepHook`` /
``PostRunStepHook`` base classes call hook methods synchronously, so
``async def`` methods on the sync bases silently produce un-awaited
coroutine warnings. Inherit from the ``*Async`` variants instead.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from burr.lifecycle import PostRunStepHookAsync, PreRunStepHookAsync

from maverick.events import ProgressEvent, StepCompleted, StepStarted
from maverick.types import StepType

if TYPE_CHECKING:
    import asyncio

    from burr.core import State

__all__ = ["ProgressEventHook"]


class ProgressEventHook(PreRunStepHookAsync, PostRunStepHookAsync):
    """Emit :class:`StepStarted` / :class:`StepCompleted` per Burr action.

    Args:
        queue: The shared event queue the driver drains. The hook puts
            :class:`ProgressEvent` instances here; it also enqueues
            ``None`` after the terminal action so the driver knows to
            stop.
        terminal_actions: Action names that signal end-of-stream. Match
            the ``halt_after`` set on the driver.
        action_labels: Optional human-readable label per action name
            (e.g. ``{"select_next_bead": "Picking next bead"}``). Falls
            back to the action name itself.
        step_type: Default :class:`StepType` for emitted events. The
            existing CLI Rich progress renderer keys off this for
            display styling.
    """

    def __init__(
        self,
        queue: asyncio.Queue[ProgressEvent | None],
        *,
        terminal_actions: Sequence[str],
        action_labels: Mapping[str, str] | None = None,
        step_type: StepType = StepType.AGENT,
    ) -> None:
        if not terminal_actions:
            raise ValueError("terminal_actions must name at least one action")
        self._queue = queue
        self._terminal = frozenset(terminal_actions)
        self._labels = dict(action_labels or {})
        self._step_type = step_type
        self._start_times: dict[str, float] = {}

    async def pre_run_step(self, *, action: Any, state: State, **_kw: Any) -> None:
        name = action.name
        self._start_times[name] = time.monotonic()
        await self._queue.put(
            StepStarted(
                step_name=name,
                step_type=self._step_type,
                display_label=self._labels.get(name, name),
            )
        )

    async def post_run_step(
        self,
        *,
        action: Any,
        state: State,
        result: Any,
        exception: BaseException | None,
        **_kw: Any,
    ) -> None:
        name = action.name
        start = self._start_times.pop(name, time.monotonic())
        duration_ms = int((time.monotonic() - start) * 1000)
        await self._queue.put(
            StepCompleted(
                step_name=name,
                step_type=self._step_type,
                success=exception is None,
                duration_ms=duration_ms,
                error=str(exception) if exception else None,
            )
        )
        if name in self._terminal:
            await self._queue.put(None)
