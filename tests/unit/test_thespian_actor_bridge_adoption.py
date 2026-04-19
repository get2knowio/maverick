"""Regression tests for active Thespian actors adopting ActorAsyncBridge."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from maverick.actors.ac_check import ACCheckActor
from maverick.actors.bead_creator import BeadCreatorActor
from maverick.actors.committer import CommitActor
from maverick.actors.fly_supervisor import FlySupervisorActor
from maverick.actors.gate import GateActor


def _close_and_return(result):
    def _runner(coro, *, timeout):
        coro.close()
        return result

    return _runner


def test_gate_actor_uses_bridge_for_gate_requests() -> None:
    actor = GateActor()
    actor.send = MagicMock()
    actor.receiveMessage({"type": "init", "timeout_seconds": 12.0}, "sender")
    actor.send.reset_mock()

    result = {"passed": True, "summary": "ok"}
    with patch.object(actor, "_run_coro", side_effect=_close_and_return(result)) as run_coro:
        actor.receiveMessage({"type": "gate"}, "sender")

    assert run_coro.call_args.kwargs["timeout"] == 12.0
    actor.send.assert_called_once_with("sender", {"type": "gate_result", **result})


def test_ac_check_actor_uses_bridge_for_checks() -> None:
    actor = ACCheckActor()
    actor.send = MagicMock()

    result = {"passed": True, "reasons": []}
    with patch.object(actor, "_run_coro", side_effect=_close_and_return(result)) as run_coro:
        actor.receiveMessage(
            {"type": "ac_check", "description": "verify", "cwd": "/tmp"},
            "sender",
        )

    assert run_coro.call_args.kwargs["timeout"] > 0
    actor.send.assert_called_once_with("sender", {"type": "ac_result", **result})


def test_commit_actor_uses_bridge_for_commits() -> None:
    actor = CommitActor()
    actor.send = MagicMock()

    result = {"success": True, "commit_sha": "abc123", "tag": None}
    with patch.object(actor, "_run_coro", side_effect=_close_and_return(result)) as run_coro:
        actor.receiveMessage(
            {"type": "commit", "bead_id": "b1", "title": "Task", "cwd": "/tmp"},
            "sender",
        )

    assert run_coro.call_args.kwargs["timeout"] > 0
    actor.send.assert_called_once_with("sender", {"type": "commit_result", **result})


def test_bead_creator_actor_uses_bridge_for_creation() -> None:
    actor = BeadCreatorActor()
    actor.send = MagicMock()
    actor.receiveMessage({"type": "init", "plan_name": "Plan", "plan_objective": "Ship"}, "sender")
    actor.send.reset_mock()

    result = {"success": True, "epic_id": "epic-1", "bead_count": 2, "deps_wired": 1}
    with patch.object(actor, "_run_coro", side_effect=_close_and_return(result)) as run_coro:
        actor.receiveMessage({"type": "create_beads", "specs": [], "deps": []}, "sender")

    assert run_coro.call_args.kwargs["timeout"] > 0
    actor.send.assert_called_once_with("sender", {"type": "beads_created", **result})


def test_fly_supervisor_uses_bridge_for_bead_selection() -> None:
    actor = FlySupervisorActor()
    actor.send = MagicMock()
    actor.receiveMessage({"type": "init", "max_beads": 2}, "sender")
    actor.send.reset_mock()
    actor._emit_output = MagicMock()
    actor._complete = MagicMock()

    result = {"done": True, "found": False}
    with patch.object(actor, "_run_coro", side_effect=_close_and_return(result)) as run_coro:
        actor._next_bead()

    assert run_coro.call_args.kwargs["timeout"] > 0
    actor._complete.assert_called_once()


def test_fly_supervisor_uses_bridge_for_runway_recording() -> None:
    actor = FlySupervisorActor()
    actor._current_bead = {"bead_id": "b1", "title": "Task"}
    actor._epic_id = "epic-1"
    actor._flight_plan_name = "plan"
    actor._review_rounds = 1
    actor._last_review_findings = []
    actor._cwd = "/tmp"

    with patch.object(actor, "_run_coro", side_effect=_close_and_return(None)) as run_coro:
        actor._record_bead_outcome({"success": True})

    assert run_coro.call_args.kwargs["timeout"] > 0
