"""Tests for PythonWorkflow._drain_supervisor_events.

The drain helper polls a Thespian supervisor actor via asys.ask and
pushes drained ProgressEvents into the workflow's _event_queue. These
tests use a fake ActorSystem that returns scripted replies — no Thespian
process is spawned.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from maverick.events import StepOutput, StepStarted
from maverick.exceptions import WorkflowError
from maverick.types import StepType


class FakeActorSystem:
    """Minimal ActorSystem stand-in.

    ``ask`` returns the next scripted reply from ``replies``. Each reply is
    either a dict (returned as-is) or a callable that receives the
    ``message`` dict and returns a dict.
    """

    def __init__(self, replies: list[Any]) -> None:
        self._replies = list(replies)
        self.asks: list[tuple[Any, dict[str, Any]]] = []

    def ask(self, target: Any, message: dict[str, Any], timeout: float) -> Any:
        self.asks.append((target, dict(message)))
        if not self._replies:
            raise RuntimeError("FakeActorSystem ran out of scripted replies")
        reply = self._replies.pop(0)
        if callable(reply):
            return reply(message)
        return reply


def _make_workflow(workflow_name: str = "drain-test") -> Any:
    from maverick.config import MaverickConfig, ModelConfig
    from maverick.registry import ComponentRegistry
    from tests.unit.workflows.conftest import _make_concrete_workflow_class

    ConcreteTestWorkflow = _make_concrete_workflow_class()
    cfg = MagicMock(spec=MaverickConfig)
    cfg.model = ModelConfig()
    cfg.steps = {}
    cfg.agents = {}
    wf = ConcreteTestWorkflow(
        run_fn=None,
        config=cfg,
        registry=MagicMock(spec=ComponentRegistry),
        workflow_name=workflow_name,
    )
    # execute() normally sets _event_queue; the drain helper is usually
    # called from inside _run() which runs after execute() has initialised
    # state. In these tests we call the helper directly, so set up the
    # queue manually.
    wf._event_queue = asyncio.Queue()
    return wf


def _events_reply(
    serialized_events: list[dict[str, Any]],
    *,
    next_cursor: int,
    done: bool = False,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": "events",
        "events": serialized_events,
        "next_cursor": next_cursor,
        "done": done,
        "result": result,
    }


def _output(message: str, level: str = "info") -> dict[str, Any]:
    return StepOutput(
        step_name="fly",
        message=message,
        level=level,  # type: ignore[arg-type]
    ).to_dict()


class TestDrainBasic:
    async def test_immediate_done_empty_buffer(self) -> None:
        wf = _make_workflow()
        asys = FakeActorSystem(
            [
                _events_reply([], next_cursor=0, done=True, result={"success": True}),
            ]
        )
        result = await wf._drain_supervisor_events(asys=asys, supervisor="sup", poll_interval=0.01)
        assert result == {"success": True}
        assert wf._event_queue.empty()
        # Exactly one ask, with since=0
        assert len(asys.asks) == 1
        assert asys.asks[0][1] == {"type": "get_events", "since": 0}

    async def test_drains_events_into_queue(self) -> None:
        wf = _make_workflow()
        asys = FakeActorSystem(
            [
                _events_reply(
                    [_output("one"), _output("two")],
                    next_cursor=2,
                    done=True,
                    result={"success": True},
                ),
            ]
        )
        await wf._drain_supervisor_events(asys=asys, supervisor="sup", poll_interval=0.01)
        queued: list[Any] = []
        while not wf._event_queue.empty():
            queued.append(wf._event_queue.get_nowait())
        assert len(queued) == 2
        assert all(isinstance(e, StepOutput) for e in queued)
        assert queued[0].message == "one"
        assert queued[1].message == "two"

    async def test_multi_poll_advances_cursor(self) -> None:
        wf = _make_workflow()
        asys = FakeActorSystem(
            [
                _events_reply([_output("one")], next_cursor=1, done=False),
                _events_reply([_output("two")], next_cursor=2, done=False),
                _events_reply(
                    [_output("three")],
                    next_cursor=3,
                    done=True,
                    result={"success": True, "count": 3},
                ),
            ]
        )
        result = await wf._drain_supervisor_events(
            asys=asys, supervisor="sup", poll_interval=0.001
        )
        assert result == {"success": True, "count": 3}

        # Cursor advanced on each poll
        assert [ask[1]["since"] for ask in asys.asks] == [0, 1, 2]

        queued: list[Any] = []
        while not wf._event_queue.empty():
            queued.append(wf._event_queue.get_nowait())
        assert [e.message for e in queued] == ["one", "two", "three"]

    async def test_returns_none_when_result_missing(self) -> None:
        wf = _make_workflow()
        asys = FakeActorSystem(
            [
                _events_reply([], next_cursor=0, done=True, result=None),
            ]
        )
        result = await wf._drain_supervisor_events(asys=asys, supervisor="sup", poll_interval=0.01)
        assert result is None

    async def test_rehydrates_typed_events(self) -> None:
        wf = _make_workflow()
        started = StepStarted(step_name="impl", step_type=StepType.AGENT).to_dict()
        asys = FakeActorSystem(
            [
                _events_reply([started], next_cursor=1, done=True, result={}),
            ]
        )
        await wf._drain_supervisor_events(asys=asys, supervisor="sup", poll_interval=0.01)
        event = wf._event_queue.get_nowait()
        assert isinstance(event, StepStarted)
        assert event.step_type == StepType.AGENT

    async def test_skips_undecodable_event_with_warning(self) -> None:
        wf = _make_workflow()
        asys = FakeActorSystem(
            [
                _events_reply(
                    [
                        {"event": "NotARealEvent", "garbage": True},
                        _output("good"),
                    ],
                    next_cursor=2,
                    done=True,
                    result={},
                ),
            ]
        )
        await wf._drain_supervisor_events(asys=asys, supervisor="sup", poll_interval=0.01)
        queued: list[Any] = []
        while not wf._event_queue.empty():
            queued.append(wf._event_queue.get_nowait())
        assert len(queued) == 1
        assert queued[0].message == "good"


class TestDrainErrors:
    async def test_unexpected_reply_raises(self) -> None:
        wf = _make_workflow()
        asys = FakeActorSystem([{"type": "something_else"}])
        with pytest.raises(WorkflowError, match="unexpected supervisor reply"):
            await wf._drain_supervisor_events(asys=asys, supervisor="sup", poll_interval=0.01)

    async def test_none_reply_retries_then_times_out(self) -> None:
        """None replies (supervisor busy) are retried until hard timeout."""
        wf = _make_workflow()
        asys = FakeActorSystem([None] * 100)
        with pytest.raises(WorkflowError, match="exceeded"):
            await wf._drain_supervisor_events(
                asys=asys,
                supervisor="sup",
                poll_interval=0.001,
                hard_timeout_seconds=0.05,
            )

    async def test_hard_timeout_raises(self) -> None:
        wf = _make_workflow()

        # Replies keep saying "not done yet" — the drain should eventually
        # give up via the hard timeout.
        def _never_done(_msg: dict[str, Any]) -> dict[str, Any]:
            return _events_reply([], next_cursor=0, done=False)

        asys = FakeActorSystem([_never_done] * 1000)
        with pytest.raises(WorkflowError, match="exceeded"):
            await wf._drain_supervisor_events(
                asys=asys,
                supervisor="sup",
                poll_interval=0.001,
                hard_timeout_seconds=0.05,
            )
