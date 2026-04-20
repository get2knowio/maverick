"""DecomposerActor — Thespian actor for flight plan decomposition.

Receives outline/detail/fix requests from the supervisor. Sends ACP
prompts via asyncio.run(). The actual results come back to the
supervisor via MCP tool calls (Thespian message from MCP server),
not from this actor's response.

This actor confirms "prompt sent" and the supervisor waits for the
MCP tool call to arrive in its inbox.

Two roles:
- **primary**: handles outline, detail, and fix phases.
  Tools: submit_outline, submit_details, submit_fix
- **pool**: handles detail phase only.
  Tools: submit_details
"""

import os
import sys
from typing import Any

from thespian.actors import Actor

from maverick.actors._bridge import ActorAsyncBridge
from maverick.agents.tools import PLANNER_TOOLS
from maverick.logging import get_logger

logger = get_logger(__name__)

READ_ONLY_DECOMPOSER_TOOLS: tuple[str, ...] = tuple(sorted(PLANNER_TOOLS))
PRIMARY_DECOMPOSER_MCP_TOOLS: tuple[str, ...] = (
    "submit_outline",
    "submit_details",
    "submit_fix",
)
POOL_DECOMPOSER_MCP_TOOLS: tuple[str, ...] = ("submit_details",)


class DecomposerActor(ActorAsyncBridge, Actor):
    """Sends ACP prompts for decomposition phases.

    Uses a persistent event loop in a background thread for async
    ACP calls. This avoids the asyncio.run() teardown issue where
    ACP's async generators conflict with loop closure.
    """

    def receiveMessage(self, message, sender):
        # Thespian's asys.shutdown() delivers ActorExitRequest (not a
        # dict). Tear down the ACP subprocess here or it outlives us.
        if self._handle_actor_exit(message):
            return
        if not isinstance(message, dict):
            return

        msg_type = message.get("type")

        if msg_type == "init":
            self._cwd = message.get("cwd")
            role = message.get("role", "primary")
            self._role = role
            self._detail_session_max_turns = max(
                1,
                int(message.get("detail_session_max_turns", 5)),
            )
            self._fix_session_max_turns = max(
                1,
                int(message.get("fix_session_max_turns", 1)),
            )
            if role == "pool":
                self._mcp_tool_names = POOL_DECOMPOSER_MCP_TOOLS
            else:
                self._mcp_tool_names = PRIMARY_DECOMPOSER_MCP_TOOLS
            self._mcp_tools = ",".join(self._mcp_tool_names)
            self._admin_port = message.get("admin_port", 19500)
            self._supervisor_addr = sender
            # Tag used in all lifecycle logs so one pool actor's session
            # narrative can be grepped out from the rest.
            self._actor_tag = f"decomposer[{role}:pid={os.getpid()}]"
            self._executor = None
            self._session_id = None
            self._session_mode: str | None = None
            self._session_turns_in_mode = 0
            # Per-actor context populated by "set_context" before any
            # detail_request arrives. Keeps detail_request messages
            # tiny (just a unit_id) instead of re-shipping ~60KB of
            # outline + flight plan + verification per fan-out message.
            self._detail_outline_json: str = "{}"
            self._detail_flight_plan: str = ""
            self._detail_verification: str = ""
            self._detail_seed_stale = True
            self._fix_outline_json: str = '{"work_units": []}'
            self._fix_details_json: str = '{"details": []}'
            self._fix_verification: str = ""
            self._fix_seed_stale = True
            self._start_async_bridge()
            self.send(sender, {"type": "init_ok"})

        elif msg_type == "set_context":
            self._detail_outline_json = message.get("outline_json", "{}")
            self._detail_flight_plan = message.get("flight_plan_content", "")
            self._detail_verification = message.get("verification_properties", "")
            self._detail_seed_stale = True

        elif msg_type == "shutdown":
            self._cleanup_executor()
            self.send(sender, {"type": "shutdown_ok"})

        elif msg_type == "outline_request":
            self._run_async(
                self._send_outline_prompt(message),
                sender,
                "outline",
            )

        elif msg_type == "detail_request":
            unit_id = message.get("unit_id") or (message.get("unit_ids") or [""])[0]
            self._run_async(
                self._send_detail_prompt(message),
                sender,
                "detail",
                unit_id=unit_id,
            )

        elif msg_type == "fix_request":
            self._fix_outline_json = message.get("outline_json", self._fix_outline_json)
            self._fix_details_json = message.get("details_json", self._fix_details_json)
            self._fix_verification = message.get(
                "verification_properties",
                self._fix_verification,
            )
            self._fix_seed_stale = True
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

    def _run_async(self, coro, sender, phase, *, unit_id: str | None = None):
        """Run an async coroutine on the persistent event loop."""
        logger.debug("decomposer.phase_starting", phase=phase, unit_id=unit_id)
        try:
            self._run_coro(coro, timeout=1800)
            logger.debug("decomposer.phase_completed", phase=phase, unit_id=unit_id)
            reply: dict[str, Any] = {"type": "prompt_sent", "phase": phase}
            if unit_id:
                reply["unit_id"] = unit_id
            self.send(sender, reply)
        except Exception as exc:
            from maverick.exceptions.quota import is_quota_error

            error_str = str(exc)
            _is_quota = is_quota_error(error_str)
            logger.debug(
                "decomposer.phase_failed",
                phase=phase,
                unit_id=unit_id,
                error=error_str,
            )
            err_reply: dict[str, Any] = {
                "type": "prompt_error",
                "phase": phase,
                "error": error_str,
                "quota_exhausted": _is_quota,
            }
            if unit_id:
                err_reply["unit_id"] = unit_id
            self.send(sender, err_reply)

    def _needs_new_mode_session(
        self,
        mode: str,
        *,
        max_turns: int,
        seed_stale: bool,
    ) -> bool:
        """Return whether the next prompt requires a fresh ACP session."""
        return (
            not getattr(self, "_session_id", None)
            or getattr(self, "_session_mode", None) != mode
            or self._session_turns_in_mode >= max(1, max_turns)
            or seed_stale
        )

    def _mark_turn_completed(self, mode: str) -> None:
        """Advance the turn counter for the current seeded session mode."""
        if self._session_mode == mode:
            self._session_turns_in_mode += 1

    async def _ensure_executor(self):
        """Create this actor's ACP executor on first use.

        Only fires once per actor lifetime. The ACP subprocess is
        actually spawned lazily on the first ``create_session`` call
        into the connection pool — look for the ``acp_executor.
        subprocess_spawn`` INFO log immediately after this one.
        """
        if self._executor is not None:
            return

        from maverick.executor import create_default_executor

        logger.info(
            "decomposer.acp_connection_new",
            actor=self._actor_tag,
            role=getattr(self, "_role", "primary"),
        )
        self._executor = create_default_executor()

    async def _create_session(self) -> None:
        """Create a fresh ACP session on this actor's executor."""
        import shutil
        from pathlib import Path

        from acp.schema import McpServerStdio

        await self._ensure_executor()

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
        role = getattr(self, "_role", "primary")
        one_shot: list[str] | None = ["submit_outline"] if role == "primary" else None
        allowed_tools = [*READ_ONLY_DECOMPOSER_TOOLS, *self._mcp_tool_names]

        self._session_id = await self._executor.create_session(
            step_name="decompose",
            agent_name="decomposer",
            cwd=cwd,
            allowed_tools=allowed_tools,
            mcp_servers=[mcp_config],
            one_shot_tools=one_shot,
        )

    async def _ensure_mode_session(
        self,
        mode: str,
        *,
        max_turns: int,
        seed_stale: bool,
    ) -> bool:
        """Ensure a seeded-session mode has a usable ACP session.

        Returns True when a new session was created and the next prompt should
        include the large seed context.
        """
        previous_session = getattr(self, "_session_id", None)
        previous_mode = getattr(self, "_session_mode", None)
        previous_turns = self._session_turns_in_mode

        if not previous_session:
            reason = "initial"
        elif previous_mode != mode:
            reason = "mode_change"
        elif previous_turns >= max(1, max_turns):
            reason = "turn_limit"
        elif seed_stale:
            reason = "seed_stale"
        else:
            return False

        # Log the *intent* to rotate before we spawn the new session so
        # the narrative reads "rotating → created → seeded" in order.
        if previous_session:
            logger.info(
                "decomposer.session_rotated",
                actor=self._actor_tag,
                role=self._role,
                mode=mode,
                reason=reason,
                previous_session=previous_session,
                previous_mode=previous_mode,
                previous_turns=previous_turns,
                max_turns=max_turns,
            )

        await self._create_session()
        self._session_mode = mode
        self._session_turns_in_mode = 0
        logger.info(
            "decomposer.session_created",
            actor=self._actor_tag,
            role=self._role,
            mode=mode,
            reason=reason,
            session_id=self._session_id,
            max_turns=max_turns,
        )
        return True

    async def _ensure_agent(self):
        """Spawn this actor's own ACP agent and create a session.

        Each actor owns its own agent subprocess — no shared
        connections, no shared sessions, no registry. The actor
        creates everything it needs from maverick.yaml config.
        """
        if getattr(self, "_session_id", None):
            return  # already running

        await self._create_session()

    async def _prompt(
        self,
        prompt_text: str,
        step_name: str = "decompose",
        *,
        timeout_seconds: int = 1800,
    ):
        """Send a prompt to this actor's own ACP session.

        ``timeout_seconds`` is the per-turn cap the executor enforces via
        ``asyncio.wait_for``. When it elapses, the executor sends an ACP
        CancelNotification so the agent stops, then raises
        ``MaverickTimeoutError`` — which this actor surfaces back to the
        supervisor as a ``prompt_error`` so the supervisor can requeue
        the unit instead of waiting indefinitely.
        """
        from maverick.executor.config import StepConfig

        await self._ensure_agent()

        config = StepConfig(timeout=timeout_seconds)

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

        # Outline is always the initial large prompt — no prior context
        # to reuse. Log before dispatch so session_id (assigned inside
        # _prompt via _ensure_agent) is resolved when the log reaches
        # downstream consumers.
        await self._ensure_agent()
        logger.info(
            "decomposer.prompt_seeded",
            actor=self._actor_tag,
            role=self._role,
            mode="outline",
            session_id=self._session_id,
            prompt_chars=len(prompt_text),
        )
        await self._prompt(prompt_text, "decompose_outline")

    async def _send_detail_prompt(self, message):
        from maverick.library.actions.decompose import (
            build_detail_seed_prompt,
            build_detail_turn_prompt,
        )

        # The bulky outline/flight-plan/verification payloads are
        # stored on this actor via a one-time "set_context" message
        # the supervisor sends before the first detail fan-out. The
        # detail_request itself only carries unit_id(s).
        unit_ids = message.get("unit_ids", [])
        if not unit_ids and message.get("unit_id"):
            unit_ids = [message["unit_id"]]

        needs_seed = await self._ensure_mode_session(
            "detail",
            max_turns=self._detail_session_max_turns,
            seed_stale=self._detail_seed_stale,
        )
        if needs_seed:
            self._detail_seed_stale = True
        prompt_parts = []
        if needs_seed:
            prompt_parts.append(
                build_detail_seed_prompt(
                    flight_plan_content=self._detail_flight_plan,
                    outline_json=self._detail_outline_json,
                    verification_properties=self._detail_verification,
                )
            )
        prompt_parts.append(build_detail_turn_prompt(unit_ids=unit_ids))
        prompt_text = "\n\n".join(prompt_parts)

        prompt_text += (
            "\n\n## REQUIRED: Submit via tool call\n"
            "You MUST call the `submit_details` tool with your results."
        )

        if needs_seed:
            logger.info(
                "decomposer.prompt_seeded",
                actor=self._actor_tag,
                role=self._role,
                mode="detail",
                session_id=self._session_id,
                prompt_chars=len(prompt_text),
                unit_ids=list(unit_ids),
            )
        else:
            logger.info(
                "decomposer.prompt_reused",
                actor=self._actor_tag,
                role=self._role,
                mode="detail",
                session_id=self._session_id,
                turn=self._session_turns_in_mode + 1,
                max_turns=self._detail_session_max_turns,
                prompt_chars=len(prompt_text),
                unit_ids=list(unit_ids),
            )

        # Shorter timeout than outline/fix: a detail is a single work
        # unit, so 20 minutes is generous. Hanging sessions surface as
        # MaverickTimeoutError and the supervisor requeues them.
        await self._prompt(prompt_text, "decompose_detail", timeout_seconds=1200)
        self._detail_seed_stale = False
        self._mark_turn_completed("detail")

    async def _send_fix_prompt(self, message):
        from maverick.library.actions.decompose import build_fix_seed_prompt, build_fix_turn_prompt

        needs_seed = await self._ensure_mode_session(
            "fix",
            max_turns=self._fix_session_max_turns,
            seed_stale=self._fix_seed_stale,
        )
        if needs_seed:
            self._fix_seed_stale = True
        prompt_parts = []
        if needs_seed:
            prompt_parts.append(
                build_fix_seed_prompt(
                    outline_json=self._fix_outline_json,
                    details_json=self._fix_details_json,
                    verification_properties=self._fix_verification,
                )
            )
        prompt_parts.append(
            build_fix_turn_prompt(
                coverage_gaps=message.get("coverage_gaps", []),
                overloaded=message.get("overloaded", []),
            )
        )
        prompt_parts.append(
            "\n\n## REQUIRED: Submit via tool call\n"
            "You MUST call the `submit_fix` tool with the COMPLETE "
            "updated work_units and details."
        )

        fix_prompt_text = "\n\n".join(prompt_parts)
        if needs_seed:
            logger.info(
                "decomposer.prompt_seeded",
                actor=self._actor_tag,
                role=self._role,
                mode="fix",
                session_id=self._session_id,
                prompt_chars=len(fix_prompt_text),
            )
        else:
            logger.info(
                "decomposer.prompt_reused",
                actor=self._actor_tag,
                role=self._role,
                mode="fix",
                session_id=self._session_id,
                turn=self._session_turns_in_mode + 1,
                max_turns=self._fix_session_max_turns,
                prompt_chars=len(fix_prompt_text),
            )

        await self._prompt(fix_prompt_text, "decompose_fix")
        self._fix_seed_stale = False
        self._mark_turn_completed("fix")

    async def _send_nudge(self, message):
        tool_name = message.get("expected_tool", "submit_outline")
        await self._prompt(
            f"Your response was not registered because you did not "
            f"call the `{tool_name}` tool. Please call "
            f"`{tool_name}` now with your results.",
            f"decompose_nudge_{tool_name}",
        )
