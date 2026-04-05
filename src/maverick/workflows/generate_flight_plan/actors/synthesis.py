"""SynthesisActor — deterministic briefing merge."""

from __future__ import annotations

from typing import Any

from maverick.logging import get_logger
from maverick.workflows.fly_beads.actors.protocol import Message, MessageType

logger = get_logger(__name__)


class SynthesisActor:
    """Merges 4 briefing agent results into a BriefingDocument."""

    def __init__(self, *, plan_name: str = "") -> None:
        self._plan_name = plan_name

    @property
    def name(self) -> str:
        return "synthesis"

    async def receive(self, message: Message) -> list[Message]:
        if message.msg_type != MessageType.SYNTHESIS_REQUEST:
            return []

        from maverick.preflight_briefing.synthesis import (
            synthesize_preflight_briefing,
        )
        from maverick.preflight_briefing.serializer import (
            serialize_briefing_to_markdown,
        )

        payload = message.payload

        try:
            briefing_doc = synthesize_preflight_briefing(
                self._plan_name,
                payload.get("scopist"),
                payload.get("analyst"),
                payload.get("criteria"),
                payload.get("contrarian"),
            )
            briefing_md = serialize_briefing_to_markdown(briefing_doc)
        except Exception as exc:
            logger.warning("synthesis_actor.error", error=str(exc))
            briefing_doc = None
            briefing_md = ""

        return [
            Message(
                msg_type=MessageType.SYNTHESIS_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload={
                    "briefing_doc": briefing_doc,
                    "briefing_markdown": briefing_md,
                },
                in_reply_to=message.sequence,
            )
        ]

    def get_state_snapshot(self) -> dict[str, Any]:
        return {}

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        pass
