"""ValidatorActor — deterministic decomposition validation.

Wraps validate_decomposition() behind the Actor protocol.
No ACP session — pure Python.
"""

from __future__ import annotations

from typing import Any

from maverick.logging import get_logger
from maverick.workflows.fly_beads.actors.protocol import (
    Message,
    MessageType,
)

logger = get_logger(__name__)


class ValidatorActor:
    """Deterministic actor for decomposition validation.

    Checks SC coverage, dependency acyclicity, overloaded work units.
    Returns validation result with specific gap/overload details.
    """

    def __init__(
        self,
        *,
        flight_plan: Any = None,
        success_criteria_refs: list[str] | None = None,
    ) -> None:
        self._flight_plan = flight_plan
        self._sc_refs = success_criteria_refs or []

    @property
    def name(self) -> str:
        return "validator"

    async def receive(self, message: Message) -> list[Message]:
        if message.msg_type != MessageType.VALIDATE_REQUEST:
            logger.warning(
                "validator_actor.unexpected_message",
                msg_type=message.msg_type,
            )
            return []

        from maverick.library.actions.decompose import (
            SCCoverageError,
            validate_decomposition,
        )

        payload = message.payload
        specs = payload.get("specs", [])

        sc_list = getattr(self._flight_plan, "success_criteria", []) if self._flight_plan else []
        sc_count = len(sc_list)
        sc_refs = [
            getattr(sc, "ref", None) or f"SC-{i + 1:03d}" for i, sc in enumerate(sc_list)
        ] or self._sc_refs

        try:
            validate_decomposition(
                specs=specs,
                success_criteria_count=sc_count,
                expected_sc_refs=sc_refs or None,
            )
            return [
                Message(
                    msg_type=MessageType.VALIDATE_RESULT,
                    sender=self.name,
                    recipient="supervisor",
                    payload={"passed": True},
                    in_reply_to=message.sequence,
                )
            ]
        except SCCoverageError as exc:
            return [
                Message(
                    msg_type=MessageType.VALIDATE_RESULT,
                    sender=self.name,
                    recipient="supervisor",
                    payload={
                        "passed": False,
                        "error_type": "coverage",
                        "gaps": list(exc.gaps) if exc.gaps else [],
                        "message": str(exc),
                    },
                    in_reply_to=message.sequence,
                )
            ]
        except Exception as exc:
            return [
                Message(
                    msg_type=MessageType.VALIDATE_RESULT,
                    sender=self.name,
                    recipient="supervisor",
                    payload={
                        "passed": False,
                        "error_type": "other",
                        "gaps": [],
                        "message": str(exc),
                    },
                    in_reply_to=message.sequence,
                )
            ]

    def get_state_snapshot(self) -> dict[str, Any]:
        return {}

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        pass
