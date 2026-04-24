"""xoscar BeadCreatorActor — deterministic bead creator.

Creates beads from validated work-unit specs via the ``bd`` CLI. Pure
async Python — no MCP inbox, no ``supervisor_ref``. The supervisor
calls ``create_beads(...)`` via in-pool RPC and awaits the typed
``BeadsCreatedResult``.
"""

from __future__ import annotations

import json

import xoscar as xo

from maverick.actors.xoscar.messages import BeadsCreatedResult, CreateBeadsRequest
from maverick.logging import get_logger

logger = get_logger(__name__)

BEAD_CREATION_TIMEOUT_SECONDS = 300.0


class BeadCreatorActor(xo.Actor):
    """Creates beads from work-unit specs."""

    def __init__(self, plan_name: str = "", plan_objective: str = "") -> None:
        self._plan_name = plan_name
        self._plan_objective = plan_objective

    async def create_beads(self, request: CreateBeadsRequest) -> BeadsCreatedResult:
        from maverick.library.actions.beads import create_beads, wire_dependencies

        specs = list(request.specs)
        extracted_deps = list(request.deps)

        epic_def = {
            "title": self._plan_name,
            "bead_type": "epic",
            "priority": 1,
            "category": "user_story",
            "description": self._plan_objective,
            "task_list": [s.id if hasattr(s, "id") else s.get("id", "") for s in specs],
        }

        work_defs: list[dict[str, object]] = []
        for s in specs:
            sid = s.id if hasattr(s, "id") else s.get("id", "")
            task = s.task if hasattr(s, "task") else s.get("task", "")
            instructions = (
                s.instructions if hasattr(s, "instructions") else s.get("instructions", "")
            )
            work_defs.append(
                {
                    "title": task[:490],
                    "bead_type": "task",
                    "priority": 2,
                    "category": "user_story",
                    "description": (instructions or task)[:500],
                    "user_story_id": sid,
                }
            )

        try:
            creation_result = await create_beads(
                epic_definition=epic_def,
                work_definitions=work_defs,
            )

            dep_result = None
            if extracted_deps:
                dep_result = await wire_dependencies(
                    work_definitions=work_defs,
                    created_map=creation_result.created_map,
                    tasks_content="",
                    extracted_deps=json.dumps(extracted_deps),
                )

            epic = creation_result.epic or {}
            epic_id = (
                epic.get("bd_id", "")
                if isinstance(epic, dict)
                else getattr(epic, "bd_id", "")
            )

            return BeadsCreatedResult(
                success=True,
                epic_id=epic_id,
                bead_count=len(creation_result.work_beads),
                deps_wired=getattr(dep_result, "wired_count", 0) if dep_result else 0,
            )
        except Exception as exc:  # noqa: BLE001 — matches legacy behaviour
            logger.error("bead_creator.error", error=str(exc))
            return BeadsCreatedResult(success=False, error=str(exc))
