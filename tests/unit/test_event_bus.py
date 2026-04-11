"""Tests for SupervisorEventBusMixin.

The mixin is pure list semantics and does not require Thespian — we can
test it with a minimal fake actor that records ``send()`` calls.
"""

from __future__ import annotations

from typing import Any

import pytest

from maverick.actors.event_bus import SupervisorEventBusMixin
from maverick.events import StepOutput, StepStarted, WorkflowCompleted
from maverick.types import StepType


class FakeSupervisor(SupervisorEventBusMixin):
    """Minimal stand-in for a Thespian Actor that records outbound sends."""

    def __init__(self) -> None:
        self._init_event_bus()
        self.sent: list[tuple[Any, Any]] = []

    def send(self, target: Any, payload: Any) -> None:
        self.sent.append((target, payload))


class TestInit:
    def test_initial_state_is_empty(self) -> None:
        sup = FakeSupervisor()
        assert sup._events == []
        assert sup._done is False
        assert sup._terminal_result is None


class TestEmit:
    def test_emit_appends_event(self) -> None:
        sup = FakeSupervisor()
        event = StepOutput(step_name="x", message="hello")
        sup._emit(event)
        assert sup._events == [event]

    def test_emit_output_constructs_step_output(self) -> None:
        sup = FakeSupervisor()
        sup._emit_output("fly", "bead selected", level="info", source="fly-supervisor")
        assert len(sup._events) == 1
        event = sup._events[0]
        assert isinstance(event, StepOutput)
        assert event.step_name == "fly"
        assert event.message == "bead selected"
        assert event.level == "info"
        assert event.source == "fly-supervisor"

    def test_emit_output_with_metadata(self) -> None:
        sup = FakeSupervisor()
        sup._emit_output("fly", "commit landed", metadata={"bead_id": "b-001"})
        assert sup._events[0].metadata == {"bead_id": "b-001"}  # type: ignore[union-attr]

    def test_emit_preserves_order(self) -> None:
        sup = FakeSupervisor()
        sup._emit_output("a", "first")
        sup._emit_output("a", "second")
        sup._emit_output("a", "third")
        messages = [e.message for e in sup._events]  # type: ignore[attr-defined]
        assert messages == ["first", "second", "third"]


class TestHandleGetEvents:
    def test_empty_buffer_reply(self) -> None:
        sup = FakeSupervisor()
        sup._handle_get_events({"type": "get_events", "since": 0}, sender="wf")
        assert len(sup.sent) == 1
        target, reply = sup.sent[0]
        assert target == "wf"
        assert reply["type"] == "events"
        assert reply["events"] == []
        assert reply["next_cursor"] == 0
        assert reply["done"] is False
        assert reply["result"] is None

    def test_reply_contains_serialized_events(self) -> None:
        sup = FakeSupervisor()
        sup._emit_output("fly", "bead selected")
        sup._emit_output("fly", "gate passed", level="success")

        sup._handle_get_events({"type": "get_events", "since": 0}, sender="wf")
        reply = sup.sent[0][1]
        assert reply["next_cursor"] == 2
        assert len(reply["events"]) == 2
        # Serialized form carries class name as "event"
        assert reply["events"][0]["event"] == "StepOutput"
        assert reply["events"][0]["message"] == "bead selected"
        assert reply["events"][1]["level"] == "success"

    def test_since_cursor_returns_only_new(self) -> None:
        sup = FakeSupervisor()
        sup._emit_output("fly", "one")
        sup._emit_output("fly", "two")
        sup._emit_output("fly", "three")

        sup._handle_get_events({"since": 1}, sender="wf")
        reply = sup.sent[0][1]
        assert len(reply["events"]) == 2
        assert reply["events"][0]["message"] == "two"
        assert reply["events"][1]["message"] == "three"
        assert reply["next_cursor"] == 3

    def test_since_equal_to_length_returns_empty(self) -> None:
        sup = FakeSupervisor()
        sup._emit_output("fly", "one")
        sup._handle_get_events({"since": 1}, sender="wf")
        reply = sup.sent[0][1]
        assert reply["events"] == []
        assert reply["next_cursor"] == 1

    def test_negative_since_is_clamped_to_zero(self) -> None:
        sup = FakeSupervisor()
        sup._emit_output("fly", "one")
        sup._handle_get_events({"since": -5}, sender="wf")
        reply = sup.sent[0][1]
        assert len(reply["events"]) == 1

    def test_missing_since_defaults_to_zero(self) -> None:
        sup = FakeSupervisor()
        sup._emit_output("fly", "one")
        sup._handle_get_events({"type": "get_events"}, sender="wf")
        reply = sup.sent[0][1]
        assert len(reply["events"]) == 1

    def test_handles_mixed_event_types(self) -> None:
        sup = FakeSupervisor()
        sup._emit(StepStarted(step_name="impl", step_type=StepType.AGENT))
        sup._emit_output("fly", "progress")
        sup._emit(
            WorkflowCompleted(
                workflow_name="fly", success=True, total_duration_ms=100
            )
        )
        sup._handle_get_events({"since": 0}, sender="wf")
        reply = sup.sent[0][1]
        assert [e["event"] for e in reply["events"]] == [
            "StepStarted",
            "StepOutput",
            "WorkflowCompleted",
        ]


