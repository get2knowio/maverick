"""Tests for persisted notify delivery state (data-model.md §4,
contracts/delivery-state-schema.md).

Covers round-trip load/save, atomic write, missing/corrupt file handling,
schema_version refusal, the pid-stamped lockfile (acquire/release/stale
reclaim), the FR-023 prune predicate, and (tasks.md T022, US3)
:func:`~maverick.assumptions.schedule.state.finalize_state` — the
write-after-success reconciliation between a speculative
``EvaluationOutcome.state_after`` and which of its delivery decisions
actually succeeded.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from maverick.assumptions.models import (
    STATUS_OPEN,
    AssumptionRecord,
    AssumptionReportEntry,
    Severity,
)
from maverick.assumptions.schedule.evaluate import evaluate
from maverick.assumptions.schedule.models import DecisionKind
from maverick.assumptions.schedule.state import (
    DeliveryRecord,
    DeliveryState,
    DeliveryStateSchemaError,
    EntryTrackingRecord,
    TerminalOutcome,
    WindowDecisionRecord,
    acquire_lock,
    finalize_state,
    load_state,
    prune,
    release_lock,
    save_state,
)
from maverick.config import AssumptionScheduleConfig


def _make_state() -> DeliveryState:
    return DeliveryState(
        updated_at="2026-08-05T13:00:12Z",
        window_decisions={
            "2026-08-05/09:00": WindowDecisionRecord(
                outcome="delivered",
                decided_at="2026-08-05T13:00:12Z",
                entry_ids=["mav-abc", "mav-def"],
                rule="window 09:00 due",
            ),
        },
        entry_tracking={
            "mav-hi1": EntryTrackingRecord(
                first_seen="2026-08-05T03:10:00Z",
                severity="high",
                interrupt_delivered_at="2026-08-05T03:10:05Z",
            ),
        },
        deliveries=[
            DeliveryRecord(
                kind="interrupt",
                delivered_at="2026-08-05T03:10:05Z",
                trigger="high severity recorded; high_overrides_quiet=true",
                entry_ids=["mav-hi1"],
                summary={
                    "counts": {"high": 1, "medium": 0, "low": 0},
                    "owner_specs": ["054-assumption-batch-scheduler"],
                    "oldest_age_hours": 0.1,
                    "review_invocation": "maverick review --list --status open",
                },
            ),
        ],
    )


# --- round-trip load/save --------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_load_round_trip(tmp_path: Path) -> None:
    state = _make_state()

    await save_state(state, tmp_path)
    loaded = await load_state(tmp_path)

    assert loaded == state


@pytest.mark.asyncio
async def test_save_writes_expected_path(tmp_path: Path) -> None:
    state = _make_state()

    await save_state(state, tmp_path)

    state_path = tmp_path / ".maverick" / "notify" / "state.json"
    assert state_path.is_file()
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    assert raw["window_decisions"]["2026-08-05/09:00"]["outcome"] == "delivered"
    assert raw["entry_tracking"]["mav-hi1"]["severity"] == "high"
    assert raw["deliveries"][0]["kind"] == "interrupt"


@pytest.mark.asyncio
async def test_save_is_atomic_no_partial_file_on_crash(tmp_path: Path) -> None:
    """atomic_write_json writes via temp-file+rename; verify no `.tmp` litter
    remains and the final file is valid JSON after a normal save."""
    state = _make_state()
    await save_state(state, tmp_path)

    notify_dir = tmp_path / ".maverick" / "notify"
    leftovers = [p for p in notify_dir.iterdir() if p.name != "state.json"]
    assert leftovers == []


# --- missing / corrupt file -------------------------------------------------


@pytest.mark.asyncio
async def test_load_missing_file_returns_empty_state(tmp_path: Path) -> None:
    state = await load_state(tmp_path)

    assert state.schema_version == 1
    assert state.window_decisions == {}
    assert state.entry_tracking == {}
    assert state.deliveries == []
    assert state.updated_at != ""


@pytest.mark.asyncio
async def test_load_schema_version_mismatch_refuses(tmp_path: Path) -> None:
    state_path = tmp_path / ".maverick" / "notify" / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps({"schema_version": 2, "updated_at": "2026-08-05T13:00:12Z"}),
        encoding="utf-8",
    )

    with pytest.raises(DeliveryStateSchemaError):
        await load_state(tmp_path)


@pytest.mark.asyncio
async def test_load_corrupt_json_returns_empty_state_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    state_path = tmp_path / ".maverick" / "notify" / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text("{not valid json", encoding="utf-8")

    state = await load_state(tmp_path)

    assert state.window_decisions == {}
    assert state.entry_tracking == {}
    assert state.deliveries == []


@pytest.mark.asyncio
async def test_load_schema_valid_json_invalid_shape_returns_empty_state(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / ".maverick" / "notify" / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "2026-08-05T13:00:12Z",
                "window_decisions": "not-a-dict",
            }
        ),
        encoding="utf-8",
    )

    state = await load_state(tmp_path)

    assert state.window_decisions == {}
    assert state.entry_tracking == {}
    assert state.deliveries == []


# --- pid lockfile ------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_and_release_lock(tmp_path: Path) -> None:
    acquired = await acquire_lock(tmp_path)
    assert acquired is True

    lock_path = tmp_path / ".maverick" / "notify" / "lock"
    assert lock_path.is_file()
    assert lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())

    await release_lock(tmp_path)
    assert not lock_path.exists()


@pytest.mark.asyncio
async def test_acquire_lock_contention_from_live_pid(tmp_path: Path) -> None:
    lock_path = tmp_path / ".maverick" / "notify" / "lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(str(os.getpid()), encoding="utf-8")

    acquired = await acquire_lock(tmp_path)

    assert acquired is False


@pytest.mark.asyncio
async def test_acquire_lock_reclaims_stale_dead_pid(tmp_path: Path) -> None:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    dead_pid = proc.pid
    proc.wait()  # reap the child; dead_pid is now guaranteed not to be alive

    lock_path = tmp_path / ".maverick" / "notify" / "lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(str(dead_pid), encoding="utf-8")

    acquired = await acquire_lock(tmp_path)

    assert acquired is True
    assert lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())


@pytest.mark.asyncio
async def test_acquire_lock_reclaims_malformed_lockfile(tmp_path: Path) -> None:
    lock_path = tmp_path / ".maverick" / "notify" / "lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("not-a-pid", encoding="utf-8")

    acquired = await acquire_lock(tmp_path)

    assert acquired is True


@pytest.mark.asyncio
async def test_release_lock_missing_is_noop(tmp_path: Path) -> None:
    await release_lock(tmp_path)  # no lockfile exists; must not raise


# --- FR-023 prune ------------------------------------------------------------


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def test_prune_removes_terminal_entry_past_retention() -> None:
    now = datetime(2026, 8, 5, tzinfo=UTC)
    terminal_at = now - timedelta(days=91)
    state = DeliveryState(
        updated_at=_iso(now),
        entry_tracking={
            "mav-old": EntryTrackingRecord(
                first_seen=_iso(terminal_at - timedelta(days=1)),
                severity="medium",
                terminal=TerminalOutcome(kind="resolved-by-human", at=_iso(terminal_at)),
            ),
        },
    )

    result = prune(state, now)

    assert result.entry_tracking == {}


def test_prune_keeps_terminal_entry_within_retention() -> None:
    now = datetime(2026, 8, 5, tzinfo=UTC)
    terminal_at = now - timedelta(days=10)
    state = DeliveryState(
        updated_at=_iso(now),
        entry_tracking={
            "mav-recent": EntryTrackingRecord(
                first_seen=_iso(terminal_at - timedelta(days=1)),
                severity="medium",
                terminal=TerminalOutcome(kind="resolved-by-human", at=_iso(terminal_at)),
            ),
        },
    )

    result = prune(state, now)

    assert "mav-recent" in result.entry_tracking


def test_prune_never_removes_open_entry() -> None:
    now = datetime(2026, 8, 5, tzinfo=UTC)
    state = DeliveryState(
        updated_at=_iso(now),
        entry_tracking={
            "mav-open": EntryTrackingRecord(
                first_seen=_iso(now - timedelta(days=200)),
                severity="high",
                terminal=None,
            ),
        },
    )

    result = prune(state, now)

    assert "mav-open" in result.entry_tracking


def test_prune_removes_delivery_and_window_decision_when_all_entries_prunable() -> None:
    now = datetime(2026, 8, 5, tzinfo=UTC)
    terminal_at = now - timedelta(days=91)
    state = DeliveryState(
        updated_at=_iso(now),
        window_decisions={
            "2026-01-01/09:00": WindowDecisionRecord(
                outcome="delivered",
                decided_at=_iso(terminal_at),
                entry_ids=["mav-old"],
                rule="window 09:00 due",
            ),
        },
        entry_tracking={
            "mav-old": EntryTrackingRecord(
                first_seen=_iso(terminal_at - timedelta(days=1)),
                severity="medium",
                terminal=TerminalOutcome(kind="resolved-by-human", at=_iso(terminal_at)),
            ),
        },
        deliveries=[
            DeliveryRecord(
                kind="window-batch",
                delivered_at=_iso(terminal_at),
                trigger="2026-01-01/09:00",
                entry_ids=["mav-old"],
                summary={"counts": {"medium": 1}},
            ),
        ],
    )

    result = prune(state, now)

    assert result.window_decisions == {}
    assert result.deliveries == []
    assert result.entry_tracking == {}


def test_prune_never_removes_record_referencing_any_open_entry() -> None:
    """A window_decisions/deliveries record survives as long as *any*
    referenced entry is still open — even if a co-referenced terminal entry
    is independently pruned from entry_tracking on its own 90-day clock
    (contracts/delivery-state-schema.md invariant 6: the record-level rule
    and the entry_tracking-row rule are each self-contained)."""
    now = datetime(2026, 8, 5, tzinfo=UTC)
    terminal_at = now - timedelta(days=91)
    state = DeliveryState(
        updated_at=_iso(now),
        window_decisions={
            "2026-01-01/09:00": WindowDecisionRecord(
                outcome="delivered",
                decided_at=_iso(terminal_at),
                entry_ids=["mav-old", "mav-open"],
                rule="window 09:00 due",
            ),
        },
        entry_tracking={
            "mav-old": EntryTrackingRecord(
                first_seen=_iso(terminal_at - timedelta(days=1)),
                severity="medium",
                terminal=TerminalOutcome(kind="resolved-by-human", at=_iso(terminal_at)),
            ),
            "mav-open": EntryTrackingRecord(
                first_seen=_iso(terminal_at - timedelta(days=1)),
                severity="medium",
                terminal=None,
            ),
        },
        deliveries=[
            DeliveryRecord(
                kind="window-batch",
                delivered_at=_iso(terminal_at),
                trigger="2026-01-01/09:00",
                entry_ids=["mav-old", "mav-open"],
                summary={"counts": {"medium": 2}},
            ),
        ],
    )

    result = prune(state, now)

    assert "2026-01-01/09:00" in result.window_decisions
    assert len(result.deliveries) == 1
    # mav-old's own terminal+90days clock has elapsed, independent of the
    # still-kept record that references it.
    assert "mav-old" not in result.entry_tracking
    assert "mav-open" in result.entry_tracking


def test_prune_never_removes_record_referencing_unknown_entry() -> None:
    """An entry id absent from entry_tracking entirely is conservatively
    treated as not-prunable (unknown status errs toward "open")."""
    now = datetime(2026, 8, 5, tzinfo=UTC)
    terminal_at = now - timedelta(days=91)
    state = DeliveryState(
        updated_at=_iso(now),
        window_decisions={
            "2026-01-01/09:00": WindowDecisionRecord(
                outcome="delivered",
                decided_at=_iso(terminal_at),
                entry_ids=["mav-unknown"],
                rule="window 09:00 due",
            ),
        },
    )

    result = prune(state, now)

    assert "2026-01-01/09:00" in result.window_decisions


def test_prune_keeps_empty_batch_window_decision_within_retention() -> None:
    """A decision referencing zero entries ('empty' outcome) is dated by its
    own ``decided_at`` — inside the 90-day horizon the audit trail for "why
    was nothing delivered at 09:00" must survive."""
    now = datetime(2026, 8, 5, tzinfo=UTC)
    recent = now - timedelta(days=10)
    state = DeliveryState(
        updated_at=_iso(now),
        window_decisions={
            "2026-07-26/09:00": WindowDecisionRecord(
                outcome="empty",
                decided_at=_iso(recent),
                entry_ids=[],
                rule="0 entries due",
            ),
        },
    )

    result = prune(state, now)

    assert "2026-07-26/09:00" in result.window_decisions


