"""ImplementerActor — Thespian actor for code implementation.

Self-contained: spawns own ACP agent, creates new session per bead.
Keeps ACP connection alive across beads. Calls submit_implementation
and submit_fix_result MCP tools.
"""

import asyncio
import shutil
import sys
import threading

from thespian.actors import Actor


class ImplementerActor(Actor):
    """Implements bead work and addresses fix requests."""

    def receiveMessage(self, message, sender):
        if not isinstance(message, dict):
            return

        msg_type = message.get("type")

        if msg_type == "init":
            self._admin_port = message.get("admin_port", 19500)
            self._cwd = message.get("cwd")
            self._mcp_tools = "submit_implementation,submit_fix_result"
            self._executor = None
            self._session_id = None
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._loop.run_forever, daemon=True
            )
            self._thread.start()
            self.send(sender, {"type": "init_ok"})

        elif msg_type == "new_bead":
            # Create fresh ACP session for this bead
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._new_session(), self._loop
                )
                future.result(timeout=30)
                self.send(sender, {"type": "session_ready"})
            except Exception as exc:
                self.send(sender, {
                    "type": "prompt_error",
                    "phase": "new_bead",
                    "error": str(exc),
                })

        elif msg_type == "implement":
            self._run_prompt(message, sender, "implement")

        elif msg_type == "fix":
            self._run_prompt(message, sender, "fix")

        elif msg_type == "shutdown":
            if self._executor:
                try:
                    asyncio.run_coroutine_threadsafe(
                        self._executor.cleanup(), self._loop
                    ).result(timeout=5)
                except Exception:
                    pass
            self.send(sender, {"type": "shutdown_ok"})

    def _run_prompt(self, message, sender, phase):
        print(
            f"IMPLEMENTER: starting {phase}...",
            file=sys.stderr, flush=True,
        )
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._send_prompt(message, phase), self._loop
            )
            future.result(timeout=1800)
            print(
                f"IMPLEMENTER: {phase} completed!",
                file=sys.stderr, flush=True,
            )
            self.send(sender, {"type": "prompt_sent", "phase": phase})
        except Exception as exc:
            print(
                f"IMPLEMENTER: {phase} FAILED: {exc}",
                file=sys.stderr, flush=True,
            )
            self.send(sender, {
                "type": "prompt_error",
                "phase": phase,
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

        maverick_bin = (
            shutil.which("maverick")
            or str(Path(sys.executable).parent / "maverick")
        )
        mcp_config = McpServerStdio(
            name="supervisor-inbox",
            command=maverick_bin,
            args=[
                "serve-inbox",
                "--tools", self._mcp_tools,
                "--admin-port", str(self._admin_port),
            ],
            env=[],
        )

        cwd = Path(self._cwd) if self._cwd else Path.cwd()

        self._session_id = await self._executor.create_session(
            step_name="implement",
            agent_name="implementer",
            cwd=cwd,
            mcp_servers=[mcp_config],
        )

    async def _send_prompt(self, message, phase):
        from maverick.executor.config import StepConfig

        await self._ensure_executor()
        if not self._session_id:
            await self._new_session()

        prompt_text = message.get("prompt", "")

        tool_name = (
            "submit_implementation" if phase == "implement"
            else "submit_fix_result"
        )
        prompt_text += (
            f"\n\n## REQUIRED: Submit via tool call\n"
            f"You MUST call the `{tool_name}` tool with your results."
        )

        await self._executor.prompt_session(
            session_id=self._session_id,
            prompt_text=prompt_text,
            config=StepConfig(timeout=1800),
            step_name=phase,
            agent_name="implementer",
        )
