"""Integration test: end-to-end ``maverick notify`` flow (tasks.md T023, US3).

Simulates a multi-day cron-driven run of the assumption batch scheduler by
composing the real production modules the same way
``src/maverick/cli/commands/notify.py::_evaluate_and_effect`` does —
:func:`~maverick.assumptions.ledger.report_entries` (against a mocked
``BeadClient.query``/``.show``, never a real ``bd``),
:func:`~maverick.assumptions.schedule.evaluate.evaluate` (pure, injected
``now``), :class:`~maverick.assumptions.schedule.deliver.NtfyDeliverer`
(real HTTP-shaped requests captured via ``httpx.MockTransport``, never a
real network call), and :mod:`~maverick.assumptions.schedule.state`'s
``load_state``/``finalize_state``/``save_state`` — driven tick by tick with
an injected sequence of ``now`` values instead of the wall clock, per
research R6 ("no freezegun, no ``datetime.now`` mocking"). The CLI dispatch
layer itself (lock acquisition, JSON envelope shape, error mapping) is
already covered by ``tests/unit/cli/commands/test_notify_json.py`` — this
file proves the module composition end-to-end instead.

Covers:

* **SC-001**: entries recorded at arbitrary hours overnight accumulate
  silently through quiet hours and deliver as exactly one 09:00 batch.
* **SC-003**: repeated invocations — within the same window, and later the
  same day with nothing new — never re-deliver.
* **SC-004**: every fire is reconstructible from ``state.json`` alone
  (rule citations + covered entry ids match what actually happened).
* **SC-005**: every entry in a mixed run (open medium, open high,
  answered, waived, low-severity) ends up accounted for — delivered,
  human-resolved, or knowingly silent-and-low — never silently dropped.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
from tenacity import wait_fixed

from maverick.assumptions.ledger import report_entries
from maverick.assumptions.models import STATUS_ANSWERED, STATUS_OPEN, STATUS_WAIVED
from maverick.assumptions.schedule.deliver import DeliveryFailedError, NtfyDeliverer
from maverick.assumptions.schedule.evaluate import evaluate
from maverick.assumptions.schedule.models import EvaluationOutcome
from maverick.assumptions.schedule.state import (
    DeliveryState,
    finalize_state,
    load_state,
    save_state,
)
from maverick.beads.client import BeadClient
from maverick.beads.models import BeadDetails, BeadSummary
from maverick.config import AssumptionScheduleConfig, NotificationConfig, QuietHoursConfig

NY = ZoneInfo("America/New_York")

_DESCRIPTION = (
    "## Question\n\nQ?\n\n"
    "## Adopted Answer\n\nA.\n\n"
    "## Alternatives Considered\n\n(none)\n\n"
    "## Context\n\nSource bead: mav-source — Source\n"
)


def _bead(
    bead_id: str,
    *,
    severity: str = "medium",
    status: str = STATUS_OPEN,
    owner_spec: str = "054-assumption-batch-scheduler",
    created_at: str,
    answer_text: str | None = None,
    waived_by: str | None = None,
    waive_reason: str | None = None,
) -> BeadDetails:
    """A minimal, valid ``assumption``-labeled bead — real enough for
    ``report_entries()``/``evaluate()`` to process; inert on everything
    they don't look at (question/answer text)."""
    state: dict[str, str] = {
        "assumption_severity": severity,
        "assumption_status": status,
        "assumption_owner_spec": owner_spec,
        "source_bead": "mav-source",
    }
    if answer_text is not None:
        state["assumption_answer"] = answer_text
    if waived_by is not None:
        state["assumption_waived_by"] = waived_by
        state["assumption_waive_reason"] = waive_reason or "n/a"
        state["assumption_waived_at"] = created_at
    return BeadDetails(
        id=bead_id,
        title=f"Assumption: {bead_id}",
        description=_DESCRIPTION,
        bead_type="task",
        status="open" if status == STATUS_OPEN else "closed",
        labels=["assumption"],
        state=state,
        created_at=created_at,
    )


def _wire_ledger(monkeypatch: pytest.MonkeyPatch, beads: dict[str, BeadDetails]) -> None:
    """Point a real ``BeadClient`` at an in-memory, mutable bd-shaped
    ledger — ``.query``/``.show`` read *beads* live, so mutating the dict
    between ticks (answer/waive) is visible on the next sweep, exactly as
    a real ``bd`` database would be. Never shells out to a real ``bd``."""

    async def _query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
        return [
            BeadSummary(id=details.id, title=details.title, status=details.status)
            for details in beads.values()
        ]

    async def _show(self: BeadClient, bead_id: str) -> BeadDetails:
        return beads[bead_id]

    async def _verify_available(self: BeadClient) -> bool:
        return True

    monkeypatch.setattr(BeadClient, "query", _query)
    monkeypatch.setattr(BeadClient, "show", _show)
    monkeypatch.setattr(BeadClient, "verify_available", _verify_available)


