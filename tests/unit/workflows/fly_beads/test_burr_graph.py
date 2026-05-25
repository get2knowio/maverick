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
    """Minimal stand-in for :class:`FlySquadron`.

    ``correctness_by_tier`` / ``completeness_by_tier`` let tests
    return distinct reviewer instances per tier name; the bare
    ``correctness`` / ``completeness`` slots are the default fallback
    when a tier-specific lookup misses.
    """

    def __init__(
        self,
        *,
        coder: StubCodingAgent | None = None,
        correctness: StubReviewerAgent | None = None,
        completeness: StubReviewerAgent | None = None,
        correctness_by_tier: dict[str, StubReviewerAgent] | None = None,
        completeness_by_tier: dict[str, StubReviewerAgent] | None = None,
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
        self.correctness_by_tier: dict[str, StubReviewerAgent] = correctness_by_tier or {}
        self.completeness_by_tier: dict[str, StubReviewerAgent] = completeness_by_tier or {}

    def coder_for(self, _tier: str) -> StubCodingAgent:
        return self.coder

    def correctness_reviewer_for(self, tier: str) -> StubReviewerAgent:
        return self.correctness_by_tier.get(tier, self.correctness)

    def completeness_reviewer_for(self, tier: str) -> StubReviewerAgent:
        return self.completeness_by_tier.get(tier, self.completeness)

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


class TestFlyBurrReviewerTransientEscalation:
    async def test_transient_failure_escalates_to_next_tier(self, tmp_path: Path) -> None:
        """Transient reviewer error → bump tier → next tier approves → bead commits."""
        from airframe.errors import RuntimeTransientError

        from maverick.workflows.fly_beads.graceful_stop import reset_graceful_stop

        reset_graceful_stop()

        # Tier 0 (_default) correctness raises a transient. The action
        # should escalate and re-run on the next-tier reviewer pair,
        # which is the squadron's fallback ``correctness`` /
        # ``completeness`` slots.
        default_correctness = StubReviewerAgent(
            review_kind="correctness",
            review_payloads=[SubmitReviewPayload(approved=True, findings=())],
        )
        default_correctness.raise_error = RuntimeTransientError("rate limited")
        default_completeness = StubReviewerAgent(
            review_kind="completeness",
            review_payloads=[SubmitReviewPayload(approved=True, findings=())],
        )

        squadron = StubFlySquadron(
            correctness=StubReviewerAgent(
                review_kind="correctness",
                review_payloads=[SubmitReviewPayload(approved=True, findings=())],
            ),
            completeness=StubReviewerAgent(
                review_kind="completeness",
                review_payloads=[SubmitReviewPayload(approved=True, findings=())],
            ),
            correctness_by_tier={"_default": default_correctness},
            completeness_by_tier={"_default": default_completeness},
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
        # Escalation bumped the tier and the next tier approved.
        assert state["reviewer_escalation_level"] == 1
        assert state["approved"] is True
        assert state["succeeded_count"] == 1
        assert state["needs_human_review"] is False

    async def test_transient_failure_exhausts_escalation_marks_human_review(
        self, tmp_path: Path
    ) -> None:
        """Every tier raises transient → needs-human-review with error message."""
        from airframe.errors import RuntimeTransientError

        from maverick.workflows.fly_beads.graceful_stop import reset_graceful_stop

        reset_graceful_stop()

        # Both the per-tier dict and the bare fallback raise transients —
        # because the action calls ``correctness_reviewer_for(tier)``
        # for each level, we ensure every lookup hits a raising stub.
        def _raising() -> StubReviewerAgent:
            r = StubReviewerAgent(
                review_kind="correctness",
                review_payloads=[
                    SubmitReviewPayload(approved=True, findings=()) for _ in range(2)
                ],
            )
            r.raise_error = RuntimeTransientError("upstream fault")
            return r

        class _AlwaysRaising:
            """Force every call to raise transient, regardless of how many tiers."""

            def __init__(self, kind: str) -> None:
                self.kind = kind
                self.calls = 0

            async def review(self, **_kwargs: Any) -> SubmitReviewPayload:
                self.calls += 1
                raise RuntimeTransientError(f"{self.kind} fault #{self.calls}")

        correctness_always = _AlwaysRaising("correctness")
        completeness_always = _AlwaysRaising("completeness")

        squadron = StubFlySquadron()
        # Override the tier-dispatch methods to always return the
        # raising stubs.
        squadron.correctness_reviewer_for = lambda _tier: correctness_always  # type: ignore[assignment]
        squadron.completeness_reviewer_for = lambda _tier: completeness_always  # type: ignore[assignment]

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
        # Climbed all 5 ladder rungs (level 0..4) and then exited.
        assert state["reviewer_escalation_level"] == 4
        assert state["needs_human_review"] is True
        assert state["approved"] is False
        # Each rung tried once → 5 correctness attempts; completeness
        # may be cancelled mid-flight by the gather, so we only assert
        # the lower bound for it.
        assert correctness_always.calls == 5
        # Finding text carries the exhaustion reason.
        finding_text = " ".join(state["last_review_findings"])
        assert "exhausted escalation" in finding_text


class TestFlyBurrAggregateReview:
    async def test_two_beads_trigger_aggregate(self, tmp_path: Path) -> None:
        """≥2 successful beads → ``aggregate_review`` runs before ``done``."""
        from maverick.workflows.fly_beads.graceful_stop import reset_graceful_stop

        reset_graceful_stop()

        agg_calls: list[dict[str, Any]] = []

        async def _fake_aggregate(
            *, objective: str, bead_list: str, diff_stat: str
        ) -> SubmitReviewPayload:
            agg_calls.append(
                {"objective": objective, "bead_list": bead_list, "diff_stat": diff_stat}
            )
            return SubmitReviewPayload(
                approved=False,
                findings=(
                    ReviewFindingPayload(severity="major", issue="cross-bead inconsistency"),
                ),
            )

        coder = StubCodingAgent(
            implement_payloads=[
                SubmitImplementationPayload(summary="i1"),
                SubmitImplementationPayload(summary="i2"),
            ],
            fix_payloads=[SubmitFixResultPayload(summary="f") for _ in range(5)],
        )
        squadron = StubFlySquadron(coder=coder)
        # Patch the .aggregate method directly on the per-tier reviewer
        # stub the squadron will return.
        squadron.correctness.aggregate = _fake_aggregate  # type: ignore[attr-defined]

        async def _fake_diff_stat(*_args: Any, **_kw: Any) -> Any:
            class _R:
                returncode = 0
                stdout = " src/foo.py | 12 ++++++++----\n"

            return _R()

        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
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
                    return_value=MarkBeadCompleteResult(success=True, bead_id="x", error=None)
                ),
            ),
            patch(
                "maverick.runners.command.CommandRunner.run",
                new=_fake_diff_stat,
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
        assert sequence[-2] == "aggregate_review"
        assert sequence[-1] == "done"

        assert len(agg_calls) == 1
        call = agg_calls[0]
        assert call["objective"] == "e-1"
        assert "b-1" in call["bead_list"]
        assert "b-2" in call["bead_list"]
        assert "src/foo.py" in call["diff_stat"]

        _, _, state = driver.result
        assert state["aggregate_review_payload"] is not None
        assert state["aggregate_review_payload"]["approved"] is False

    async def test_single_bead_skips_aggregate(self, tmp_path: Path) -> None:
        """1 successful bead → aggregate is below threshold → no-op."""
        from maverick.workflows.fly_beads.graceful_stop import reset_graceful_stop

        reset_graceful_stop()

        called = False

        async def _fail_if_called(*_args: Any, **_kw: Any) -> SubmitReviewPayload:
            nonlocal called
            called = True
            return SubmitReviewPayload(approved=True, findings=())

        squadron = StubFlySquadron()
        squadron.correctness.aggregate = _fail_if_called  # type: ignore[attr-defined]

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

        assert called is False
        _, _, state = driver.result
        assert state["aggregate_review_payload"] is None


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
