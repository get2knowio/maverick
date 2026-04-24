"""xoscar DecomposerActor — agent actor with its own MCP inbox.

Two method groups, matching Design Decision #3 in the migration plan:

* **Supervisor → agent (ACP kickoff):** ``set_context``, ``send_outline``,
  ``send_detail``, ``send_fix``, ``send_nudge``. Each prompts the agent's
  ACP session and returns when the prompt completes. Results flow back
  to the supervisor via this actor's own MCP inbox — **not** via the
  return value of these methods.

* **MCP subprocess → agent (this actor's inbox):** ``on_tool_call``
  parses the tools this actor owns (``submit_outline``, ``submit_details``,
  ``submit_fix``) into ``SupervisorInboxPayload`` objects and forwards
  them to the supervisor via typed in-pool RPC
  (``await self._supervisor_ref.outline_ready(payload)``).

Two roles:

* ``primary`` — outline + detail + fix; owns all three tools.
* ``pool`` — detail-only worker; owns ``submit_details`` only.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import xoscar as xo
from acp.schema import McpServerStdio

from maverick.actors.step_config import load_step_config, step_config_with_timeout
from maverick.actors.xoscar.messages import (
    DecomposerContext,
    DetailRequest,
    FixRequest,
    NudgeRequest,
    OutlineRequest,
    PromptError,
)
from maverick.agents.tools import PLANNER_TOOLS
from maverick.logging import get_logger
from maverick.tools.agent_inbox.models import (
    SubmitDetailsPayload,
    SubmitFixPayload,
    SubmitOutlinePayload,
    SupervisorToolPayloadError,
    parse_supervisor_tool_payload,
)

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig

logger = get_logger(__name__)

READ_ONLY_DECOMPOSER_TOOLS: tuple[str, ...] = tuple(sorted(PLANNER_TOOLS))
PRIMARY_DECOMPOSER_MCP_TOOLS: tuple[str, ...] = (
    "submit_outline",
    "submit_details",
    "submit_fix",
)
POOL_DECOMPOSER_MCP_TOOLS: tuple[str, ...] = ("submit_details",)

DETAIL_TIMEOUT_SECONDS = 1200
DEFAULT_PROMPT_TIMEOUT_SECONDS = 1800


class DecomposerActor(xo.Actor):
    """Sends ACP prompts for decomposition phases and owns its MCP inbox."""

    def __init__(
        self,
        supervisor_ref: xo.ActorRef,
        *,
        cwd: str,
        config: StepConfig | dict[str, Any] | None = None,
        role: str = "primary",
        detail_session_max_turns: int = 5,
        fix_session_max_turns: int = 1,
    ) -> None:
        if not cwd:
            raise ValueError("DecomposerActor requires 'cwd'")
        self._supervisor_ref = supervisor_ref
        self._cwd = cwd
        self._step_config = load_step_config(config)
        self._role = role
        self._detail_session_max_turns = max(1, int(detail_session_max_turns))
        self._fix_session_max_turns = max(1, int(fix_session_max_turns))

        if role == "pool":
            self._mcp_tool_names = POOL_DECOMPOSER_MCP_TOOLS
        else:
            self._mcp_tool_names = PRIMARY_DECOMPOSER_MCP_TOOLS
        self._mcp_tools_csv = ",".join(self._mcp_tool_names)

    async def __post_create__(self) -> None:
        self._actor_tag = f"decomposer[{self._role}:{self.uid}]"
        self._executor: Any = None
        self._session_id: str | None = None
        self._session_mode: str | None = None
        self._session_turns_in_mode = 0

        # Bulk context broadcast once per detail phase — keeps per-unit
        # detail_request messages tiny.
        self._detail_outline_json: str = "{}"
        self._detail_flight_plan: str = ""
        self._detail_verification: str = ""
        self._detail_seed_stale = True

        self._fix_outline_json: str = '{"work_units": []}'
        self._fix_details_json: str = '{"details": []}'
        self._fix_verification: str = ""
        self._fix_seed_stale = True

    async def __pre_destroy__(self) -> None:
        """Kill the ACP subprocess on teardown.

        Matches the ``_cleanup_executor`` call that the Thespian actor
        performed on shutdown messages. Best-effort: log and swallow.
        """

        if self._executor is None:
            return
        try:
            await self._executor.cleanup()
        except Exception as exc:  # noqa: BLE001 — teardown must not raise
            logger.debug(
                "decomposer.cleanup_failed",
                actor=self._actor_tag,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Supervisor → agent surface
    # ------------------------------------------------------------------

    async def set_context(self, context: DecomposerContext) -> None:
        """Broadcast context for the upcoming detail phase."""
        self._detail_outline_json = context.outline_json
        self._detail_flight_plan = context.flight_plan_content
        self._detail_verification = context.verification_properties
        self._detail_seed_stale = True

    async def send_outline(self, request: OutlineRequest) -> None:
        """Send the outline prompt. Result arrives via on_tool_call."""
        await self._run_prompt(self._send_outline_prompt(request), phase="outline")

    async def send_detail(self, request: DetailRequest) -> None:
        """Send a detail prompt for one work unit. Result arrives via
        on_tool_call."""
        unit_id = request.unit_ids[0] if request.unit_ids else None
        await self._run_prompt(
            self._send_detail_prompt(request),
            phase="detail",
            unit_id=unit_id,
        )

    async def send_fix(self, request: FixRequest) -> None:
        """Send a fix prompt with updated coverage gaps / overloaded units."""
        self._fix_outline_json = request.outline_json or self._fix_outline_json
        self._fix_details_json = request.details_json or self._fix_details_json
        self._fix_verification = request.verification_properties or self._fix_verification
        self._fix_seed_stale = True
        await self._run_prompt(self._send_fix_prompt(request), phase="fix")

    async def send_nudge(self, request: NudgeRequest) -> None:
        """Re-prompt when a previous turn didn't call the expected tool."""
        await self._run_prompt(
            self._send_nudge_prompt(request),
            phase="nudge",
            unit_id=request.unit_id,
        )

    async def _run_prompt(
        self,
        coro: Any,
        *,
        phase: str,
        unit_id: str | None = None,
    ) -> None:
        """Run an ACP-driving coroutine and translate exceptions into
        ``PromptError`` messages on the supervisor's ref.

        The supervisor fans these out concurrently via ``asyncio.gather``
        or a task pool. This method blocks only until the underlying
        ``prompt_session`` call completes — the structured result lands
        on the supervisor through the MCP inbox path during that time.
        """
        from maverick.exceptions.quota import is_quota_error

        logger.debug("decomposer.phase_starting", phase=phase, unit_id=unit_id)
        try:
            await coro
            logger.debug("decomposer.phase_completed", phase=phase, unit_id=unit_id)
        except Exception as exc:  # noqa: BLE001 — route all errors to the supervisor
            error_str = str(exc)
            quota = is_quota_error(error_str)
            logger.debug(
                "decomposer.phase_failed",
                phase=phase,
                unit_id=unit_id,
                error=error_str,
            )
            await self._supervisor_ref.prompt_error(
                PromptError(
                    phase=phase,
                    error=error_str,
                    quota_exhausted=quota,
                    unit_id=unit_id,
                )
            )

    # ------------------------------------------------------------------
    # MCP subprocess → agent inbox
    # ------------------------------------------------------------------

    async def on_tool_call(self, tool: str, args: dict[str, Any]) -> str:
        """Parse an MCP tool call and forward the typed result to the
        supervisor via in-pool RPC.

        Only handles tools this agent owns (primary: outline/details/fix;
        pool: details). Unknown tools are reported to the supervisor as
        a payload error so it can surface the misrouted call in the CLI.
        """
        try:
            payload = parse_supervisor_tool_payload(tool, args)
        except (SupervisorToolPayloadError, ValueError) as exc:
            await self._supervisor_ref.payload_parse_error(tool, str(exc))
            return "error"

        if isinstance(payload, SubmitOutlinePayload):
            await self._supervisor_ref.outline_ready(payload)
        elif isinstance(payload, SubmitDetailsPayload):
            await self._supervisor_ref.detail_ready(payload)
        elif isinstance(payload, SubmitFixPayload):
            await self._supervisor_ref.fix_ready(payload)
        else:
            # Defensive: a tool name this agent advertises but this
            # module didn't branch on. Tell the supervisor so the
            # misconfiguration surfaces instead of being silently dropped.
            await self._supervisor_ref.payload_parse_error(
                tool, f"Decomposer has no handler for tool {tool!r}"
            )
            return "error"
        return "ok"

    # ------------------------------------------------------------------
    # ACP session plumbing (internal)
    # ------------------------------------------------------------------

    async def _ensure_executor(self) -> None:
        if self._executor is not None:
            return
        from maverick.executor import create_default_executor

        logger.info(
            "decomposer.acp_connection_new",
            actor=self._actor_tag,
            role=self._role,
        )
        self._executor = create_default_executor()

    async def _create_session(self) -> None:
        await self._ensure_executor()

        maverick_bin = shutil.which("maverick") or str(Path(sys.executable).parent / "maverick")
        mcp_config = McpServerStdio(
            name="agent-inbox",
            command=maverick_bin,
            args=[
                "serve-inbox",
                "--tools",
                self._mcp_tools_csv,
                "--inbox-address",
                self.address,
                "--inbox-uid",
                self.uid,
            ],
            env=[],
        )

        cwd = Path(self._cwd)
        one_shot: list[str] | None = ["submit_outline"] if self._role == "primary" else None
        allowed_tools = [*READ_ONLY_DECOMPOSER_TOOLS, *self._mcp_tool_names]

        self._session_id = await self._executor.create_session(
            provider=self._step_config.provider if self._step_config else None,
            config=self._step_config,
            step_name="decompose",
            agent_name="decomposer",
            cwd=cwd,
            allowed_tools=allowed_tools,
            mcp_servers=[mcp_config],
            one_shot_tools=one_shot,
        )

    async def _ensure_mode_session(
        self,
        mode: str,
        *,
        max_turns: int,
        seed_stale: bool,
    ) -> bool:
        """Ensure a seeded-session mode has a usable ACP session.

        Returns ``True`` when a new session was created and the next
        prompt should include the large seed context.
        """
        previous_session = self._session_id
        previous_mode = self._session_mode
        previous_turns = self._session_turns_in_mode

        if not previous_session:
            reason = "initial"
        elif previous_mode != mode:
            reason = "mode_change"
        elif previous_turns >= max(1, max_turns):
            reason = "turn_limit"
        elif seed_stale:
            reason = "seed_stale"
        else:
            return False

        if previous_session:
            logger.info(
                "decomposer.session_rotated",
                actor=self._actor_tag,
                role=self._role,
                mode=mode,
                reason=reason,
                previous_session=previous_session,
                previous_mode=previous_mode,
                previous_turns=previous_turns,
                max_turns=max_turns,
            )

        await self._create_session()
        self._session_mode = mode
        self._session_turns_in_mode = 0
        logger.info(
            "decomposer.session_created",
            actor=self._actor_tag,
            role=self._role,
            mode=mode,
            reason=reason,
            session_id=self._session_id,
            max_turns=max_turns,
        )
        return True

    async def _ensure_agent(self) -> None:
        if self._session_id:
            return
        await self._create_session()

    async def _mark_turn_completed(self, mode: str) -> None:
        if self._session_mode == mode:
            self._session_turns_in_mode += 1

    async def _prompt(
        self,
        prompt_text: str,
        step_name: str = "decompose",
        *,
        timeout_seconds: int = DEFAULT_PROMPT_TIMEOUT_SECONDS,
    ) -> None:
        await self._ensure_agent()
        await self._executor.prompt_session(
            session_id=self._session_id,
            prompt_text=prompt_text,
            provider=self._step_config.provider if self._step_config else None,
            config=step_config_with_timeout(self._step_config, timeout_seconds),
            step_name=step_name,
            agent_name="decomposer",
        )

    # ------------------------------------------------------------------
    # Prompt builders (mirror the Thespian implementation)
    # ------------------------------------------------------------------

    async def _send_outline_prompt(self, request: OutlineRequest) -> None:
        from maverick.library.actions.decompose import build_outline_prompt

        prompt_text = build_outline_prompt(
            request.flight_plan_content,
            request.codebase_context,
            briefing=request.briefing,
            runway_context=request.runway_context,
        )

        if request.validation_feedback:
            prompt_text += (
                "\n\n## PREVIOUS ATTEMPT FAILED VALIDATION\n"
                f"{request.validation_feedback}\n"
                "Fix these issues in your new decomposition."
            )

        prompt_text += (
            "\n\n## REQUIRED: Submit via tool call\n"
            "You MUST call the `submit_outline` tool with your results."
        )

        await self._ensure_agent()
        logger.info(
            "decomposer.prompt_seeded",
            actor=self._actor_tag,
            role=self._role,
            mode="outline",
            session_id=self._session_id,
            prompt_chars=len(prompt_text),
        )
        await self._prompt(prompt_text, "decompose_outline")

    async def _send_detail_prompt(self, request: DetailRequest) -> None:
        from maverick.library.actions.decompose import (
            build_detail_seed_prompt,
            build_detail_turn_prompt,
        )

        unit_ids = list(request.unit_ids)

        needs_seed = await self._ensure_mode_session(
            "detail",
            max_turns=self._detail_session_max_turns,
            seed_stale=self._detail_seed_stale,
        )
        if needs_seed:
            self._detail_seed_stale = True
        prompt_parts: list[str] = []
        if needs_seed:
            prompt_parts.append(
                build_detail_seed_prompt(
                    flight_plan_content=self._detail_flight_plan,
                    outline_json=self._detail_outline_json,
                    verification_properties=self._detail_verification,
                )
            )
        prompt_parts.append(build_detail_turn_prompt(unit_ids=unit_ids))
        prompt_text = "\n\n".join(prompt_parts)

        prompt_text += (
            "\n\n## REQUIRED: Submit via tool call\n"
            "You MUST call the `submit_details` tool with your results."
        )

        if needs_seed:
            logger.info(
                "decomposer.prompt_seeded",
                actor=self._actor_tag,
                role=self._role,
                mode="detail",
                session_id=self._session_id,
                prompt_chars=len(prompt_text),
                unit_ids=unit_ids,
            )
        else:
            logger.info(
                "decomposer.prompt_reused",
                actor=self._actor_tag,
                role=self._role,
                mode="detail",
                session_id=self._session_id,
                turn=self._session_turns_in_mode + 1,
                max_turns=self._detail_session_max_turns,
                prompt_chars=len(prompt_text),
                unit_ids=unit_ids,
            )

        await self._prompt(prompt_text, "decompose_detail", timeout_seconds=DETAIL_TIMEOUT_SECONDS)
        self._detail_seed_stale = False
        await self._mark_turn_completed("detail")

    async def _send_fix_prompt(self, request: FixRequest) -> None:
        from maverick.library.actions.decompose import (
            build_fix_seed_prompt,
            build_fix_turn_prompt,
        )

        needs_seed = await self._ensure_mode_session(
            "fix",
            max_turns=self._fix_session_max_turns,
            seed_stale=self._fix_seed_stale,
        )
        if needs_seed:
            self._fix_seed_stale = True
        prompt_parts: list[str] = []
        if needs_seed:
            prompt_parts.append(
                build_fix_seed_prompt(
                    outline_json=self._fix_outline_json,
                    details_json=self._fix_details_json,
                    verification_properties=self._fix_verification,
                )
            )
        prompt_parts.append(
            build_fix_turn_prompt(
                coverage_gaps=list(request.coverage_gaps),
                overloaded=list(request.overloaded),
            )
        )
        prompt_parts.append(
            "\n\n## REQUIRED: Submit via tool call\n"
            "You MUST call the `submit_fix` tool with the COMPLETE "
            "updated work_units and details."
        )

        fix_prompt_text = "\n\n".join(prompt_parts)
        if needs_seed:
            logger.info(
                "decomposer.prompt_seeded",
                actor=self._actor_tag,
                role=self._role,
                mode="fix",
                session_id=self._session_id,
                prompt_chars=len(fix_prompt_text),
            )
        else:
            logger.info(
                "decomposer.prompt_reused",
                actor=self._actor_tag,
                role=self._role,
                mode="fix",
                session_id=self._session_id,
                turn=self._session_turns_in_mode + 1,
                max_turns=self._fix_session_max_turns,
                prompt_chars=len(fix_prompt_text),
            )

        await self._prompt(fix_prompt_text, "decompose_fix")
        self._fix_seed_stale = False
        await self._mark_turn_completed("fix")

    async def _send_nudge_prompt(self, request: NudgeRequest) -> None:
        tool_name = request.expected_tool
        unit_id = request.unit_id
        reason = request.reason

        if tool_name == "submit_details" and unit_id:
            prompt_text = (
                f"Your last response was not registered because you did not "
                f"call the `submit_details` tool for unit `{unit_id}`. "
                f"Please call `submit_details` now with a complete entry "
                f"for `{unit_id}`."
            )
        else:
            prompt_text = (
                f"Your response was not registered because you did not "
                f"call the `{tool_name}` tool. Please call "
                f"`{tool_name}` now with your results."
            )
        if reason:
            prompt_text += f" (reason: {reason})"

        await self._prompt(prompt_text, f"decompose_nudge_{tool_name}")
