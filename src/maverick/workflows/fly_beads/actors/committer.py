"""CommitActor — deterministic commit and bead completion.

Wraps jj commit, bead status update, and runway recording behind
the Actor protocol.  No ACP session — pure Python.
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


class CommitActor:
    """Deterministic actor for committing bead work.

    Receives COMMIT_REQUEST, commits via jj, marks bead complete,
    records runway outcome, returns COMMIT_RESULT.
    """

    def __init__(
        self,
        *,
        bead_id: str,
        title: str,
        cwd: Path | None = None,
    ) -> None:
        self._bead_id = bead_id
        self._title = title
        self._cwd = cwd

    @property
    def name(self) -> str:
        return "committer"

    async def receive(self, message: Message) -> list[Message]:
        if message.msg_type != MessageType.COMMIT_REQUEST:
            logger.warning(
                "commit_actor.unexpected_message", msg_type=message.msg_type
            )
            return []

        tag = message.payload.get("tag")

        from maverick.library.actions.beads import mark_bead_complete
        from maverick.library.actions.jj import jj_commit_bead

        commit_message = f"bead({self._bead_id}): {self._title}"
        if tag:
            commit_message = f"bead({self._bead_id}) [{tag}]: {self._title}"

        commit_result = await jj_commit_bead(
            message=commit_message,
            cwd=self._cwd,
        )

        await mark_bead_complete(bead_id=self._bead_id)

        return [
            Message(
                msg_type=MessageType.COMMIT_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload={
                    "success": commit_result.get("success", False),
                    "commit_sha": commit_result.get("change_id"),
                    "tag": tag,
                },
                in_reply_to=message.sequence,
            )
        ]

    def get_state_snapshot(self) -> dict[str, Any]:
        return {}

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        pass
