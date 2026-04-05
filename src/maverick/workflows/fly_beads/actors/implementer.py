"""ImplementerActor — agent actor that implements and fixes code.

Maintains a persistent ACP session for the bead's lifetime.  The
implementer remembers its own decisions across fix requests — when the
reviewer or gate sends findings, the implementer has full context of
why it wrote the code that way and can make targeted fixes.
"""

from __future__ import annotations

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
    - FIX_REQUEST: Address gate failures, AC failures, or review findings
      (reuses same session — full context preserved)

    The session persists for the entire bead's lifetime.  The implementer
    has access to its full conversation history, so when the reviewer says
    "fix F001," the implementer knows exactly what F001 refers to and why
    it made the original choice.
    """

    def __init__(
        self,
        *,
        session_registry: BeadSessionRegistry,
        executor: Any,  # AcpStepExecutor
        cwd: Path | None = None,
        config: StepConfig | None = None,
        allowed_tools: list[str] | None = None,
        agent_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self._registry = session_registry
        self._executor = executor
        self._cwd = cwd
        self._config = config
        self._allowed_tools = allowed_tools
        self._agent_kwargs = agent_kwargs or {}
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

        # Build structured prompt from payload fields
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

        prompt_text = "\n\n".join(parts)

        # Create session and send first prompt
        session_id = await self._registry.get_or_create(
            self.name,
            self._executor,
            cwd=self._cwd,
            config=self._config,
            allowed_tools=self._allowed_tools,
        )

        result = await self._executor.prompt_session(
            session_id=session_id,
            prompt_text=prompt_text,
            provider=self._registry.get_provider(self.name),
            config=self._config,
            step_name="implement",
            agent_name="implementer",
        )
        self._turns += 1

        return [
            Message(
                msg_type=MessageType.IMPLEMENT_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload={
                    "summary": _truncate(
                        result.output if isinstance(result.output, str) else "", 2000
                    ),
                    "turn": self._turns,
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

        if payload.get("reviewer_message"):
            parts.append(
                f"## Reviewer Notes\n\n{payload['reviewer_message']}"
            )

        prompt_text = "\n\n".join(parts)

        # Send to existing session (same conversation context)
        session_id = self._registry.get_session(self.name)
        if not session_id:
            # Shouldn't happen, but create if needed
            session_id = await self._registry.get_or_create(
                self.name,
                self._executor,
                cwd=self._cwd,
                config=self._config,
                allowed_tools=self._allowed_tools,
            )

        result = await self._executor.prompt_session(
            session_id=session_id,
            prompt_text=prompt_text,
            provider=self._registry.get_provider(self.name),
            config=self._config,
            step_name="implement_fix",
            agent_name="implementer",
        )
        self._turns += 1

        return [
            Message(
                msg_type=MessageType.FIX_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload={
                    "summary": _truncate(
                        result.output if isinstance(result.output, str) else "", 2000
                    ),
                    "turn": self._turns,
                },
                in_reply_to=message.sequence,
            )
        ]

    def get_state_snapshot(self) -> dict[str, Any]:
        return {"turns": self._turns}

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        self._turns = snapshot.get("turns", 0)


def _truncate(text: str, max_len: int) -> str:
    """Truncate text for message payloads (summaries, not full output)."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "... (truncated)"
