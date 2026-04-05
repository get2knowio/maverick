"""RefuelSupervisor — message routing for flight plan decomposition.

Routes messages between the DecomposerActor (persistent session),
ValidatorActor (deterministic), and BeadCreatorActor (deterministic).

The supervisor replaces the decompose retry loop in workflow.py.
Instead of throwing away the full decomposition on validation failure,
the decomposer receives a targeted FIX_DECOMPOSE_REQUEST and patches
the specific gaps — saving 10-15 minutes per retry.
"""

from __future__ import annotations

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

#: Maximum fix rounds before giving up.
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

    Flow:
    1. OUTLINE_REQUEST → decomposer
    2. DETAIL_REQUEST → decomposer (same session)
    3. VALIDATE_REQUEST → validator
    4. If gaps: FIX_DECOMPOSE_REQUEST → decomposer → VALIDATE again
    5. CREATE_BEADS_REQUEST → bead creator
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

        # Accumulated decomposition state
        self._outline: dict[str, Any] | None = None
        self._details: dict[str, Any] | None = None
        self._specs: list[Any] = []

    async def process(self) -> RefuelOutcome:
        """Main supervisor loop."""
        t0 = time.monotonic()

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
                    sender=message.sender,
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
            return RefuelOutcome(
                success=False,
                message_log=list(self._message_log),
                fix_rounds=self._fix_rounds,
                duration_seconds=elapsed,
                error=str(exc),
            )

        elapsed = time.monotonic() - t0

        # Extract outcome from last CREATE_BEADS_RESULT
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
        """Routing policy for refuel decomposition."""

        match message.msg_type:

            case MessageType.OUTLINE_RESULT:
                self._outline = message.payload.get("outline")
                # Send all unit IDs for detail filling
                unit_ids = [
                    wu.get("id", "")
                    for wu in (self._outline or {}).get("work_units", [])
                ]
                return [
                    self._make_message(
                        MessageType.DETAIL_REQUEST,
                        sender="supervisor",
                        recipient="decomposer",
                        payload={
                            "unit_ids": unit_ids,
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
                self._details = message.payload.get("details")
                # Merge and validate
                self._specs = self._merge_outline_details()
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
                    # Build deps list from specs
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
                    # Enrich gaps with SC text from flight plan
                    gaps = message.payload.get("gaps", [])
                    enriched_gaps = self._enrich_gaps(gaps)
                    overloaded = message.payload.get("overloaded", [])
                    return [
                        self._make_message(
                            MessageType.FIX_DECOMPOSE_REQUEST,
                            sender="supervisor",
                            recipient="decomposer",
                            payload={
                                "coverage_gaps": enriched_gaps,
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
                    return []  # Stop — workflow will report failure

            case MessageType.FIX_DECOMPOSE_RESULT:
                # Re-merge from patched output and re-validate
                patched = message.payload.get("patched", {})
                if patched:
                    self._details = patched
                    self._specs = self._merge_outline_details()
                return [
                    self._make_message(
                        MessageType.VALIDATE_REQUEST,
                        sender="supervisor",
                        recipient="validator",
                        payload={"specs": self._specs},
                    )
                ]

            case MessageType.CREATE_BEADS_RESULT:
                return []  # Done

        return []

    def _merge_outline_details(self) -> list[Any]:
        """Merge outline work units with detail data into specs."""
        from maverick.library.actions.decompose import (
            merge_outline_and_details,
        )
        from maverick.workflows.refuel_maverick.models import (
            DecompositionOutline,
            DetailBatchOutput,
        )

        if not self._outline or not self._details:
            return []

        try:
            outline = DecompositionOutline.model_validate(self._outline)
            # Details may come as {details: [...]} or as full spec list
            if isinstance(self._details, dict) and "details" in self._details:
                detail_batches = [
                    DetailBatchOutput.model_validate(self._details)
                ]
            elif isinstance(self._details, list):
                detail_batches = [
                    DetailBatchOutput(details=self._details)
                ]
            else:
                detail_batches = []
            return merge_outline_and_details(outline, detail_batches)
        except Exception as exc:
            logger.warning(
                "refuel_supervisor.merge_failed", error=str(exc)
            )
            return []

    def _extract_deps(self) -> list[list[str]]:
        """Extract dependency pairs from specs for wiring."""
        deps: list[list[str]] = []
        for spec in self._specs:
            spec_id = spec.id if hasattr(spec, "id") else spec.get("id", "")
            depends_on = (
                spec.depends_on
                if hasattr(spec, "depends_on")
                else spec.get("depends_on", [])
            )
            for dep_id in depends_on:
                deps.append([spec_id, dep_id])
        return deps

    def _enrich_gaps(self, gaps: list[str]) -> list[str]:
        """Enrich SC gap references with actual text from flight plan."""
        if not self._flight_plan:
            return gaps

        enriched = []
        sc_list = getattr(self._flight_plan, "success_criteria", [])
        sc_map = {}
        for i, sc in enumerate(sc_list):
            ref = getattr(sc, "ref", None) or f"SC-{i+1:03d}"
            text = getattr(sc, "text", str(sc))
            sc_map[ref] = text

        for gap in gaps:
            # Gap might be "SC-015 not explicitly covered..."
            for ref, text in sc_map.items():
                if ref in gap:
                    gap = f"{gap} — Full text: {text}"
                    break
            enriched.append(gap)
        return enriched

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
