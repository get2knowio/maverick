"""BriefingActor — Thespian actor for plan briefing room agents.

Generic actor reused for Scopist, CodebaseAnalyst, CriteriaWriter,
and Contrarian. Each instance is parameterized with its MCP tool name
and spawns its own ACP agent subprocess.
"""

import asyncio
import shutil
import sys
import threading

from thespian.actors import Actor


class BriefingActor(Actor):
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
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._loop.run_forever, daemon=True
            )
            self._thread.start()
            self.send(sender, {"type": "init_ok"})

        elif msg_type == "shutdown":
            if self._executor:
                try:
                    asyncio.run_coroutine_threadsafe(
                        self._executor.cleanup(), self._loop
                    ).result(timeout=5)
                except Exception:
                    pass
            self.send(sender, {"type": "shutdown_ok"})

        elif msg_type == "briefing":
            print(
                f"BRIEFING({self._mcp_tool}): starting prompt...",
                file=sys.stderr, flush=True,
            )
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._send_prompt(message), self._loop
                )
                future.result(timeout=1800)
                print(
                    f"BRIEFING({self._mcp_tool}): prompt completed!",
                    file=sys.stderr, flush=True,
                )
                self.send(sender, {
                    "type": "prompt_sent",
                    "tool": self._mcp_tool,
                })
            except Exception as exc:
                print(
                    f"BRIEFING({self._mcp_tool}): FAILED: {exc}",
                    file=sys.stderr, flush=True,
                )
                self.send(sender, {
                    "type": "prompt_error",
                    "tool": self._mcp_tool,
                    "error": str(exc),
                })

    async def _ensure_executor(self):
        if self._executor is None:
            from maverick.executor import create_default_executor
            self._executor = create_default_executor()

    async def _new_session(self):
        from pathlib import Path

        from acp.schema import McpServerStdio
        await self._ensure_executor()

        maverick_bin = shutil.which("maverick") or "maverick"
        mcp_config = McpServerStdio(
            name="supervisor-inbox",
            command=maverick_bin,
            args=[
                "serve-inbox",
                "--tools", self._mcp_tool,
                "--admin-port", str(self._admin_port),
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
