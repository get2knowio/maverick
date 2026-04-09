"""ReviewerActor — Thespian actor for code review.

Self-contained: spawns own ACP agent, creates new session per bead.
Keeps ACP connection alive across beads. Calls submit_review MCP tool.
On follow-up reviews, the session preserves conversation history.

Also handles aggregate (post-flight) reviews across all beads.
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
            self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
            self._thread.start()
            self.send(sender, {"type": "init_ok"})

        elif msg_type == "new_bead":
            self._review_count = 0
            try:
                future = asyncio.run_coroutine_threadsafe(self._new_session(), self._loop)
                future.result(timeout=30)
                self.send(sender, {"type": "session_ready"})
            except Exception as exc:
                self.send(
                    sender,
                    {
                        "type": "prompt_error",
                        "phase": "new_bead",
                        "error": str(exc),
                    },
                )

        elif msg_type == "review":
            self._review_count += 1
            self._run_prompt(message, sender)

        elif msg_type == "aggregate_review":
            self._run_aggregate_review(message, sender)

        elif msg_type == "shutdown":
            if self._executor:
                try:
                    asyncio.run_coroutine_threadsafe(self._executor.cleanup(), self._loop).result(
                        timeout=5
                    )
                except Exception:
                    pass
            self.send(sender, {"type": "shutdown_ok"})

    def _run_prompt(self, message, sender):
        print(
            f"REVIEWER: starting review #{self._review_count}...",
            file=sys.stderr,
            flush=True,
        )
        try:
            future = asyncio.run_coroutine_threadsafe(self._send_review(message), self._loop)
            future.result(timeout=1200)
            print(
                f"REVIEWER: review #{self._review_count} completed!",
                file=sys.stderr,
                flush=True,
            )
            self.send(
                sender,
                {
                    "type": "prompt_sent",
                    "phase": "review",
                    "review_count": self._review_count,
                },
            )
        except Exception as exc:
            print(
                f"REVIEWER: review FAILED: {exc}",
                file=sys.stderr,
                flush=True,
            )
            self.send(
                sender,
                {
                    "type": "prompt_error",
                    "phase": "review",
                    "error": str(exc),
                },
            )

    def _run_aggregate_review(self, message, sender):
        """Run post-flight aggregate review across all beads."""
        print(
            f"REVIEWER: starting aggregate review ({message.get('bead_count', 0)} beads)...",
            file=sys.stderr,
            flush=True,
        )
        try:
            # Create a fresh session for aggregate review
            future = asyncio.run_coroutine_threadsafe(self._new_session(), self._loop)
            future.result(timeout=30)

            future = asyncio.run_coroutine_threadsafe(
                self._send_aggregate_review(message), self._loop
            )
            future.result(timeout=600)
            print(
                "REVIEWER: aggregate review completed!",
                file=sys.stderr,
                flush=True,
            )
            self.send(
                sender,
                {
                    "type": "aggregate_review_complete",
                    "findings": [],  # Findings delivered via MCP tool call
                },
            )
        except Exception as exc:
            print(
                f"REVIEWER: aggregate review FAILED: {exc}",
                file=sys.stderr,
                flush=True,
            )
            # Don't block completion on aggregate review failure
            self.send(
                sender,
                {
                    "type": "aggregate_review_complete",
                    "findings": [],
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
                "submit_review",
                "--admin-port",
                str(self._admin_port),
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
        work_unit_md = message.get("work_unit_md", "")
        briefing_context = message.get("briefing_context", "")

        if self._review_count == 1:
            # Build enriched first-review prompt
            parts = [
                "Review the code changes in the working directory.\n",
            ]

            if work_unit_md:
                parts.append(f"## Work Unit Specification\n\n{work_unit_md}\n")
            else:
                parts.append(f"## Task Description\n\n{bead_description}\n")

            if briefing_context:
                # Cap briefing to avoid overwhelming the reviewer
                briefing_excerpt = briefing_context[:4000]
                parts.append(
                    f"## Pre-Flight Briefing (risks & contrarian findings)\n\n{briefing_excerpt}\n"
                )

            parts.append(
                "## Historical Context (Runway)\n\n"
                "Check `.maverick/runway/` for project knowledge:\n"
                "- `episodic/review-findings.jsonl` — prior review findings "
                "and resolutions\n"
                "- `episodic/bead-outcomes.jsonl` — what worked and what didn't\n"
                "- `semantic/` — architecture notes and decision records\n\n"
                "Read these if they exist — they may reveal recurring issues "
                "or architectural decisions relevant to this review.\n\n"
                "## Review Instructions\n\n"
                "1. Check that the implementation satisfies ALL acceptance "
                "criteria listed in the work unit specification above.\n"
                "2. Check for bugs, security issues, and correctness.\n"
                "3. Verify the approach aligns with the briefing's risk "
                "assessment and contrarian findings.\n"
                "4. Only flag CRITICAL or MAJOR issues.\n\n"
                "## REQUIRED: Submit via tool call\n"
                "Call the `submit_review` tool. Set approved=true if "
                "no critical/major issues."
            )

            prompt = "\n".join(parts)
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

    async def _send_aggregate_review(self, message):
        """Send aggregate review prompt for cross-bead analysis."""
        from maverick.executor.config import StepConfig

        await self._ensure_executor()
        if not self._session_id:
            await self._new_session()

        objective = message.get("objective", "")
        bead_list = message.get("bead_list", "")
        diff_stat = message.get("diff_stat", "")

        prompt = (
            "Review the AGGREGATE changes across all beads in this epic.\n\n"
            f"## Flight Plan\n\n{objective}\n\n"
            f"## Beads Completed\n\n{bead_list}\n\n"
            f"## Full Diff Stats\n\n```\n{diff_stat}\n```\n\n"
            "## Focus Areas\n\n"
            "- Cross-bead consistency: are deleted modules still "
            "referenced elsewhere?\n"
            "- Architectural coherence: do the approaches across "
            "beads align with each other?\n"
            "- Missing integration between beads\n"
            "- Dead code left behind by one bead that another "
            "bead depended on\n\n"
            "Do NOT re-review individual bead correctness — that "
            "was already done per-bead.\n\n"
            "## REQUIRED: Submit via tool call\n"
            "Call the `submit_review` tool. Set approved=true if "
            "no cross-bead concerns found."
        )

        await self._executor.prompt_session(
            session_id=self._session_id,
            prompt_text=prompt,
            config=StepConfig(timeout=600),
            step_name="aggregate_review",
            agent_name="reviewer",
        )
