"""Unit tests for the Burr-mode fly_beads graph.

End-to-end checks of the substrate-side state machine — outer bead
loop, per-stage pipeline, abandon path, and the cycle back into
``select_next_bead``. All offline: no LLM, no xoscar pool, no bd CLI.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from maverick.burr import BurrWorkflowDriver
from maverick.events import (
    ProgressEvent,
    StepStarted,
)
from maverick.library.actions.types import MarkBeadCompleteResult, SelectNextBeadResult
from maverick.payloads import (
    ReviewFindingPayload,
    SubmitFixResultPayload,
    SubmitImplementationPayload,
    SubmitReviewPayload,
)
from maverick.workflows.fly_beads.burr_graph import (
    FLY_TERMINAL_ACTIONS,
    build_fly_application,
)
from tests.unit.agents.airframe_stubs import StubCodingAgent, StubReviewerAgent

# ---------------------------------------------------------------------------
# Stub squadron
# ---------------------------------------------------------------------------


class _NullCM:
    """Stand-in for ``squadron.bead_context(...)`` context manager."""

    def __enter__(self) -> _NullCM:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


class StubFlySquadron:
    """Minimal stand-in for :class:`FlySquadron`."""

    def __init__(
        self,
        *,
        coder: StubCodingAgent | None = None,
        correctness: StubReviewerAgent | None = None,
        completeness: StubReviewerAgent | None = None,
    ) -> None:
        self.coder = coder or StubCodingAgent(
            implement_payloads=[SubmitImplementationPayload(summary="stub impl")],
            fix_payloads=[SubmitFixResultPayload(summary="stub fix") for _ in range(5)],
        )
        self.correctness = correctness or StubReviewerAgent(
            review_kind="correctness",
            review_payloads=[SubmitReviewPayload(approved=True, findings=())],
        )
        self.completeness = completeness or StubReviewerAgent(
            review_kind="completeness",
            review_payloads=[SubmitReviewPayload(approved=True, findings=())],
        )

    def coder_for(self, _tier: str) -> StubCodingAgent:
        return self.coder

    def correctness_reviewer_for(self, _tier: str) -> StubReviewerAgent:
        return self.correctness

    def completeness_reviewer_for(self, _tier: str) -> StubReviewerAgent:
        return self.completeness

    def bead_context(self, **_kwargs: Any) -> _NullCM:
        return _NullCM()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bead(
    bead_id: str, title: str = "stub bead", description: str = "stub work"
) -> SelectNextBeadResult:
    return SelectNextBeadResult(
        found=True,
        bead_id=bead_id,
        title=title,
        description=description,
        priority=2,
        epic_id="e-1",
        done=False,
    )


_NO_MORE = SelectNextBeadResult(
    found=False,
    bead_id="",
    title="",
    description="",
    priority=0,
    epic_id="",
    done=True,
)


def _gate_passed() -> dict[str, Any]:
    return {"passed": True, "summary": "OK", "stage_results": {}}


def _gate_failed(summary: str = "fmt: 1 error") -> dict[str, Any]:
    return {"passed": False, "summary": summary, "stage_results": {}}


async def _collect(driver: BurrWorkflowDriver) -> list[ProgressEvent]:
    events: list[ProgressEvent] = []
    async for evt in driver.events():
        events.append(evt)
    return events


def _action_sequence(events: list[ProgressEvent]) -> list[str]:
    return [e.step_name for e in events if isinstance(e, StepStarted)]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFlyBurrHappyPath:
    async def test_one_bead_full_pipeline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One ready bead → implement → gate → ac → spec → review → commit → no more → done."""
        # Ensure no graceful-stop leak from prior tests.
        from maverick.workflows.fly_beads.graceful_stop import reset_graceful_stop

        reset_graceful_stop()

        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        squadron = StubFlySquadron()

        with (
            patch(
                "maverick.library.actions.beads.select_next_bead",
                new=AsyncMock(side_effect=[_bead("b-1"), _NO_MORE]),
            ),
            patch(
                "maverick.library.actions.validation.run_independent_gate",
                new=AsyncMock(return_value=_gate_passed()),
            ),
            patch(
                "maverick.library.actions.jj.jj_commit_bead",
                new=AsyncMock(return_value={"change_id": "c1", "success": True}),
            ),
            patch(
                "maverick.library.actions.beads.mark_bead_complete",
                new=AsyncMock(
                    return_value=MarkBeadCompleteResult(success=True, bead_id="b-1", error=None)
                ),
            ),
        ):
            app = build_fly_application(
                squadron=squadron,  # type: ignore[arg-type]
                event_queue=queue,
                epic_id="e-1",
                cwd=str(tmp_path),
                max_beads=10,
                completed_bead_ids=(),
            )
            driver = BurrWorkflowDriver(app, halt_after=FLY_TERMINAL_ACTIONS, event_queue=queue)
            events = await _collect(driver)

        sequence = _action_sequence(events)
        # The cycle hits select_next_bead twice (once to pick b-1, once
        # to detect end-of-stream). The pipeline runs once.
        assert "implement" in sequence
        assert "gate" in sequence
        assert "ac_check" in sequence
        assert "spec_check" in sequence
        assert "review" in sequence
        assert "commit" in sequence
        assert "record_outcome" in sequence
        assert sequence.count("select_next_bead") >= 2
        assert sequence[-1] == "done"

        _, _, state = driver.result
        assert state["succeeded_count"] == 1
        assert state["failed_count"] == 0
        assert state["completed_bead_ids"] == ["b-1"]
        assert state["loop_done_reason"] == "no_more_beads"

    async def test_max_beads_terminates_loop(self, tmp_path: Path) -> None:
        """``max_beads=1`` exits even when more beads are available."""
        from maverick.workflows.fly_beads.graceful_stop import reset_graceful_stop

        reset_graceful_stop()

        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        squadron = StubFlySquadron(
            coder=StubCodingAgent(
                implement_payloads=[
                    SubmitImplementationPayload(summary="i1"),
                    SubmitImplementationPayload(summary="i2"),
                ],
                fix_payloads=[SubmitFixResultPayload(summary="f") for _ in range(5)],
            )
        )

        with (
            patch(
                "maverick.library.actions.beads.select_next_bead",
                new=AsyncMock(side_effect=[_bead("b-1"), _bead("b-2"), _NO_MORE]),
            ),
            patch(
                "maverick.library.actions.validation.run_independent_gate",
                new=AsyncMock(return_value=_gate_passed()),
            ),
            patch(
                "maverick.library.actions.jj.jj_commit_bead",
                new=AsyncMock(return_value={"change_id": "c", "success": True}),
            ),
            patch(
                "maverick.library.actions.beads.mark_bead_complete",
                new=AsyncMock(
                    return_value=MarkBeadCompleteResult(success=True, bead_id="b-1", error=None)
                ),
            ),
        ):
            app = build_fly_application(
                squadron=squadron,  # type: ignore[arg-type]
                event_queue=queue,
                epic_id="e-1",
                cwd=str(tmp_path),
                max_beads=1,
            )
            driver = BurrWorkflowDriver(app, halt_after=FLY_TERMINAL_ACTIONS, event_queue=queue)
            await _collect(driver)

        _, _, state = driver.result
        assert state["succeeded_count"] == 1
        assert state["loop_done_reason"] == "max_beads"


