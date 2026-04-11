"""BeadCreatorActor — deterministic bead creation and dependency wiring.

Wraps create_beads() and wire_dependencies() behind the Actor protocol.
No ACP session — pure Python + bd CLI calls.
"""

from __future__ import annotations

from typing import Any

from maverick.logging import get_logger
from maverick.workflows.fly_beads.actors.protocol import (
    Message,
    MessageType,
)

logger = get_logger(__name__)


class BeadCreatorActor:
    """Deterministic actor for creating beads from work unit specs.

    Receives CREATE_BEADS_REQUEST with work unit specs, creates
    epic + task beads via bd, wires dependencies.
    """

    def __init__(
        self,
        *,
        flight_plan_name: str = "",
        flight_plan_objective: str = "",
    ) -> None:
        self._plan_name = flight_plan_name
        self._plan_objective = flight_plan_objective

    @property
    def name(self) -> str:
        return "bead_creator"

    async def receive(self, message: Message) -> list[Message]:
        if message.msg_type != MessageType.CREATE_BEADS_REQUEST:
            logger.warning(
                "bead_creator_actor.unexpected_message",
                msg_type=message.msg_type,
            )
            return []

        payload = message.payload
        specs = payload.get("specs", [])
        extracted_deps = payload.get("extracted_deps", [])

        from maverick.library.actions.beads import (
            create_beads,
            wire_dependencies,
        )

        # Build definitions for create_beads
        epic_def = {
            "title": self._plan_name,
            "description": self._plan_objective,
            "task_list": [s.id if hasattr(s, "id") else s.get("id", "") for s in specs],
        }

        work_defs = []
        for s in specs:
            sid = s.id if hasattr(s, "id") else s.get("id", "")
            task = s.task if hasattr(s, "task") else s.get("task", "")
            instructions = (
                s.instructions if hasattr(s, "instructions") else s.get("instructions", "")
            )  # noqa: E501
            work_defs.append(
                {
                    "title": task[:490],
                    "description": (instructions or task)[:500],
                    "user_story_id": sid,
                }
            )

        try:
            creation_result = await create_beads(
                epic_definition=epic_def,
                work_definitions=work_defs,
            )

            # Wire dependencies
            dep_result = None
            if extracted_deps:
                dep_result = await wire_dependencies(
                    work_definitions=work_defs,
                    created_map=creation_result.created_map,
                    tasks_content=payload.get("tasks_content", ""),
                    extracted_deps=extracted_deps,
                )

            epic = creation_result.epic
            epic_id = (epic.get("bd_id", "") if isinstance(epic, dict) else "") if epic else ""
            return [
                Message(
                    msg_type=MessageType.CREATE_BEADS_RESULT,
                    sender=self.name,
                    recipient="supervisor",
                    payload={
                        "success": True,
                        "epic_id": epic_id,
                        "bead_count": len(creation_result.work_beads),
                        "deps_wired": len(dep_result.dependencies) if dep_result else 0,
                    },
                    in_reply_to=message.sequence,
                )
            ]
        except Exception as exc:
            logger.error("bead_creator_actor.error", error=str(exc))
            return [
                Message(
                    msg_type=MessageType.CREATE_BEADS_RESULT,
                    sender=self.name,
                    recipient="supervisor",
                    payload={
                        "success": False,
                        "error": str(exc),
                    },
                    in_reply_to=message.sequence,
                )
            ]

    def get_state_snapshot(self) -> dict[str, Any]:
        return {}

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        pass
