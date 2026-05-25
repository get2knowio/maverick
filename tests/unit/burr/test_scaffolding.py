"""Unit tests for ``maverick.burr`` scaffolding.

Phase 0 scaffolding tests only — verify the driver + hook integrate
correctly against a trivial Burr graph that has no LLM, no squadron,
no maverick-internal coupling. Per-workflow application tests live next
to their workflow under ``tests/unit/workflows/<name>/test_burr_*.py``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from burr.core import ApplicationBuilder, State, action

from maverick.burr import BurrWorkflowDriver, ProgressEventHook
from maverick.events import ProgressEvent, StepCompleted, StepStarted
from maverick.types import StepType


@action(reads=[], writes=["counter"])
async def _start(state: State) -> tuple[dict[str, Any], State]:
    return {"counter": 0}, state.update(counter=0)


@action(reads=["counter"], writes=["counter"])
async def _bump(state: State) -> tuple[dict[str, Any], State]:
    new_counter = state["counter"] + 1
    return {"counter": new_counter}, state.update(counter=new_counter)


@action(reads=["counter"], writes=[])
async def _finish(state: State) -> tuple[dict[str, Any], State]:
    return {"counter": state["counter"]}, state


@action(reads=[], writes=[])
async def _boom(state: State) -> tuple[dict[str, Any], State]:
    raise RuntimeError("intentional test failure")


def _build_happy_app(
    queue: asyncio.Queue[ProgressEvent | None],
) -> Any:
    """Three-action graph: start → bump → finish."""
    hook = ProgressEventHook(
        queue,
        terminal_actions=["finish"],
        action_labels={"start": "Init", "bump": "Bump", "finish": "Done"},
    )
    return (
        ApplicationBuilder()
        .with_actions(start=_start, bump=_bump, finish=_finish)
        .with_transitions(("start", "bump"), ("bump", "finish"))
        .with_entrypoint("start")
        .with_state(counter=0)
        .with_hooks(hook)
        .build()
    )


class TestProgressEventHook:
    async def test_emits_step_started_then_completed_per_action(self) -> None:
        """Each action produces a paired StepStarted + StepCompleted event."""
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        app = _build_happy_app(queue)
        driver = BurrWorkflowDriver(app, halt_after=["finish"], event_queue=queue)

        events: list[ProgressEvent] = []
        async for evt in driver.events():
            events.append(evt)

        # Three actions → 6 events (StepStarted + StepCompleted each)
        assert len(events) == 6
        for i, action_name in enumerate(("start", "bump", "finish")):
            started = events[2 * i]
            completed = events[2 * i + 1]
            assert isinstance(started, StepStarted)
            assert started.step_name == action_name
            assert started.step_type == StepType.AGENT
            assert isinstance(completed, StepCompleted)
            assert completed.step_name == action_name
            assert completed.success is True
            assert completed.error is None
            assert completed.duration_ms >= 0

    async def test_display_label_overrides_action_name(self) -> None:
        """``action_labels`` mapping populates ``StepStarted.display_label``."""
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        app = _build_happy_app(queue)
        driver = BurrWorkflowDriver(app, halt_after=["finish"], event_queue=queue)

        labels = [
            evt.display_label async for evt in driver.events() if isinstance(evt, StepStarted)
        ]
        assert labels == ["Init", "Bump", "Done"]

    async def test_post_run_step_records_exception(self) -> None:
        """A raised action emits StepCompleted(success=False, error=<msg>)."""
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        hook = ProgressEventHook(queue, terminal_actions=["boom"])
        app = (
            ApplicationBuilder()
            .with_actions(start=_start, boom=_boom)
            .with_transitions(("start", "boom"))
            .with_entrypoint("start")
            .with_state(counter=0)
            .with_hooks(hook)
            .build()
        )
        driver = BurrWorkflowDriver(app, halt_after=["boom"], event_queue=queue)

        events: list[ProgressEvent] = []
        with pytest.raises(RuntimeError, match="intentional test failure"):
            async for evt in driver.events():
                events.append(evt)
            # Result access re-raises the underlying RuntimeError.
            _ = driver.result

        boom_completed = [
            e for e in events if isinstance(e, StepCompleted) and e.step_name == "boom"
        ]
        assert len(boom_completed) == 1
        assert boom_completed[0].success is False
        assert "intentional test failure" in (boom_completed[0].error or "")

    async def test_rejects_empty_terminal_actions(self) -> None:
        """``terminal_actions`` must not be empty (no end-of-stream signal)."""
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        with pytest.raises(ValueError, match="terminal_actions"):
            ProgressEventHook(queue, terminal_actions=[])


class TestBurrWorkflowDriver:
    async def test_result_exposes_app_arun_return(self) -> None:
        """After draining, ``driver.result`` returns Burr's tuple."""
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        app = _build_happy_app(queue)
        driver = BurrWorkflowDriver(app, halt_after=["finish"], event_queue=queue)

        async for _ in driver.events():
            pass

        last_action, _result, state = driver.result
        assert last_action.name == "finish"
        assert state["counter"] == 1

    async def test_result_before_drain_raises(self) -> None:
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        app = _build_happy_app(queue)
        driver = BurrWorkflowDriver(app, halt_after=["finish"], event_queue=queue)

        with pytest.raises(RuntimeError, match="must be drained"):
            _ = driver.result

    async def test_rejects_empty_halt_after(self) -> None:
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        app = _build_happy_app(queue)
        with pytest.raises(ValueError, match="halt_after"):
            BurrWorkflowDriver(app, halt_after=[], event_queue=queue)
