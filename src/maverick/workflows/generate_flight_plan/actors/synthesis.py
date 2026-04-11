"""SynthesisActor — deterministic briefing merge."""

from __future__ import annotations

import json
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

        from maverick.preflight_briefing.serializer import (
            serialize_preflight_briefing,
        )
        from maverick.preflight_briefing.synthesis import (
            synthesize_preflight_briefing,
        )

        payload = message.payload

        # MCP tool calls deliver raw dicts; synthesis expects Pydantic
        # models. Try to validate, fall back to simple markdown summary.
        from maverick.preflight_briefing.models import (
            CodebaseAnalystBrief,
            CriteriaWriterBrief,
            PreFlightContrarianBrief,
            ScopistBrief,
        )

        try:
            scopist_data = payload.get("scopist") or {}
            analyst_data = payload.get("analyst") or {}
            criteria_data = payload.get("criteria") or {}
            contrarian_data = payload.get("contrarian") or {}

            # Coerce dicts to Pydantic if needed
            scopist = (
                scopist_data
                if isinstance(scopist_data, ScopistBrief)
                else ScopistBrief.model_validate(scopist_data)
            )
            analyst = (
                analyst_data
                if isinstance(analyst_data, CodebaseAnalystBrief)
                else CodebaseAnalystBrief.model_validate(analyst_data)
            )
            criteria = (
                criteria_data
                if isinstance(criteria_data, CriteriaWriterBrief)
                else CriteriaWriterBrief.model_validate(criteria_data)
            )
            contrarian = (
                contrarian_data
                if isinstance(contrarian_data, PreFlightContrarianBrief)
                else PreFlightContrarianBrief.model_validate(contrarian_data)
            )

            briefing_doc = synthesize_preflight_briefing(
                self._plan_name,
                scopist,
                analyst,
                criteria,
                contrarian,
            )
            briefing_md = serialize_preflight_briefing(briefing_doc)
        except Exception as exc:
            logger.warning("synthesis_actor.error", error=str(exc))
            # Fallback: simple markdown from raw dicts
            briefing_doc = None
            parts = []
            for key, data in [
                ("Scope", payload.get("scopist")),
                ("Analysis", payload.get("analyst")),
                ("Criteria", payload.get("criteria")),
                ("Challenges", payload.get("contrarian")),
            ]:
                if data:
                    parts.append(f"## {key}\n\n{json.dumps(data, indent=2)}")
            briefing_md = "\n\n".join(parts) if parts else ""

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
