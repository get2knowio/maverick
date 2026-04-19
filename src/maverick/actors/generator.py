"""GeneratorActor — Thespian actor for flight plan generation.

Self-contained: spawns own ACP agent, sends prompt, agent calls
submit_flight_plan MCP tool → supervisor receives result.
"""

import shutil
import sys

from thespian.actors import Actor

from maverick.actors._bridge import ActorAsyncBridge
from maverick.logging import get_logger

logger = get_logger(__name__)


class GeneratorActor(ActorAsyncBridge, Actor):
    """Generates flight plan from PRD + briefing context."""

    def receiveMessage(self, message, sender):
        if self._handle_actor_exit(message):
            return
        if not isinstance(message, dict):
            return

        msg_type = message.get("type")

        if msg_type == "init":
            self._admin_port = message.get("admin_port", 19500)
            self._cwd = message.get("cwd")
            self._executor = None
            self._session_id = None
            self._start_async_bridge()
            self.send(sender, {"type": "init_ok"})

        elif msg_type == "shutdown":
            self._cleanup_executor()
            self.send(sender, {"type": "shutdown_ok"})

        elif msg_type == "generate":
            logger.debug("generator.prompt_starting")
            try:
                self._run_coro(self._send_prompt(message), timeout=1800)
                logger.debug("generator.prompt_completed")
                self.send(sender, {"type": "prompt_sent", "phase": "generate"})
            except Exception as exc:
                from maverick.exceptions.quota import is_quota_error

                error_str = str(exc)
                logger.debug("generator.prompt_failed", error=error_str)
                self.send(
                    sender,
                    {
                        "type": "prompt_error",
                        "phase": "generate",
                        "error": error_str,
                        "quota_exhausted": is_quota_error(error_str),
                    },
                )

    async def _ensure_executor(self):
        if self._executor is None:
            from maverick.executor import create_default_executor

            self._executor = create_default_executor()

    async def _new_session(self):
        from pathlib import Path

        from acp.schema import McpServerStdio

        await self._ensure_executor()

        maverick_bin = shutil.which("maverick") or str(Path(sys.executable).parent / "maverick")
        mcp_config = McpServerStdio(
            name="supervisor-inbox",
            command=maverick_bin,
            args=[
                "serve-inbox",
                "--tools",
                "submit_flight_plan",
                "--admin-port",
                str(self._admin_port),
            ],
            env=[],
        )

        cwd = Path(self._cwd) if self._cwd else Path.cwd()

        self._session_id = await self._executor.create_session(
            step_name="generate",
            agent_name="flight_plan_generator",
            cwd=cwd,
            mcp_servers=[mcp_config],
        )

    async def _send_prompt(self, message):
        from maverick.executor.config import StepConfig

        await self._ensure_executor()
        if not self._session_id:
            await self._new_session()

        raw_prompt = message.get("prompt", "")
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
            config=StepConfig(timeout=1200),
            step_name="generate",
            agent_name="flight_plan_generator",
        )
        # Log response for debugging
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
