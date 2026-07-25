"""Unit tests for the mid-flight reconcile pass (052-conditional-landing, US3).

See specs/052-conditional-landing/contracts/mid-flight-reconcile.md for the
contract this module implements: at every fly bead boundary, detect
newly-answered assumption-ledger entries and — when any are found — run
``ReconcileWorkflow`` in-process, without ever letting a failure interrupt
the Burr drain loop.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from maverick.assumptions.errors import AssumptionLedgerError
from maverick.assumptions.models import AssumptionRecord, Severity
from maverick.burr import BurrWorkflowDriver
from maverick.config import MaverickConfig, ReconcileConfig
from maverick.events import ProgressEvent, StepOutput, WorkflowCompleted, WorkflowStarted
from maverick.exceptions import WorkflowError
from maverick.library.actions.types import MarkBeadCompleteResult
from maverick.payloads import SubmitFixResultPayload, SubmitImplementationPayload
from maverick.workflows.fly_beads import mid_flight as mid_flight_module
from maverick.workflows.fly_beads.burr_graph import FLY_TERMINAL_ACTIONS, build_fly_application
from maverick.workflows.fly_beads.graceful_stop import (
    request_graceful_stop,
    reset_graceful_stop,
)
from maverick.workflows.fly_beads.mid_flight import MidFlightOutcome, run_mid_flight_pass
from tests.unit.agents.airframe_stubs import StubCodingAgent
from tests.unit.workflows.fly_beads.test_burr_graph import (
    _NO_MORE,
    StubFlySquadron,
    _action_sequence,
    _bead,
    _collect,
    _gate_passed,
)


@pytest.fixture(autouse=True)
def _reset_graceful_stop_flag() -> Any:
    reset_graceful_stop()
    yield
    reset_graceful_stop()


def _config(*, mid_flight: bool = True) -> MaverickConfig:
    return MaverickConfig(reconcile=ReconcileConfig(mid_flight=mid_flight))


def _assumption_record(entry_id: str = "bd-1") -> AssumptionRecord:
    return AssumptionRecord(
        bead_id=entry_id,
        question="Which auth provider?",
        adopted_answer="OAuth",
        alternatives=(),
        severity=Severity.MEDIUM,
        severity_defaulted=False,
        status="answered",
        owner_spec="052-conditional-landing",
        source_bead="",
        change_ids=(),
        is_legacy=False,
    )


class _FakeWorkflowResult:
    def __init__(self, *, success: bool, final_output: dict[str, Any] | None) -> None:
        self.success = success
        self.final_output = final_output


class _FakeReconcileWorkflow:
    """Stub matching the ``PythonWorkflow.execute()`` shape mid_flight drives.

    Records every ``inputs`` dict it was constructed/executed with (class
    level, so tests can assert on it) and yields a couple of fake
    ``ProgressEvent``s before setting ``self.result``, mirroring
    ``PythonWorkflow.execute()``'s real contract: an async generator of
    events, with ``.result`` populated once draining completes.
    """

    captured_configs: list[MaverickConfig] = []
    captured_inputs: list[dict[str, Any]] = []
    #: Set by a test to make ``execute()`` raise instead of completing.
    raise_error: Exception | None = None
    #: Outcomes list controls the report's ``outcomes`` field.
    outcomes: list[dict[str, Any]] = [
        {"entry_id": "bd-1", "status": "reconciled"},
    ]

    def __init__(self, *, config: MaverickConfig) -> None:
        type(self).captured_configs.append(config)
        self.config = config
        self.result: _FakeWorkflowResult | None = None

    async def execute(self, inputs: dict[str, Any]):  # noqa: ANN201 - async generator, mirrors PythonWorkflow
        type(self).captured_inputs.append(inputs)
        yield WorkflowStarted(workflow_name="reconcile", inputs=inputs)
        yield StepOutput(step_name="detect", message="detecting", display_label="")
        if type(self).raise_error is not None:
            raise type(self).raise_error
        self.result = _FakeWorkflowResult(
            success=True, final_output={"outcomes": list(type(self).outcomes)}
        )
        yield WorkflowCompleted(workflow_name="reconcile", success=True, total_duration_ms=1)


@pytest.fixture(autouse=True)
def _reset_fake_reconcile_workflow() -> Any:
    _FakeReconcileWorkflow.captured_configs = []
    _FakeReconcileWorkflow.captured_inputs = []
    _FakeReconcileWorkflow.raise_error = None
    _FakeReconcileWorkflow.outcomes = [{"entry_id": "bd-1", "status": "reconciled"}]
    yield


async def _collect_events(queue: asyncio.Queue[ProgressEvent | None]) -> list[ProgressEvent]:
    events: list[ProgressEvent] = []
    while not queue.empty():
        evt = queue.get_nowait()
        if evt is not None:
            events.append(evt)
    return events


# ---------------------------------------------------------------------------
# Precondition short-circuits
# ---------------------------------------------------------------------------


async def test_disabled_skips_without_touching_bd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    detect_mock = AsyncMock(return_value=(_assumption_record(),))
    monkeypatch.setattr(mid_flight_module, "answered_unreconciled_entries", detect_mock)

    queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
    outcome = await run_mid_flight_pass(
        cwd=tmp_path,
        config=_config(mid_flight=False),
        fly_run_id="fly-1",
        event_sink=queue,
    )

    assert outcome == MidFlightOutcome(
        detected=0, processed=0, escalated=0, skipped_reason="disabled", error=None
    )
    detect_mock.assert_not_called()


async def test_graceful_stop_skips_without_touching_bd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    detect_mock = AsyncMock(return_value=(_assumption_record(),))
    monkeypatch.setattr(mid_flight_module, "answered_unreconciled_entries", detect_mock)
    request_graceful_stop()

    queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
    outcome = await run_mid_flight_pass(
        cwd=tmp_path,
        config=_config(),
        fly_run_id="fly-1",
        event_sink=queue,
    )

    assert outcome == MidFlightOutcome(
        detected=0, processed=0, escalated=0, skipped_reason="graceful-stop", error=None
    )
    detect_mock.assert_not_called()


async def test_none_detected_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mid_flight_module, "answered_unreconciled_entries", AsyncMock(return_value=())
    )

    queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
    outcome = await run_mid_flight_pass(
        cwd=tmp_path,
        config=_config(),
        fly_run_id="fly-1",
        event_sink=queue,
    )

    assert outcome == MidFlightOutcome(
        detected=0, processed=0, escalated=0, skipped_reason="none-detected", error=None
    )


async def test_detection_query_failure_treated_as_none_detected_with_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        mid_flight_module,
        "answered_unreconciled_entries",
        AsyncMock(side_effect=AssumptionLedgerError("bd query failed")),
    )

    queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
    outcome = await run_mid_flight_pass(
        cwd=tmp_path,
        config=_config(),
        fly_run_id="fly-1",
        event_sink=queue,
    )

    assert outcome.skipped_reason == "none-detected"
    assert outcome.error is None

    events = await _collect_events(queue)
    warnings = [e for e in events if isinstance(e, StepOutput) and e.level == "warning"]
    assert len(warnings) == 1
    assert "bd query failed" in warnings[0].message


# ---------------------------------------------------------------------------
# Non-empty detection: invokes ReconcileWorkflow with the contract's inputs
# ---------------------------------------------------------------------------


async def test_non_empty_detection_invokes_reconcile_workflow_with_expected_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        mid_flight_module,
        "answered_unreconciled_entries",
        AsyncMock(return_value=(_assumption_record(),)),
    )
    monkeypatch.setattr(mid_flight_module, "ReconcileWorkflow", _FakeReconcileWorkflow)

    queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
    config = _config()
    outcome = await run_mid_flight_pass(
        cwd=tmp_path,
        config=config,
        fly_run_id="fly-run-42",
        event_sink=queue,
    )

    assert outcome.detected == 1
    assert outcome.processed == 1
    assert outcome.escalated == 0
    assert outcome.skipped_reason is None
    assert outcome.error is None

    assert len(_FakeReconcileWorkflow.captured_inputs) == 1
    inputs = _FakeReconcileWorkflow.captured_inputs[0]
    assert inputs["cwd"] == str(tmp_path)
    assert inputs["dry_run"] is False
    assert inputs["active_fly_run_id"] == "fly-run-42"
    assert isinstance(inputs["run_id"], str) and inputs["run_id"]

    assert _FakeReconcileWorkflow.captured_configs == [config]


async def test_progress_events_forwarded_to_event_sink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        mid_flight_module,
        "answered_unreconciled_entries",
        AsyncMock(return_value=(_assumption_record(),)),
    )
    monkeypatch.setattr(mid_flight_module, "ReconcileWorkflow", _FakeReconcileWorkflow)

    queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
    await run_mid_flight_pass(
        cwd=tmp_path,
        config=_config(),
        fly_run_id="fly-1",
        event_sink=queue,
    )

    events = await _collect_events(queue)
    # The child workflow's own WorkflowStarted/StepOutput/WorkflowCompleted
    # events must be forwarded verbatim (not just fly's own summary output).
    assert any(isinstance(e, WorkflowStarted) for e in events)
    assert any(isinstance(e, WorkflowCompleted) for e in events)


async def test_escalated_outcomes_counted_separately_from_reconciled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        mid_flight_module,
        "answered_unreconciled_entries",
        AsyncMock(return_value=(_assumption_record("bd-1"), _assumption_record("bd-2"))),
    )
    _FakeReconcileWorkflow.outcomes = [
        {"entry_id": "bd-1", "status": "reconciled"},
        {"entry_id": "bd-2", "status": "needs_interactive_review"},
    ]
    monkeypatch.setattr(mid_flight_module, "ReconcileWorkflow", _FakeReconcileWorkflow)

    queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
    outcome = await run_mid_flight_pass(
        cwd=tmp_path,
        config=_config(),
        fly_run_id="fly-1",
        event_sink=queue,
    )

    assert outcome.detected == 2
    assert outcome.processed == 1
    assert outcome.escalated == 1


# ---------------------------------------------------------------------------
# Failure handling — never raises into the Burr application
# ---------------------------------------------------------------------------


async def test_workflow_error_from_child_caught_and_returns_error_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        mid_flight_module,
        "answered_unreconciled_entries",
        AsyncMock(return_value=(_assumption_record(),)),
    )
    _FakeReconcileWorkflow.raise_error = WorkflowError("cannot run reconcile: fly is flying")
    monkeypatch.setattr(mid_flight_module, "ReconcileWorkflow", _FakeReconcileWorkflow)

    queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
    # Must not raise.
    outcome = await run_mid_flight_pass(
        cwd=tmp_path,
        config=_config(),
        fly_run_id="fly-1",
        event_sink=queue,
    )

    assert outcome.detected == 1
    assert outcome.processed == 0
    assert outcome.escalated == 0
    assert outcome.skipped_reason is None
    assert outcome.error is not None
    assert "cannot run reconcile" in outcome.error

    events = await _collect_events(queue)
    warnings = [e for e in events if isinstance(e, StepOutput) and e.level == "warning"]
    assert len(warnings) == 1


# ---------------------------------------------------------------------------
# T031: end-to-end graph scenario
# ---------------------------------------------------------------------------


class TestMidFlightEndToEnd:
    """T031: drive the full Burr graph with a changed answer appearing

    mid-run. Covers: the pass fires at the boundary after bead 1; bead 2
    still implements and commits; the final pass runs before
    ``aggregate_review``; a second detection call returns nothing
    (idempotence, FR-015); and a bead whose readiness was released by the
    mid-flight answer (FR-012) is picked up by a later
    ``select_next_bead`` cycle in the same run.
    """

    async def test_changed_answer_between_beads_reconciles_without_stalling_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reset_graceful_stop()

        # Detection: one changed answer at the first boundary (after
        # bead b-1); every subsequent boundary call finds nothing —
        # proving idempotence (FR-015): the same answer is never
        # re-processed once reconciled.
        detect_mock = AsyncMock(side_effect=[(_assumption_record("bd-answer-1"),), (), (), ()])
        monkeypatch.setattr(mid_flight_module, "answered_unreconciled_entries", detect_mock)
        monkeypatch.setattr(mid_flight_module, "ReconcileWorkflow", _FakeReconcileWorkflow)

        # bd_select: b-1, then b-2 (already queued), then b-3 — a bead
        # that only becomes selectable on the THIRD cycle, standing in
        # for one whose `blocks` edge was released by the mid-flight
        # answer/waive between boundaries (FR-012; readiness re-query is
        # bd's job — research R10 — so a stubbed bd_select returning it
        # on a later cycle is the correct unit-level stand-in).
        select_mock = AsyncMock(side_effect=[_bead("b-1"), _bead("b-2"), _bead("b-3"), _NO_MORE])

        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        coder = StubCodingAgent(
            implement_payloads=[
                SubmitImplementationPayload(summary="i1"),
                SubmitImplementationPayload(summary="i2"),
                SubmitImplementationPayload(summary="i3"),
            ],
            fix_payloads=[SubmitFixResultPayload(summary="f") for _ in range(5)],
        )
        squadron = StubFlySquadron(coder=coder)

        with (
            patch(
                "maverick.library.actions.beads.select_next_bead",
                new=select_mock,
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
        ):
            app = build_fly_application(
                squadron=squadron,  # type: ignore[arg-type]
                event_queue=queue,
                epic_id="e-1",
                cwd=str(tmp_path),
                max_beads=10,
                reconcile_config=MaverickConfig(),
                fly_run_id="fly-e2e-1",
            )
            driver = BurrWorkflowDriver(app, halt_after=FLY_TERMINAL_ACTIONS, event_queue=queue)
            events = await _collect(driver)

        sequence = _action_sequence(events)

        # All three beads (including the one whose readiness was
        # released mid-run) completed in this same run.
        assert sequence.count("implement") == 3
        assert sequence.count("commit") == 3

        # The boundary pass ran once per bead, plus the final pass.
        assert sequence.count("reconcile_answers") == 3
        assert sequence.count("reconcile_answers_final") == 1
        assert sequence[-3] == "reconcile_answers_final"
        assert sequence[-2] == "aggregate_review"
        assert sequence[-1] == "done"

        _, _, state = driver.result
        assert state["succeeded_count"] == 3
        assert state["failed_count"] == 0
        assert state["completed_bead_ids"] == ["b-1", "b-2", "b-3"]

        # Detection ran at every boundary (3 record_outcome passes + 1
        # final = 4 calls); only the first found anything, and the
        # ReconcileWorkflow was invoked exactly once as a result —
        # idempotence (FR-015): the second and third detection calls
        # (post-reconcile) found nothing left to do.
        assert detect_mock.await_count == 4
        assert len(_FakeReconcileWorkflow.captured_inputs) == 1
        assert _FakeReconcileWorkflow.captured_inputs[0]["active_fly_run_id"] == "fly-e2e-1"
