"""Tests for the refuel supervisor's nudge path (REFUEL_ISSUES #3 + #10).

The supervisor nudges agents when ``prompt_sent`` arrives but the
expected MCP tool call hasn't. These tests cover:

* Detail phase: nudge goes to the specific pool actor (sender), not
  the primary, and carries the unit_id.
* Detail phase: once submit_details lands, a second prompt_sent for
  the same unit does NOT re-nudge.
* Fix phase: predicate uses ``_awaiting_fix`` (not details/fix_rounds)
  so nudging fires when the supervisor is still waiting for submit_fix.
* Fix phase: submit_fix clears ``_awaiting_fix`` so subsequent
  prompt_sent does not re-nudge.
* Nudge budget is per-key: a stalled unit does not eat the primary's
  nudge allowance.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import maverick.actors.refuel_supervisor as refuel_supervisor_module


def _make_supervisor() -> refuel_supervisor_module.RefuelSupervisorActor:
    sup = object.__new__(refuel_supervisor_module.RefuelSupervisorActor)
    sup._pending_detail_ids = set()
    sup._outline = None
    sup._awaiting_fix = False
    sup._nudge_count = {}
    sup._decomposer = MagicMock(name="primary_decomposer")
    sup._emit_output = MagicMock()
    sent: list[tuple[Any, Any]] = []

    def _send(target: Any, msg: Any) -> None:
        sent.append((target, msg))

    sup.send = _send
    sup._sent = sent  # type: ignore[attr-defined]
    return sup


class TestDetailPhaseNudging:
    def test_nudge_goes_to_sender_not_primary(self) -> None:
        sup = _make_supervisor()
        pool_actor = MagicMock(name="pool_actor_2")
        sup._pending_detail_ids = {"uid-1"}  # submit_details has NOT arrived

        sup._handle_prompt_sent("detail", unit_id="uid-1", sender=pool_actor)

        assert len(sup._sent) == 1  # type: ignore[attr-defined]
        target, msg = sup._sent[0]  # type: ignore[attr-defined]
        assert target is pool_actor, "nudge must target the pool actor, not primary"
        assert msg["type"] == "nudge"
        assert msg["expected_tool"] == "submit_details"
        assert msg["unit_id"] == "uid-1"

    def test_no_nudge_when_submit_details_already_arrived(self) -> None:
        sup = _make_supervisor()
        pool_actor = MagicMock(name="pool_actor_2")
        # Unit is NOT in pending_detail_ids → submit_details already arrived.

        sup._handle_prompt_sent("detail", unit_id="uid-1", sender=pool_actor)

        assert sup._sent == []  # type: ignore[attr-defined]

    def test_max_nudges_per_unit_stops_further_nudging(self) -> None:
        sup = _make_supervisor()
        pool_actor = MagicMock(name="pool_actor_2")
        sup._pending_detail_ids = {"uid-1"}

        # Drive it past MAX_NUDGES (2).
        sup._handle_prompt_sent("detail", unit_id="uid-1", sender=pool_actor)
        sup._handle_prompt_sent("detail", unit_id="uid-1", sender=pool_actor)
        sup._handle_prompt_sent("detail", unit_id="uid-1", sender=pool_actor)

        nudges = [msg for _, msg in sup._sent if msg.get("type") == "nudge"]  # type: ignore[attr-defined]
        assert len(nudges) == 2, "detail nudging must respect MAX_NUDGES"

    def test_unit_nudge_budget_is_separate_from_other_units(self) -> None:
        sup = _make_supervisor()
        pool_a = MagicMock(name="pool_a")
        pool_b = MagicMock(name="pool_b")
        sup._pending_detail_ids = {"uid-1", "uid-2"}

        # Exhaust budget for uid-1.
        sup._handle_prompt_sent("detail", unit_id="uid-1", sender=pool_a)
        sup._handle_prompt_sent("detail", unit_id="uid-1", sender=pool_a)
        # uid-2 should still get its own full budget.
        sup._handle_prompt_sent("detail", unit_id="uid-2", sender=pool_b)

        nudges = [msg for _, msg in sup._sent if msg.get("type") == "nudge"]  # type: ignore[attr-defined]
        uid1_nudges = [m for m in nudges if m.get("unit_id") == "uid-1"]
        uid2_nudges = [m for m in nudges if m.get("unit_id") == "uid-2"]
        assert len(uid1_nudges) == 2
        assert len(uid2_nudges) == 1


class TestFixPhaseNudging:
    def test_nudge_fires_while_awaiting_fix(self) -> None:
        sup = _make_supervisor()
        sup._awaiting_fix = True

        sup._handle_prompt_sent("fix")

        nudges = [msg for _, msg in sup._sent if msg.get("type") == "nudge"]  # type: ignore[attr-defined]
        assert len(nudges) == 1
        assert nudges[0]["expected_tool"] == "submit_fix"

    def test_nudge_goes_to_primary_decomposer(self) -> None:
        sup = _make_supervisor()
        sup._awaiting_fix = True
        some_sender = MagicMock(name="pool_actor")

        sup._handle_prompt_sent("fix", sender=some_sender)

        target, _ = sup._sent[0]  # type: ignore[attr-defined]
        assert target is sup._decomposer

    def test_no_nudge_after_submit_fix_arrives(self) -> None:
        sup = _make_supervisor()
        sup._awaiting_fix = False  # cleared by _handle_tool_call

        sup._handle_prompt_sent("fix")

        assert sup._sent == []  # type: ignore[attr-defined]


class TestOutlinePhaseNudgingUnchanged:
    def test_outline_still_nudges_primary_on_missing_outline(self) -> None:
        sup = _make_supervisor()
        sup._outline = None

        sup._handle_prompt_sent("outline")

        target, msg = sup._sent[0]  # type: ignore[attr-defined]
        assert target is sup._decomposer
        assert msg["expected_tool"] == "submit_outline"
        assert "unit_id" not in msg

    def test_outline_no_nudge_when_outline_present(self) -> None:
        sup = _make_supervisor()
        sup._outline = MagicMock()

        sup._handle_prompt_sent("outline")

        assert sup._sent == []  # type: ignore[attr-defined]
