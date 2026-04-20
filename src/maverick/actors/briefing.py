"""BriefingActor — Thespian actor for briefing room agents.

Each instance runs in its own OS process with its own ACP connection.
All briefing agents deliver results via MCP tool calls to the
supervisor inbox. The tool name is set during init:

- Plan generate: submit_scope, submit_analysis, submit_criteria, submit_challenge
- Refuel: submit_navigator_brief, submit_structuralist_brief,
  submit_recon_brief, submit_contrarian_brief
"""

import shutil
import sys

from thespian.actors import Actor

from maverick.actors._bridge import ActorAsyncBridge
from maverick.actors._step_config import (
    load_step_config,
    step_allowed_tools,
    step_config_with_timeout,
)
from maverick.logging import get_logger

logger = get_logger(__name__)


class BriefingActor(ActorAsyncBridge, Actor):
    """Self-contained briefing agent using MCP tools.

    Spawns own ACP agent with MCP server. Agent calls its assigned
    tool to deliver results → supervisor receives via Thespian tell().
    """

    def receiveMessage(self, message, sender):
        if self._handle_actor_exit(message):
            return
        if not isinstance(message, dict):
            return

        msg_type = message.get("type")

        if msg_type == "init":
            cwd_in = message.get("cwd")
            if not cwd_in:
                raise ValueError("BriefingActor init requires 'cwd'")
            self._mcp_tool = message.get("mcp_tool", "")
            self._admin_port = message.get("admin_port", 19500)
            self._cwd = cwd_in
            self._agent_name = message.get("agent_name", "")
            self._step_config = load_step_config(message.get("config"))
            self._executor = None
            self._session_id = None
            self._start_async_bridge()
            self.send(sender, {"type": "init_ok"})

        elif msg_type == "shutdown":
            self._cleanup_executor()
            self.send(sender, {"type": "shutdown_ok"})

        elif msg_type == "briefing":
            logger.debug(
                "briefing.prompt_starting",
                agent=self._agent_name,
                tool=self._mcp_tool,
            )
            try:
                self._run_coro(self._send_prompt(message), timeout=1800)
                logger.debug(
                    "briefing.prompt_completed",
                    agent=self._agent_name,
                    tool=self._mcp_tool,
                )
                self.send(
                    sender,
                    {
                        "type": "prompt_sent",
                        "phase": "briefing",
                        "tool": self._mcp_tool,
                        "agent_name": self._agent_name,
                    },
                )
            except Exception as exc:
                from maverick.exceptions.quota import is_quota_error

                error_str = str(exc)
                _is_quota = is_quota_error(error_str)
                # Quota errors are expected operational events, not bugs.
                # Log at debug to prevent raw structlog ERROR lines
                # leaking to the terminal.
                if _is_quota:
                    logger.debug(
                        "briefing.quota_exhausted",
                        agent=self._agent_name,
                        tool=self._mcp_tool,
                        error=error_str,
                    )
                else:
                    logger.debug(
                        "briefing.prompt_failed",
                        agent=self._agent_name,
                        tool=self._mcp_tool,
                        error=error_str,
                    )
                self.send(
                    sender,
                    {
                        "type": "prompt_error",
                        "phase": "briefing",
                        "tool": self._mcp_tool,
                        "agent_name": self._agent_name,
                        "error": error_str,
                        "quota_exhausted": _is_quota,
                    },
                )

    async def _ensure_executor(self):
        if self._executor is None:
            from maverick.executor import create_default_executor

            self._executor = create_default_executor()

    async def _new_session(self):
        from pathlib import Path

        from acp.schema import McpServerStdio

        maverick_bin = shutil.which("maverick") or str(Path(sys.executable).parent / "maverick")
        mcp_config = McpServerStdio(
            name="supervisor-inbox",
            command=maverick_bin,
            args=[
                "serve-inbox",
                "--tools",
                self._mcp_tool,
                "--admin-port",
                str(self._admin_port),
            ],
            env=[],
        )

        cwd = Path(self._cwd)

        self._session_id = await self._executor.create_session(
            provider=self._step_config.provider if self._step_config else None,
            config=self._step_config,
            step_name=f"briefing_{self._agent_name}",
            agent_name=self._agent_name,
            cwd=cwd,
            allowed_tools=step_allowed_tools(self._step_config),
            mcp_servers=[mcp_config],
        )

    async def _send_prompt(self, message):
        await self._ensure_executor()
        if not self._session_id:
            await self._new_session()

        prompt_text = message.get("prompt", "")
        prompt_text += (
            f"\n\n## REQUIRED: Submit via tool call\n"
            f"You MUST call the `{self._mcp_tool}` tool with your "
            f"results. Do NOT put results in a text response — the "
            f"supervisor can only receive your work via the "
            f"{self._mcp_tool} tool call."
        )

        await self._executor.prompt_session(
            session_id=self._session_id,
            prompt_text=prompt_text,
            provider=self._step_config.provider if self._step_config else None,
            config=step_config_with_timeout(self._step_config, 1200),
            step_name=f"briefing_{self._agent_name}",
            agent_name=self._agent_name,
        )
