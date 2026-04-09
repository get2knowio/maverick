"""BeadSupervisor — message routing and policy engine for bead processing.

The supervisor replaces the 500-line bead loop body in workflow.py.
It creates actors, seeds the first message, routes responses via
the ``_route()`` method, and writes the fly report at completion.

The supervisor does not do work — it routes messages between actors
and enforces the workflow policy (how many review rounds, when to
commit partial work, when to tag for human review).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from maverick.logging import get_logger
from maverick.workflows.fly_beads.actors.protocol import (
    Actor,
    Message,
    MessageType,
)

logger = get_logger(__name__)

#: Maximum review-fix rounds before committing with human-review tag.
MAX_REVIEW_ROUNDS = 3

#: Maximum gate remediation attempts (implementer fix after gate failure).
MAX_GATE_FIX_ATTEMPTS = 2

#: Maximum AC/spec fix attempts.
MAX_DETERMINISTIC_FIX_ATTEMPTS = 2


@dataclass
class BeadOutcome:
    """Result of processing a single bead through the supervisor."""

    bead_id: str
    committed: bool = False
    needs_human_review: bool = False
    commit_sha: str | None = None
    files_changed: list[str] = field(default_factory=list)
    message_log: list[Message] = field(default_factory=list)
    review_rounds: int = 0
    gate_attempts: int = 0
    findings_trajectory: list[int] = field(default_factory=list)
    duration_seconds: float = 0.0
    error: str | None = None


class BeadSupervisor:
    """Routes messages between actors for a single bead's processing.

    The supervisor:
    1. Creates actors for the bead (done externally, passed in)
    2. Seeds the first message (IMPLEMENT_REQUEST)
    3. Routes response messages to their recipients via ``_route()``
    4. Decides when processing is complete (commit or abandon)
    5. Returns a BeadOutcome with the complete message log

    The routing policy in ``_route()`` encodes the workflow logic that
    was previously scattered across the 500-line bead loop.  Making it
    a match statement makes the policy explicit and testable.
    """

    def __init__(
        self,
        *,
        bead_id: str,
        actors: dict[str, Actor],
        initial_payload: dict[str, Any],
    ) -> None:
        self._bead_id = bead_id
        self._actors = actors
        self._initial_payload = initial_payload
        self._message_log: list[Message] = []
        self._sequence: int = 0

        # Policy counters
        self._review_rounds: int = 0
        self._gate_fix_attempts: int = 0
        self._ac_fix_attempts: int = 0
        self._spec_fix_attempts: int = 0
        self._findings_trajectory: list[int] = []

    async def process_bead(self) -> BeadOutcome:
        """Main supervisor loop. Returns when bead is committed or abandoned."""
        t0 = time.monotonic()

        # Seed: ask implementer to implement
        pending: list[Message] = [
            self._make_message(
                MessageType.IMPLEMENT_REQUEST,
                sender="supervisor",
                recipient="implementer",
                payload=self._initial_payload,
            )
        ]

        try:
            while pending:
                message = pending.pop(0)
                self._message_log.append(message)

                # Deliver to recipient actor
                actor = self._actors.get(message.recipient)
                if actor is None:
                    logger.error(
                        "supervisor.unknown_recipient",
                        recipient=message.recipient,
                        msg_type=message.msg_type,
                    )
                    continue

                logger.debug(
                    "supervisor.deliver",
                    bead_id=self._bead_id,
                    msg_type=message.msg_type.value,
                    sender=message.sender,
                    recipient=message.recipient,
                    sequence=message.sequence,
                )

                responses = await actor.receive(message)

                for response in responses:
                    response = self._stamp(response)
                    self._message_log.append(response)

                    # Route through policy
                    routed = self._route(response)
                    pending.extend(routed)

        except Exception as exc:
            logger.error(
                "supervisor.error",
                bead_id=self._bead_id,
                error=str(exc),
            )
            elapsed = time.monotonic() - t0
            return BeadOutcome(
                bead_id=self._bead_id,
                committed=False,
                message_log=list(self._message_log),
                review_rounds=self._review_rounds,
                gate_attempts=self._gate_fix_attempts,
                findings_trajectory=self._findings_trajectory,
                duration_seconds=elapsed,
                error=str(exc),
            )

        elapsed = time.monotonic() - t0

        # Extract outcome from the last COMMIT_RESULT
        commit_result = self._find_last_message(MessageType.COMMIT_RESULT)
        committed = commit_result is not None and commit_result.payload.get("success", False)
        needs_review = (
            commit_result is not None and commit_result.payload.get("tag") == "needs-human-review"
        )

        return BeadOutcome(
            bead_id=self._bead_id,
            committed=committed,
            needs_human_review=needs_review,
            commit_sha=(commit_result.payload.get("commit_sha") if commit_result else None),
            message_log=list(self._message_log),
            review_rounds=self._review_rounds,
            gate_attempts=self._gate_fix_attempts,
            findings_trajectory=self._findings_trajectory,
            duration_seconds=elapsed,
        )

    def _route(self, message: Message) -> list[Message]:
        """Supervisor routing policy.

        This is where the workflow logic lives — extracted from the
        500-line bead loop into an explicit, testable match statement.
        """
        match message.msg_type:
            case MessageType.IMPLEMENT_RESULT:
                # Implementation done → run gate
                return [
                    self._make_message(
                        MessageType.GATE_REQUEST,
                        sender="supervisor",
                        recipient="gate",
                    )
                ]

            case MessageType.GATE_RESULT:
                passed = message.payload.get("passed", False)
                if passed:
                    # Gate passed → acceptance check
                    return [
                        self._make_message(
                            MessageType.AC_REQUEST,
                            sender="supervisor",
                            recipient="acceptance_criteria",
                        )
                    ]
                elif self._gate_fix_attempts < MAX_GATE_FIX_ATTEMPTS:
                    # Gate failed → ask implementer to fix
                    self._gate_fix_attempts += 1
                    return [
                        self._make_message(
                            MessageType.FIX_REQUEST,
                            sender="supervisor",
                            recipient="implementer",
                            payload={"gate_failures": message.payload},
                            in_reply_to=message.sequence,
                        )
                    ]
                else:
                    # Gate failed, exhausted fix attempts → commit partial
                    logger.warning(
                        "supervisor.gate_exhausted",
                        bead_id=self._bead_id,
                        attempts=self._gate_fix_attempts,
                    )
                    return [
                        self._make_message(
                            MessageType.COMMIT_REQUEST,
                            sender="supervisor",
                            recipient="committer",
                            payload={"tag": "needs-human-review"},
                        )
                    ]

            case MessageType.AC_RESULT:
                passed = message.payload.get("passed", False)
                if passed:
                    # AC passed → spec compliance
                    return [
                        self._make_message(
                            MessageType.SPEC_REQUEST,
                            sender="supervisor",
                            recipient="spec_compliance",
                        )
                    ]
                elif self._ac_fix_attempts < MAX_DETERMINISTIC_FIX_ATTEMPTS:
                    self._ac_fix_attempts += 1
                    return [
                        self._make_message(
                            MessageType.FIX_REQUEST,
                            sender="supervisor",
                            recipient="implementer",
                            payload={"ac_failures": message.payload},
                            in_reply_to=message.sequence,
                        )
                    ]
                else:
                    return [
                        self._make_message(
                            MessageType.COMMIT_REQUEST,
                            sender="supervisor",
                            recipient="committer",
                            payload={"tag": "needs-human-review"},
                        )
                    ]

            case MessageType.SPEC_RESULT:
                passed = message.payload.get("passed", False)
                if passed:
                    # Spec passed → review
                    return [
                        self._make_message(
                            MessageType.REVIEW_REQUEST,
                            sender="supervisor",
                            recipient="reviewer",
                        )
                    ]
                elif self._spec_fix_attempts < MAX_DETERMINISTIC_FIX_ATTEMPTS:
                    self._spec_fix_attempts += 1
                    return [
                        self._make_message(
                            MessageType.FIX_REQUEST,
                            sender="supervisor",
                            recipient="implementer",
                            payload={"spec_failures": message.payload},
                            in_reply_to=message.sequence,
                        )
                    ]
                else:
                    return [
                        self._make_message(
                            MessageType.COMMIT_REQUEST,
                            sender="supervisor",
                            recipient="committer",
                            payload={"tag": "needs-human-review"},
                        )
                    ]

            case MessageType.REVIEW_RESULT:
                approved = message.payload.get("approved", False)
                findings_count = message.payload.get("findings_count", 0)
                self._findings_trajectory.append(findings_count)

                if approved:
                    # Reviewer approved → commit
                    return [
                        self._make_message(
                            MessageType.COMMIT_REQUEST,
                            sender="supervisor",
                            recipient="committer",
                        )
                    ]
                elif self._review_rounds < MAX_REVIEW_ROUNDS:
                    # Reviewer found issues → send to implementer for fix
                    self._review_rounds += 1
                    return [
                        self._make_message(
                            MessageType.FIX_REQUEST,
                            sender="supervisor",
                            recipient="implementer",
                            payload={
                                "review_findings": message.payload.get("findings", []),
                            },
                            in_reply_to=message.sequence,
                        )
                    ]
                else:
                    # Exhausted review rounds → commit with tag
                    logger.info(
                        "supervisor.review_exhausted",
                        bead_id=self._bead_id,
                        rounds=self._review_rounds,
                        trajectory=self._findings_trajectory,
                    )
                    return [
                        self._make_message(
                            MessageType.COMMIT_REQUEST,
                            sender="supervisor",
                            recipient="committer",
                            payload={"tag": "needs-human-review"},
                        )
                    ]

            case MessageType.FIX_RESULT:
                # Implementer claims to have fixed → re-run gate
                # (gate will cascade through AC → spec → review)
                return [
                    self._make_message(
                        MessageType.GATE_REQUEST,
                        sender="supervisor",
                        recipient="gate",
                    )
                ]

            case MessageType.COMMIT_RESULT:
                # Done — no more messages
                return []

        return []

    def _make_message(
        self,
        msg_type: MessageType,
        *,
        sender: str,
        recipient: str,
        payload: dict[str, Any] | None = None,
        in_reply_to: int | None = None,
    ) -> Message:
        """Create a new message with auto-incrementing sequence."""
        self._sequence += 1
        return Message(
            msg_type=msg_type,
            sender=sender,
            recipient=recipient,
            payload=payload or {},
            sequence=self._sequence,
            in_reply_to=in_reply_to,
        )

    def _stamp(self, message: Message) -> Message:
        """Assign a sequence number to an actor-produced message."""
        self._sequence += 1
        return Message(
            msg_type=message.msg_type,
            sender=message.sender,
            recipient=message.recipient,
            payload=message.payload,
            sequence=self._sequence,
            in_reply_to=message.in_reply_to,
        )

    def _find_last_message(self, msg_type: MessageType) -> Message | None:
        """Find the last message of a given type in the log."""
        for msg in reversed(self._message_log):
            if msg.msg_type == msg_type:
                return msg
        return None
