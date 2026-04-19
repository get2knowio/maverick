"""ReviewerActor — agent actor that reviews code changes.

Maintains a persistent ACP session for the bead's lifetime.
Communicates review results to the supervisor via the submit_review
MCP tool — schema enforced by the protocol. No heuristic text
parsing needed.

On follow-up reviews, the reviewer checks its own prior findings
because the conversation history is preserved in the session.
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
from maverick.workflows.fly_beads.session_registry import SessionRegistry

logger = get_logger(__name__)


class ReviewerActor:
    """Agent actor that reviews code for completeness and correctness.

    Handles REVIEW_REQUEST messages. On the first review, does a full
    diff review. On subsequent reviews (same session), checks whether
    prior findings were addressed.

    Results delivered via submit_review MCP tool call.
    """

    def __init__(
        self,
        *,
        session_registry: SessionRegistry,
        executor: Any = None,
        cwd: Path | None = None,
        config: StepConfig | None = None,
        bead_description: str = "",
        inbox_path: Path,
        mcp_server_config: Any = None,
    ) -> None:
        self._registry = session_registry
        self._executor = executor
        self._cwd = cwd
        self._config = config
        self._bead_description = bead_description
        self._inbox_path = inbox_path
        self._mcp_config = mcp_server_config
        self._review_count: int = 0

    @property
    def name(self) -> str:
        return "reviewer"

    async def receive(self, message: Message) -> list[Message]:
        if message.msg_type != MessageType.REVIEW_REQUEST:
            logger.warning(
                "reviewer_actor.unexpected_message",
                msg_type=message.msg_type,
            )
            return []

        self._review_count += 1

        if self._review_count == 1:
            return await self._initial_review(message)
        else:
            return await self._followup_review(message)

    async def _initial_review(self, message: Message) -> list[Message]:
        """First review — full review of the code changes."""
        prompt_text = (
            "Review the code changes in the working directory for "
            "completeness and correctness. Use the Read, Glob, and "
            "Grep tools to examine the code.\n\n"
            f"## Task Description\n\n{self._bead_description}\n\n"
            "## Instructions\n\n"
            "1. Read the changed files to understand what was implemented.\n"
            "2. Check that the implementation satisfies the task description "
            "and acceptance criteria.\n"
            "3. Check for bugs, security issues, and correctness problems.\n"
            "4. Only flag CRITICAL (runtime crash, security, data corruption) "
            "or MAJOR (bugs, missing required behavior) issues.\n\n"
            "## REQUIRED: Submit via tool call\n"
            "Call the `submit_review` tool with your findings. Set "
            "approved=true if no critical/major issues, or approved=false "
            "with a findings array describing each issue."
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
            mcp_servers=mcp_servers,
        )

        await self._executor.prompt_session(
            session_id=session_id,
            prompt_text=prompt_text,
            provider=self._registry.get_provider(self.name),
            config=self._config,
            step_name="review",
            agent_name="reviewer",
        )

        inbox_data = await self._read_inbox_with_retry(session_id)
        payload = (
            inbox_data.get("arguments", {})
            if inbox_data
            else {
                "approved": True,
            }
        )
        payload["review_round"] = self._review_count

        return [
            Message(
                msg_type=MessageType.REVIEW_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload=payload,
                in_reply_to=message.sequence,
            )
        ]

    async def _followup_review(self, message: Message) -> list[Message]:
        """Follow-up review — check if prior findings were addressed."""
        prompt_text = (
            "The implementer has made changes to address your previous "
            "findings. Review ONLY whether your previous findings were "
            "addressed. Do NOT do a fresh full review.\n\n"
            "Use the Read tool to check the specific files and lines "
            "you flagged previously.\n\n"
            "For each previous finding, determine if it was:\n"
            "- ADDRESSED: the issue is fixed\n"
            "- STILL PRESENT: the issue remains\n"
            "- ACCEPTED: the implementer's approach is valid\n\n"
            "IMPORTANT: Do NOT introduce new findings that weren't in "
            "your previous review.\n\n"
            "## REQUIRED: Submit via tool call\n"
            "Call the `submit_review` tool. Set approved=true if all "
            "findings are addressed/accepted, or approved=false with "
            "remaining issues in the findings array."
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
            step_name="review_followup",
            agent_name="reviewer",
        )

        inbox_data = await self._read_inbox_with_retry(session_id)
        payload = (
            inbox_data.get("arguments", {})
            if inbox_data
            else {
                "approved": True,
            }
        )
        payload["review_round"] = self._review_count

        return [
            Message(
                msg_type=MessageType.REVIEW_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload=payload,
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
            logger.info("reviewer_actor.inbox_retry", retry=retry + 1)
            await self._executor.prompt_session(
                session_id=session_id,
                prompt_text=(
                    "Your review was not registered because you did not "
                    "call the `submit_review` tool. Please call "
                    "`submit_review` now with your findings."
                ),
                provider=self._registry.get_provider(self.name),
                config=self._config,
                step_name="review_nudge",
                agent_name="reviewer",
            )
            data = self._read_inbox_file()
            if data is not None:
                return data

        logger.warning("reviewer_actor.inbox_exhausted")
        return None

    def _read_inbox_file(self) -> dict[str, Any] | None:
        if self._inbox_path.exists():
            try:
                data = json.loads(self._inbox_path.read_text(encoding="utf-8"))
                self._inbox_path.unlink()
                return data
            except Exception as exc:
                logger.warning("reviewer_actor.inbox_read_failed", error=str(exc))
        return None

    def get_state_snapshot(self) -> dict[str, Any]:
        return {"review_count": self._review_count}

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        self._review_count = snapshot.get("review_count", 0)
