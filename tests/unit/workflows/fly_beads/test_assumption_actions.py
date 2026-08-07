"""Tests for assumption-ledger wiring in the fly_beads Burr actions.

Covers: implement/review/fix accumulate payload ``assumptions`` into
``pending_assumptions`` (cleared on bead start), ``record_assumptions``
creates entries non-fatally, and ``commit`` captures ``commit_change_id``
and stamps recorded entries non-fatally.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from burr.core import State

from maverick.assumptions.errors import AssumptionLedgerError
from maverick.assumptions.models import (
    AssumptionRecord,
    AssumptionReportEntry,
    Severity,
    StampResult,
)
from maverick.events import ProgressEvent
from maverick.payloads import SubmitFixResultPayload, SubmitImplementationPayload
from maverick.runway.store import RunwayStore
from maverick.workflows.fly_beads import actions as fly_actions
from tests.unit.agents.airframe_stubs import StubCodingAgent

pytestmark = pytest.mark.asyncio


async def _initialized_runway_cwd(tmp_path: Path) -> str:
    """Create a tmp checkout with an initialized runway store at ``cwd``.

    Mirrors ``library.actions.runway._get_store``'s ``is_initialized``
    contract so production code building a store from ``cwd`` finds one
    regardless of exactly how it locates it.
    """
    store = RunwayStore(tmp_path / ".maverick" / "runway")
    await store.initialize()
    return str(tmp_path)


class _NullCM:
    def __enter__(self) -> _NullCM:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _StubSquadron:
    def __init__(self, coder: StubCodingAgent) -> None:
        self._coder = coder

    def coder_for(self, _tier: str) -> StubCodingAgent:
        return self._coder

    def bead_context(self, **_kwargs: object) -> _NullCM:
        return _NullCM()


def _queue() -> asyncio.Queue[ProgressEvent | None]:
    return asyncio.Queue()


_ASSUMPTION_DICT = {"question": "Q?", "adopted_answer": "A.", "severity": "medium"}


class TestImplementAccumulatesAssumptions:
    async def test_appends_assumptions_from_payload(self) -> None:
        squadron = _StubSquadron(
            StubCodingAgent(
                implement_payloads=[
                    SubmitImplementationPayload(
                        summary="did stuff", assumptions=[_ASSUMPTION_DICT]
                    )
                ]
            )
        )
        state = State(
            {
                "current_bead": {"bead_id": "b-1", "title": "t", "description": "d"},
                "current_bead_id": "b-1",
                "implementer_escalation_level": 0,
                "pending_assumptions": [],
            }
        )
        _, new_state = await fly_actions.implement(state, squadron=squadron, events=_queue())  # type: ignore[arg-type]
        pending = new_state["pending_assumptions"]
        assert len(pending) == 1
        assert pending[0]["question"] == "Q?"

    async def test_preserves_existing_pending_assumptions(self) -> None:
        squadron = _StubSquadron(
            StubCodingAgent(implement_payloads=[SubmitImplementationPayload(summary="did stuff")])
        )
        state = State(
            {
                "current_bead": {"bead_id": "b-1", "title": "t", "description": "d"},
                "current_bead_id": "b-1",
                "implementer_escalation_level": 0,
                "pending_assumptions": [dict(_ASSUMPTION_DICT)],
            }
        )
        _, new_state = await fly_actions.implement(state, squadron=squadron, events=_queue())  # type: ignore[arg-type]
        assert len(new_state["pending_assumptions"]) == 1


class TestFixAccumulatesAssumptions:
    async def test_run_fix_returns_assumptions_from_fix_payload(self) -> None:
        squadron = _StubSquadron(
            StubCodingAgent(
                fix_payloads=[
                    SubmitFixResultPayload(summary="fixed", assumptions=[_ASSUMPTION_DICT])
                ]
            )
        )
        ok, level, assumptions = await fly_actions._run_fix(
            squadron=squadron,  # type: ignore[arg-type]
            events=_queue(),
            bead_id="b-1",
            phase="gate",
            round_n=1,
            failure_message="boom",
        )
        assert ok is True
        assert level == 0
        assert len(assumptions) == 1
        assert assumptions[0]["question"] == "Q?"


class TestProcessBeadStartResetsAssumptionState:
    async def test_resets_all_three_keys(self) -> None:
        state = State(
            {
                "current_bead": {"bead_id": "b-1"},
                "current_bead_id": "b-1",
                "pending_assumptions": [dict(_ASSUMPTION_DICT)],
                "recorded_assumption_ids": ["dea-1"],
                "commit_change_id": "old-change-id",
            }
        )
        _, new_state = await fly_actions.process_bead_start(state)
        assert new_state["pending_assumptions"] == []
        assert new_state["recorded_assumption_ids"] == []
        assert new_state["commit_change_id"] == ""


class TestRecordAssumptionsAction:
    async def test_no_pending_assumptions_is_a_noop(self) -> None:
        state = State({"current_bead_id": "b-1", "pending_assumptions": []})
        _, new_state = await fly_actions.record_assumptions(
            state, cwd="/tmp/repo", epic_id="epic-1", events=_queue()
        )
        assert new_state["recorded_assumption_ids"] == []

    async def test_records_each_pending_assumption(self) -> None:
        state = State(
            {
                "current_bead_id": "b-1",
                "pending_assumptions": [dict(_ASSUMPTION_DICT)],
            }
        )
        record = AssumptionRecord(
            bead_id="dea-1",
            question="Q?",
            adopted_answer="A.",
            alternatives=(),
            severity=Severity.MEDIUM,
            severity_defaulted=False,
            status="open",
            owner_spec="epic-1",
            source_bead="b-1",
            change_ids=(),
            is_legacy=False,
        )
        with patch(
            "maverick.assumptions.ledger.record_assumption",
            new=AsyncMock(return_value=record),
        ) as mock_record:
            _, new_state = await fly_actions.record_assumptions(
                state, cwd="/tmp/repo", epic_id="epic-1", events=_queue()
            )
        mock_record.assert_awaited_once()
        assert new_state["recorded_assumption_ids"] == ["dea-1"]

    async def test_ledger_error_warns_and_continues(self) -> None:
        state = State(
            {
                "current_bead_id": "b-1",
                "pending_assumptions": [dict(_ASSUMPTION_DICT)],
            }
        )
        with patch(
            "maverick.assumptions.ledger.record_assumption",
            new=AsyncMock(side_effect=AssumptionLedgerError("bd unavailable")),
        ):
            _, new_state = await fly_actions.record_assumptions(
                state, cwd="/tmp/repo", epic_id="epic-1", events=_queue()
            )
        # Non-fatal: no exception propagates, entry just isn't recorded.
        assert new_state["recorded_assumption_ids"] == []


class TestRecordAssumptionsCallsAttachSuggestions:
    """055-learned-assumption-resolution T014 (US2): after the recording
    loop, ``record_assumptions`` hands the newly recorded entries to
    ``assumptions.suggestions.attach_suggestions`` so a matching prior
    resolution can be surfaced later — non-fatally (research R5, T019).
    """

    async def test_calls_attach_suggestions_with_recorded_entries(self, tmp_path: Path) -> None:
        cwd = await _initialized_runway_cwd(tmp_path)
        state = State(
            {
                "current_bead_id": "b-1",
                "pending_assumptions": [dict(_ASSUMPTION_DICT)],
            }
        )
        record = AssumptionRecord(
            bead_id="dea-1",
            question="Q?",
            adopted_answer="A.",
            alternatives=(),
            severity=Severity.MEDIUM,
            severity_defaulted=False,
            status="open",
            owner_spec="epic-1",
            source_bead="b-1",
            change_ids=(),
            is_legacy=False,
        )
        with (
            patch(
                "maverick.assumptions.ledger.record_assumption",
                new=AsyncMock(return_value=record),
            ),
            patch(
                "maverick.workflows.fly_beads.actions.attach_suggestions",
                new=AsyncMock(),
            ) as mock_attach,
        ):
            _, new_state = await fly_actions.record_assumptions(
                state, cwd=cwd, epic_id="epic-1", events=_queue()
            )

        assert new_state["recorded_assumption_ids"] == ["dea-1"]
        mock_attach.assert_awaited_once()
        call_args = list(mock_attach.await_args.args) + list(
            mock_attach.await_args.kwargs.values()
        )
        records_arg = next((a for a in call_args if isinstance(a, (list, tuple))), None)
        assert records_arg is not None, (
            "expected attach_suggestions to be called with a list/tuple of "
            f"newly recorded entries; got call args {call_args!r}"
        )
        # Must be `AssumptionReportEntry`s, not bare `AssumptionRecord`s:
        # `attach_suggestions` reads `entry.record.*`, so handing it a raw
        # record raises `AttributeError` inside its own best-effort handler
        # and silently disables suggestions on this path.
        assert all(isinstance(item, AssumptionReportEntry) for item in records_arg), (
            f"expected AssumptionReportEntry instances; got {records_arg!r}"
        )
        assert {item.record.bead_id for item in records_arg} == {"dea-1"}

    async def test_attach_suggestions_failure_is_non_fatal(self, tmp_path: Path) -> None:
        cwd = await _initialized_runway_cwd(tmp_path)
        state = State(
            {
                "current_bead_id": "b-1",
                "pending_assumptions": [dict(_ASSUMPTION_DICT)],
            }
        )
        record = AssumptionRecord(
            bead_id="dea-1",
            question="Q?",
            adopted_answer="A.",
            alternatives=(),
            severity=Severity.MEDIUM,
            severity_defaulted=False,
            status="open",
            owner_spec="epic-1",
            source_bead="b-1",
            change_ids=(),
            is_legacy=False,
        )
        with (
            patch(
                "maverick.assumptions.ledger.record_assumption",
                new=AsyncMock(return_value=record),
            ),
            patch(
                "maverick.workflows.fly_beads.actions.attach_suggestions",
                new=AsyncMock(side_effect=RuntimeError("runway unavailable")),
            ),
        ):
            result_dict, new_state = await fly_actions.record_assumptions(
                state, cwd=cwd, epic_id="epic-1", events=_queue()
            )

        # The action must still complete normally and preserve its
        # existing return shape even though attach_suggestions blew up.
        assert result_dict == {"recorded": 1}
        assert new_state["recorded_assumption_ids"] == ["dea-1"]

    async def test_no_pending_assumptions_does_not_call_attach_suggestions(
        self, tmp_path: Path
    ) -> None:
        cwd = await _initialized_runway_cwd(tmp_path)
        state = State({"current_bead_id": "b-1", "pending_assumptions": []})
        with patch(
            "maverick.workflows.fly_beads.actions.attach_suggestions",
            new=AsyncMock(),
        ) as mock_attach:
            _, new_state = await fly_actions.record_assumptions(
                state, cwd=cwd, epic_id="epic-1", events=_queue()
            )

        assert new_state["recorded_assumption_ids"] == []
        mock_attach.assert_not_awaited()


class TestCommitCapturesChangeIdAndStamps:
    async def test_captures_commit_change_id(self) -> None:
        state = State(
            {
                "current_bead": {"bead_id": "b-1", "title": "t"},
                "current_bead_id": "b-1",
                "approved": True,
                "needs_human_review": False,
                "review_rounds": 0,
                "recorded_assumption_ids": [],
            }
        )
        with (
            patch(
                "maverick.library.actions.jj.jj_commit_bead",
                new=AsyncMock(return_value={"change_id": "c-123", "success": True}),
            ),
            patch(
                "maverick.library.actions.beads.mark_bead_complete",
                new=AsyncMock(),
            ),
        ):
            _, new_state = await fly_actions.commit(state, cwd="/tmp/repo", events=_queue())
        assert new_state["commit_change_id"] == "c-123"
        assert new_state["commit_ok"] is True

    async def test_stamps_recorded_assumption_ids(self) -> None:
        state = State(
            {
                "current_bead": {"bead_id": "b-1", "title": "t"},
                "current_bead_id": "b-1",
                "approved": True,
                "needs_human_review": False,
                "review_rounds": 0,
                "recorded_assumption_ids": ["dea-1", "dea-2"],
            }
        )
        with (
            patch(
                "maverick.library.actions.jj.jj_commit_bead",
                new=AsyncMock(return_value={"change_id": "c-123", "success": True}),
            ),
            patch(
                "maverick.library.actions.beads.mark_bead_complete",
                new=AsyncMock(),
            ),
            patch(
                "maverick.assumptions.ledger.stamp_change_id",
                new=AsyncMock(
                    return_value=StampResult(
                        change_id="c-123", stamped=("dea-1", "dea-2"), failed={}
                    )
                ),
            ) as mock_stamp,
        ):
            await fly_actions.commit(state, cwd="/tmp/repo", events=_queue())

        mock_stamp.assert_awaited_once()
        assert mock_stamp.await_args.kwargs["entry_ids"] == ["dea-1", "dea-2"]
        assert mock_stamp.await_args.kwargs["change_id"] == "c-123"

    async def test_stamp_failure_does_not_fail_commit(self) -> None:
        state = State(
            {
                "current_bead": {"bead_id": "b-1", "title": "t"},
                "current_bead_id": "b-1",
                "approved": True,
                "needs_human_review": False,
                "review_rounds": 0,
                "recorded_assumption_ids": ["dea-1"],
            }
        )
        with (
            patch(
                "maverick.library.actions.jj.jj_commit_bead",
                new=AsyncMock(return_value={"change_id": "c-123", "success": True}),
            ),
            patch(
                "maverick.library.actions.beads.mark_bead_complete",
                new=AsyncMock(),
            ),
            patch(
                "maverick.assumptions.ledger.stamp_change_id",
                new=AsyncMock(
                    return_value=StampResult(
                        change_id="c-123", stamped=(), failed={"dea-1": "boom"}
                    )
                ),
            ),
        ):
            _, new_state = await fly_actions.commit(state, cwd="/tmp/repo", events=_queue())

        assert new_state["commit_ok"] is True