def test_prune_removes_empty_batch_window_decision_past_retention() -> None:
    """Past the 90-day horizon an empty-batch decision prunes on the same
    rule as any other record (contracts/delivery-state-schema.md invariant 6:
    "every entry id it references is prunable" holds vacuously) — otherwise
    every quiet window occurrence is immortal state."""
    now = datetime(2026, 8, 5, tzinfo=UTC)
    old = now - timedelta(days=365)
    state = DeliveryState(
        updated_at=_iso(now),
        window_decisions={
            "2025-08-05/09:00": WindowDecisionRecord(
                outcome="empty",
                decided_at=_iso(old),
                entry_ids=[],
                rule="0 entries due",
            ),
        },
    )

    result = prune(state, now)

    assert result.window_decisions == {}


def test_prune_empty_batch_window_decision_retention_boundary() -> None:
    """Exactly 90 days old is prunable (``>= _RETENTION``, matching the
    entry_tracking rule); one second short of it is retained."""
    now = datetime(2026, 8, 5, tzinfo=UTC)
    state = DeliveryState(
        updated_at=_iso(now),
        window_decisions={
            "at-horizon": WindowDecisionRecord(
                outcome="empty",
                decided_at=_iso(now - timedelta(days=90)),
                entry_ids=[],
                rule="0 entries due",
            ),
            "inside-horizon": WindowDecisionRecord(
                outcome="empty",
                decided_at=_iso(now - timedelta(days=90) + timedelta(seconds=1)),
                entry_ids=[],
                rule="0 entries due",
            ),
        },
    )

    result = prune(state, now)

    assert "at-horizon" not in result.window_decisions
    assert "inside-horizon" in result.window_decisions


