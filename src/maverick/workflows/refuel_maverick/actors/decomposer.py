"""DecomposerActor — persistent-session actor for flight plan decomposition.

Handles outline generation, detail filling, and targeted fix requests
in a single ACP session. The session persists across all three phases
so the decomposer remembers the full context when patching gaps.
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


class DecomposerActor:
    """Agent actor that decomposes a flight plan into work units.

    Handles:
    - OUTLINE_REQUEST: Produce work unit skeleton (turn 1)
    - DETAIL_REQUEST: Fill in procedures, AC, verification (turn 2)
    - FIX_DECOMPOSE_REQUEST: Patch specific gaps/overloads (turn 3+)

    All turns happen on the same persistent ACP session.
    """

    def __init__(
        self,
        *,
        session_registry: BeadSessionRegistry,
        executor: Any,  # AcpStepExecutor
        cwd: Path | None = None,
        outline_config: StepConfig | None = None,
        detail_config: StepConfig | None = None,
        output_dir: Path | None = None,
    ) -> None:
        self._registry = session_registry
        self._executor = executor
        self._cwd = cwd
        self._outline_config = outline_config
        self._detail_config = detail_config
        self._output_dir = output_dir
        self._turns: int = 0
        self._outline_json: str | None = None

    @property
    def name(self) -> str:
        return "decomposer"

    async def receive(self, message: Message) -> list[Message]:
        match message.msg_type:
            case MessageType.OUTLINE_REQUEST:
                return await self._handle_outline(message)
            case MessageType.DETAIL_REQUEST:
                return await self._handle_detail(message)
            case MessageType.FIX_DECOMPOSE_REQUEST:
                return await self._handle_fix(message)
            case _:
                logger.warning(
                    "decomposer_actor.unexpected_message",
                    msg_type=message.msg_type,
                )
                return []

    async def _handle_outline(self, message: Message) -> list[Message]:
        """Generate the work unit outline (turn 1)."""
        from maverick.library.actions.decompose import build_outline_prompt
        from maverick.workflows.refuel_maverick.models import (
            DecompositionOutline,
        )

        payload = message.payload
        prompt_text = build_outline_prompt(
            flight_plan_content=payload["flight_plan_content"],
            success_criteria_refs=payload.get("success_criteria_refs", []),
            codebase_context=payload.get("codebase_context", ""),
            briefing=payload.get("briefing", ""),
            validation_feedback=payload.get("validation_feedback", ""),
        )

        session_id = await self._registry.get_or_create(
            self.name,
            self._executor,
            cwd=self._cwd,
            config=self._outline_config,
        )

        result = await self._executor.prompt_session(
            session_id=session_id,
            prompt_text=prompt_text,
            provider=self._registry.get_provider(self.name),
            config=self._outline_config,
            step_name="decompose_outline",
            agent_name="decomposer",
            output_schema=DecompositionOutline,
        )
        self._turns += 1

        # Cache the outline JSON for detail prompt building
        output = result.output
        if isinstance(output, DecompositionOutline):
            self._outline_json = output.model_dump_json()
            outline_data = output.model_dump()
        elif isinstance(output, str):
            self._outline_json = output
            outline_data = json.loads(output)
        else:
            self._outline_json = json.dumps(output)
            outline_data = output

        return [
            Message(
                msg_type=MessageType.OUTLINE_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload={
                    "outline": outline_data,
                    "outline_json": self._outline_json,
                    "unit_count": len(outline_data.get("work_units", [])),
                },
                in_reply_to=message.sequence,
            )
        ]

    async def _handle_detail(self, message: Message) -> list[Message]:
        """Fill in details for all work units (turn 2)."""
        from maverick.library.actions.decompose import build_detail_prompt

        payload = message.payload
        unit_ids = payload["unit_ids"]

        # Build output file path
        output_file = None
        if self._output_dir:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            output_file = self._output_dir / "detail-all.json"
            output_file.unlink(missing_ok=True)

        prompt_text = build_detail_prompt(
            flight_plan_content=payload.get("flight_plan_content", ""),
            outline_json=self._outline_json or "{}",
            unit_ids=unit_ids,
            output_file_path=str(output_file) if output_file else None,
            verification_properties=payload.get(
                "verification_properties", ""
            ),
        )

        session_id = self._registry.get_session(self.name)
        if not session_id:
            session_id = await self._registry.get_or_create(
                self.name,
                self._executor,
                cwd=self._cwd,
                config=self._detail_config,
            )

        result = await self._executor.prompt_session(
            session_id=session_id,
            prompt_text=prompt_text,
            provider=self._registry.get_provider(self.name),
            config=self._detail_config,
            step_name="decompose_detail",
            agent_name="decomposer",
        )
        self._turns += 1

        # Read from file if written, otherwise parse from text
        detail_data: dict[str, Any] | None = None
        if output_file and output_file.exists():
            try:
                detail_data = json.loads(
                    output_file.read_text(encoding="utf-8")
                )
                logger.info(
                    "decomposer_actor.detail_from_file",
                    path=str(output_file),
                )
            except Exception as exc:
                logger.warning(
                    "decomposer_actor.detail_file_parse_failed",
                    error=str(exc),
                )

        if detail_data is None:
            # Try parsing from text output
            text = result.output if isinstance(result.output, str) else ""
            from maverick.agents.contracts import validate_output

            from maverick.workflows.refuel_maverick.models import (
                DetailBatchOutput,
            )

            parsed = validate_output(text, DetailBatchOutput, strict=False)
            if parsed is not None:
                detail_data = parsed.model_dump()
            else:
                detail_data = {"details": []}

        return [
            Message(
                msg_type=MessageType.DETAIL_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload={
                    "details": detail_data,
                    "detail_count": len(
                        detail_data.get("details", [])
                    ),
                },
                in_reply_to=message.sequence,
            )
        ]

    async def _handle_fix(self, message: Message) -> list[Message]:
        """Patch specific validation gaps (turn 3+)."""
        payload = message.payload

        parts: list[str] = [
            "Your previous decomposition had validation issues. "
            "Fix ONLY the specific problems listed below — do not "
            "regenerate everything.\n"
        ]

        if payload.get("coverage_gaps"):
            parts.append("## Missing SC Coverage\n")
            for gap in payload["coverage_gaps"]:
                parts.append(f"- {gap}")
            parts.append(
                "\nAssign each missing SC to an existing work unit's "
                "acceptance_criteria, or create a minimal new work unit."
            )

        if payload.get("overloaded"):
            parts.append("\n## Overloaded Work Units\n")
            for item in payload["overloaded"]:
                parts.append(f"- {item}")
            parts.append(
                "\nSplit overloaded units into smaller pieces with "
                "depends_on links."
            )

        # Output the complete patched decomposition as JSON
        output_file = None
        if self._output_dir:
            output_file = self._output_dir / "detail-fix.json"
            output_file.unlink(missing_ok=True)

        parts.append(
            "\n## Output\n"
            "Write the COMPLETE updated decomposition (all work units "
            "with full details) as JSON"
        )
        if output_file:
            parts.append(f" to the file: {output_file}")
        parts.append(
            ".\nUse the same schema as before: "
            '{"work_units": [...], "details": [...]}'
        )

        prompt_text = "\n".join(parts)

        session_id = self._registry.get_session(self.name)
        if not session_id:
            session_id = await self._registry.get_or_create(
                self.name,
                self._executor,
                cwd=self._cwd,
                config=self._detail_config,
            )

        result = await self._executor.prompt_session(
            session_id=session_id,
            prompt_text=prompt_text,
            provider=self._registry.get_provider(self.name),
            config=self._detail_config,
            step_name="decompose_fix",
            agent_name="decomposer",
        )
        self._turns += 1

        # Read patched output
        fix_data: dict[str, Any] | None = None
        if output_file and output_file.exists():
            try:
                fix_data = json.loads(
                    output_file.read_text(encoding="utf-8")
                )
            except Exception:
                pass

        if fix_data is None:
            text = result.output if isinstance(result.output, str) else ""
            try:
                fix_data = json.loads(text)
            except Exception:
                fix_data = {}

        return [
            Message(
                msg_type=MessageType.FIX_DECOMPOSE_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload={"patched": fix_data},
                in_reply_to=message.sequence,
            )
        ]

    def get_state_snapshot(self) -> dict[str, Any]:
        return {
            "turns": self._turns,
            "has_outline": self._outline_json is not None,
        }

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        self._turns = snapshot.get("turns", 0)
