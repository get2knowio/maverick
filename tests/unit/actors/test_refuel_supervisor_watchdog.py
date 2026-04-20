"""Tests for the refuel supervisor's stale-in-flight watchdog.

Background: during a real run we observed 6 detail units freeze for 3+
hours on pool actors because the ACP socket wedged in a state where
neither the decomposer's ``_run_coro`` timeout nor ``prompt_session``'s
``asyncio.wait_for`` fired. The supervisor knew the units were stale
(it was logging their age in the heartbeat) but took no action.

The watchdog inside ``_handle_wakeup`` now detects units that have
been in flight past ``STALE_IN_FLIGHT_SECONDS`` and synthesizes a
``prompt_error`` so the existing retry/abandon logic handles them
uniformly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import maverick.actors.refuel_supervisor as refuel_supervisor_module


def _make_supervisor() -> refuel_supervisor_module.RefuelSupervisorActor:
    sup = object.__new__(refuel_supervisor_module.RefuelSupervisorActor)
    sup._heartbeat_active = True
    sup._pending_detail_ids = {"unit-stuck", "unit-done-1"}
    sup._accumulated_details = [MagicMock(), MagicMock()]  # 2 completed
    sup._detail_in_flight = 1
    sup._detail_queue = []
    sup._last_detail_time = 0.0
    sup._detail_retries = {}
    sup._detail_dispatch_info = {}
    # Supervisor helpers that would normally exist after init.
    sup._emit_output = MagicMock()
    sup.wakeupAfter = MagicMock()
    sup._dispatch_pending_details = MagicMock()
    sup.send = MagicMock()
    sup._validator = MagicMock()
    # _handle_detail_error is the real method we want to exercise end-to-end.
    return sup


class TestStaleInFlightWatchdog:
    def test_fresh_in_flight_is_not_requeued(self, monkeypatch) -> None:
        sup = _make_supervisor()
        # Dispatched 60s ago — well under the stale threshold.
        sup._detail_dispatch_info = {
            "unit-stuck": {"at": 940.0, "pool_idx": 0},
        }
        monkeypatch.setattr("time.monotonic", lambda: 1000.0)
        wakeup = MagicMock(payload="detail_heartbeat")

        sup._handle_wakeup(wakeup)

        # Watchdog did NOT requeue — unit stays in flight, retry count unchanged.
        assert sup._detail_retries == {}
        assert sup._detail_dispatch_info == {
            "unit-stuck": {"at": 940.0, "pool_idx": 0}
        }
        assert sup._detail_in_flight == 1
        assert sup._detail_queue == []
        sup._dispatch_pending_details.assert_not_called()

    def test_stale_in_flight_is_force_requeued(self, monkeypatch) -> None:
        sup = _make_supervisor()
        # Dispatched well past the stale threshold.
        threshold = refuel_supervisor_module.STALE_IN_FLIGHT_SECONDS
        sup._detail_dispatch_info = {
            "unit-stuck": {"at": 0.0, "pool_idx": 0},
        }
        monkeypatch.setattr("time.monotonic", lambda: threshold + 500.0)
        wakeup = MagicMock(payload="detail_heartbeat")

        sup._handle_wakeup(wakeup)

        # Unit was requeued (retry count incremented, queue populated).
        assert sup._detail_retries.get("unit-stuck") == 1
        assert "unit-stuck" in sup._detail_queue
        # Dispatch info cleared.
        assert "unit-stuck" not in sup._detail_dispatch_info
        # In-flight count decremented.
        assert sup._detail_in_flight == 0
        # Dispatch got triggered so an idle pool actor can pick it up.
        sup._dispatch_pending_details.assert_called_once()

    def test_watchdog_abandons_after_retry_budget_exceeded(self, monkeypatch) -> None:
        sup = _make_supervisor()
        threshold = refuel_supervisor_module.STALE_IN_FLIGHT_SECONDS
        # Already at the retry budget — next stale detection must abandon,
        # not requeue forever.
        sup._detail_retries = {
            "unit-stuck": refuel_supervisor_module.MAX_DETAIL_RETRIES
        }
        sup._detail_dispatch_info = {
            "unit-stuck": {"at": 0.0, "pool_idx": 2},
        }
        monkeypatch.setattr("time.monotonic", lambda: threshold + 500.0)
        wakeup = MagicMock(payload="detail_heartbeat")

        sup._handle_wakeup(wakeup)

        # Unit was abandoned (not requeued), retries incremented past budget.
        assert sup._detail_retries["unit-stuck"] > refuel_supervisor_module.MAX_DETAIL_RETRIES
        assert "unit-stuck" not in sup._detail_queue
        assert "unit-stuck" not in sup._pending_detail_ids
