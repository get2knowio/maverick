"""RefuelSupervisor — message routing for flight plan decomposition.

Routes messages between the DecomposerActor (persistent session with
MCP tools), ValidatorActor (deterministic), and BeadCreatorActor.

The decomposer delivers structured results via MCP tool calls —
the schema is enforced by the protocol, so no coercion layer is
needed. The supervisor reads tool call data directly.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from maverick.logging import get_logger
from maverick.workflows.fly_beads.actors.protocol import (
    Actor,
    Message,
    MessageType,
)

logger = get_logger(__name__)

MAX_FIX_ROUNDS = 3


@dataclass
class RefuelOutcome:
    """Result of processing decomposition through the supervisor."""

    success: bool = False
    specs: list[Any] = field(default_factory=list)
    epic_id: str = ""
    bead_count: int = 0
    fix_rounds: int = 0
    message_log: list[Message] = field(default_factory=list)
    duration_seconds: float = 0.0
    error: str | None = None


class RefuelSupervisor:
    """Routes messages between decomposer, validator, and bead creator.

    The decomposer sends structured data via MCP tool calls.
    The supervisor reads it directly — no JSON extraction, no coercion.
    """

    def __init__(
        self,
        *,
        actors: dict[str, Actor],
        initial_payload: dict[str, Any],
        flight_plan: Any = None,
    ) -> None:
        self._actors = actors
        self._initial_payload = initial_payload
        self._flight_plan = flight_plan
        self._message_log: list[Message] = []
        self._sequence: int = 0
        self._fix_rounds: int = 0

        # Accumulated state from tool calls
        self._outline_data: dict[str, Any] | None = None
        self._detail_data: dict[str, Any] | None = None
        self._specs: list[Any] = []

        # Thespian actor system for inbox
        self._actor_system: Any = None
        self._inbox_addr: Any = None

    def _start_actor_system(self) -> None:
        """Start Thespian ActorSystem and create inbox actor."""
        from thespian.actors import ActorSystem

        from maverick.actors.inbox import InboxActor

        self._actor_system = ActorSystem(
            "multiprocTCPBase", transientUnique=True
        )
        self._inbox_addr = self._actor_system.createActor(
            InboxActor, globalName="supervisor-inbox"
        )
        logger.info("refuel_supervisor.actor_system_started")

    def _stop_actor_system(self) -> None:
        """Shutdown Thespian ActorSystem cleanly."""
        if self._actor_system is not None:
            try:
                self._actor_system.shutdown()
                logger.info("refuel_supervisor.actor_system_stopped")
            except Exception as exc:
                logger.warning(
                    "refuel_supervisor.actor_system_shutdown_error",
                    error=str(exc),
                )
            self._actor_system = None
            self._inbox_addr = None

    async def read_inbox(self, timeout: float = 60.0) -> dict[str, Any] | None:
        """Read the latest message from the Thespian inbox actor.

        Wraps the blocking ask() in run_in_executor for async compat.
        """
        import asyncio

        if self._actor_system is None or self._inbox_addr is None:
            return None

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._actor_system.ask(
                self._inbox_addr, "get_latest", timeout=timeout
            ),
        )
        return result

    async def process(self) -> RefuelOutcome:
        """Main supervisor loop."""
        t0 = time.monotonic()

        self._start_actor_system()

        pending: list[Message] = [
            self._make_message(
                MessageType.OUTLINE_REQUEST,
                sender="supervisor",
                recipient="decomposer",
                payload=self._initial_payload,
            )
        ]

        try:
            while pending:
                message = pending.pop(0)
                self._message_log.append(message)

                actor = self._actors.get(message.recipient)
                if actor is None:
                    logger.error(
                        "refuel_supervisor.unknown_recipient",
                        recipient=message.recipient,
                    )
                    continue

                logger.debug(
                    "refuel_supervisor.deliver",
                    msg_type=message.msg_type.value,
                    recipient=message.recipient,
                )

                responses = await actor.receive(message)

                for response in responses:
                    response = self._stamp(response)
                    self._message_log.append(response)
                    routed = self._route(response)
                    pending.extend(routed)

        except Exception as exc:
            logger.error("refuel_supervisor.error", error=str(exc))
            elapsed = time.monotonic() - t0
            self._stop_actor_system()
            return RefuelOutcome(
                success=False,
                message_log=list(self._message_log),
                fix_rounds=self._fix_rounds,
                duration_seconds=elapsed,
                error=str(exc),
            )

        self._stop_actor_system()
        elapsed = time.monotonic() - t0

        create_result = self._find_last(MessageType.CREATE_BEADS_RESULT)
        success = (
            create_result is not None
            and create_result.payload.get("success", False)
        )

        return RefuelOutcome(
            success=success,
            specs=self._specs,
            epic_id=(
                create_result.payload.get("epic_id", "")
                if create_result
                else ""
            ),
            bead_count=(
                create_result.payload.get("bead_count", 0)
                if create_result
                else 0
            ),
            fix_rounds=self._fix_rounds,
            message_log=list(self._message_log),
            duration_seconds=elapsed,
        )

    def _route(self, message: Message) -> list[Message]:
        """Routing policy."""

        match message.msg_type:

            case MessageType.OUTLINE_RESULT:
                # Data came directly from MCP tool call — already structured
                self._outline_data = message.payload
                work_units = message.payload.get("work_units", [])
                unit_ids = [
                    wu.get("id", "") for wu in work_units
                    if isinstance(wu, dict)
                ]

                outline_json = json.dumps(self._outline_data)

                return [
                    self._make_message(
                        MessageType.DETAIL_REQUEST,
                        sender="supervisor",
                        recipient="decomposer",
                        payload={
                            "unit_ids": unit_ids,
                            "outline_json": outline_json,
                            "flight_plan_content": self._initial_payload.get(
                                "flight_plan_content", ""
                            ),
                            "verification_properties": self._initial_payload.get(
                                "verification_properties", ""
                            ),
                        },
                    )
                ]

            case MessageType.DETAIL_RESULT:
                self._detail_data = message.payload
                self._specs = self._merge_to_specs()

                return [
                    self._make_message(
                        MessageType.VALIDATE_REQUEST,
                        sender="supervisor",
                        recipient="validator",
                        payload={"specs": self._specs},
                    )
                ]

            case MessageType.VALIDATE_RESULT:
                passed = message.payload.get("passed", False)
                if passed:
                    extracted_deps = self._extract_deps()
                    return [
                        self._make_message(
                            MessageType.CREATE_BEADS_REQUEST,
                            sender="supervisor",
                            recipient="bead_creator",
                            payload={
                                "specs": self._specs,
                                "extracted_deps": extracted_deps,
                            },
                        )
                    ]
                elif self._fix_rounds < MAX_FIX_ROUNDS:
                    self._fix_rounds += 1
                    gaps = message.payload.get("gaps", [])
                    enriched = self._enrich_gaps(gaps)
                    overloaded = message.payload.get("overloaded", [])
                    return [
                        self._make_message(
                            MessageType.FIX_DECOMPOSE_REQUEST,
                            sender="supervisor",
                            recipient="decomposer",
                            payload={
                                "coverage_gaps": enriched,
                                "overloaded": overloaded,
                            },
                        )
                    ]
                else:
                    logger.error(
                        "refuel_supervisor.validation_exhausted",
                        rounds=self._fix_rounds,
                        gaps=message.payload.get("gaps"),
                    )
                    return []

            case MessageType.FIX_DECOMPOSE_RESULT:
                # Fix provides updated work_units + details
                fix_data = message.payload
                if fix_data.get("work_units") or fix_data.get("details"):
                    if fix_data.get("work_units"):
                        self._outline_data = {
                            "work_units": fix_data["work_units"]
                        }
                    if fix_data.get("details"):
                        self._detail_data = {
                            "details": fix_data["details"]
                        }
                    self._specs = self._merge_to_specs()
                    return [
                        self._make_message(
                            MessageType.VALIDATE_REQUEST,
                            sender="supervisor",
                            recipient="validator",
                            payload={"specs": self._specs},
                        )
                    ]
                else:
                    # Agent didn't call the submit_fix tool — empty payload.
                    # Don't retry with the same specs (would loop forever).
                    # Proceed to bead creation with what we have.
                    logger.warning(
                        "refuel_supervisor.fix_empty_payload",
                        round=self._fix_rounds,
                        msg="Agent did not call submit_fix tool; "
                        "proceeding with existing specs",
                    )
                    extracted_deps = self._extract_deps()
                    return [
                        self._make_message(
                            MessageType.CREATE_BEADS_REQUEST,
                            sender="supervisor",
                            recipient="bead_creator",
                            payload={
                                "specs": self._specs,
                                "extracted_deps": extracted_deps,
                            },
                        )
                    ]

            case MessageType.CREATE_BEADS_RESULT:
                return []

        return []

    # ------------------------------------------------------------------
    # Spec construction — simple merge, no coercion needed
    # ------------------------------------------------------------------

    def _merge_to_specs(self) -> list[Any]:
        """Merge outline work_units with detail entries into specs.

        Since the data came from MCP tool calls with enforced schemas,
        we just need to combine outline skeletons with detail entries
        by matching on ID. No coercion or type fixing needed.
        """
        from maverick.workflows.refuel_maverick.models import (
            WorkUnitSpec,
        )

        work_units = (
            self._outline_data.get("work_units", [])
            if self._outline_data
            else []
        )
        details = (
            self._detail_data.get("details", [])
            if self._detail_data
            else []
        )

        # Index details by ID
        detail_map: dict[str, dict[str, Any]] = {}
        for d in details:
            if isinstance(d, dict):
                detail_map[d.get("id", "")] = d

        specs: list[Any] = []
        for wu in work_units:
            if not isinstance(wu, dict):
                continue

            wu_id = wu.get("id", "")
            detail = detail_map.get(wu_id, {})

            # Merge: outline fields + detail fields
            merged = {
                "id": wu_id,
                "task": wu.get("task", ""),
                "sequence": wu.get("sequence", 0),
                "parallel_group": wu.get("parallel_group"),
                "depends_on": wu.get("depends_on", []),
                "file_scope": wu.get("file_scope", {}),
                "instructions": detail.get("instructions", ""),
                "acceptance_criteria": detail.get(
                    "acceptance_criteria", []
                ),
                "verification": detail.get("verification", []),
                "test_specification": detail.get(
                    "test_specification", ""
                ),
            }

            try:
                specs.append(WorkUnitSpec.model_validate(merged))
            except Exception as exc:
                logger.warning(
                    "refuel_supervisor.spec_validation_failed",
                    wu_id=wu_id,
                    error=str(exc),
                )
                # Include as dict for validation to report on
                specs.append(merged)

        return specs

    def _extract_deps(self) -> list[list[str]]:
        """Extract dependency pairs from specs."""
        deps: list[list[str]] = []
        for spec in self._specs:
            sid = spec.id if hasattr(spec, "id") else spec.get("id", "")
            dep_list = (
                spec.depends_on
                if hasattr(spec, "depends_on")
                else spec.get("depends_on", [])
            )
            for dep_id in dep_list:
                deps.append([sid, dep_id])
        return deps

    def _enrich_gaps(self, gaps: list[str]) -> list[str]:
        """Enrich SC gap references with text from flight plan."""
        if not self._flight_plan:
            return gaps

        sc_list = getattr(self._flight_plan, "success_criteria", [])
        sc_map = {}
        for i, sc in enumerate(sc_list):
            ref = getattr(sc, "ref", None) or f"SC-{i+1:03d}"
            text = getattr(sc, "text", str(sc))
            sc_map[ref] = text

        enriched = []
        for gap in gaps:
            for ref, text in sc_map.items():
                if ref in gap:
                    gap = f"{gap} — Full text: {text}"
                    break
            enriched.append(gap)
        return enriched

    # ------------------------------------------------------------------
    # Message helpers
    # ------------------------------------------------------------------

    def _make_message(
        self,
        msg_type: MessageType,
        *,
        sender: str,
        recipient: str,
        payload: dict[str, Any] | None = None,
        in_reply_to: int | None = None,
    ) -> Message:
        self._sequence += 1
        return Message(
            msg_type=msg_type,
            sender=sender,
            recipient=recipient,
            payload=payload or {},
            sequence=self._sequence,
            in_reply_to=in_reply_to,
        )

    def _stamp(self, message: Message) -> Message:
        self._sequence += 1
        return Message(
            msg_type=message.msg_type,
            sender=message.sender,
            recipient=message.recipient,
            payload=message.payload,
            sequence=self._sequence,
            in_reply_to=message.in_reply_to,
        )

    def _find_last(self, msg_type: MessageType) -> Message | None:
        for msg in reversed(self._message_log):
            if msg.msg_type == msg_type:
                return msg
        return None