class TestFlyBurrAbandonPath:
    async def test_gate_exhaustion_abandons_bead(self, tmp_path: Path) -> None:
        """Gate failure beyond MAX_GATE_FIX_ATTEMPTS → abandon + record_failure."""
        from maverick.workflows.fly_beads.graceful_stop import reset_graceful_stop

        reset_graceful_stop()

        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        squadron = StubFlySquadron()

        with (
            patch(
                "maverick.library.actions.beads.select_next_bead",
                new=AsyncMock(side_effect=[_bead("b-1"), _NO_MORE]),
            ),
            patch(
                "maverick.library.actions.validation.run_independent_gate",
                new=AsyncMock(return_value=_gate_failed()),
            ),
        ):
            app = build_fly_application(
                squadron=squadron,  # type: ignore[arg-type]
                event_queue=queue,
                epic_id="e-1",
                cwd=str(tmp_path),
                max_beads=10,
            )
            driver = BurrWorkflowDriver(app, halt_after=FLY_TERMINAL_ACTIONS, event_queue=queue)
            events = await _collect(driver)

        sequence = _action_sequence(events)
        assert "abandon_bead" in sequence
        # Never reached commit.
        assert "commit" not in sequence

        _, _, state = driver.result
        assert state["succeeded_count"] == 0
        assert state["failed_count"] == 1


