"""xoscar GeneratorActor — flight-plan generation agent.

Owns one MCP tool: ``submit_flight_plan``. The supervisor passes the
composite PRD + briefing prompt via ``send_generate``; the agent
submits the structured plan via ``submit_flight_plan`` → supervisor's
``flight_plan_ready`` method.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import xoscar as xo
from acp.schema import McpServerStdio

from maverick.actors.step_config import (
    load_step_config,
    step_allowed_tools,
    step_config_with_timeout,
)
from maverick.actors.xoscar.messages import GenerateRequest, PromptError
from maverick.logging import get_logger
from maverick.tools.agent_inbox.models import (
    SubmitFlightPlanPayload,
    SupervisorToolPayloadError,
    parse_supervisor_tool_payload,
)

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig

logger = get_logger(__name__)

GENERATOR_MCP_TOOL = "submit_flight_plan"
GENERATOR_PROMPT_TIMEOUT_SECONDS = 1200


class GeneratorActor(xo.Actor):
    """Generates flight plan from PRD + briefing context."""

    def __init__(
        self,
        supervisor_ref: xo.ActorRef,
        *,
        cwd: str,
        config: StepConfig | dict[str, Any] | None = None,
    ) -> None:
        if not cwd:
            raise ValueError("GeneratorActor requires 'cwd'")
        self._supervisor_ref = supervisor_ref
        self._cwd = cwd
        self._step_config = load_step_config(config)

    async def __post_create__(self) -> None:
        self._actor_tag = f"generator[{self.uid}]"
        self._executor: Any = None
        self._session_id: str | None = None

    async def __pre_destroy__(self) -> None:
        if self._executor is None:
            return
        try:
            await self._executor.cleanup()
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "generator.cleanup_failed",
                actor=self._actor_tag,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Supervisor → agent
    # ------------------------------------------------------------------

    async def send_generate(self, request: GenerateRequest) -> None:
        from maverick.exceptions.quota import is_quota_error

        logger.debug("generator.prompt_starting")
        try:
            await self._send_prompt(request.prompt)
            logger.debug("generator.prompt_completed")
        except Exception as exc:  # noqa: BLE001
            error_str = str(exc)
            logger.debug("generator.prompt_failed", error=error_str)
            await self._supervisor_ref.prompt_error(
                PromptError(
                    phase="generate",
                    error=error_str,
                    quota_exhausted=is_quota_error(error_str),
                )
            )

    # ------------------------------------------------------------------
    # MCP subprocess → agent inbox
    # ------------------------------------------------------------------

    async def on_tool_call(self, tool: str, args: dict[str, Any]) -> str:
        if tool != GENERATOR_MCP_TOOL:
            await self._supervisor_ref.payload_parse_error(
                tool,
                f"Generator advertises {GENERATOR_MCP_TOOL!r}, got {tool!r}",
            )
            return "error"
        try:
            payload = parse_supervisor_tool_payload(tool, args)
        except (SupervisorToolPayloadError, ValueError) as exc:
            await self._supervisor_ref.payload_parse_error(tool, str(exc))
            return "error"
        if not isinstance(payload, SubmitFlightPlanPayload):
            await self._supervisor_ref.payload_parse_error(
                tool, f"Unexpected payload type for {tool!r}"
            )
            return "error"
        await self._supervisor_ref.flight_plan_ready(payload)
        return "ok"

    # ------------------------------------------------------------------
    # ACP plumbing
    # ------------------------------------------------------------------

    async def _ensure_executor(self) -> None:
        if self._executor is None:
            from maverick.executor import create_default_executor

            self._executor = create_default_executor()

    async def _new_session(self) -> None:
        await self._ensure_executor()

        maverick_bin = shutil.which("maverick") or str(
            Path(sys.executable).parent / "maverick"
        )
        mcp_config = McpServerStdio(
            name="agent-inbox",
            command=maverick_bin,
            args=[
                "serve-inbox",
                "--tools",
                GENERATOR_MCP_TOOL,
                "--inbox-address",
                self.address,
                "--inbox-uid",
                self.uid,
            ],
            env=[],
        )

        cwd = Path(self._cwd)
        self._session_id = await self._executor.create_session(
            provider=self._step_config.provider if self._step_config else None,
            config=self._step_config,
            step_name="generate",
            agent_name="flight_plan_generator",
            cwd=cwd,
            allowed_tools=step_allowed_tools(self._step_config),
            mcp_servers=[mcp_config],
        )

    async def _send_prompt(self, raw_prompt: str) -> None:
        await self._ensure_executor()
        if not self._session_id:
            await self._new_session()

        prompt_text = (
            "You are a flight plan generator. Your ONLY job is to read "
            "the PRD and briefing below, then call the `submit_flight_plan` "
            "tool with a structured flight plan.\n\n"
            "DO NOT read files from the filesystem. DO NOT explore the codebase. "
            "DO NOT write any code. Your sole output is a single call to "
            "`submit_flight_plan`.\n\n"
            "The tool requires:\n"
            "- objective: one-line summary of what this plan achieves\n"
            "- success_criteria: array of {description, verification} objects\n"
            "- in_scope: array of strings for what's in scope\n"
            "- out_of_scope: array of strings for what's out of scope\n"
            "- constraints: array of strings for constraints\n"
            "- context: background context as markdown\n"
            "- tags: categorization tags\n\n"
            f"{raw_prompt}\n\n"
            "Now call `submit_flight_plan` with the structured plan. "
            "Do NOT respond with text — ONLY call the tool."
        )

        result = await self._executor.prompt_session(
            session_id=self._session_id,
            prompt_text=prompt_text,
            provider=self._step_config.provider if self._step_config else None,
            config=step_config_with_timeout(
                self._step_config, GENERATOR_PROMPT_TIMEOUT_SECONDS
            ),
            step_name="generate",
            agent_name="flight_plan_generator",
        )
        text = getattr(result, "text", "") or ""
        output = getattr(result, "output", None)
        success = getattr(result, "success", None)
        logger.debug(
            "generator.result",
            success=success,
            text_len=len(text),
            output_type=type(output).__name__,
            output_preview=str(output)[:500],
        )
