"""SynthesisActor — deterministic briefing merge."""

from __future__ import annotations

from typing import Any

from maverick.logging import get_logger
from maverick.workflows.fly_beads.actors.protocol import Message, MessageType

logger = get_logger(__name__)


class SynthesisActor:
    """Merges 4 briefing agent results into Markdown.

    Works directly with raw dicts from MCP tool calls — no Pydantic
    coercion needed since the MCP tool schemas are the single source
    of truth for field names.
    """

    def __init__(self, *, plan_name: str = "") -> None:
        self._plan_name = plan_name

    @property
    def name(self) -> str:
        return "synthesis"

    async def receive(self, message: Message) -> list[Message]:
        if message.msg_type != MessageType.SYNTHESIS_REQUEST:
            return []

        from maverick.preflight_briefing.serializer import serialize_briefs_to_markdown

        payload = message.payload

        briefing_md = serialize_briefs_to_markdown(
            self._plan_name,
            scope=payload.get("scopist"),
            analysis=payload.get("analyst"),
            criteria=payload.get("criteria"),
            challenge=payload.get("contrarian"),
        )

        return [
            Message(
                msg_type=MessageType.SYNTHESIS_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload={
                    "briefing_markdown": briefing_md,
                },
                in_reply_to=message.sequence,
            )
        ]

    def get_state_snapshot(self) -> dict[str, Any]:
        return {}

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        pass