class TestFlyBurrReviewLoop:
    async def test_review_fix_then_approve(self, tmp_path: Path) -> None:
        """First review has findings → fix → second review approves."""
        from maverick.workflows.fly_beads.graceful_stop import reset_graceful_stop

        reset_graceful_stop()

        # Two review rounds: first returns findings, second clean.
        correctness = StubReviewerAgent(
            review_kind="correctness",
            review_payloads=[
                SubmitReviewPayload(
                    approved=False,
                    findings=(
                        ReviewFindingPayload(
                            severity="major",
                            issue="missing edge case",
                            file="src/foo.py",
                        ),
                    ),
                ),
                SubmitReviewPayload(approved=True, findings=()),
            ],
        )
        completeness = StubReviewerAgent(
            review_kind="completeness",
            review_payloads=[
                SubmitReviewPayload(approved=True, findings=()),
                SubmitReviewPayload(approved=True, findings=()),
            ],
        )
        squadron = StubFlySquadron(
            correctness=correctness,
            completeness=completeness,
            coder=StubCodingAgent(
                implement_payloads=[SubmitImplementationPayload(summary="i1")],
                fix_payloads=[
                    SubmitFixResultPayload(summary="addressed feedback") for _ in range(3)
                ],
            ),
        )

        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        with (
            patch(
                "maverick.library.actions.beads.select_next_bead",
                new=AsyncMock(side_effect=[_bead("b-1"), _NO_MORE]),
            ),
            patch(
                "maverick.library.actions.validation.run_independent_gate",
                new=AsyncMock(return_value=_gate_passed()),
            ),
            patch(
                "maverick.library.actions.jj.jj_commit_bead",
                new=AsyncMock(return_value={"change_id": "c", "success": True}),
            ),
            patch(
                "maverick.library.actions.beads.mark_bead_complete",
                new=AsyncMock(
                    return_value=MarkBeadCompleteResult(success=True, bead_id="b-1", error=None)
                ),
            ),
        ):
            app = build_fly_application(
                squadron=squadron,  # type: ignore[arg-type]
                event_queue=queue,
                epic_id="e-1",
                cwd=str(tmp_path),
                max_beads=10,
            )
            driver = BurrWorkflowDriver(app, halt_after=FLY_TERMINAL_ACTIONS, event_queue=queue)
            await _collect(driver)

        _, _, state = driver.result
        assert state["approved"] is True
        # Two rounds, one of which had findings.
        assert state["review_rounds"] == 1
        assert state["succeeded_count"] == 1


