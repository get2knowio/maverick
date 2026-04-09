"""DecomposerActor — Thespian actor for flight plan decomposition.

Receives outline/detail/fix requests from the supervisor. Sends ACP
prompts via asyncio.run(). The actual results come back to the
supervisor via MCP tool calls (Thespian message from MCP server),
not from this actor's response.

This actor confirms "prompt sent" and the supervisor waits for the
MCP tool call to arrive in its inbox.
"""

import asyncio
import sys
import threading

from thespian.actors import Actor


class DecomposerActor(Actor):
    """Sends ACP prompts for decomposition phases.

    Uses a persistent event loop in a background thread for async
    ACP calls. This avoids the asyncio.run() teardown issue where
    ACP's async generators conflict with loop closure.
    """

    def receiveMessage(self, message, sender):
        if not isinstance(message, dict):
            return

        msg_type = message.get("type")

        if msg_type == "init":
            self._cwd = message.get("cwd")
            self._mcp_tools = message.get("mcp_tools", "")
            self._admin_port = message.get("admin_port", 19500)
            self._supervisor_addr = sender
            # Create persistent event loop for async ACP calls
            self._loop = asyncio.new_event_loop()
            self._loop_thread = threading.Thread(target=self._loop.run_forever, daemon=True)
            self._loop_thread.start()
            self.send(sender, {"type": "init_ok"})

        elif msg_type == "shutdown":
            if hasattr(self, "_executor") and self._executor:
                try:
                    asyncio.run_coroutine_threadsafe(self._executor.cleanup(), self._loop).result(
                        timeout=5
                    )
                except Exception:
                    pass
            self.send(sender, {"type": "shutdown_ok"})

        elif msg_type == "outline_request":
            self._run_async(
                self._send_outline_prompt(message),
                sender,
                "outline",
            )

        elif msg_type == "detail_request":
            self._run_async(
                self._send_detail_prompt(message),
                sender,
                "detail",
            )

        elif msg_type == "fix_request":
            self._run_async(
                self._send_fix_prompt(message),
                sender,
                "fix",
            )

        elif msg_type == "nudge":
            self._run_async(
                self._send_nudge(message),
                sender,
                "nudge",
            )

    def _run_async(self, coro, sender, phase):
        """Run an async coroutine on the persistent event loop."""
        print(f"DECOMPOSER: starting {phase}...", file=sys.stderr, flush=True)
        try:
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
            print(
                f"DECOMPOSER: waiting for {phase} (timeout=1800s)...", file=sys.stderr, flush=True
            )
            future.result(timeout=1800)  # blocks until done
            print(f"DECOMPOSER: {phase} completed!", file=sys.stderr, flush=True)
            self.send(sender, {"type": "prompt_sent", "phase": phase})
        except Exception as exc:
            print(f"DECOMPOSER: {phase} FAILED: {exc}", file=sys.stderr, flush=True)
            self.send(
                sender,
                {
                    "type": "prompt_error",
                    "phase": phase,
                    "error": str(exc),
                },
            )

    async def _ensure_agent(self):
        """Spawn this actor's own ACP agent and create a session.

        Each actor owns its own agent subprocess — no shared
        connections, no shared sessions, no registry. The actor
        creates everything it needs from maverick.yaml config.
        """
        if getattr(self, "_session_id", None):
            return  # already running

        import shutil
        from pathlib import Path

        from acp.schema import McpServerStdio

        from maverick.executor import create_default_executor

        self._executor = create_default_executor()

        # Build MCP server config with admin port for Thespian discovery
        maverick_bin = shutil.which("maverick") or str(Path(sys.executable).parent / "maverick")
        admin_port = str(getattr(self, "_admin_port", 19500))
        mcp_config = McpServerStdio(
            name="supervisor-inbox",
            command=maverick_bin,
            args=[
                "serve-inbox",
                "--tools",
                self._mcp_tools,
                "--admin-port",
                admin_port,
            ],
            env=[],
        )

        cwd = Path(self._cwd) if self._cwd else Path.cwd()

        self._session_id = await self._executor.create_session(
            step_name="decompose",
            agent_name="decomposer",
            cwd=cwd,
            mcp_servers=[mcp_config],
        )

    async def _prompt(self, prompt_text: str, step_name: str = "decompose"):
        """Send a prompt to this actor's own ACP session."""
        from maverick.executor.config import StepConfig

        await self._ensure_agent()

        config = StepConfig(timeout=1800)

        await self._executor.prompt_session(
            session_id=self._session_id,
            prompt_text=prompt_text,
            config=config,
            step_name=step_name,
            agent_name="decomposer",
        )

    async def _send_outline_prompt(self, message):
        from maverick.library.actions.decompose import build_outline_prompt

        prompt_text = build_outline_prompt(
            message.get("flight_plan_content", ""),
            message.get("codebase_context"),
            briefing=message.get("briefing"),
            runway_context=message.get("runway_context"),
        )

        validation_feedback = message.get("validation_feedback", "")
        if validation_feedback:
            prompt_text += (
                f"\n\n## PREVIOUS ATTEMPT FAILED VALIDATION\n"
                f"{validation_feedback}\n"
                f"Fix these issues in your new decomposition."
            )

        prompt_text += (
            "\n\n## REQUIRED: Submit via tool call\n"
            "You MUST call the `submit_outline` tool with your results."
        )

        await self._prompt(prompt_text, "decompose_outline")

    async def _send_detail_prompt(self, message):
        from maverick.library.actions.decompose import build_detail_prompt

        prompt_text = build_detail_prompt(
            flight_plan_content=message.get("flight_plan_content", ""),
            outline_json=message.get("outline_json", "{}"),
            unit_ids=message.get("unit_ids", []),
            verification_properties=message.get("verification_properties", ""),
        )

        prompt_text += (
            "\n\n## REQUIRED: Submit via tool call\n"
            "You MUST call the `submit_details` tool with your results."
        )

        await self._prompt(prompt_text, "decompose_detail")

    async def _send_fix_prompt(self, message):
        parts = [
            "Your previous decomposition had validation issues. "
            "Fix ONLY the specific problems listed below.\n"
        ]

        if message.get("coverage_gaps"):
            parts.append("## Missing SC Coverage\n")
            for gap in message["coverage_gaps"]:
                parts.append(f"- {gap}")

        if message.get("overloaded"):
            parts.append("\n## Overloaded Work Units\n")
            for item in message["overloaded"]:
                parts.append(f"- {item}")

        parts.append(
            "\n\n## REQUIRED: Submit via tool call\n"
            "You MUST call the `submit_fix` tool with the COMPLETE "
            "updated work_units and details."
        )

        await self._prompt("\n".join(parts), "decompose_fix")

    async def _send_nudge(self, message):
        tool_name = message.get("expected_tool", "submit_outline")
        await self._prompt(
            f"Your response was not registered because you did not "
            f"call the `{tool_name}` tool. Please call "
            f"`{tool_name}` now with your results.",
            f"decompose_nudge_{tool_name}",
        )
