"""Tests for the supervisor's payload-parse-error handling (REFUEL_ISSUES #4).

A malformed-but-JSON-schema-valid tool payload used to escalate to a
terminal ``_handle_error`` that killed every agent. The new behavior:

* ``submit_outline`` / ``submit_fix`` payload rejections trigger a
  nudge to the primary decomposer with the failure reason.
* ``submit_details`` rejections emit an error line but do not kill
  the run — other pool actors keep going.
* Unknown tools still hit the hard-abort path.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import maverick.actors.refuel_supervisor as refuel_supervisor_module


def _make_supervisor() -> refuel_supervisor_module.RefuelSupervisorActor:
    sup = object.__new__(refuel_supervisor_module.RefuelSupervisorActor)
    sup._decomposer = MagicMock(name="primary_decomposer")
    sup._decomposer_pool = []
    sup._briefing_actors = {}
    sup._specs = []
    sup._fix_rounds = 0
    sup._emit_output = MagicMock()
    sup._mark_done = MagicMock()
    sent: list[tuple[Any, Any]] = []
    sup.send = lambda target, msg: sent.append((target, msg))
    sup._sent = sent  # type: ignore[attr-defined]
    return sup


def test_outline_payload_error_nudges_primary() -> None:
    sup = _make_supervisor()

    sup._handle_payload_parse_error(
        "submit_outline", ValueError("kebab-case required")
    )

    sup._mark_done.assert_not_called()
    nudges = [msg for _, msg in sup._sent if msg.get("type") == "nudge"]  # type: ignore[attr-defined]
    assert len(nudges) == 1
    assert nudges[0]["expected_tool"] == "submit_outline"
    assert "kebab-case" in nudges[0]["reason"]


def test_fix_payload_error_nudges_primary() -> None:
    sup = _make_supervisor()

    sup._handle_payload_parse_error(
        "submit_fix", ValueError("empty task")
    )

    sup._mark_done.assert_not_called()
    nudges = [msg for _, msg in sup._sent if msg.get("type") == "nudge"]  # type: ignore[attr-defined]
    assert len(nudges) == 1
    assert nudges[0]["expected_tool"] == "submit_fix"


def test_detail_payload_error_does_not_kill_run() -> None:
    sup = _make_supervisor()

    sup._handle_payload_parse_error(
        "submit_details", ValueError("bad unit id")
    )

    sup._mark_done.assert_not_called()
    nudges = [msg for _, msg in sup._sent if msg.get("type") == "nudge"]  # type: ignore[attr-defined]
    assert nudges == []


def test_unknown_tool_payload_error_escalates_to_handle_error() -> None:
    sup = _make_supervisor()
    sup._shutdown_all = MagicMock()

    sup._handle_payload_parse_error(
        "submit_mystery", ValueError("no such tool")
    )

    # _handle_error calls _shutdown_all and _mark_done.
    sup._shutdown_all.assert_called_once()
    sup._mark_done.assert_called_once()
