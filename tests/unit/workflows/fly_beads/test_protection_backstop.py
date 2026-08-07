"""Tests for fly's protection-blocks wiring (056-context-file-protection T020).

Covers: the ``protection_blocks`` state slot is seeded ``[]`` in the
graph; the squadron's collector is drained (and a ``ContextFileWriteBlocked``
event emitted per record) after every agent-calling action; exactly one
``StepOutput(level="warning", metadata={"block_count": n})`` fires at loop
exit when ``n >= 1`` and none when ``n == 0``; the slot is never read by
any fix-loop-feeding action (Guardrail 10 corollary).
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from burr.core import State

from maverick.events import ContextFileWriteBlocked, ProgressEvent, StepOutput
from maverick.payloads import SubmitImplementationPayload, SubmitReviewPayload
from maverick.protection.records import BlockCollector, BlockRecord
from maverick.workflows.fly_beads import actions
from maverick.workflows.fly_beads.burr_graph import build_fly_application
from tests.unit.agents.airframe_stubs import StubCodingAgent, StubReviewerAgent
from tests.unit.workflows.fly_beads.test_burr_graph import StubFlySquadron


class _ProtectedStubSquadron(StubFlySquadron):
    """A ``StubFlySquadron`` with a real ``block_collector`` attached."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.block_collector = BlockCollector()


def _block(path: str = "CLAUDE.md") -> BlockRecord:
    return BlockRecord(
        agent_role="implement",
        workflow="fly-beads",
        operation="restore",
        path=path,
        layer="backstop",
        bead_id="b-1",
        detail="restored after backstop-detected mutation",
    )


async def _drain_queue(queue: asyncio.Queue[ProgressEvent | None]) -> list[ProgressEvent]:
    events: list[ProgressEvent] = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


class TestStateSlotSeeded:
    def test_protection_blocks_seeded_empty_list(self) -> None:
        squadron = _ProtectedStubSquadron()
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        app = build_fly_application(
            squadron=squadron,  # type: ignore[arg-type]
            event_queue=queue,
            epic_id="e-1",
            cwd="/tmp",
        )
        assert app.state.get("protection_blocks") == []


class TestImplementDrainsCollector:
    async def test_blocks_appear_in_returned_state(self) -> None:
        squadron = _ProtectedStubSquadron(
            coder=StubCodingAgent(
                implement_payloads=[SubmitImplementationPayload(summary="did it")]
            )
        )
        squadron.block_collector.append(_block("CLAUDE.md"))
        events: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        state = State(
            {
                "current_bead": {"bead_id": "b-1", "title": "t", "description": "d"},
                "current_bead_id": "b-1",
                "implementer_escalation_level": 0,
                "pending_assumptions": [],
                "protection_blocks": [],
            }
        )

        _result, new_state = await actions.implement(
            state,
            squadron=squadron,
            events=events,  # type: ignore[arg-type]
        )

        assert len(new_state.get("protection_blocks")) == 1
        assert new_state.get("protection_blocks")[0]["path"] == "CLAUDE.md"
        # The collector itself is drained — a second read is empty.
        assert squadron.block_collector.drain() == []

    async def test_context_file_write_blocked_event_emitted(self) -> None:
        squadron = _ProtectedStubSquadron(
            coder=StubCodingAgent(
                implement_payloads=[SubmitImplementationPayload(summary="did it")]
            )
        )
        squadron.block_collector.append(_block("AGENTS.md"))
        events: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        state = State(
            {
                "current_bead": {"bead_id": "b-1", "title": "t", "description": "d"},
                "current_bead_id": "b-1",
                "implementer_escalation_level": 0,
                "pending_assumptions": [],
                "protection_blocks": [],
            }
        )

        await actions.implement(state, squadron=squadron, events=events)  # type: ignore[arg-type]

        emitted = await _drain_queue(events)
        blocked_events = [e for e in emitted if isinstance(e, ContextFileWriteBlocked)]
        assert len(blocked_events) == 1
        assert blocked_events[0].path == "AGENTS.md"

    async def test_no_blocks_no_events_clean_run(self) -> None:
        squadron = _ProtectedStubSquadron(
            coder=StubCodingAgent(
                implement_payloads=[SubmitImplementationPayload(summary="did it")]
            )
        )
        events: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        state = State(
            {
                "current_bead": {"bead_id": "b-1", "title": "t", "description": "d"},
                "current_bead_id": "b-1",
                "implementer_escalation_level": 0,
                "pending_assumptions": [],
                "protection_blocks": [],
            }
        )

        _result, new_state = await actions.implement(
            state,
            squadron=squadron,
            events=events,  # type: ignore[arg-type]
        )
        assert new_state.get("protection_blocks") == []
        emitted = await _drain_queue(events)
        assert not any(isinstance(e, ContextFileWriteBlocked) for e in emitted)


