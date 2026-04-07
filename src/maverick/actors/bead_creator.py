"""BeadCreatorActor — Thespian actor for creating beads via bd CLI.

Calls async create_beads() and wire_dependencies() via asyncio.run().
"""

import asyncio

from thespian.actors import Actor


class BeadCreatorActor(Actor):
    """Creates beads from work unit specs."""

    def receiveMessage(self, message, sender):
        if not isinstance(message, dict):
            return

        msg_type = message.get("type")

        if msg_type == "init":
            self._plan_name = message.get("plan_name", "")
            self._plan_objective = message.get("plan_objective", "")
            self.send(sender, {"type": "init_ok"})

        elif msg_type == "create_beads":
            try:
                result = asyncio.run(self._create_beads(message))
                self.send(sender, {"type": "beads_created", **result})
            except Exception as exc:
                self.send(sender, {
                    "type": "beads_created",
                    "success": False,
                    "error": str(exc),
                })

    async def _create_beads(self, message):
        from maverick.library.actions.beads import (
            create_beads,
            wire_dependencies,
        )

        specs = message.get("specs", [])
        extracted_deps = message.get("deps", [])

        plan_name = getattr(self, "_plan_name", "")
        plan_objective = getattr(self, "_plan_objective", "")

        epic_def = {
            "title": plan_name,
            "bead_type": "epic",
            "priority": 1,
            "category": "user_story",
            "description": plan_objective,
            "task_list": [
                s.id if hasattr(s, "id") else s.get("id", "")
                for s in specs
            ],
        }

        work_defs = []
        for s in specs:
            sid = s.id if hasattr(s, "id") else s.get("id", "")
            task = s.task if hasattr(s, "task") else s.get("task", "")
            instructions = (
                s.instructions
                if hasattr(s, "instructions")
                else s.get("instructions", "")
            )
            work_defs.append({
                "title": task[:490],
                "bead_type": "task",
                "priority": 2,
                "category": "user_story",
                "description": (instructions or task)[:500],
                "user_story_id": sid,
            })

        creation_result = await create_beads(
            epic_definition=epic_def,
            work_definitions=work_defs,
        )

        dep_result = None
        if extracted_deps:
            import json
            dep_result = await wire_dependencies(
                work_definitions=work_defs,
                created_map=creation_result.get("created_map", {}),
                tasks_content="",  # Not needed for extracted deps
                extracted_deps=json.dumps(extracted_deps),
            )

        return {
            "success": True,
            "epic_id": creation_result.get("epic", {}).get("bd_id", ""),
            "bead_count": len(creation_result.get("work_beads", [])),
            "deps_wired": dep_result.get("wired_count", 0) if dep_result else 0,
        }
