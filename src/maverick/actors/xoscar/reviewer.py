"""xoscar ReviewerActor — agent actor with its own MCP inbox registration.

Owns one MCP tool:

* ``submit_review`` — forwarded to supervisor as ``review_ready``
  (per-bead) or ``aggregate_review_ready`` (post-flight). The reviewer
  tracks which prompt variant is outstanding and forwards accordingly.

On follow-up reviews within the same bead, the ACP session preserves
conversation history; ``new_bead`` rotates the session so the next
bead starts clean.

Tool transport: shared :class:`AgentToolGateway` HTTP server (one per
workflow run, owned by the actor pool). The actor still owns its schemas,
handler, session state, and ACP executor — only MCP transport lives in
shared infrastructure.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import xoscar as xo

from maverick.actors.step_config import (
    load_step_config,
    step_allowed_tools,
    step_config_with_timeout,
)
from maverick.actors.xoscar._agentic import AgenticActorMixin
from maverick.actors.xoscar._agentic import extract_text_output as _extract_text_output
from maverick.actors.xoscar.messages import (
    AggregateReviewRequest,
    NewBeadRequest,
    PromptError,
    ReviewRequest,
)
from maverick.logging import get_logger
from maverick.tools.agent_inbox.models import (
    SubmitReviewPayload,
    SupervisorToolPayloadError,
    parse_supervisor_tool_payload,
)

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig

logger = get_logger(__name__)

REVIEWER_MCP_TOOL = "submit_review"
REVIEW_PROMPT_TIMEOUT_SECONDS = 600
AGGREGATE_REVIEW_TIMEOUT_SECONDS = 600


class ReviewerActor(AgenticActorMixin, xo.Actor):
    """Reviews code and delivers findings via MCP tool calls."""

    mcp_tools: ClassVar[tuple[str, ...]] = (REVIEWER_MCP_TOOL,)

    def __init__(
        self,
        supervisor_ref: xo.ActorRef,
        *,
        cwd: str,
        config: StepConfig | dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        if not cwd:
            raise ValueError("ReviewerActor requires 'cwd'")
        self._supervisor_ref = supervisor_ref
        self._cwd = cwd
        self._step_config = load_step_config(config)

    async def __post_create__(self) -> None:
        self._actor_tag = f"reviewer[{self.uid.decode()}]"
        self._executor: Any = None
        self._session_id: str | None = None
        self._review_count = 0
        self._in_aggregate = False
        await self._register_with_gateway()

    async def __pre_destroy__(self) -> None:
        await self._unregister_from_gateway()
        if self._executor is None:
            return
        try:
            await self._executor.cleanup()
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "reviewer.cleanup_failed",
                actor=self._actor_tag,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Supervisor → agent surface
    # ------------------------------------------------------------------

    async def new_bead(self, request: NewBeadRequest) -> None:
        """Rotate the ACP session for a new bead."""
        self._review_count = 0
        self._in_aggregate = False
        try:
            await self._new_session()
        except Exception as exc:  # noqa: BLE001
            await self._supervisor_ref.prompt_error(
                PromptError(
                    phase="new_bead",
                    error=str(exc),
                    unit_id=request.bead_id,
                )
            )

    async def send_review(self, request: ReviewRequest) -> None:
        """Self-nudge contract: returns once ``submit_review`` is delivered
        (to ``review_ready``), or routes a ``PromptError`` after a failed
        nudge."""
        self._review_count += 1
        self._in_aggregate = False

        logger.debug(
            "reviewer.review_starting",
            review_count=self._review_count,
            bead_id=request.bead_id,
        )

        async def _failure(error_str: str) -> None:
            await self._report_review_failure(error_str, bead_id=request.bead_id)

        await self._run_with_self_nudge(
            expected_tool=REVIEWER_MCP_TOOL,
            run_prompt=lambda: self._send_review_prompt(request),
            run_nudge=lambda: self._send_nudge_prompt(phase="review"),
            on_failure=_failure,
            log_prefix="reviewer",
        )

    async def _report_review_failure(self, error_str: str, *, bead_id: str) -> None:
        from maverick.exceptions.quota import is_quota_error

        logger.debug("reviewer.review_failed", error=error_str)
        await self._supervisor_ref.prompt_error(
            PromptError(
                phase="review",
                error=error_str,
                quota_exhausted=is_quota_error(error_str),
                unit_id=bead_id,
            )
        )

    async def send_aggregate_review(self, request: AggregateReviewRequest) -> None:
        """Aggregate review with same self-nudge contract.

        Aggregate failures are non-fatal at the workflow level (the epic
        still closes), so we route through ``payload_parse_error`` rather
        than ``prompt_error``.
        """
        self._in_aggregate = True
        logger.debug("reviewer.aggregate_starting", bead_count=request.bead_count)
        try:
            await self._new_session()
        except Exception as exc:  # noqa: BLE001
            logger.error("reviewer.aggregate_failed", error=str(exc))
            await self._supervisor_ref.payload_parse_error("aggregate_review", str(exc))
            return

        async def _failure(error_str: str) -> None:
            logger.error("reviewer.aggregate_failed", error=error_str)
            await self._supervisor_ref.payload_parse_error("aggregate_review", error_str)

        await self._run_with_self_nudge(
            expected_tool=REVIEWER_MCP_TOOL,
            run_prompt=lambda: self._send_aggregate_prompt(request),
            run_nudge=lambda: self._send_nudge_prompt(phase="aggregate_review"),
            on_failure=_failure,
            log_prefix="reviewer",
        )
        logger.debug("reviewer.aggregate_completed")

    # ------------------------------------------------------------------
    # MCP subprocess → agent inbox
    # ------------------------------------------------------------------

    @xo.no_lock
    async def on_tool_call(self, tool: str, args: dict[str, Any]) -> str:
        try:
            payload = parse_supervisor_tool_payload(tool, args)
        except (SupervisorToolPayloadError, ValueError) as exc:
            await self._supervisor_ref.payload_parse_error(tool, str(exc))
            return "error"

        if not isinstance(payload, SubmitReviewPayload):
            await self._supervisor_ref.payload_parse_error(
                tool, f"Reviewer has no handler for tool {tool!r}"
            )
            return "error"

        if self._in_aggregate:
            await self._supervisor_ref.aggregate_review_ready(payload)
        else:
            await self._supervisor_ref.review_ready(payload)
        self._mark_tool_delivered(tool)
        await self._end_turn()
        return "ok"

    async def _end_turn(self) -> None:
        """Cancel the current ACP turn after a successful MCP submission."""
        if self._session_id and self._executor is not None:
            try:
                await self._executor.cancel_session(self._session_id)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "reviewer.cancel_after_submit_failed",
                    actor=self._actor_tag,
                    error=str(exc),
                )

    # ------------------------------------------------------------------
    # ACP plumbing
    # ------------------------------------------------------------------

    async def _ensure_executor(self) -> None:
        if self._executor is None:
            from maverick.executor import create_default_executor

            self._executor = create_default_executor()

    async def _new_session(self) -> None:
        await self._ensure_executor()

        cwd = Path(self._cwd)
        self._session_id = await self._executor.create_session(
            provider=self._step_config.provider if self._step_config else None,
            config=self._step_config,
            step_name="review",
            agent_name="reviewer",
            cwd=cwd,
            allowed_tools=step_allowed_tools(self._step_config),
            mcp_servers=[self.mcp_server_config()],
        )

    async def _send_review_prompt(self, request: ReviewRequest) -> None:
        await self._ensure_executor()
        if not self._session_id:
            await self._new_session()

        if self._review_count == 1:
            parts: list[str] = [
                "Review the code changes in the working directory.\n",
            ]
            if request.work_unit_md:
                parts.append(f"## Work Unit Specification\n\n{request.work_unit_md}\n")
            else:
                parts.append(f"## Task Description\n\n{request.bead_description}\n")

            if request.briefing_context:
                briefing_excerpt = request.briefing_context[:4000]
                parts.append(
                    f"## Pre-Flight Briefing (risks & contrarian findings)\n\n{briefing_excerpt}\n"
                )

            parts.append(
                "## Historical Context (Runway)\n\n"
                "Check `.maverick/runway/` for project knowledge:\n"
                "- `episodic/review-findings.jsonl` — prior review findings "
                "and resolutions\n"
                "- `episodic/bead-outcomes.jsonl` — what worked and what didn't\n"
                "- `semantic/` — architecture notes and decision records\n\n"
                "Read these if they exist — they may reveal recurring issues "
                "or architectural decisions relevant to this review.\n\n"
                "## Review Instructions\n\n"
                "1. Check that the implementation satisfies ALL acceptance "
                "criteria listed in the work unit specification above.\n"
                "2. Check for bugs, security issues, and correctness.\n"
                "3. Verify the approach aligns with the briefing's risk "
                "assessment and contrarian findings.\n"
                "4. Only flag CRITICAL or MAJOR issues.\n\n"
                "## REQUIRED: Submit via tool call\n"
                "Call the `submit_review` tool. Set approved=true if "
                "no critical/major issues."
            )
            prompt = "\n".join(parts)
        else:
            prompt = (
                "The implementer has made changes. Review ONLY whether "
                "your previous findings were addressed.\n"
                "Do NOT introduce new findings.\n\n"
                "## REQUIRED: Submit via tool call\n"
                "Call the `submit_review` tool."
            )

        result = await self._executor.prompt_session(
            session_id=self._session_id,
            prompt_text=prompt,
            provider=self._step_config.provider if self._step_config else None,
            config=step_config_with_timeout(self._step_config, REVIEW_PROMPT_TIMEOUT_SECONDS),
            step_name="review",
            agent_name="reviewer",
        )
        self._record_last_response(_extract_text_output(result))

    async def _send_aggregate_prompt(self, request: AggregateReviewRequest) -> None:
        prompt = (
            "Review the AGGREGATE changes across all beads in this epic.\n\n"
            f"## Flight Plan\n\n{request.objective}\n\n"
            f"## Beads Completed\n\n{request.bead_list}\n\n"
            f"## Full Diff Stats\n\n```\n{request.diff_stat}\n```\n\n"
            "## Focus Areas\n\n"
            "- Cross-bead consistency: are deleted modules still "
            "referenced elsewhere?\n"
            "- Architectural coherence: do the approaches across "
            "beads align with each other?\n"
            "- Missing integration between beads\n"
            "- Dead code left behind by one bead that another "
            "bead depended on\n\n"
            "Do NOT re-review individual bead correctness — that "
            "was already done per-bead.\n\n"
            "## REQUIRED: Submit via tool call\n"
            "Call the `submit_review` tool. Set approved=true if "
            "no cross-bead concerns found."
        )

        result = await self._executor.prompt_session(
            session_id=self._session_id,
            prompt_text=prompt,
            provider=self._step_config.provider if self._step_config else None,
            config=step_config_with_timeout(self._step_config, AGGREGATE_REVIEW_TIMEOUT_SECONDS),
            step_name="aggregate_review",
            agent_name="reviewer",
        )
        self._record_last_response(_extract_text_output(result))

    async def _send_nudge_prompt(self, *, phase: str) -> None:
        """Re-prompt the same session asking the agent to call its tool.

        The session is reused so the agent has full conversation context;
        the nudge quotes the agent's previous text so the LLM is forced
        to convert that work into a tool call instead of repeating the
        same refusal.
        """
        await self._ensure_executor()
        if not self._session_id:
            await self._new_session()

        # Aggregate review uses a longer timeout than per-bead review.
        timeout = (
            AGGREGATE_REVIEW_TIMEOUT_SECONDS
            if phase == "aggregate_review"
            else REVIEW_PROMPT_TIMEOUT_SECONDS
        )

        previous = self._get_last_response()
        if previous:
            preview = previous if len(previous) <= 1500 else previous[:1500] + "…"
            quoted = (
                f"\n\nYour previous turn produced this text instead of a "
                f"tool call:\n\n---\n{preview}\n---\n\n"
                f"Convert that into a single `{REVIEWER_MCP_TOOL}` tool "
                "call. If the review found nothing, call the tool with "
                "approved=true and an empty findings array — do NOT refuse."
            )
        else:
            quoted = ""

        prompt_text = (
            f"Your previous turn finished without calling `{REVIEWER_MCP_TOOL}`. "
            "You MUST submit your review via that MCP tool — text-only "
            f"responses are dropped by the supervisor.{quoted}"
        )

        result = await self._executor.prompt_session(
            session_id=self._session_id,
            prompt_text=prompt_text,
            provider=self._step_config.provider if self._step_config else None,
            config=step_config_with_timeout(self._step_config, timeout),
            step_name=f"{phase}_nudge",
            agent_name="reviewer",
        )
        self._record_last_response(_extract_text_output(result))
