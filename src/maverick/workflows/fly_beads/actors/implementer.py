"""ImplementerActor — agent actor that implements and fixes code.

Maintains a persistent ACP session for the bead's lifetime.
Communicates results to the supervisor via MCP tool calls
(submit_implementation, submit_fix_result) — schema enforced
by the MCP protocol.
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


class ImplementerActor:
    """Agent actor that implements bead work and addresses fix requests.

    Handles:
    - IMPLEMENT_REQUEST: Initial implementation (creates session)
    - FIX_REQUEST: Address gate/AC/review findings (same session)

    Results delivered via MCP tool calls, not text output.
    """

    def __init__(
        self,
        *,
        session_registry: BeadSessionRegistry,
        executor: Any,
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
        self._turns: int = 0

    @property
    def name(self) -> str:
        return "implementer"

    async def receive(self, message: Message) -> list[Message]:
        match message.msg_type:
            case MessageType.IMPLEMENT_REQUEST:
                return await self._handle_implement(message)
            case MessageType.FIX_REQUEST:
                return await self._handle_fix(message)
            case _:
                logger.warning(
                    "implementer_actor.unexpected_message",
                    msg_type=message.msg_type,
                )
                return []

    async def _handle_implement(self, message: Message) -> list[Message]:
        """Handle initial implementation request."""
        payload = message.payload

        parts: list[str] = []
        parts.append(f"## Task\n\n{payload.get('task_description', '')}")

        if payload.get("acceptance_criteria"):
            parts.append(f"## Acceptance Criteria\n\n{payload['acceptance_criteria']}")
        if payload.get("file_scope"):
            parts.append(f"## File Scope\n\n{payload['file_scope']}")
        if payload.get("procedure"):
            parts.append(f"## Procedure\n\n{payload['procedure']}")
        if payload.get("test_to_pass"):
            parts.append(f"## Test to Pass\n\n{payload['test_to_pass']}")
        if payload.get("verification_commands"):
            parts.append(
                f"## Verification Commands\n\n{payload['verification_commands']}"
            )
        if payload.get("runway_context"):
            parts.append(f"## Prior Context\n\n{payload['runway_context']}")

        parts.append(
            "\n\n## REQUIRED: Submit via tool call\n"
            "When implementation is complete, you MUST call the "
            "`submit_implementation` tool with a summary and list of "
            "files changed. Do NOT just respond in text."
        )

        prompt_text = "\n\n".join(parts)

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
            step_name="implement",
            agent_name="implementer",
        )
        self._turns += 1

        inbox_data = await self._read_inbox_with_retry(
            "submit_implementation", session_id
        )

        return [
            Message(
                msg_type=MessageType.IMPLEMENT_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload=inbox_data.get("arguments", {}) if inbox_data else {
                    "summary": "implementation completed (no tool call)",
                },
                in_reply_to=message.sequence,
            )
        ]

    async def _handle_fix(self, message: Message) -> list[Message]:
        """Handle fix request — address gate/AC/review findings."""
        payload = message.payload

        parts: list[str] = ["Please fix the following issues:\n"]

        if payload.get("gate_failures"):
            gate = payload["gate_failures"]
            summary = gate.get("summary", "")
            parts.append(f"## Gate Failures\n\n{summary}")

        if payload.get("ac_failures"):
            ac = payload["ac_failures"]
            reasons = ac.get("reasons", [])
            if reasons:
                parts.append(
                    "## Acceptance Check Failures\n\n"
                    + "\n".join(f"- {r}" for r in reasons)
                )

        if payload.get("spec_failures"):
            spec = payload["spec_failures"]
            details = spec.get("details", "")
            parts.append(f"## Spec Compliance Failures\n\n{details}")

        if payload.get("review_findings"):
            findings = payload["review_findings"]
            if isinstance(findings, list):
                parts.append("## Review Findings to Address\n")
                for f in findings:
                    severity = f.get("severity", "")
                    issue = f.get("issue", "")
                    file = f.get("file", "")
                    line = f.get("line", "")
                    parts.append(f"- **{severity}** `{file}:{line}`: {issue}")
            elif isinstance(findings, str):
                parts.append(f"## Review Findings\n\n{findings}")

        parts.append(
            "\n\n## REQUIRED: Submit via tool call\n"
            "When fixes are complete, call the `submit_fix_result` tool "
            "with a summary of what you addressed."
        )

        prompt_text = "\n\n".join(parts)

        session_id = self._registry.get_session(self.name)
        if not session_id:
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
            step_name="implement_fix",
            agent_name="implementer",
        )
        self._turns += 1

        inbox_data = await self._read_inbox_with_retry(
            "submit_fix_result", session_id
        )

        return [
            Message(
                msg_type=MessageType.FIX_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload=inbox_data.get("arguments", {}) if inbox_data else {
                    "summary": "fixes applied (no tool call)",
                },
                in_reply_to=message.sequence,
            )
        ]

    async def _read_inbox_with_retry(
        self, expected_tool: str, session_id: str, max_retries: int = 2
    ) -> dict[str, Any] | None:
        data = self._read_inbox_file()
        if data is not None:
            return data

        for retry in range(max_retries):
            logger.info(
                "implementer_actor.inbox_retry",
                tool=expected_tool, retry=retry + 1,
            )
            await self._executor.prompt_session(
                session_id=session_id,
                prompt_text=(
                    f"Your work was not registered because you did not "
                    f"call the `{expected_tool}` tool. Please call "
                    f"`{expected_tool}` now."
                ),
                provider=self._registry.get_provider(self.name),
                config=self._config,
                step_name=f"implement_nudge_{expected_tool}",
                agent_name="implementer",
            )
            self._turns += 1
            data = self._read_inbox_file()
            if data is not None:
                return data

        logger.warning("implementer_actor.inbox_exhausted", tool=expected_tool)
        return None

    def _read_inbox_file(self) -> dict[str, Any] | None:
        if self._inbox_path.exists():
            try:
                data = json.loads(
                    self._inbox_path.read_text(encoding="utf-8")
                )
                self._inbox_path.unlink()
                return data
            except Exception as exc:
                logger.warning(
                    "implementer_actor.inbox_read_failed", error=str(exc)
                )
        return None

    def get_state_snapshot(self) -> dict[str, Any]:
        return {"turns": self._turns}

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        self._turns = snapshot.get("turns", 0)
