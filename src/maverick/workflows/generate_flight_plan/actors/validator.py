"""ValidatorActor — deterministic flight plan validation (V1-V9)."""

from __future__ import annotations

from typing import Any

from maverick.logging import get_logger
from maverick.workflows.fly_beads.actors.protocol import Message, MessageType

logger = get_logger(__name__)


class PlanValidatorActor:
    """Runs V1-V9 validation checks on the flight plan."""

    @property
    def name(self) -> str:
        return "plan_validator"

    async def receive(self, message: Message) -> list[Message]:
        if message.msg_type != MessageType.VALIDATE_PLAN_REQUEST:
            return []

        import tempfile
        from pathlib import Path

        import yaml

        from maverick.flight.validator import validate_flight_plan_file

        payload = message.payload
        flight_plan = payload.get("flight_plan") or {}

        warnings: list[str] = []
        passed = True
        try:
            # Materialise the in-memory plan dict to a temp markdown file
            # so the existing file-based validator can run its V1–V9 checks.
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".md",
                delete=False,
                encoding="utf-8",
            ) as tmp:
                frontmatter = yaml.safe_dump(flight_plan, sort_keys=False)
                tmp.write(f"---\n{frontmatter}---\n")
                tmp_path = Path(tmp.name)
            try:
                issues = validate_flight_plan_file(tmp_path)
                warnings = [f"{i.location}: {i.message}" for i in issues]
            finally:
                tmp_path.unlink(missing_ok=True)
        except Exception as exc:
            warnings = [str(exc)]
            passed = False

        return [
            Message(
                msg_type=MessageType.VALIDATE_PLAN_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload={
                    "passed": passed,
                    "warnings": warnings,
                },
                in_reply_to=message.sequence,
            )
        ]

    def get_state_snapshot(self) -> dict[str, Any]:
        return {}

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        pass
