"""BriefingActor — generic actor for all briefing room agents.

A single actor class parameterized by agent name, MCP tool name,
and prompt builder. Handles Scopist, CodebaseAnalyst, CriteriaWriter,
and Contrarian — all follow the same pattern: receive prompt, do
analysis work, call one MCP tool to deliver results.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from maverick.executor.config import StepConfig
from maverick.logging import get_logger
from maverick.workflows.fly_beads.actors.protocol import (
    Message,
    MessageType,
)
from maverick.workflows.fly_beads.session_registry import BeadSessionRegistry

logger = get_logger(__name__)


class BriefingActor:
    """Generic agent actor for briefing room participants.

    Parameterized per agent — the same class handles Scopist,
    CodebaseAnalyst, CriteriaWriter, and Contrarian. Each gets
    a different MCP tool (submit_scope, submit_analysis, etc.)
    that constrains its output to the supervisor's expected schema.
    """

    def __init__(
        self,
        *,
        actor_name: str,
        mcp_tool_name: str,
        session_registry: BeadSessionRegistry,
        executor: Any,
        cwd: Path | None = None,
        config: StepConfig | None = None,
        inbox_path: Path,
        mcp_server_config: Any = None,
    ) -> None:
        self._actor_name = actor_name
        self._mcp_tool_name = mcp_tool_name
        self._registry = session_registry
        self._executor = executor
        self._cwd = cwd
        self._config = config
        self._inbox_path = inbox_path
        self._mcp_config = mcp_server_config

    @property
    def name(self) -> str:
        return self._actor_name

    async def receive(self, message: Message) -> list[Message]:
        if message.msg_type != MessageType.BRIEFING_REQUEST:
            logger.warning(
                "briefing_actor.unexpected_message",
                actor=self._actor_name,
                msg_type=message.msg_type,
            )
            return []

        payload = message.payload
        prompt_text = payload.get("prompt", "")

        # Append tool call instruction
        prompt_text += (
            f"\n\n## REQUIRED: Submit via tool call\n"
            f"You MUST call the `{self._mcp_tool_name}` tool with your "
            f"results. Do NOT put results in a text response — the "
            f"supervisor can only receive your work via the "
            f"{self._mcp_tool_name} tool call."
        )

        # Create session with MCP server
        mcp_servers = [self._mcp_config] if self._mcp_config else None
        session_id = await self._registry.get_or_create(
            self.name,
            self._executor,
            cwd=self._cwd,
            config=self._config,
            mcp_servers=mcp_servers,
        )

        await self._executor.prompt_session(
            session_id=session_id,
            prompt_text=prompt_text,
            provider=self._registry.get_provider(self.name),
            config=self._config,
            step_name=f"briefing_{self._actor_name}",
            agent_name=self._actor_name,
        )

        # Read from inbox with nudge retry
        inbox_data = await self._read_inbox_with_retry(session_id)

        return [
            Message(
                msg_type=MessageType.BRIEFING_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload={
                    "agent": self._actor_name,
                    "tool": self._mcp_tool_name,
                    **(inbox_data.get("arguments", {}) if inbox_data else {}),
                },
                in_reply_to=message.sequence,
            )
        ]

    async def _read_inbox_with_retry(
        self,
        session_id: str,
        max_retries: int = 2,
    ) -> dict[str, Any] | None:
        """Read inbox, nudging if agent didn't call the tool."""
        data = self._read_inbox_file()
        if data is not None:
            return data

        for retry in range(max_retries):
            logger.info(
                "briefing_actor.inbox_retry",
                actor=self._actor_name,
                tool=self._mcp_tool_name,
                retry=retry + 1,
            )
            nudge = (
                f"Your response was not registered because you did not "
                f"call the `{self._mcp_tool_name}` tool. Please call "
                f"`{self._mcp_tool_name}` now with your results."
            )
            await self._executor.prompt_session(
                session_id=session_id,
                prompt_text=nudge,
                provider=self._registry.get_provider(self.name),
                config=self._config,
                step_name=f"briefing_{self._actor_name}_nudge",
                agent_name=self._actor_name,
            )
            data = self._read_inbox_file()
            if data is not None:
                return data

        logger.warning(
            "briefing_actor.inbox_exhausted",
            actor=self._actor_name,
        )
        return None

    def _read_inbox_file(self) -> dict[str, Any] | None:
        if self._inbox_path.exists():
            try:
                data = json.loads(self._inbox_path.read_text(encoding="utf-8"))
                self._inbox_path.unlink()
                logger.info(
                    "briefing_actor.inbox_read",
                    actor=self._actor_name,
                    tool=data.get("tool"),
                )
                return data
            except Exception as exc:
                logger.warning(
                    "briefing_actor.inbox_read_failed",
                    error=str(exc),
                )
        return None

    def get_state_snapshot(self) -> dict[str, Any]:
        return {}

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        pass
