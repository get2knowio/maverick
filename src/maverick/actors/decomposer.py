"""DecomposerActor — Thespian actor for flight plan decomposition.

Receives outline/detail/fix requests from the supervisor. Sends ACP
prompts via asyncio.run(). The actual results come back to the
supervisor via MCP tool calls (Thespian message from MCP server),
not from this actor's response.

This actor confirms "prompt sent" and the supervisor waits for the
MCP tool call to arrive in its inbox.
"""

import asyncio

from thespian.actors import Actor


class DecomposerActor(Actor):
    """Sends ACP prompts for decomposition phases.

    The decomposer is fire-and-forget for each phase: it sends the
    prompt and confirms. The actual structured result arrives at the
    supervisor via the MCP tool call path.
    """

    def receiveMessage(self, message, sender):
        if not isinstance(message, dict):
            return

        msg_type = message.get("type")

        if msg_type == "init":
            # Store config for lazy executor creation
            self._cwd = message.get("cwd")
            self._mcp_tools = message.get("mcp_tools", "")
            self._supervisor_addr = sender
            self.send(sender, {"type": "init_ok"})

        elif msg_type == "outline_request":
            try:
                asyncio.run(self._send_outline_prompt(message))
                self.send(sender, {"type": "prompt_sent", "phase": "outline"})
            except Exception as exc:
                self.send(sender, {
                    "type": "prompt_error",
                    "phase": "outline",
                    "error": str(exc),
                })

        elif msg_type == "detail_request":
            try:
                asyncio.run(self._send_detail_prompt(message))
                self.send(sender, {"type": "prompt_sent", "phase": "detail"})
            except Exception as exc:
                self.send(sender, {
                    "type": "prompt_error",
                    "phase": "detail",
                    "error": str(exc),
                })

        elif msg_type == "fix_request":
            try:
                asyncio.run(self._send_fix_prompt(message))
                self.send(sender, {"type": "prompt_sent", "phase": "fix"})
            except Exception as exc:
                self.send(sender, {
                    "type": "prompt_error",
                    "phase": "fix",
                    "error": str(exc),
                })

        elif msg_type == "nudge":
            # Agent didn't call the MCP tool — re-prompt
            try:
                asyncio.run(self._send_nudge(message))
                self.send(sender, {"type": "prompt_sent", "phase": "nudge"})
            except Exception as exc:
                self.send(sender, {
                    "type": "prompt_error",
                    "phase": "nudge",
                    "error": str(exc),
                })

    def _get_executor(self):
        """Lazy-create ACP executor in this actor's process."""
        if not hasattr(self, "_executor") or self._executor is None:
            from maverick.executor import create_default_executor

            self._executor = create_default_executor()
        return self._executor

    def _get_session_registry(self):
        """Lazy-create session registry."""
        if not hasattr(self, "_registry") or self._registry is None:
            from maverick.workflows.fly_beads.session_registry import (
                BeadSessionRegistry,
            )

            self._registry = BeadSessionRegistry(bead_id="refuel")
        return self._registry

    async def _get_or_create_session(self):
        """Get or create the persistent ACP session."""
        import shutil
        from pathlib import Path

        from acp.schema import McpServerStdio

        registry = self._get_session_registry()
        executor = self._get_executor()

        session_id = registry.get_session("decomposer")
        if session_id:
            return session_id

        # Build MCP server config
        maverick_bin = shutil.which("maverick") or "maverick"
        mcp_config = McpServerStdio(
            name="supervisor-inbox",
            command=maverick_bin,
            args=["serve-inbox", "--tools", self._mcp_tools],
            env=[],
        )

        from maverick.executor.config import resolve_step_config
        from maverick.config import load_config

        config = load_config()
        step_config = resolve_step_config(
            step_name="decompose_outline",
            step_type="python",
            agent_name="decomposer",
            project_config=config,
        )

        cwd = Path(self._cwd) if self._cwd else Path.cwd()

        session_id = await registry.get_or_create(
            "decomposer",
            executor,
            cwd=cwd,
            config=step_config,
            mcp_servers=[mcp_config],
        )
        return session_id

    async def _prompt(self, prompt_text: str, step_name: str = "decompose"):
        """Send a prompt to the persistent ACP session."""
        executor = self._get_executor()
        registry = self._get_session_registry()
        session_id = await self._get_or_create_session()

        await executor.prompt_session(
            session_id=session_id,
            prompt_text=prompt_text,
            provider=registry.get_provider("decomposer"),
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
            verification_properties=message.get(
                "verification_properties", ""
            ),
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