async def _run_tick(
    *,
    cwd: Path,
    client: BeadClient,
    schedule: AssumptionScheduleConfig,
    notif: NotificationConfig,
    now: datetime,
    transport: httpx.MockTransport,
) -> tuple[EvaluationOutcome, DeliveryState]:
    """One ``maverick notify`` evaluation.

    Replicates ``notify.py``'s real-mode ``_evaluate_and_effect`` body —
    the same ``report_entries`` -> ``evaluate`` -> deliver ->
    ``finalize_state`` -> ``save_state`` composition — sans the CLI/lock
    plumbing around it (lock acquisition and the JSON envelope are proven
    directly against the CLI in ``tests/unit/cli/commands/test_notify_json.py``).
    Driven with an injected *now* instead of the wall clock (research R6).
    """
    entries = await report_entries(client)
    state = await load_state(cwd)
    outcome = evaluate(entries, schedule, state, now)

    failed_indices: set[int] = set()
    if outcome.deliveries:
        assert notif.topic is not None
        async with NtfyDeliverer(
            server=notif.server,
            topic=notif.topic,
            transport=transport,
            wait=wait_fixed(0),
        ) as deliverer:
            for index, decision in enumerate(outcome.deliveries):
                try:
                    await deliverer.deliver(decision.kind, decision.summary)
                except DeliveryFailedError:
                    failed_indices.add(index)

    final_state = finalize_state(
        outcome=outcome, prior_state=state, failed_indices=failed_indices, now=now
    )
    await save_state(final_state, cwd)
    return outcome, final_state


def _mock_transport(sent: list[httpx.Request]) -> httpx.MockTransport:
    def _handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200)

    return httpx.MockTransport(_handler)


