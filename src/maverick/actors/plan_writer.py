"""PlanWriterActor — Thespian actor for writing flight plan to disk."""

from thespian.actors import Actor


class PlanWriterActor(Actor):
    """Deterministic file writer for flight plan and briefing."""

    def receiveMessage(self, message, sender):
        if not isinstance(message, dict):
            return

        if message.get("type") == "init":
            self._output_dir = message.get("output_dir", "")
            self.send(sender, {"type": "init_ok"})

        elif message.get("type") == "write":
            from pathlib import Path

            output_dir = Path(self._output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            plan_content = message.get("flight_plan_markdown", "")
            briefing_content = message.get("briefing_markdown", "")

            plan_path = output_dir / "flight-plan.md"
            plan_path.write_text(plan_content, encoding="utf-8")

            briefing_path = None
            if briefing_content:
                briefing_path = output_dir / "briefing.md"
                briefing_path.write_text(briefing_content, encoding="utf-8")

            self.send(
                sender,
                {
                    "type": "write_result",
                    "flight_plan_path": str(plan_path),
                    "briefing_path": str(briefing_path) if briefing_path else None,
                },
            )
