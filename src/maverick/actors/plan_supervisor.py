"""PlanSupervisorActor — Thespian actor for flight plan generation.

Routes messages between briefing agents (parallel fan-out),
contrarian, generator, validator, and writer. Collects briefing
results and synthesizes them inline.

The workflow sends "start" and then drains progress events via
``{"type": "get_events", "since": int}`` polls until the supervisor
marks itself done. The terminal result rides on the final
``done=True`` reply — see ``SupervisorEventBusMixin``.
"""

import json

from thespian.actors import Actor

from maverick.actors.event_bus import SupervisorEventBusMixin
from maverick.logging import get_logger

_SOURCE = "plan-supervisor"

logger = get_logger(__name__)


class PlanSupervisorActor(SupervisorEventBusMixin, Actor):
    """Orchestrates flight plan generation via message routing.

    Fan-out: sends to 3 briefing agents simultaneously
    Fan-in: collects results, routes to contrarian when complete
    Sequential: contrarian → synthesize → generate → validate → write
    """

    def receiveMessage(self, message, sender):
        logger.debug(
            "plan_supervisor.received",
            msg_type=type(message).__name__,
            preview=str(message)[:150] if message else "None",
        )

        # --- Init ---
        if isinstance(message, dict) and message.get("type") == "init":
            self._init(message, sender)
            return

        if isinstance(message, dict) and message.get("type") == "init_ok":
            return

        # --- Event-bus drain poll (must precede other dict routing) ---
        if isinstance(message, dict) and message.get("type") == "get_events":
            self._handle_get_events(message, sender)
            return

        # --- Start ---
        if message == "start":
            if self._skip_briefing:
                self._emit_output(
                    "plan",
                    "Skipping briefing; sending directly to generator",
                    level="info",
                    source=_SOURCE,
                )
                self._send_to_generator()
            else:
                self._start_briefing()
            return

        # --- Prompt confirmations (informational) ---
        # Check BEFORE tool routing — prompt_sent messages also have
        # a "tool" key, so they'd be misrouted otherwise.
        if isinstance(message, dict) and message.get("type") == "prompt_sent":
            return

        # --- MCP tool calls from agents ---
        if isinstance(message, dict) and "tool" in message:
            tool = message["tool"]
            args = message.get("arguments", {})
            self._handle_tool_call(tool, args)
            return

        if isinstance(message, dict) and message.get("type") == "prompt_error":
            error = message.get("error", "unknown")
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
        self._init_event_bus()
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

        # Provider labels for CLI display (resolved by workflow from config)
        self._provider_labels: dict[str, str] = message.get("provider_labels", {})

        # State
        self._briefs = {}
        self._briefing_markdown = ""
        self._flight_plan_data = {}
        self._briefing_start_times: dict[str, float] = {}

        self.send(sender, {"type": "init_ok"})

    # ------------------------------------------------------------------
    # Briefing fan-out
    # ------------------------------------------------------------------

    def _start_briefing(self):
        """Send briefing requests to 3 agents in parallel."""
        import time as _time

        from maverick.agents.preflight_briefing.prompts import (
            build_preflight_briefing_prompt,
        )

        prompt = build_preflight_briefing_prompt(self._prd_content)

        self._briefing_start_times = {}

        # Emit agent-started events for Rich Live display
        for name in ("Scopist", "Codebase Analyst", "Criteria Writer"):
            self._emit_agent_started("briefing", name, self._provider_labels.get(name, ""))
            self._briefing_start_times[name] = _time.monotonic()

        # Fan-out: 3 messages sent, Thespian delivers to 3 separate
        # actor processes which run in parallel
        self.send(self._scopist, {"type": "briefing", "prompt": prompt})
        self.send(self._analyst, {"type": "briefing", "prompt": prompt})
        self.send(self._criteria, {"type": "briefing", "prompt": prompt})

    # ------------------------------------------------------------------
    # Tool call routing
    # ------------------------------------------------------------------

    def _handle_tool_call(self, tool, args):
        import time as _time

        # Briefing results
        if tool == "submit_scope":
            self._briefs["scope"] = args
            elapsed = _time.monotonic() - self._briefing_start_times.get("Scopist", 0)
            self._emit_agent_completed("briefing", "Scopist", elapsed)
            self._check_briefing_complete()

        elif tool == "submit_analysis":
            self._briefs["analysis"] = args
            elapsed = _time.monotonic() - self._briefing_start_times.get("Codebase Analyst", 0)
            self._emit_agent_completed("briefing", "Codebase Analyst", elapsed)
            self._check_briefing_complete()

        elif tool == "submit_criteria":
            self._briefs["criteria"] = args
            elapsed = _time.monotonic() - self._briefing_start_times.get("Criteria Writer", 0)
            self._emit_agent_completed("briefing", "Criteria Writer", elapsed)
            self._check_briefing_complete()

        elif tool == "submit_challenge":
            self._briefs["challenge"] = args
            elapsed = _time.monotonic() - self._briefing_start_times.get("Contrarian", 0)
            self._emit_agent_completed("briefing", "Contrarian", elapsed)
            self._synthesize_and_generate()

        elif tool == "submit_flight_plan":
            self._flight_plan_data = args
            sc_count = len(args.get("success_criteria", []))
            self._emit_output(
                "plan",
                f"Flight plan generated ({sc_count} success criteria); validating",
                level="success",
                source=_SOURCE,
                metadata={"success_criteria_count": sc_count},
            )
            self._send_to_validator()

    def _check_briefing_complete(self):
        """Check if all 3 briefing results arrived."""
        needed = ("scope", "analysis", "criteria")
        if all(k in self._briefs for k in needed):
            # Guard against duplicate triggers
            if not getattr(self, "_contrarian_sent", False):
                self._contrarian_sent = True
                self._emit_output(
                    "plan",
                    "All 3 briefs collected; sending to contrarian",
                    level="info",
                    source=_SOURCE,
                )
                self._send_to_contrarian()

    def _send_to_contrarian(self):
        """All 3 briefs collected — send to contrarian."""
        import time as _time

        self._emit_agent_started(
            "briefing", "Contrarian", self._provider_labels.get("Contrarian", "")
        )
        self._briefing_start_times["Contrarian"] = _time.monotonic()

        # Build contrarian prompt manually since the briefs are raw
        # dicts (from MCP tool calls), not Pydantic models.
        scope_json = json.dumps(self._briefs.get("scope", {}), indent=2)
        analysis_json = json.dumps(self._briefs.get("analysis", {}), indent=2)
        criteria_json = json.dumps(self._briefs.get("criteria", {}), indent=2)

        prompt = (
            f"## PRD Content\n\n{self._prd_content}\n\n"
            f"## Scopist Analysis\n\n```json\n{scope_json}\n```\n\n"
            f"## Codebase Analysis\n\n```json\n{analysis_json}\n```\n\n"
            f"## Success Criteria\n\n```json\n{criteria_json}\n```\n\n"
            f"Challenge these analyses. Identify risks, blind spots, "
            f"and missing considerations."
        )

        self.send(self._contrarian, {"type": "briefing", "prompt": prompt})

    def _synthesize_and_generate(self):
        """Contrarian done — synthesize briefing and send to generator."""
        from maverick.preflight_briefing.serializer import serialize_briefs_to_markdown

        self._briefing_markdown = serialize_briefs_to_markdown(
            self._plan_name,
            scope=self._briefs.get("scope"),
            analysis=self._briefs.get("analysis"),
            criteria=self._briefs.get("criteria"),
            challenge=self._briefs.get("challenge"),
        )

        self._send_to_generator()

    def _send_to_generator(self):
        """Send PRD + briefing to generator."""
        self._emit_output(
            "plan",
            "Sending briefing to flight-plan generator",
            level="info",
            source=_SOURCE,
        )
        parts = [f"## PRD Content\n\n{self._prd_content}"]
        if self._briefing_markdown:
            parts.append(f"## Pre-Flight Briefing\n\n{self._briefing_markdown}")
        prompt = "\n\n".join(parts)

        self.send(self._generator, {"type": "generate", "prompt": prompt})

    def _send_to_validator(self):
        """Send flight plan to validator."""
        self.send(
            self._validator,
            {
                "type": "validate",
                "flight_plan": self._flight_plan_data,
            },
        )

    # ------------------------------------------------------------------
    # Validation + Write
    # ------------------------------------------------------------------

    def _handle_validation(self, message):
        passed = message.get("passed", False)
        if not passed:
            warnings = message.get("warnings", [])
            self._emit_output(
                "plan",
                f"Validation warnings ({len(warnings)}); continuing to write",
                level="warning",
                source=_SOURCE,
                metadata={"warning_count": len(warnings)},
            )
        else:
            self._emit_output(
                "plan",
                "Validation passed",
                level="success",
                source=_SOURCE,
            )
        # Write regardless — validation is non-blocking for plan
        # Format flight plan data as markdown with YAML frontmatter
        from datetime import date

        fp = self._flight_plan_data
        sc_list = fp.get("success_criteria", [])

        # Default objective from PRD first line if agent didn't provide one
        default_objective = self._prd_content.split("\n")[0].lstrip("#").strip()[:200]
        frontmatter = {
            "name": self._plan_name,
            "version": "1",
            "created": str(date.today()),
            "objective": fp.get("objective") or default_objective,
            "tags": fp.get("tags", []),
            "scope": fp.get(
                "scope",
                {
                    "in_scope": fp.get("in_scope", []),
                    "out_of_scope": fp.get("out_of_scope", []),
                    "boundaries": fp.get("boundaries", []),
                },
            ),
        }

        import yaml as _yaml

        fm_str = _yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)

        objective = fp.get("objective") or default_objective

        body_parts = [f"# {self._plan_name}\n"]

        # Objective — required by parser
        body_parts.append(f"## Objective\n\n{objective}\n")

        if fp.get("context"):
            body_parts.append(f"## Context\n\n{fp['context']}\n")

        # Success Criteria — parser expects checkbox format
        body_parts.append("## Success Criteria\n")
        for sc in sc_list:
            if isinstance(sc, dict):
                desc = sc.get("description", str(sc))
            else:
                desc = str(sc)
            body_parts.append(f"- [ ] {desc}")

        # Scope — parser expects ## Scope with ### In / ### Out
        in_scope = fp.get("in_scope", [])
        out_of_scope = fp.get("out_of_scope", [])
        if in_scope or out_of_scope:
            body_parts.append("\n## Scope\n")
            if in_scope:
                body_parts.append("### In\n")
                for item in in_scope:
                    body_parts.append(f"- {item}")
            if out_of_scope:
                body_parts.append("\n### Out\n")
                for item in out_of_scope:
                    body_parts.append(f"- {item}")

        if fp.get("constraints"):
            body_parts.append("\n## Constraints\n")
            for item in fp["constraints"]:
                body_parts.append(f"- {item}")

        flight_plan_md = f"---\n{fm_str}---\n\n" + "\n".join(body_parts) + "\n"

        self.send(
            self._writer,
            {
                "type": "write",
                "flight_plan_markdown": flight_plan_md,
                "briefing_markdown": self._briefing_markdown,
            },
        )

    def _handle_write_complete(self, message):
        """Plan written — shutdown agents, mark done."""
        # Shutdown agent actors (cleanup ACP subprocesses)
        for addr in [
            self._scopist,
            self._analyst,
            self._criteria,
            self._contrarian,
            self._generator,
        ]:
            if addr:
                self.send(addr, {"type": "shutdown"})

        sc_count = len(self._flight_plan_data.get("success_criteria", []))
        self._emit_output(
            "plan",
            f"Flight plan written ({sc_count} success criteria)",
            level="success",
            source=_SOURCE,
            metadata={"success_criteria_count": sc_count},
        )
        self._mark_done(
            {
                "success": True,
                "flight_plan_path": message.get("flight_plan_path", ""),
                "briefing_path": message.get("briefing_path"),
                "success_criteria_count": sc_count,
                "validation_passed": True,
            }
        )

    def _handle_error(self, error_msg):
        for addr in [
            self._scopist,
            self._analyst,
            self._criteria,
            self._contrarian,
            self._generator,
        ]:
            if addr:
                self.send(addr, {"type": "shutdown"})

        self._emit_output(
            "plan",
            f"Plan generation failed: {error_msg}",
            level="error",
            source=_SOURCE,
        )
        self._mark_done(
            {
                "success": False,
                "error": error_msg,
            }
        )
