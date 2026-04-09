"""Actor protocol, message types, and core abstractions.

This module defines the foundational types for the actor-mailbox
architecture.  All actors (agent-backed or deterministic) implement
the Actor protocol.  All inter-actor communication uses the Message
dataclass.

Messages are the third information type in Maverick (alongside beads
and files).  They are ephemeral process coordination — invisible to
humans during processing, captured in the fly report at bead completion.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class MessageType(str, Enum):
    """Types of messages exchanged between actors within a bead's processing."""

    # Supervisor → Implementer
    IMPLEMENT_REQUEST = "implement_request"
    # Implementer → Supervisor
    IMPLEMENT_RESULT = "implement_result"

    # Supervisor → Gate (deterministic)
    GATE_REQUEST = "gate_request"
    # Gate → Supervisor
    GATE_RESULT = "gate_result"

    # Supervisor → AcceptanceCriteria (deterministic)
    AC_REQUEST = "ac_request"
    # AcceptanceCriteria → Supervisor
    AC_RESULT = "ac_result"

    # Supervisor → SpecCompliance (deterministic)
    SPEC_REQUEST = "spec_request"
    # SpecCompliance → Supervisor
    SPEC_RESULT = "spec_result"

    # Supervisor → Reviewer
    REVIEW_REQUEST = "review_request"
    # Reviewer → Supervisor
    REVIEW_RESULT = "review_result"

    # Supervisor → Implementer (fix gate/AC/review findings)
    FIX_REQUEST = "fix_request"
    # Implementer → Supervisor
    FIX_RESULT = "fix_result"

    # Supervisor → Committer (deterministic)
    COMMIT_REQUEST = "commit_request"
    # Committer → Supervisor
    COMMIT_RESULT = "commit_result"

    # --- Refuel decomposition messages ---

    # Supervisor → Decomposer
    OUTLINE_REQUEST = "outline_request"
    # Decomposer → Supervisor
    OUTLINE_RESULT = "outline_result"

    # Supervisor → Decomposer (fill details for all work units)
    DETAIL_REQUEST = "detail_request"
    # Decomposer → Supervisor
    DETAIL_RESULT = "detail_result"

    # Supervisor → Validator (deterministic)
    VALIDATE_REQUEST = "validate_request"
    # Validator → Supervisor
    VALIDATE_RESULT = "validate_result"

    # Supervisor → Decomposer (fix validation gaps/overloads)
    FIX_DECOMPOSE_REQUEST = "fix_decompose_request"
    # Decomposer → Supervisor
    FIX_DECOMPOSE_RESULT = "fix_decompose_result"

    # Supervisor → BeadCreator (deterministic)
    CREATE_BEADS_REQUEST = "create_beads_request"
    # BeadCreator → Supervisor
    CREATE_BEADS_RESULT = "create_beads_result"

    # --- Plan generation messages ---

    # Supervisor → BriefingActor (one per briefing agent)
    BRIEFING_REQUEST = "briefing_request"
    # BriefingActor → Supervisor (via MCP tool: submit_scope/analysis/criteria/challenge)
    BRIEFING_RESULT = "briefing_result"

    # Supervisor → SynthesisActor (deterministic)
    SYNTHESIS_REQUEST = "synthesis_request"
    # SynthesisActor → Supervisor
    SYNTHESIS_RESULT = "synthesis_result"

    # Supervisor → GeneratorActor
    GENERATE_PLAN_REQUEST = "generate_plan_request"
    # GeneratorActor → Supervisor (via MCP tool: submit_flight_plan)
    GENERATE_PLAN_RESULT = "generate_plan_result"

    # Supervisor → ValidatePlanActor (deterministic)
    VALIDATE_PLAN_REQUEST = "validate_plan_request"
    # ValidatePlanActor → Supervisor
    VALIDATE_PLAN_RESULT = "validate_plan_result"

    # Supervisor → WritePlanActor (deterministic)
    WRITE_PLAN_REQUEST = "write_plan_request"
    # WritePlanActor → Supervisor
    WRITE_PLAN_RESULT = "write_plan_result"


@dataclass(frozen=True, slots=True)
class Message:
    """Ephemeral process coordination between actors.

    Messages are transient, invisible to humans during processing, but
    captured in the fly report at bead completion for runway learning.

    Attributes:
        msg_type: The message category.
        sender: Actor name that produced this message (or "supervisor").
        recipient: Actor name that should receive this message.
        payload: Arbitrary data specific to the message type.
        sequence: Monotonically increasing ID within a bead's processing.
        in_reply_to: Sequence number of the message this responds to.
    """

    msg_type: MessageType
    sender: str
    recipient: str
    payload: dict[str, Any]
    sequence: int = 0
    in_reply_to: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "msg_type": self.msg_type.value,
            "sender": self.sender,
            "recipient": self.recipient,
            "payload": self.payload,
            "sequence": self.sequence,
            "in_reply_to": self.in_reply_to,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        """Deserialize from a dictionary (e.g., from checkpoint)."""
        return cls(
            msg_type=MessageType(data["msg_type"]),
            sender=data["sender"],
            recipient=data["recipient"],
            payload=data.get("payload", {}),
            sequence=data.get("sequence", 0),
            in_reply_to=data.get("in_reply_to"),
        )


@runtime_checkable
class Actor(Protocol):
    """Protocol for all actors in the fly workflow.

    Actors are stateful within a bead's lifetime.  They are created
    when a bead starts processing and torn down when it completes.

    There are two kinds of actors:
    - **Agent actors** (ImplementerActor, ReviewerActor): Hold a
      persistent ACP session, receive prompts via the session.
    - **Deterministic actors** (GateActor, ACCheckActor, etc.):
      Pure Python, no ACP session, wrap existing action functions.

    Phase 1 is sequential — the supervisor calls actors one at a time.
    The protocol is designed for future concurrent execution (Phase 3).
    """

    @property
    def name(self) -> str:
        """Unique actor name (e.g., 'implementer', 'gate', 'reviewer')."""
        ...

    async def receive(self, message: Message) -> list[Message]:
        """Process a message and return zero or more response messages.

        The supervisor routes the returned messages to their recipients.
        An actor may return messages to multiple recipients.

        Args:
            message: The incoming message to process.

        Returns:
            List of response messages.  Empty list means this actor
            has nothing further to say for now.
        """
        ...

    def get_state_snapshot(self) -> dict[str, Any]:
        """Return serializable state for checkpoint/crash recovery.

        Called by the supervisor after each message exchange.
        """
        ...

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        """Restore actor state from a checkpoint snapshot.

        Called during crash recovery before any messages are delivered.
        """
        ...