class TestReviewDrainsCollector:
    async def test_blocks_appear_after_review(self) -> None:
        squadron = _ProtectedStubSquadron(
            correctness=StubReviewerAgent(
                review_kind="correctness",
                review_payloads=[SubmitReviewPayload(approved=True, findings=())],
            ),
            completeness=StubReviewerAgent(
                review_kind="completeness",
                review_payloads=[SubmitReviewPayload(approved=True, findings=())],
            ),
        )
        squadron.block_collector.append(_block("CLAUDE.md"))
        events: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        state = State(
            {
                "current_bead": {"bead_id": "b-1", "title": "t", "description": "d"},
                "current_bead_id": "b-1",
                "reviewer_escalation_level": 0,
                "implementer_escalation_level": 0,
                "pending_assumptions": [],
                "protection_blocks": [],
            }
        )

        _result, new_state = await actions.review(
            state,
            squadron=squadron,
            events=events,  # type: ignore[arg-type]
        )
        assert len(new_state.get("protection_blocks")) == 1


class TestAggregateReviewLoopExitSummary:
    async def test_one_warning_when_blocks_present(self) -> None:
        squadron = _ProtectedStubSquadron()
        squadron.block_collector.append(_block("CLAUDE.md"))
        squadron.block_collector.append(_block("AGENTS.md"))
        events: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        state = State(
            {
                "completed_bead_ids": ["b-1", "b-2"],
                "bead_events": [],
                "succeeded_count": 2,
                "protection_blocks": [],
            }
        )

        _result, new_state = await actions.aggregate_review(
            state,
            squadron=squadron,  # type: ignore[arg-type]
            events=events,
            cwd="/tmp",
            epic_id="e-1",
        )

        assert len(new_state.get("protection_blocks")) == 2
        emitted = await _drain_queue(events)
        summary_warnings = [
            e
            for e in emitted
            if isinstance(e, StepOutput)
            and e.level == "warning"
            and e.metadata is not None
            and "block_count" in e.metadata
        ]
        assert len(summary_warnings) == 1
        assert summary_warnings[0].metadata["block_count"] == 2

    async def test_no_warning_when_clean(self) -> None:
        squadron = _ProtectedStubSquadron()
        events: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        state = State(
            {
                "completed_bead_ids": ["b-1"],
                "bead_events": [],
                "succeeded_count": 1,
                "protection_blocks": [],
            }
        )

        await actions.aggregate_review(
            state,
            squadron=squadron,  # type: ignore[arg-type]
            events=events,
            cwd="/tmp",
            epic_id="e-1",
        )

        emitted = await _drain_queue(events)
        summary_warnings = [
            e
            for e in emitted
            if isinstance(e, StepOutput)
            and e.level == "warning"
            and e.metadata is not None
            and "block_count" in e.metadata
        ]
        assert summary_warnings == []

    async def test_repeated_retries_summarized_once_not_per_attempt(self) -> None:
        """Multiple restores across a run still produce exactly one summary
        warning at loop exit (spec edge case)."""
        squadron = _ProtectedStubSquadron()
        for _ in range(5):
            squadron.block_collector.append(_block("CLAUDE.md"))
        events: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        state = State(
            {
                "completed_bead_ids": ["b-1", "b-2"],
                "bead_events": [],
                "succeeded_count": 2,
                "protection_blocks": [],
            }
        )

        await actions.aggregate_review(
            state,
            squadron=squadron,  # type: ignore[arg-type]
            events=events,
            cwd="/tmp",
            epic_id="e-1",
        )

        emitted = await _drain_queue(events)
        summary_warnings = [
            e
            for e in emitted
            if isinstance(e, StepOutput)
            and e.level == "warning"
            and e.metadata is not None
            and "block_count" in e.metadata
        ]
        assert len(summary_warnings) == 1
        assert summary_warnings[0].metadata["block_count"] == 5


class TestSlotNeverFeedsFixLoop:
    """Guardrail 10 corollary: ``protection_blocks`` must never be read by
    any action that builds a fix-loop prompt — a separate slot from every
    fixer-feeding slot, so an uncloseable condition can never reach a fix
    loop."""

    def test_run_fix_never_reads_protection_blocks(self) -> None:
        source = inspect.getsource(actions._run_fix)
        assert "protection_blocks" not in source

    def test_call_implementer_with_escalation_never_reads_protection_blocks(self) -> None:
        source = inspect.getsource(actions._call_implementer_with_escalation)
        assert "protection_blocks" not in source

    def test_review_round_with_escalation_never_reads_protection_blocks(self) -> None:
        source = inspect.getsource(actions._review_round_with_escalation)
        assert "protection_blocks" not in source

    def test_build_implement_prompt_never_reads_protection_blocks(self) -> None:
        source = inspect.getsource(actions._build_implement_prompt)
        assert "protection_blocks" not in source


class TestDegradesGracefullyWithoutCollector:
    async def test_squadron_without_block_collector_is_a_no_op(self) -> None:
        """A squadron whose protection setup degraded (no ``block_collector``
        attribute at all) must not break the drain path."""
        squadron = StubFlySquadron(
            coder=StubCodingAgent(
                implement_payloads=[SubmitImplementationPayload(summary="did it")]
            )
        )
        assert not hasattr(squadron, "block_collector")
        events: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        state = State(
            {
                "current_bead": {"bead_id": "b-1", "title": "t", "description": "d"},
                "current_bead_id": "b-1",
                "implementer_escalation_level": 0,
                "pending_assumptions": [],
                "protection_blocks": [],
            }
        )

        _result, new_state = await actions.implement(
            state,
            squadron=squadron,
            events=events,  # type: ignore[arg-type]
        )
        assert new_state.get("protection_blocks") == []