def test_prune_keeps_empty_record_with_unparseable_timestamp() -> None:
    """An unparseable own-timestamp errs toward "keep" — the same
    conservative stance the entry-id rule takes for unknown entries."""
    now = datetime(2026, 8, 5, tzinfo=UTC)
    state = DeliveryState(
        updated_at=_iso(now),
        window_decisions={
            "2025-08-05/09:00": WindowDecisionRecord(
                outcome="empty",
                decided_at="not-a-timestamp",
                entry_ids=[],
                rule="0 entries due",
            ),
        },
    )

    result = prune(state, now)

    assert "2025-08-05/09:00" in result.window_decisions


def test_prune_removes_empty_delivery_record_past_retention() -> None:
    """The same own-timestamp basis applies to a `deliveries` record that
    references zero entries — dated by ``delivered_at``."""
    now = datetime(2026, 8, 5, tzinfo=UTC)
    state = DeliveryState(
        updated_at=_iso(now),
        deliveries=[
            DeliveryRecord(
                kind="window-batch",
                delivered_at=_iso(now - timedelta(days=365)),
                trigger="2025-08-05/09:00",
                entry_ids=[],
                summary={"counts": {}},
            ),
            DeliveryRecord(
                kind="window-batch",
                delivered_at=_iso(now - timedelta(days=10)),
                trigger="2026-07-26/09:00",
                entry_ids=[],
                summary={"counts": {}},
            ),
        ],
    )

    result = prune(state, now)

    assert [record.trigger for record in result.deliveries] == ["2026-07-26/09:00"]


