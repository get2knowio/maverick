"""GateActor — deterministic validation gate.

Wraps the existing ``run_independent_gate()`` action behind the Actor
protocol.  No ACP session — pure Python execution of cargo build,
clippy, fmt, and test commands.
"""

from __future__ import annotations

from typing import Any

from maverick.library.actions.validation import run_independent_gate
from maverick.logging import get_logger
from maverick.workflows.fly_beads.actors.protocol import (
    Message,
    MessageType,
)
from maverick.workflows.fly_beads.constants import DEFAULT_VALIDATION_STAGES

logger = get_logger(__name__)


class GateActor:
    """Deterministic actor that runs the validation gate.

    Receives GATE_REQUEST, runs build/lint/test, returns GATE_RESULT.
    Stateless — no ACP session, no conversation history.
    """

    def __init__(
        self,
        *,
        cwd: str | None = None,
        validation_commands: dict[str, list[str]] | None = None,
        timeout_seconds: float = 600.0,
    ) -> None:
        self._cwd = cwd
        self._validation_commands = validation_commands
        self._timeout = timeout_seconds

    @property
    def name(self) -> str:
        return "gate"

    async def receive(self, message: Message) -> list[Message]:
        if message.msg_type != MessageType.GATE_REQUEST:
            logger.warning("gate_actor.unexpected_message", msg_type=message.msg_type)
            return []

        try:
            result = await run_independent_gate(
                stages=list(DEFAULT_VALIDATION_STAGES),
                cwd=self._cwd,
                validation_commands=self._validation_commands or None,
                timeout_seconds=self._timeout,
            )
        except Exception as exc:
            logger.warning("gate_actor.error", error=str(exc))
            result = {
                "passed": False,
                "stage_results": {},
                "summary": f"Gate error: {exc}",
            }

        return [
            Message(
                msg_type=MessageType.GATE_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload=result,
                in_reply_to=message.sequence,
            )
        ]

    def get_state_snapshot(self) -> dict[str, Any]:
        return {}  # stateless

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        pass  # stateless
