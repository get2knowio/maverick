"""GeneratorActor — Thespian actor for flight plan generation.

Self-contained: spawns own ACP agent, sends prompt, agent calls
submit_flight_plan MCP tool → supervisor receives result.
"""

import asyncio
import shutil
import sys
import threading

from thespian.actors import Actor


class GeneratorActor(Actor):
    """Generates flight plan from PRD + briefing context."""

    def receiveMessage(self, message, sender):
        if not isinstance(message, dict):
            return

        msg_type = message.get("type")

        if msg_type == "init":
            self._admin_port = message.get("admin_port", 19500)
            self._cwd = message.get("cwd")
            self._executor = None
            self._session_id = None
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
            self._thread.start()
            self.send(sender, {"type": "init_ok"})

        elif msg_type == "shutdown":
            if self._executor:
                try:
                    asyncio.run_coroutine_threadsafe(self._executor.cleanup(), self._loop).result(
                        timeout=5
                    )
                except Exception:
                    pass
            self.send(sender, {"type": "shutdown_ok"})

        elif msg_type == "generate":
            print("GENERATOR: starting prompt...", file=sys.stderr, flush=True)
            try:
                future = asyncio.run_coroutine_threadsafe(self._send_prompt(message), self._loop)
                future.result(timeout=1800)
                print("GENERATOR: prompt completed!", file=sys.stderr, flush=True)
                self.send(sender, {"type": "prompt_sent", "phase": "generate"})
            except Exception as exc:
                print(f"GENERATOR: FAILED: {exc}", file=sys.stderr, flush=True)
                self.send(
                    sender,
                    {
                        "type": "prompt_error",
                        "phase": "generate",
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
        print(
            f"GENERATOR: result success={success}, "
            f"text_len={len(text)}, output_type={type(output).__name__}, "
            f"output_preview={str(output)[:500]}",
            file=sys.stderr,
            flush=True,
        )
