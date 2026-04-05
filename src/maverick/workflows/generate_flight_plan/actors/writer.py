"""WriterActor — deterministic flight plan file writer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maverick.logging import get_logger
from maverick.workflows.fly_beads.actors.protocol import Message, MessageType

logger = get_logger(__name__)


class PlanWriterActor:
    """Writes flight plan and briefing to disk."""

    def __init__(self, *, output_dir: Path) -> None:
        self._output_dir = output_dir

    @property
    def name(self) -> str:
        return "plan_writer"

    async def receive(self, message: Message) -> list[Message]:
        if message.msg_type != MessageType.WRITE_PLAN_REQUEST:
            return []

        payload = message.payload
        flight_plan_content = payload.get("flight_plan_markdown", "")
        briefing_content = payload.get("briefing_markdown", "")
        plan_name = payload.get("plan_name", "plan")

        self._output_dir.mkdir(parents=True, exist_ok=True)

        # Write flight plan
        plan_path = self._output_dir / "flight-plan.md"
        plan_path.write_text(flight_plan_content, encoding="utf-8")

        # Write briefing if available
        briefing_path = None
        if briefing_content:
            briefing_path = self._output_dir / "briefing.md"
            briefing_path.write_text(briefing_content, encoding="utf-8")

        return [
            Message(
                msg_type=MessageType.WRITE_PLAN_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload={
                    "flight_plan_path": str(plan_path),
                    "briefing_path": str(briefing_path) if briefing_path else None,
                },
                in_reply_to=message.sequence,
            )
        ]

    def get_state_snapshot(self) -> dict[str, Any]:
        return {}

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        pass