class TestFlyBurrHumanBeadCreation:
    async def test_review_exhaustion_creates_human_bead(self, tmp_path: Path) -> None:
        """3 review rounds with findings → create_human_bead → commit (with tag)."""
        from maverick.beads.models import BeadCategory, BeadDefinition, BeadType
        from maverick.workflows.fly_beads.graceful_stop import reset_graceful_stop

        reset_graceful_stop()

        # All 3 review rounds return findings (correctness is unhappy).
        correctness = StubReviewerAgent(
            review_kind="correctness",
            review_payloads=[
                SubmitReviewPayload(
                    approved=False,
                    findings=(ReviewFindingPayload(severity="major", issue=f"finding round {n}"),),
                )
                for n in range(1, 4)
            ],
        )
        completeness = StubReviewerAgent(
            review_kind="completeness",
            review_payloads=[SubmitReviewPayload(approved=True, findings=()) for _ in range(3)],
        )
        squadron = StubFlySquadron(
            correctness=correctness,
            completeness=completeness,
            coder=StubCodingAgent(
                implement_payloads=[SubmitImplementationPayload(summary="i1")],
                fix_payloads=[SubmitFixResultPayload(summary="f") for _ in range(5)],
            ),
        )

        captured_create_args: dict[str, Any] = {}
        captured_set_state_args: dict[str, Any] = {}

        async def _fake_create_bead(
            self: Any, definition: Any, parent_id: str | None = None
        ) -> Any:
            captured_create_args["definition"] = definition
            captured_create_args["parent_id"] = parent_id
            assert isinstance(definition, BeadDefinition)
            return type(
                "CreatedBead",
                (),
                {"bd_id": "human-bead-1", "definition": definition},
            )()

        async def _fake_set_state(
            self: Any,
            bd_id: str,
            state_dict: dict[str, Any],
            *,
            reason: str = "",
        ) -> None:
            captured_set_state_args["bd_id"] = bd_id
            captured_set_state_args["state"] = dict(state_dict)
            captured_set_state_args["reason"] = reason

        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        with (
            patch(
                "maverick.library.actions.beads.select_next_bead",
                new=AsyncMock(side_effect=[_bead("b-1"), _NO_MORE]),
            ),
            patch(
                "maverick.library.actions.validation.run_independent_gate",
                new=AsyncMock(return_value=_gate_passed()),
            ),
            patch(
                "maverick.library.actions.jj.jj_commit_bead",
                new=AsyncMock(return_value={"change_id": "c", "success": True}),
            ),
            patch(
                "maverick.library.actions.beads.mark_bead_complete",
                new=AsyncMock(
                    return_value=MarkBeadCompleteResult(success=True, bead_id="b-1", error=None)
                ),
            ),
            patch(
                "maverick.beads.client.BeadClient.create_bead",
                new=_fake_create_bead,
            ),
            patch(
                "maverick.beads.client.BeadClient.set_state",
                new=_fake_set_state,
            ),
        ):
            app = build_fly_application(
                squadron=squadron,  # type: ignore[arg-type]
                event_queue=queue,
                epic_id="e-1",
                cwd=str(tmp_path),
                max_beads=10,
                flight_plan_name="my-plan",
            )
            driver = BurrWorkflowDriver(app, halt_after=FLY_TERMINAL_ACTIONS, event_queue=queue)
            events = await _collect(driver)

        action_sequence = _action_sequence(events)
        # The escalation transition fires after review.
        assert "create_human_bead" in action_sequence
        assert action_sequence.index("create_human_bead") < action_sequence.index("commit")

        _, _, state = driver.result
        assert state["needs_human_review"] is True
        assert state["human_bead_id"] == "human-bead-1"
        # The bead-events row carries the tag for the CLI summary.
        bead_event = state["bead_events"][0]
        assert bead_event["tag"] == "needs-human-review"

        # Created with the right shape.
        defn: BeadDefinition = captured_create_args["definition"]
        assert defn.bead_type == BeadType.TASK
        assert defn.category == BeadCategory.REVIEW
        assert defn.assignee == "human"
        assert "assumption-review" in defn.labels
        assert "needs-human-review" in defn.labels
        assert captured_create_args["parent_id"] == "e-1"

        # Findings get inlined into the description, and the state-set
        # call ties the new bead back to the source.
        assert "finding round 3" in defn.description
        assert captured_set_state_args["bd_id"] == "human-bead-1"
        assert captured_set_state_args["state"]["source_bead"] == "b-1"
        assert captured_set_state_args["state"]["flight_plan"] == "my-plan"

    async def test_create_human_bead_failure_does_not_block_commit(self, tmp_path: Path) -> None:
        """If ``bd create`` raises, we still commit (with the tag)."""
        from maverick.workflows.fly_beads.graceful_stop import reset_graceful_stop

        reset_graceful_stop()

        correctness = StubReviewerAgent(
            review_kind="correctness",
            review_payloads=[
                SubmitReviewPayload(
                    approved=False,
                    findings=(ReviewFindingPayload(severity="minor", issue="x"),),
                )
                for _ in range(3)
            ],
        )
        completeness = StubReviewerAgent(
            review_kind="completeness",
            review_payloads=[SubmitReviewPayload(approved=True, findings=()) for _ in range(3)],
        )
        squadron = StubFlySquadron(
            correctness=correctness,
            completeness=completeness,
            coder=StubCodingAgent(
                implement_payloads=[SubmitImplementationPayload(summary="i1")],
                fix_payloads=[SubmitFixResultPayload(summary="f") for _ in range(5)],
            ),
        )

        async def _create_bead_fails(*_args: Any, **_kw: Any) -> Any:
            raise RuntimeError("bd create exploded")

        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        with (
            patch(
                "maverick.library.actions.beads.select_next_bead",
                new=AsyncMock(side_effect=[_bead("b-1"), _NO_MORE]),
            ),
            patch(
                "maverick.library.actions.validation.run_independent_gate",
                new=AsyncMock(return_value=_gate_passed()),
            ),
            patch(
                "maverick.library.actions.jj.jj_commit_bead",
                new=AsyncMock(return_value={"change_id": "c", "success": True}),
            ),
            patch(
                "maverick.library.actions.beads.mark_bead_complete",
                new=AsyncMock(
                    return_value=MarkBeadCompleteResult(success=True, bead_id="b-1", error=None)
                ),
            ),
            patch(
                "maverick.beads.client.BeadClient.create_bead",
                new=_create_bead_fails,
            ),
        ):
            app = build_fly_application(
                squadron=squadron,  # type: ignore[arg-type]
                event_queue=queue,
                epic_id="e-1",
                cwd=str(tmp_path),
                max_beads=10,
            )
            driver = BurrWorkflowDriver(app, halt_after=FLY_TERMINAL_ACTIONS, event_queue=queue)
            await _collect(driver)

        _, _, state = driver.result
        # human bead creation failed → empty id but the commit still ran.
        assert state["human_bead_id"] == ""
        assert state["commit_ok"] is True
        assert state["needs_human_review"] is True


