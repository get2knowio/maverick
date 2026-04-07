"""ReviewerActor — Thespian actor for code review.

Self-contained: spawns own ACP agent, creates new session per bead.
Keeps ACP connection alive across beads. Calls submit_review MCP tool.
On follow-up reviews, the session preserves conversation history.
"""

import asyncio
import shutil
import sys
import threading

from thespian.actors import Actor


class ReviewerActor(Actor):
    """Reviews code and delivers findings via MCP tool calls."""

    def receiveMessage(self, message, sender):
        if not isinstance(message, dict):
            return

        msg_type = message.get("type")

        if msg_type == "init":
            self._admin_port = message.get("admin_port", 19500)
            self._cwd = message.get("cwd")
            self._executor = None
            self._session_id = None
            self._review_count = 0
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._loop.run_forever, daemon=True
            )
            self._thread.start()
            self.send(sender, {"type": "init_ok"})

        elif msg_type == "new_bead":
            self._review_count = 0
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

        elif msg_type == "review":
            self._review_count += 1
            self._run_prompt(message, sender)

        elif msg_type == "shutdown":
            if self._executor:
                try:
                    asyncio.run_coroutine_threadsafe(
                        self._executor.cleanup(), self._loop
                    ).result(timeout=5)
                except Exception:
                    pass
            self.send(sender, {"type": "shutdown_ok"})

    def _run_prompt(self, message, sender):
        print(
            f"REVIEWER: starting review #{self._review_count}...",
            file=sys.stderr, flush=True,
        )
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._send_review(message), self._loop
            )
            future.result(timeout=1200)
            print(
                f"REVIEWER: review #{self._review_count} completed!",
                file=sys.stderr, flush=True,
            )
            self.send(sender, {
                "type": "prompt_sent",
                "phase": "review",
                "review_count": self._review_count,
            })
        except Exception as exc:
            print(
                f"REVIEWER: review FAILED: {exc}",
                file=sys.stderr, flush=True,
            )
            self.send(sender, {
                "type": "prompt_error",
                "phase": "review",
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
                "--tools", "submit_review",
                "--admin-port", str(self._admin_port),
            ],
            env=[],
        )

        cwd = Path(self._cwd) if self._cwd else Path.cwd()

        self._session_id = await self._executor.create_session(
            step_name="review",
            agent_name="reviewer",
            cwd=cwd,
            mcp_servers=[mcp_config],
        )

    async def _send_review(self, message):
        from maverick.executor.config import StepConfig

        await self._ensure_executor()
        if not self._session_id:
            await self._new_session()

        bead_description = message.get("bead_description", "")

        if self._review_count == 1:
            prompt = (
                "Review the code changes in the working directory.\n\n"
                f"## Task Description\n\n{bead_description}\n\n"
                "Check for bugs, security issues, and correctness.\n"
                "Only flag CRITICAL or MAJOR issues.\n\n"
                "## REQUIRED: Submit via tool call\n"
                "Call the `submit_review` tool. Set approved=true if "
                "no critical/major issues."
            )
        else:
            prompt = (
                "The implementer has made changes. Review ONLY whether "
                "your previous findings were addressed.\n"
                "Do NOT introduce new findings.\n\n"
                "## REQUIRED: Submit via tool call\n"
                "Call the `submit_review` tool."
            )

        await self._executor.prompt_session(
            session_id=self._session_id,
            prompt_text=prompt,
            config=StepConfig(timeout=600),
            step_name="review",
            agent_name="reviewer",
        )