class TestMarkDone:
    def test_done_transition(self) -> None:
        sup = FakeSupervisor()
        assert sup._done is False
        sup._mark_done({"success": True, "beads": 3})
        assert sup._done is True
        assert sup._terminal_result == {"success": True, "beads": 3}

    def test_done_reply_carries_result(self) -> None:
        sup = FakeSupervisor()
        sup._emit_output("fly", "wrapping up")
        sup._mark_done({"success": True})

        sup._handle_get_events({"since": 0}, sender="wf")
        reply = sup.sent[0][1]
        assert reply["done"] is True
        assert reply["result"] == {"success": True}

    def test_done_result_none_when_not_done(self) -> None:
        sup = FakeSupervisor()
        sup._handle_get_events({"since": 0}, sender="wf")
        reply = sup.sent[0][1]
        assert reply["done"] is False
        assert reply["result"] is None

    def test_done_can_be_marked_with_none_result(self) -> None:
        sup = FakeSupervisor()
        sup._mark_done(None)
        assert sup._done is True
        sup._handle_get_events({"since": 0}, sender="wf")
        reply = sup.sent[0][1]
        assert reply["done"] is True
        assert reply["result"] is None

    def test_events_after_done_still_drainable(self) -> None:
        """Supervisors may emit a final event concurrently with marking done."""
        sup = FakeSupervisor()
        sup._mark_done({"success": True})
        sup._emit_output("fly", "final tick")
        sup._handle_get_events({"since": 0}, sender="wf")
        reply = sup.sent[0][1]
        assert len(reply["events"]) == 1
        assert reply["events"][0]["message"] == "final tick"


class TestRoundTripThroughEventFromDict:
    """The workflow drain helper must be able to reconstruct events."""

    def test_emitted_events_survive_serialization(self) -> None:
        from maverick.events import event_from_dict

        sup = FakeSupervisor()
        sup._emit_output("fly", "bead selected", level="info", source="fly")
        sup._emit(StepStarted(step_name="impl", step_type=StepType.AGENT))

        sup._handle_get_events({"since": 0}, sender="wf")
        reply = sup.sent[0][1]

        restored = [event_from_dict(d) for d in reply["events"]]
        assert restored[0] == sup._events[0]
        assert restored[1] == sup._events[1]


@pytest.mark.parametrize("since", [0, 1, 2, 3, 10])
def test_cursor_math_parametrized(since: int) -> None:
    sup = FakeSupervisor()
    for i in range(3):
        sup._emit_output("fly", f"msg-{i}")
    sup._handle_get_events({"since": since}, sender="wf")
    reply = sup.sent[0][1]
    expected_count = max(0, 3 - since)
    assert len(reply["events"]) == expected_count
    assert reply["next_cursor"] == 3