def test_prune_does_not_mutate_input_state() -> None:
    now = datetime(2026, 8, 5, tzinfo=UTC)
    terminal_at = now - timedelta(days=91)
    state = DeliveryState(
        updated_at=_iso(now),
        entry_tracking={
            "mav-old": EntryTrackingRecord(
                first_seen=_iso(terminal_at - timedelta(days=1)),
                severity="medium",
                terminal=TerminalOutcome(kind="resolved-by-human", at=_iso(terminal_at)),
            ),
        },
    )

    prune(state, now)

    assert "mav-old" in state.entry_tracking


# --- finalize_state (tasks.md T022, US3 write-after-success) ----------------
#
# `finalize_state` is the pure counterpart to `evaluate()`'s speculative
# `state_after` (contracts/delivery-state-schema.md invariant 2): given the
# real `EvaluationOutcome` from a live `evaluate()` call plus which of its
# `deliveries` positions actually failed to send, it reverts exactly those
# decisions' mutations before the CLI persists the result. Building fixtures
# via the real `evaluate()` (rather than hand-assembling `EvaluationOutcome`)
# keeps the delivery-record/index alignment these tests assert on identical
# to what `notify.py` actually receives.

_NOW = datetime(2026, 8, 6, 9, 0, tzinfo=UTC)


