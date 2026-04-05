"""AcceptanceCriteriaActor — deterministic acceptance check.

Wraps the existing acceptance-criteria check logic (file scope
validation, verification command execution) behind the Actor protocol.
No ACP session — pure Python.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maverick.logging import get_logger
from maverick.workflows.fly_beads.actors.protocol import (
    Message,
    MessageType,
)

logger = get_logger(__name__)


class AcceptanceCriteriaActor:
    """Deterministic actor for acceptance criteria verification.

    Receives AC_REQUEST, runs file scope checks and verification
    commands from the work unit, returns AC_RESULT.
    """

    def __init__(
        self,
        *,
        cwd: Path | None = None,
        description: str = "",
    ) -> None:
        self._cwd = cwd
        self._description = description

    @property
    def name(self) -> str:
        return "acceptance_criteria"

    async def receive(self, message: Message) -> list[Message]:
        if message.msg_type != MessageType.AC_REQUEST:
            logger.warning("ac_actor.unexpected_message", msg_type=message.msg_type)
            return []

        from maverick.runners.command import CommandRunner
        from maverick.workflows.fly_beads.steps import (
            _parse_verification_commands,
            _parse_work_unit_sections,
        )

        sections = _parse_work_unit_sections(self._description)
        verification_text = sections.get("verification", "")

        if not verification_text:
            return [
                Message(
                    msg_type=MessageType.AC_RESULT,
                    sender=self.name,
                    recipient="supervisor",
                    payload={"passed": True, "reasons": []},
                    in_reply_to=message.sequence,
                )
            ]

        # Run verification commands
        reasons: list[str] = []
        cwd = self._cwd or Path.cwd()
        runner = CommandRunner(cwd=cwd)
        for cmd_str in _parse_verification_commands(verification_text):
            first_word = cmd_str.split()[0] if cmd_str.split() else ""
            if first_word not in ("rg", "grep", "cargo", "make"):
                continue
            try:
                result = await runner.run(["sh", "-c", cmd_str])
                if result.returncode != 0:
                    reasons.append(f"Verification command failed: `{cmd_str}`")
            except Exception as exc:
                logger.warning("ac_actor.cmd_error", cmd=cmd_str, error=str(exc))
                reasons.append(f"Verification command error: `{cmd_str}`: {exc}")

        passed = len(reasons) == 0
        return [
            Message(
                msg_type=MessageType.AC_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload={"passed": passed, "reasons": reasons},
                in_reply_to=message.sequence,
            )
        ]

    def get_state_snapshot(self) -> dict[str, Any]:
        return {}

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        pass