class TestFlyBurrWatchMode:
    async def test_watch_polls_then_exits_on_idle_cap(self, tmp_path: Path) -> None:
        """Watch mode polls past an empty cycle, then exits when the cap is hit."""
        from maverick.workflows.fly_beads.graceful_stop import reset_graceful_stop

        reset_graceful_stop()

        # Sequence: empty (poll 1) → bead → empty (poll 1) → empty
        # (poll 2 = cap) → empty (cap hit → exit).
        select_calls = AsyncMock(
            side_effect=[_NO_MORE, _bead("b-1"), _NO_MORE, _NO_MORE, _NO_MORE]
        )
        sleep_calls: list[float] = []

        async def _instant_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        squadron = StubFlySquadron()

        with (
            patch("maverick.library.actions.beads.select_next_bead", new=select_calls),
            patch(
                "maverick.library.actions.validation.run_independent_gate",
                new=AsyncMock(return_value=_gate_passed()),
            ),
            patch(
                "maverick.library.actions.jj.jj_commit_bead",
                new=AsyncMock(return_value={"change_id": "c", "success": True}),
            ),
            patch(
                "maverick.library.actions.beads.mark_bead_complete",
                new=AsyncMock(
                    return_value=MarkBeadCompleteResult(success=True, bead_id="b-1", error=None)
                ),
            ),
            patch("maverick.workflows.fly_beads.actions.asyncio.sleep", new=_instant_sleep),
        ):
            app = build_fly_application(
                squadron=squadron,  # type: ignore[arg-type]
                event_queue=queue,
                epic_id="e-1",
                cwd=str(tmp_path),
                max_beads=10,
                watch=True,
                watch_interval=7,
                max_idle_polls=2,
            )
            driver = BurrWorkflowDriver(app, halt_after=FLY_TERMINAL_ACTIONS, event_queue=queue)
            await _collect(driver)

        _, _, state = driver.result
        # Bead processed; watch then exited after the idle cap was hit.
        assert state["succeeded_count"] == 1
        assert state["loop_done_reason"] == "watch_idle_exhausted"
        # One sleep for the first empty cycle, two for the post-bead cycles.
        assert sleep_calls == [7, 7, 7]
        # idle_polls stops at the cap.
        assert state["idle_polls"] == 2
        # Pre-bead empty cycle resets idle_polls when a bead is found.
        assert select_calls.await_count == 5

    async def test_no_watch_exits_immediately_on_empty(self, tmp_path: Path) -> None:
        """Without ``watch``, the first empty poll terminates the loop."""
        from maverick.workflows.fly_beads.graceful_stop import reset_graceful_stop

        reset_graceful_stop()

        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        squadron = StubFlySquadron()
        sleep_calls: list[float] = []

        async def _instant_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        with (
            patch(
                "maverick.library.actions.beads.select_next_bead",
                new=AsyncMock(side_effect=[_NO_MORE]),
            ),
            patch("maverick.workflows.fly_beads.actions.asyncio.sleep", new=_instant_sleep),
        ):
            app = build_fly_application(
                squadron=squadron,  # type: ignore[arg-type]
                event_queue=queue,
                epic_id="e-1",
                cwd=str(tmp_path),
                max_beads=10,
                watch=False,
            )
            driver = BurrWorkflowDriver(app, halt_after=FLY_TERMINAL_ACTIONS, event_queue=queue)
            await _collect(driver)

        _, _, state = driver.result
        assert state["loop_done_reason"] == "no_more_beads"
        assert sleep_calls == []  # no watch ⇒ no polling sleep


class TestFlyBurrGracefulStop:
    async def test_graceful_stop_exits_loop(self, tmp_path: Path) -> None:
        """Setting the flag mid-run terminates after current bead."""
        from maverick.workflows.fly_beads.graceful_stop import (
            request_graceful_stop,
            reset_graceful_stop,
        )

        reset_graceful_stop()
        request_graceful_stop()
        try:
            queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
            squadron = StubFlySquadron()

            with patch(
                "maverick.library.actions.beads.select_next_bead",
                new=AsyncMock(side_effect=[_bead("b-1"), _NO_MORE]),
            ):
                app = build_fly_application(
                    squadron=squadron,  # type: ignore[arg-type]
                    event_queue=queue,
                    epic_id="e-1",
                    cwd=str(tmp_path),
                    max_beads=10,
                )
                driver = BurrWorkflowDriver(
                    app, halt_after=FLY_TERMINAL_ACTIONS, event_queue=queue
                )
                await _collect(driver)

            _, _, state = driver.result
            # Loop exits at the first select_next_bead with reason=graceful_stop.
            assert state["loop_done_reason"] == "graceful_stop"
            assert state["processed_count"] == 0
        finally:
            reset_graceful_stop()
