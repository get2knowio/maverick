"""Tests for the in-process bead supervisor."""

from __future__ import annotations

from maverick.workflows.fly_beads.actors.protocol import Message, MessageType
from maverick.workflows.fly_beads.supervisor import BeadSupervisor


def test_review_result_derives_findings_count_from_findings_payload() -> None:
    supervisor = BeadSupervisor(bead_id="bead-1", actors={}, initial_payload={})

    routed = supervisor._route(
        Message(
            msg_type=MessageType.REVIEW_RESULT,
            sender="reviewer",
            recipient="supervisor",
            payload={
                "approved": False,
                "findings": [
                    {
                        "severity": "major",
                        "message": "Add a regression test for mailbox parsing.",
                        "file": "tests/unit/tools/agent_inbox/test_gateway.py",
                    }
                ],
            },
            sequence=7,
        )
    )

    assert supervisor._findings_trajectory == [1]
    assert len(routed) == 1
    assert routed[0].msg_type == MessageType.FIX_REQUEST
    assert routed[0].payload["review_findings"][0]["issue"] == (
        "Add a regression test for mailbox parsing."
    )
