"""BriefingActor — Thespian actor for briefing room agents.

Used by both plan generate (MCP tool mode) and refuel (output_schema
mode). Each instance runs in its own OS process with its own ACP
connection. The mode is determined by the init message:

- MCP mode: ``mcp_tool`` is set, agent calls a tool to deliver results
  to the supervisor via Thespian tell().
- Schema mode: ``schema_module`` + ``schema_class`` are set, agent
  returns structured JSON validated against the schema. Result is
  sent back to the supervisor as a dict.
"""

import shutil
import sys

from thespian.actors import Actor

from maverick.actors._bridge import ActorAsyncBridge
from maverick.logging import get_logger

logger = get_logger(__name__)


class BriefingActor(ActorAsyncBridge, Actor):
    """Self-contained briefing agent.

    MCP mode: spawns ACP agent with MCP server, agent calls tool →
    supervisor receives via Thespian tell().

    Schema mode: spawns ACP agent, calls executor.execute() with
    output_schema, sends validated result back to supervisor.
    """

    def receiveMessage(self, message, sender):
        if not isinstance(message, dict):
            return

        msg_type = message.get("type")

        if msg_type == "init":
            self._mcp_tool = message.get("mcp_tool")
            self._admin_port = message.get("admin_port", 19500)
            self._cwd = message.get("cwd")
            self._agent_name = message.get("agent_name", "")
            self._schema_module = message.get("schema_module")
            self._schema_class = message.get("schema_class")
            self._executor = None
            self._session_id = None
            self._start_async_bridge()
            self.send(sender, {"type": "init_ok"})

        elif msg_type == "shutdown":
            self._cleanup_executor()
            self.send(sender, {"type": "shutdown_ok"})

        elif msg_type == "briefing":
            if self._schema_module and self._schema_class:
                self._handle_schema_mode(message, sender)
            else:
                self._handle_mcp_mode(message, sender)

    # ------------------------------------------------------------------
    # Schema mode (refuel briefing — output_schema)
    # ------------------------------------------------------------------

    def _handle_schema_mode(self, message, sender):
        logger.debug("briefing.schema_prompt_starting", agent=self._agent_name)
        try:
            result = self._run_coro(self._do_schema_briefing(message), timeout=1800)
            self.send(
                sender,
                {
                    "type": "briefing_result",
                    "agent_name": self._agent_name,
                    "output": result,
                },
            )
        except Exception as exc:
            logger.error(
                "briefing.schema_prompt_failed",
                agent=self._agent_name,
                error=str(exc),
            )
            self.send(
                sender,
                {
                    "type": "briefing_result",
                    "agent_name": self._agent_name,
                    "output": None,
                    "error": str(exc),
                },
            )

    async def _do_schema_briefing(self, message):
        import importlib

        await self._ensure_executor()

        mod = importlib.import_module(self._schema_module)
        schema_cls = getattr(mod, self._schema_class)

        prompt = message.get("prompt", "")
        result = await self._executor.execute(
            step_name=f"briefing_{self._agent_name}",
            agent_name=self._agent_name,
            prompt=prompt,
            output_schema=schema_cls,
        )

        if result.output is not None:
            if hasattr(result.output, "model_dump"):
                return result.output.model_dump()
            return result.output
        return None

    # ------------------------------------------------------------------
    # MCP mode (plan generate briefing — MCP tool calls)
    # ------------------------------------------------------------------

    def _handle_mcp_mode(self, message, sender):
        logger.debug("briefing.mcp_prompt_starting", tool=self._mcp_tool)
        try:
            self._run_coro(self._send_mcp_prompt(message), timeout=1800)
            logger.debug("briefing.mcp_prompt_completed", tool=self._mcp_tool)
            self.send(
                sender,
                {
                    "type": "prompt_sent",
                    "tool": self._mcp_tool,
                },
            )
        except Exception as exc:
            logger.error("briefing.mcp_prompt_failed", tool=self._mcp_tool, error=str(exc))
            self.send(
                sender,
                {
                    "type": "prompt_error",
                    "tool": self._mcp_tool,
                    "error": str(exc),
                },
            )

    async def _send_mcp_prompt(self, message):
        from maverick.executor.config import StepConfig

        await self._ensure_executor()
        if not self._session_id:
            await self._new_mcp_session()

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

    # ------------------------------------------------------------------
    # Shared
    # ------------------------------------------------------------------

    async def _ensure_executor(self):
        if self._executor is None:
            from maverick.executor import create_default_executor

            self._executor = create_default_executor()

    async def _new_mcp_session(self):
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

        cwd = Path(self._cwd) if self._cwd else Path.cwd()

        self._session_id = await self._executor.create_session(
            step_name=f"briefing_{self._mcp_tool}",
            agent_name="briefing",
            cwd=cwd,
            mcp_servers=[mcp_config],
        )
