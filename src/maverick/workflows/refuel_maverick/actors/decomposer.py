"""DecomposerActor — persistent-session actor for flight plan decomposition.

Uses MCP tools as the outbound mailbox to the supervisor. The agent
calls submit_outline, submit_details, or submit_fix tools to deliver
structured messages — the MCP protocol enforces the parameter schemas.

The agent receives natural-language prompts (no schema directives)
and communicates results via tool calls (schema-enforced by MCP).
"""

from __future__ import annotations

import json
import sys
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


class DecomposerActor:
    """Agent actor that decomposes a flight plan into work units.

    Handles:
    - OUTLINE_REQUEST: Produce work unit skeleton (turn 1)
    - DETAIL_REQUEST: Fill in procedures, AC, verification (turn 2)
    - FIX_DECOMPOSE_REQUEST: Patch specific gaps/overloads (turn 3+)

    All turns happen on the same persistent ACP session.
    Results are delivered via MCP tool calls, not text output.
    """

    def __init__(
        self,
        *,
        session_registry: BeadSessionRegistry,
        executor: Any,  # AcpStepExecutor
        cwd: Path | None = None,
        config: StepConfig | None = None,
        inbox_path: Path,
        mcp_server_config: Any = None,  # McpServerStdio
    ) -> None:
        self._registry = session_registry
        self._executor = executor
        self._cwd = cwd
        self._config = config
        self._inbox_path = inbox_path
        self._mcp_config = mcp_server_config
        self._turns: int = 0

    @property
    def name(self) -> str:
        return "decomposer"

    async def receive(self, message: Message) -> list[Message]:
        match message.msg_type:
            case MessageType.OUTLINE_REQUEST:
                return await self._handle_outline(message)
            case MessageType.DETAIL_REQUEST:
                return await self._handle_detail(message)
            case MessageType.FIX_DECOMPOSE_REQUEST:
                return await self._handle_fix(message)
            case _:
                logger.warning(
                    "decomposer_actor.unexpected_message",
                    msg_type=message.msg_type,
                )
                return []

    async def _handle_outline(self, message: Message) -> list[Message]:
        """Generate the work unit outline (turn 1)."""
        from maverick.library.actions.decompose import build_outline_prompt

        payload = message.payload
        prompt_text = build_outline_prompt(
            payload["flight_plan_content"],
            payload.get("codebase_context"),
            briefing=payload.get("briefing"),
            runway_context=payload.get("runway_context"),
        )

        # Append validation feedback from prior fix rounds
        validation_feedback = payload.get("validation_feedback", "")
        if validation_feedback:
            prompt_text += (
                f"\n\n## PREVIOUS ATTEMPT FAILED VALIDATION\n"
                f"{validation_feedback}\n"
                f"Fix these issues in your new decomposition."
            )

        # Append instruction to use the submit_outline tool
        prompt_text += (
            "\n\n## REQUIRED: Submit via tool call\n"
            "You MUST call the `submit_outline` tool with your results. "
            "Do NOT put your decomposition in a text response or code block — "
            "the supervisor can only receive your work via the submit_outline "
            "tool call."
        )

        # Create session with MCP server for tool-based output
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
            step_name="decompose_outline",
            agent_name="decomposer",
        )
        self._turns += 1

        # Read structured result from inbox (written by MCP tool call)
        inbox_data = await self._read_inbox_with_retry("submit_outline")

        return [
            Message(
                msg_type=MessageType.OUTLINE_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload=inbox_data.get("arguments", {}) if inbox_data else {},
                in_reply_to=message.sequence,
            )
        ]

    async def _handle_detail(self, message: Message) -> list[Message]:
        """Fill in details for all work units (turn 2)."""
        from maverick.library.actions.decompose import build_detail_prompt

        payload = message.payload

        prompt_text = build_detail_prompt(
            flight_plan_content=payload.get("flight_plan_content", ""),
            outline_json=payload.get("outline_json", "{}"),
            unit_ids=payload.get("unit_ids", []),
            verification_properties=payload.get(
                "verification_properties", ""
            ),
        )

        # Append instruction to use the submit_details tool
        prompt_text += (
            "\n\n## REQUIRED: Submit via tool call\n"
            "You MUST call the `submit_details` tool with your results. "
            "Do NOT put details in a text response or code block — "
            "the supervisor can only receive your work via the "
            "submit_details tool call."
        )

        session_id = self._registry.get_session(self.name)
        if not session_id:
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
            step_name="decompose_detail",
            agent_name="decomposer",
        )
        self._turns += 1

        inbox_data = await self._read_inbox_with_retry("submit_details")

        return [
            Message(
                msg_type=MessageType.DETAIL_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload=inbox_data.get("arguments", {}) if inbox_data else {},
                in_reply_to=message.sequence,
            )
        ]

    async def _handle_fix(self, message: Message) -> list[Message]:
        """Patch specific validation gaps (turn 3+)."""
        payload = message.payload

        parts: list[str] = [
            "Your previous decomposition had validation issues. "
            "Fix ONLY the specific problems listed below.\n"
        ]

        if payload.get("coverage_gaps"):
            parts.append("## Missing SC Coverage\n")
            for gap in payload["coverage_gaps"]:
                parts.append(f"- {gap}")
            parts.append(
                "\nAssign each missing SC to an existing work unit or "
                "create a new one."
            )

        if payload.get("overloaded"):
            parts.append("\n## Overloaded Work Units\n")
            for item in payload["overloaded"]:
                parts.append(f"- {item}")
            parts.append("\nSplit into smaller units with depends_on links.")

        parts.append(
            "\n\n## REQUIRED: Submit via tool call\n"
            "You MUST call the `submit_fix` tool with the COMPLETE "
            "updated work_units and details arrays. Do NOT respond "
            "in text — the supervisor can only receive your fix via "
            "the submit_fix tool call. If you respond without calling "
            "the tool, the fix will not be registered."
        )

        prompt_text = "\n".join(parts)

        session_id = self._registry.get_session(self.name)
        if not session_id:
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
            step_name="decompose_fix",
            agent_name="decomposer",
        )
        self._turns += 1

        inbox_data = await self._read_inbox_with_retry("submit_fix")

        return [
            Message(
                msg_type=MessageType.FIX_DECOMPOSE_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload=inbox_data.get("arguments", {}) if inbox_data else {},
                in_reply_to=message.sequence,
            )
        ]

    async def _read_inbox_with_retry(
        self,
        expected_tool: str,
        max_retries: int = 2,
    ) -> dict[str, Any] | None:
        """Read the inbox, retrying if the agent didn't call the tool.

        If the inbox is empty after a turn, immediately re-prompts
        the agent to call the expected tool. This is the self-correcting
        loop: the orchestrator tells the agent it hasn't delivered its
        message yet.
        """
        data = self._read_inbox_file()
        if data is not None:
            return data

        # Inbox empty — agent responded in text without calling the tool.
        # Re-prompt on the same session to nudge it.
        for retry in range(max_retries):
            logger.info(
                "decomposer_actor.inbox_retry",
                expected_tool=expected_tool,
                retry=retry + 1,
                turn=self._turns,
            )
            nudge = (
                f"Your response was not registered because you did not "
                f"call the `{expected_tool}` tool. The supervisor can "
                f"only receive your work via tool calls, not text. "
                f"Please call `{expected_tool}` now with your results."
            )
            session_id = self._registry.get_session(self.name)
            if session_id:
                await self._executor.prompt_session(
                    session_id=session_id,
                    prompt_text=nudge,
                    provider=self._registry.get_provider(self.name),
                    config=self._config,
                    step_name=f"decompose_nudge_{expected_tool}",
                    agent_name="decomposer",
                )
                self._turns += 1

            data = self._read_inbox_file()
            if data is not None:
                return data

        logger.warning(
            "decomposer_actor.inbox_exhausted",
            expected_tool=expected_tool,
            retries=max_retries,
        )
        return None

    def _read_inbox_file(self) -> dict[str, Any] | None:
        """Read and consume the inbox file."""
        if self._inbox_path.exists():
            try:
                data = json.loads(
                    self._inbox_path.read_text(encoding="utf-8")
                )
                self._inbox_path.unlink()  # consume the message
                logger.info(
                    "decomposer_actor.inbox_read",
                    tool=data.get("tool"),
                    turn=self._turns,
                )
                return data
            except Exception as exc:
                logger.warning(
                    "decomposer_actor.inbox_read_failed",
                    error=str(exc),
                )
        return None

    def get_state_snapshot(self) -> dict[str, Any]:
        return {"turns": self._turns}

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        self._turns = snapshot.get("turns", 0)