def _schedule(*, min_batch_size: int = 1) -> AssumptionScheduleConfig:
    return AssumptionScheduleConfig(windows=["09:00"], min_batch_size=min_batch_size)


def _empty_state() -> DeliveryState:
    return DeliveryState(updated_at="2026-08-01T00:00:00Z")


def _entry(bead_id: str, *, severity: Severity = Severity.MEDIUM) -> AssumptionReportEntry:
    return AssumptionReportEntry(
        record=AssumptionRecord(
            bead_id=bead_id,
            question="Q?",
            adopted_answer="A.",
            alternatives=(),
            severity=severity,
            severity_defaulted=False,
            status=STATUS_OPEN,
            owner_spec="054-assumption-batch-scheduler",
            source_bead="mav-source",
            change_ids=(),
            is_legacy=False,
            created_at=None,
        ),
        final_answer=None,
        waived_by=None,
        waived_at=None,
        waive_reason=None,
        reconcile_status=None,
        reconciled_answer=None,
        reconcile_change_id=None,
        reconcile_reason=None,
        pending_reconcile=False,
    )


class TestFinalizeStateNoFailures:
    def test_all_decisions_succeed_returns_full_state_after(self) -> None:
        prior = _empty_state()
        outcome = evaluate((_entry("mav-1"),), _schedule(), prior, _NOW)

        result = finalize_state(outcome=outcome, prior_state=prior, failed_indices=(), now=_NOW)

        assert "2026-08-06/09:00" in result.window_decisions
        assert result.window_decisions["2026-08-06/09:00"].outcome == "delivered"
        assert len(result.deliveries) == 1


