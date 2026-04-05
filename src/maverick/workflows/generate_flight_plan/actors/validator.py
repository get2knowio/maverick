"""ValidatorActor — deterministic flight plan validation (V1-V9)."""

from __future__ import annotations

from typing import Any

from maverick.logging import get_logger
from maverick.workflows.fly_beads.actors.protocol import Message, MessageType

logger = get_logger(__name__)


class PlanValidatorActor:
    """Runs V1-V9 validation checks on the flight plan."""

    @property
    def name(self) -> str:
        return "plan_validator"

    async def receive(self, message: Message) -> list[Message]:
        if message.msg_type != MessageType.VALIDATE_PLAN_REQUEST:
            return []

        from maverick.flight.validator import validate_flight_plan

        payload = message.payload
        flight_plan = payload.get("flight_plan")

        try:
            warnings = validate_flight_plan(flight_plan)
            passed = True
        except Exception as exc:
            warnings = [str(exc)]
            passed = False

        return [
            Message(
                msg_type=MessageType.VALIDATE_PLAN_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload={
                    "passed": passed,
                    "warnings": warnings,
                },
                in_reply_to=message.sequence,
            )
        ]

    def get_state_snapshot(self) -> dict[str, Any]:
        return {}

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        pass