@pytest.mark.asyncio
async def test_overnight_accumulation_delivers_exactly_one_batch_and_stays_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SC-001 + SC-003: entries recorded at arbitrary overnight hours
    accumulate silently through quiet hours and deliver as exactly one
    09:00 batch; re-running afterwards — within the same window, and
    later the same day with nothing new — never re-delivers.

    A single configured window (rather than the human-facing 09:00/17:00
    pair) keeps this scenario isolated to the 09:00 occurrence under test:
    a 17:00 window would already be past-due by the "overnight" ticks
    below (FR-020's delayed-cron behavior, pinned separately in
    ``tests/unit/assumptions/schedule/test_evaluate_windows.py``'s
    ``TestDelayedCron``) and would contaminate the "nothing fires
    overnight" assertion with an unrelated occurrence.
    """
    schedule = AssumptionScheduleConfig(
        windows=["09:00"],
        quiet_hours=QuietHoursConfig(start="22:00", end="07:00"),
        min_batch_size=1,
    )
    notif = NotificationConfig(enabled=True, server="https://ntfy.test", topic="scheduler-test")

    beads: dict[str, BeadDetails] = {}
    _wire_ledger(monkeypatch, beads)
    client = BeadClient(cwd=tmp_path)

    sent: list[httpx.Request] = []
    transport = _mock_transport(sent)

    async def _tick(now: datetime) -> EvaluationOutcome:
        outcome, _ = await _run_tick(
            cwd=tmp_path,
            client=client,
            schedule=schedule,
            notif=notif,
            now=now,
            transport=transport,
        )
        return outcome

    # Seed continuity: settle *yesterday's* 09:00 occurrence (empty — no
    # entries recorded yet) before quiet hours begin, exactly as a
    # daily-running cron already would have. Without this, the very first
    # evaluation below (at 23:30) would itself be evaluating an
    # already-past-due-but-never-decided 09:00 occurrence and would
    # deliver immediately (FR-020) — this seed isolates the scenario to
    # the *next* day's 09:00 occurrence, the one actually under test.
    await _tick(datetime(2026, 8, 5, 9, 5, tzinfo=NY))
    assert sent == []

    # Entries recorded at arbitrary hours overnight, inside quiet hours:
    # each evaluation accumulates silently, nothing fires.
    beads["mav-1"] = _bead("mav-1", created_at="2026-08-05T23:10:00Z")
    await _tick(datetime(2026, 8, 5, 23, 30, tzinfo=NY))
    assert sent == []

    beads["mav-2"] = _bead("mav-2", created_at="2026-08-06T02:45:00Z")
    await _tick(datetime(2026, 8, 6, 3, 0, tzinfo=NY))
    assert sent == []

    beads["mav-3"] = _bead("mav-3", created_at="2026-08-06T06:50:00Z")
    await _tick(datetime(2026, 8, 6, 6, 55, tzinfo=NY))
    assert sent == []

    # 09:00: exactly one batch, covering every accumulated entry.
    delivered = await _tick(datetime(2026, 8, 6, 9, 0, tzinfo=NY))
    assert len(sent) == 1
    assert len(delivered.deliveries) == 1
    batch = delivered.deliveries[0]
    assert set(batch.entry_ids) == {"mav-1", "mav-2", "mav-3"}

    # 09:05, same window: idempotent re-run (SC-003) — zero new pushes.
    rerun = await _tick(datetime(2026, 8, 6, 9, 5, tzinfo=NY))
    assert rerun.deliveries == ()
    assert any(skip.reason.value == "already-delivered" for skip in rerun.skips)
    assert len(sent) == 1

    # Later the same day, nothing new accumulated: nothing due — the
    # single 09:00 occurrence for today is already decided. Picked well
    # under mav-1's 24h max_entry_age_hours (created 2026-08-05T23:10:00Z)
    # so this tick stays isolated to window-batch idempotence and doesn't
    # cross into US4's max-age escalation (T027) — that interaction is
    # covered separately in test_evaluate_escalation.py.
    later = await _tick(datetime(2026, 8, 6, 15, 0, tzinfo=NY))
    assert later.deliveries == ()
    assert len(sent) == 1

    # SC-004: the delivery is fully reconstructible from state.json alone.
    state_path = tmp_path / ".maverick" / "notify" / "state.json"
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    key = "2026-08-06/09:00"
    window_decision = persisted["window_decisions"][key]
    assert window_decision["outcome"] == "delivered"
    assert set(window_decision["entry_ids"]) == {"mav-1", "mav-2", "mav-3"}
    assert window_decision["rule"]  # non-empty rule citation

    assert len(persisted["deliveries"]) == 1
    delivery_record = persisted["deliveries"][0]
    assert delivery_record["kind"] == "window-batch"
    assert delivery_record["trigger"] == key
    assert set(delivery_record["entry_ids"]) == {"mav-1", "mav-2", "mav-3"}
    assert delivery_record["delivered_at"]


@pytest.mark.asyncio
async def test_every_entry_is_accounted_for_across_a_mixed_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SC-005: across a run mixing an open medium entry, an open high
    entry, an already-answered entry, an already-waived entry, and a
    low-severity entry, every single entry ends the evaluation either
    delivered, human-resolved, or knowingly silent-and-low — none is
    silently dropped from evaluation (FR-016)."""
    schedule = AssumptionScheduleConfig(windows=["09:00"], min_batch_size=1)
    notif = NotificationConfig(enabled=True, server="https://ntfy.test", topic="scheduler-test")

    beads: dict[str, BeadDetails] = {
        "mav-med": _bead("mav-med", severity="medium", created_at="2026-08-06T05:00:00Z"),
        "mav-hi": _bead("mav-hi", severity="high", created_at="2026-08-06T05:00:00Z"),
        "mav-answered": _bead(
            "mav-answered",
            severity="medium",
            status=STATUS_ANSWERED,
            created_at="2026-08-06T05:00:00Z",
            answer_text="Yes.",
        ),
        "mav-waived": _bead(
            "mav-waived",
            severity="medium",
            status=STATUS_WAIVED,
            created_at="2026-08-06T05:00:00Z",
            waived_by="alice",
            waive_reason="not needed",
        ),
        "mav-low": _bead("mav-low", severity="low", created_at="2026-08-06T05:00:00Z"),
    }
    _wire_ledger(monkeypatch, beads)
    client = BeadClient(cwd=tmp_path)
    sent: list[httpx.Request] = []
    transport = _mock_transport(sent)

    outcome, final_state = await _run_tick(
        cwd=tmp_path,
        client=client,
        schedule=schedule,
        notif=notif,
        now=datetime(2026, 8, 6, 14, 0, tzinfo=NY),
        transport=transport,
    )

    covered_by_delivery: set[str] = set()
    for decision in outcome.deliveries:
        covered_by_delivery.update(decision.entry_ids)

    entries = await report_entries(client)
    for entry in entries:
        bead_id = entry.record.bead_id
        if bead_id in covered_by_delivery:
            continue
        if entry.bucket in ("resolved", "waived"):
            continue  # human-resolved — accounted for
        if entry.record.severity.value == "low":
            continue  # knowingly silent by design (clarification Q5) — not a drop
        pytest.fail(f"entry {bead_id} was neither delivered, resolved, nor low-severity")

    # Concretely: the open medium and high entries were both delivered
    # (as a window batch and an interrupt respectively, no cross-talk)...
    assert "mav-med" in covered_by_delivery
    assert "mav-hi" in covered_by_delivery
    # ...the already-resolved entries never entered a batch at all
    # (FR-014, structural exclusion)...
    assert "mav-answered" not in covered_by_delivery
    assert "mav-waived" not in covered_by_delivery
    # ...and the low entry is tracked (so its age is auditable) but never
    # delivered on its own — silently accumulating by design, not dropped.
    assert "mav-low" in final_state.entry_tracking
    assert "mav-low" not in covered_by_delivery