class TestFinalizeStateDeliveryFailureExcluded:
    """FR-012: a decision whose delivery failed leaves the occurrence/entry
    undecided in the persisted state — it is due again next time."""

    def test_failed_window_batch_leaves_occurrence_undecided(self) -> None:
        prior = _empty_state()
        outcome = evaluate((_entry("mav-1"), _entry("mav-2")), _schedule(), prior, _NOW)
        assert len(outcome.deliveries) == 1
        assert outcome.deliveries[0].kind == DecisionKind.WINDOW_BATCH

        result = finalize_state(outcome=outcome, prior_state=prior, failed_indices={0}, now=_NOW)

        assert "2026-08-06/09:00" not in result.window_decisions
        assert result.deliveries == []

    def test_failed_interrupt_reverts_entry_tracking_marker(self) -> None:
        prior = _empty_state()
        outcome = evaluate((_entry("mav-hi", severity=Severity.HIGH),), _schedule(), prior, _NOW)
        assert len(outcome.deliveries) == 1
        assert outcome.deliveries[0].kind == DecisionKind.INTERRUPT

        result = finalize_state(outcome=outcome, prior_state=prior, failed_indices={0}, now=_NOW)

        assert result.entry_tracking["mav-hi"].interrupt_delivered_at is None
        assert result.deliveries == []

    def test_undecided_occurrence_is_due_again_on_reevaluation(self) -> None:
        """The functional proof: reverting a failed window batch's state
        must make the *same* occurrence deliver again — not silently
        vanish, and not be mistaken for `already-delivered`."""
        entries = (_entry("mav-1"),)
        prior = _empty_state()
        outcome = evaluate(entries, _schedule(), prior, _NOW)

        reverted = finalize_state(outcome=outcome, prior_state=prior, failed_indices={0}, now=_NOW)
        retried = evaluate(entries, _schedule(), reverted, _NOW + timedelta(minutes=5))

        assert len(retried.deliveries) == 1
        assert retried.deliveries[0].kind == DecisionKind.WINDOW_BATCH
        assert retried.deliveries[0].entry_ids == ("mav-1",)


class TestFinalizeStatePartialSuccess:
    def test_one_succeeds_one_fails_persists_only_the_success(self) -> None:
        """A mixed ledger (medium + high) produces two due decisions in one
        evaluation with no cross-talk (research R9) — a failure on one must
        not take down the other's persisted state, and each is recorded
        individually."""
        entries = (
            _entry("mav-med", severity=Severity.MEDIUM),
            _entry("mav-hi", severity=Severity.HIGH),
        )
        prior = _empty_state()
        outcome = evaluate(entries, _schedule(), prior, _NOW)
        assert len(outcome.deliveries) == 2
        index_by_kind = {d.kind: i for i, d in enumerate(outcome.deliveries)}
        failed_index = index_by_kind[DecisionKind.INTERRUPT]
        succeeded_index = index_by_kind[DecisionKind.WINDOW_BATCH]

        result = finalize_state(
            outcome=outcome, prior_state=prior, failed_indices={failed_index}, now=_NOW
        )

        # The succeeded window batch is fully persisted...
        assert "2026-08-06/09:00" in result.window_decisions
        assert len(result.deliveries) == 1
        assert result.deliveries[0].kind == "window-batch"
        assert result.deliveries[0].entry_ids == ["mav-med"]
        assert succeeded_index >= 0  # sanity: both indices resolved above

        # ...while the failed interrupt's marker is reverted and it never
        # lands in the persisted audit trail.
        assert result.entry_tracking["mav-hi"].interrupt_delivered_at is None
        assert not any(record.kind == "interrupt" for record in result.deliveries)


class TestFinalizeStatePrunesSurvivingState:
    def test_finalize_state_applies_fr023_pruning(self) -> None:
        """`finalize_state` must apply the same FR-023 retention rule
        `prune()` does — it is the sole gateway between `evaluate()`'s
        candidate state and what `notify.py` persists."""
        terminal_at = _NOW - timedelta(days=91)
        prior = DeliveryState(
            updated_at="2026-08-01T00:00:00Z",
            entry_tracking={
                "mav-old": EntryTrackingRecord(
                    first_seen="2026-05-01T00:00:00Z",
                    severity="medium",
                    terminal=TerminalOutcome(kind="resolved-by-human", at=_iso(terminal_at)),
                ),
            },
        )
        outcome = evaluate((), _schedule(), prior, _NOW)

        result = finalize_state(outcome=outcome, prior_state=prior, failed_indices=(), now=_NOW)

        assert "mav-old" not in result.entry_tracking
