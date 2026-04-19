"""GeneratorActor — produces the flight plan from briefing context.

Receives the serialized briefing and PRD, calls the submit_flight_plan
MCP tool to deliver the structured flight plan to the supervisor.
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


class GeneratorActor:
    """Agent actor that generates a flight plan from PRD + briefing."""

    def __init__(
        self,
        *,
        session_registry: BeadSessionRegistry,
        executor: Any = None,
        cwd: Path | None = None,
        config: StepConfig | None = None,
        allowed_tools: list[str] | None = None,
        inbox_path: Path,
        mcp_server_config: Any = None,
    ) -> None:
        self._registry = session_registry
        self._executor = executor
        self._cwd = cwd
        self._config = config
        self._allowed_tools = allowed_tools
        self._inbox_path = inbox_path
        self._mcp_config = mcp_server_config

    @property
    def name(self) -> str:
        return "generator"

    async def receive(self, message: Message) -> list[Message]:
        if message.msg_type != MessageType.GENERATE_PLAN_REQUEST:
            logger.warning(
                "generator_actor.unexpected_message",
                msg_type=message.msg_type,
            )
            return []

        payload = message.payload
        prompt_text = payload.get("prompt", "")

        prompt_text += (
            "\n\n## REQUIRED: Submit via tool call\n"
            "You MUST call the `submit_flight_plan` tool with your "
            "flight plan. Do NOT put the plan in a text response — the "
            "supervisor can only receive it via the submit_flight_plan "
            "tool call."
        )

        if self._executor is None:
            from maverick.executor import create_default_executor

            self._executor = create_default_executor()

        mcp_servers = [self._mcp_config] if self._mcp_config else None
        session_id = await self._registry.get_or_create(
            self.name,
            self._executor,
            cwd=self._cwd,
            config=self._config,
            allowed_tools=self._allowed_tools,
            mcp_servers=mcp_servers,
        )

        await self._executor.prompt_session(
            session_id=session_id,
            prompt_text=prompt_text,
            provider=self._registry.get_provider(self.name),
            config=self._config,
            step_name="generate",
            agent_name="flight_plan_generator",
        )

        # Read with nudge
        inbox_data = await self._read_inbox_with_retry(session_id)

        return [
            Message(
                msg_type=MessageType.GENERATE_PLAN_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload=inbox_data.get("arguments", {}) if inbox_data else {},
                in_reply_to=message.sequence,
            )
        ]

    async def _read_inbox_with_retry(
        self, session_id: str, max_retries: int = 2
    ) -> dict[str, Any] | None:
        data = self._read_inbox_file()
        if data is not None:
            return data

        for retry in range(max_retries):
            logger.info("generator_actor.inbox_retry", retry=retry + 1)
            await self._executor.prompt_session(
                session_id=session_id,
                prompt_text=(
                    "Your response was not registered because you did not "
                    "call the `submit_flight_plan` tool. Please call "
                    "`submit_flight_plan` now with your flight plan."
                ),
                provider=self._registry.get_provider(self.name),
                config=self._config,
                step_name="generate_nudge",
                agent_name="flight_plan_generator",
            )
            data = self._read_inbox_file()
            if data is not None:
                return data

        logger.warning("generator_actor.inbox_exhausted")
        return None

    def _read_inbox_file(self) -> dict[str, Any] | None:
        if self._inbox_path.exists():
            try:
                data = json.loads(self._inbox_path.read_text(encoding="utf-8"))
                self._inbox_path.unlink()
                return data
            except Exception as exc:
                logger.warning("generator_actor.inbox_read_failed", error=str(exc))
        return None

    def get_state_snapshot(self) -> dict[str, Any]:
        return {}

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        pass
