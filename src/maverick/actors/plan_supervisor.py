"""PlanSupervisorActor — Thespian actor for flight plan generation.

Routes messages between briefing agents (parallel fan-out),
contrarian, generator, validator, and writer. Collects briefing
results and synthesizes them inline.
"""

import json
import sys

from thespian.actors import Actor


class PlanSupervisorActor(Actor):
    """Orchestrates flight plan generation via message routing.

    Fan-out: sends to 3 briefing agents simultaneously
    Fan-in: collects results, routes to contrarian when complete
    Sequential: contrarian → synthesize → generate → validate → write
    """

    def receiveMessage(self, message, sender):
        msg_preview = str(message)[:150] if message else "None"
        print(
            f"PLAN_SUPERVISOR: received from={sender} "
            f"preview={msg_preview}",
            file=sys.stderr, flush=True,
        )

        # --- Init ---
        if isinstance(message, dict) and message.get("type") == "init":
            self._init(message, sender)
            return

        if isinstance(message, dict) and message.get("type") == "init_ok":
            return

        # --- Start ---
        if message == "start":
            self._workflow_sender = sender
            if self._skip_briefing:
                self._send_to_generator()
            else:
                self._start_briefing()
            return

        # --- MCP tool calls from agents ---
        if isinstance(message, dict) and "tool" in message:
            tool = message["tool"]
            args = message.get("arguments", {})
            print(
                f"PLAN_SUPERVISOR: tool call: {tool}",
                file=sys.stderr, flush=True,
            )
            self._handle_tool_call(tool, args)
            return

        # --- Prompt confirmations (informational) ---
        if isinstance(message, dict) and message.get("type") == "prompt_sent":
            return

        if isinstance(message, dict) and message.get("type") == "prompt_error":
            error = message.get("error", "unknown")
            print(
                f"PLAN_SUPERVISOR: prompt error: {error}",
                file=sys.stderr, flush=True,
            )
            self._handle_error(f"Agent error: {error}")
            return

        # --- Validation result ---
        if isinstance(message, dict) and message.get("type") == "validation_result":
            self._handle_validation(message)
            return

        # --- Write result ---
        if isinstance(message, dict) and message.get("type") == "write_result":
            self._handle_write_complete(message)
            return

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def _init(self, message, sender):
        self._prd_content = message.get("prd_content", "")
        self._plan_name = message.get("plan_name", "")
        self._skip_briefing = message.get("skip_briefing", False)

        # Child actor addresses
        self._scopist = message.get("scopist_addr")
        self._analyst = message.get("analyst_addr")
        self._criteria = message.get("criteria_addr")
        self._contrarian = message.get("contrarian_addr")
        self._generator = message.get("generator_addr")
        self._validator = message.get("validator_addr")
        self._writer = message.get("writer_addr")

        # State
        self._briefs = {}
        self._briefing_markdown = ""
        self._flight_plan_data = {}
        self._workflow_sender = None

        self.send(sender, {"type": "init_ok"})

    # ------------------------------------------------------------------
    # Briefing fan-out
    # ------------------------------------------------------------------

    def _start_briefing(self):
        """Send briefing requests to 3 agents in parallel."""
        from maverick.agents.preflight_briefing.prompts import (
            build_preflight_briefing_prompt,
        )

        prompt = build_preflight_briefing_prompt(self._prd_content)

        # Fan-out: 3 messages sent, Thespian delivers to 3 separate
        # actor processes which run in parallel
        self.send(self._scopist, {"type": "briefing", "prompt": prompt})
        self.send(self._analyst, {"type": "briefing", "prompt": prompt})
        self.send(self._criteria, {"type": "briefing", "prompt": prompt})

        print(
            "PLAN_SUPERVISOR: briefing fan-out sent (3 agents)",
            file=sys.stderr, flush=True,
        )

    # ------------------------------------------------------------------
    # Tool call routing
    # ------------------------------------------------------------------

    def _handle_tool_call(self, tool, args):
        # Briefing results
        if tool == "submit_scope":
            self._briefs["scope"] = args
            self._check_briefing_complete()

        elif tool == "submit_analysis":
            self._briefs["analysis"] = args
            self._check_briefing_complete()

        elif tool == "submit_criteria":
            self._briefs["criteria"] = args
            self._check_briefing_complete()

        elif tool == "submit_challenge":
            self._briefs["challenge"] = args
            self._synthesize_and_generate()

        elif tool == "submit_flight_plan":
            self._flight_plan_data = args
            self._send_to_validator()

    def _check_briefing_complete(self):
        """Check if all 3 briefing results arrived."""
        needed = ("scope", "analysis", "criteria")
        arrived = [k for k in needed if k in self._briefs]
        print(
            f"PLAN_SUPERVISOR: briefs collected: {arrived} "
            f"(need all 3)",
            file=sys.stderr, flush=True,
        )

        if all(k in self._briefs for k in needed):
            self._send_to_contrarian()

    def _send_to_contrarian(self):
        """All 3 briefs collected — send to contrarian."""
        from maverick.agents.preflight_briefing.prompts import (
            build_preflight_contrarian_prompt,
        )

        prompt = build_preflight_contrarian_prompt(
            self._prd_content,
            self._briefs.get("scope", {}),
            self._briefs.get("analysis", {}),
            self._briefs.get("criteria", {}),
        )

        self.send(self._contrarian, {"type": "briefing", "prompt": prompt})

    def _synthesize_and_generate(self):
        """Contrarian done — synthesize briefing and send to generator."""
        from maverick.preflight_briefing.serializer import (
            serialize_briefing_to_markdown,
        )
        from maverick.preflight_briefing.synthesis import (
            synthesize_preflight_briefing,
        )
        from maverick.preflight_briefing.models import (
            CodebaseAnalystBrief,
            CriteriaWriterBrief,
            PreFlightContrarianBrief,
            ScopistBrief,
        )

        try:
            scopist = ScopistBrief.model_validate(
                self._briefs.get("scope", {})
            )
            analyst = CodebaseAnalystBrief.model_validate(
                self._briefs.get("analysis", {})
            )
            criteria = CriteriaWriterBrief.model_validate(
                self._briefs.get("criteria", {})
            )
            contrarian = PreFlightContrarianBrief.model_validate(
                self._briefs.get("challenge", {})
            )

            briefing_doc = synthesize_preflight_briefing(
                self._plan_name, scopist, analyst, criteria, contrarian
            )
            self._briefing_markdown = serialize_briefing_to_markdown(
                briefing_doc
            )
        except Exception as exc:
            print(
                f"PLAN_SUPERVISOR: synthesis failed: {exc}, using raw JSON",
                file=sys.stderr, flush=True,
            )
            # Fallback: raw JSON of briefs
            parts = []
            for key, data in self._briefs.items():
                parts.append(f"## {key}\n\n{json.dumps(data, indent=2)}")
            self._briefing_markdown = "\n\n".join(parts)

        self._send_to_generator()

    def _send_to_generator(self):
        """Send PRD + briefing to generator."""
        parts = [f"## PRD Content\n\n{self._prd_content}"]
        if self._briefing_markdown:
            parts.append(
                f"## Pre-Flight Briefing\n\n{self._briefing_markdown}"
            )
        prompt = "\n\n".join(parts)

        self.send(self._generator, {"type": "generate", "prompt": prompt})

    def _send_to_validator(self):
        """Send flight plan to validator."""
        self.send(self._validator, {
            "type": "validate",
            "flight_plan": self._flight_plan_data,
        })

    # ------------------------------------------------------------------
    # Validation + Write
    # ------------------------------------------------------------------

    def _handle_validation(self, message):
        passed = message.get("passed", False)
        if not passed:
            print(
                f"PLAN_SUPERVISOR: validation failed: {message.get('warnings')}",
                file=sys.stderr, flush=True,
            )
        # Write regardless — validation is non-blocking for plan
        self.send(self._writer, {
            "type": "write",
            "flight_plan_markdown": json.dumps(
                self._flight_plan_data, indent=2, default=str
            ),
            "briefing_markdown": self._briefing_markdown,
        })

    def _handle_write_complete(self, message):
        """Plan written — shutdown agents, send complete to workflow."""
        # Shutdown agent actors (cleanup ACP subprocesses)
        for addr in [
            self._scopist, self._analyst, self._criteria,
            self._contrarian, self._generator,
        ]:
            if addr:
                self.send(addr, {"type": "shutdown"})

        sc_count = len(self._flight_plan_data.get("success_criteria", []))
        print(
            f"PLAN_SUPERVISOR: complete ({sc_count} SCs)",
            file=sys.stderr, flush=True,
        )
        if self._workflow_sender:
            self.send(self._workflow_sender, {
                "type": "complete",
                "success": True,
                "flight_plan_path": message.get("flight_plan_path", ""),
                "briefing_path": message.get("briefing_path"),
                "success_criteria_count": sc_count,
                "validation_passed": True,
            })

    def _handle_error(self, error_msg):
        for addr in [
            self._scopist, self._analyst, self._criteria,
            self._contrarian, self._generator,
        ]:
            if addr:
                self.send(addr, {"type": "shutdown"})

        if self._workflow_sender:
            self.send(self._workflow_sender, {
                "type": "complete",
                "success": False,
                "error": error_msg,
            })
