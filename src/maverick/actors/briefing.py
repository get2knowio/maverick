"""BriefingActor — Thespian actor for plan briefing room agents.

Generic actor reused for Scopist, CodebaseAnalyst, CriteriaWriter,
and Contrarian. Each instance is parameterized with its MCP tool name
and spawns its own ACP agent subprocess.
"""

import shutil
import sys

from thespian.actors import Actor

from maverick.actors._bridge import ActorAsyncBridge
from maverick.logging import get_logger

logger = get_logger(__name__)


class BriefingActor(ActorAsyncBridge, Actor):
    """Self-contained briefing agent. Spawns own ACP agent, sends
    prompt, agent calls MCP tool → supervisor receives result."""

    def receiveMessage(self, message, sender):
        if not isinstance(message, dict):
            return

        msg_type = message.get("type")

        if msg_type == "init":
            self._mcp_tool = message["mcp_tool"]
            self._admin_port = message.get("admin_port", 19500)
            self._cwd = message.get("cwd")
            self._executor = None
            self._session_id = None
            self._start_async_bridge()
            self.send(sender, {"type": "init_ok"})

        elif msg_type == "shutdown":
            self._cleanup_executor()
            self.send(sender, {"type": "shutdown_ok"})

        elif msg_type == "briefing":
            logger.debug("briefing.prompt_starting", tool=self._mcp_tool)
            try:
                self._run_coro(self._send_prompt(message), timeout=1800)
                logger.debug("briefing.prompt_completed", tool=self._mcp_tool)
                self.send(
                    sender,
                    {
                        "type": "prompt_sent",
                        "tool": self._mcp_tool,
                    },
                )
            except Exception as exc:
                logger.error("briefing.prompt_failed", tool=self._mcp_tool, error=str(exc))
                self.send(
                    sender,
                    {
                        "type": "prompt_error",
                        "tool": self._mcp_tool,
                        "error": str(exc),
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
                self._mcp_tool,
                "--admin-port",
                str(self._admin_port),
            ],
            env=[],
        )

        cwd = Path(self._cwd) if self._cwd else Path.cwd()

        self._session_id = await self._executor.create_session(
            step_name=f"briefing_{self._mcp_tool}",
            agent_name="briefing",
            cwd=cwd,
            mcp_servers=[mcp_config],
        )

    async def _send_prompt(self, message):
        from maverick.executor.config import StepConfig

        await self._ensure_executor()
        if not self._session_id:
            await self._new_session()

        prompt_text = message.get("prompt", "")
        prompt_text += (
            f"\n\n## REQUIRED: Submit via tool call\n"
            f"You MUST call the `{self._mcp_tool}` tool with your "
            f"results. Do NOT put results in a text response."
        )

        await self._executor.prompt_session(
            session_id=self._session_id,
            prompt_text=prompt_text,
            config=StepConfig(timeout=1200),
            step_name=f"briefing_{self._mcp_tool}",
            agent_name="briefing",
        )
