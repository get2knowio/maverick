"""RefuelSupervisorActor — Thespian actor that orchestrates decomposition.

The supervisor IS the actor with the inbox. MCP tool calls arrive
directly here. Routing logic is methods on this class. All inter-actor
communication uses Thespian message passing.

The workflow sends "start" and receives "complete" when done.
Everything in between is Thespian messages.
"""

import json

from thespian.actors import Actor

MAX_FIX_ROUNDS = 3


class RefuelSupervisorActor(Actor):
    """Orchestrates flight plan decomposition via message routing.

    Message protocol:
    - "start" from workflow → kicks off outline phase
    - {"tool": ...} from MCP server → tool call result
    - {"type": "prompt_sent"} from decomposer → informational
    - {"type": "prompt_error"} from decomposer → error
    - {"type": "validation_result"} from validator
    - {"type": "beads_created"} from bead creator
    - {"type": "init"} → configure child actor addresses
    """

    def receiveMessage(self, message, sender):
        import sys

        # Log every message for debugging
        msg_preview = str(message)[:200] if message else "None"
        print(
            f"SUPERVISOR: received msg type={type(message).__name__} "
            f"from={sender} preview={msg_preview}",
            file=sys.stderr,
            flush=True,
        )

        # --- Init: receive config and child actor addresses ---
        if isinstance(message, dict) and message.get("type") == "init":
            self._init(message, sender)
            return

        # --- Start signal from workflow ---
        if message == "start":
            self._workflow_sender = sender
            self._start_outline()
            return

        # --- Decomposer prompt confirmation ---
        # Check BEFORE tool routing — prompt_sent may contain a "tool" key
        if isinstance(message, dict) and message.get("type") == "prompt_sent":
            phase = message.get("phase", "")
            print(f"SUPERVISOR: prompt_sent phase={phase}", file=sys.stderr, flush=True)
            self._handle_prompt_sent(phase)
            return

        # --- Tool call from MCP server (via Thespian tell) ---
        if isinstance(message, dict) and "tool" in message:
            print(
                f"SUPERVISOR: tool call received: {message.get('tool')}",
                file=sys.stderr,
                flush=True,
            )
            self._handle_tool_call(message)
            return

        if isinstance(message, dict) and message.get("type") == "prompt_error":
            print(
                f"SUPERVISOR: prompt_error phase={message.get('phase')} error={message.get('error')}",
                file=sys.stderr,
                flush=True,
            )
            self._handle_error(
                f"Decomposer error ({message.get('phase')}): {message.get('error')}"
            )
            return

        # --- Validation result ---
        if isinstance(message, dict) and message.get("type") == "validation_result":
            self._handle_validation(message)
            return

        # --- Beads created ---
        if isinstance(message, dict) and message.get("type") == "beads_created":
            self._handle_beads_created(message)
            return

        # --- Init acks from child actors ---
        if isinstance(message, dict) and message.get("type") == "init_ok":
            return

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def _init(self, message, sender):
        """Store config and create child actors."""
        self._config = message.get("config", {})
        self._decomposer = message.get("decomposer_addr")
        self._validator = message.get("validator_addr")
        self._bead_creator = message.get("bead_creator_addr")

        # State
        self._outline = None
        self._details = None
        self._specs = []
        self._fix_rounds = 0
        self._nudge_count = 0
        self._workflow_sender = None
        self._initial_payload = message.get("initial_payload", {})

        self.send(sender, {"type": "init_ok"})

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def _start_outline(self):
        """Kick off the outline phase."""
        self.send(
            self._decomposer,
            {
                "type": "outline_request",
                **self._initial_payload,
            },
        )

    def _handle_prompt_sent(self, phase):
        """Check if expected tool call arrived; nudge if not."""
        import sys

        MAX_NUDGES = 2
        # Map phase to expected tool and state check
        phase_tool_map = {
            "outline": ("submit_outline", lambda: self._outline is not None),
            "detail": ("submit_details", lambda: self._details is not None),
            "fix": ("submit_fix", lambda: self._fix_rounds > 0 and self._details is not None),
        }

        if phase not in phase_tool_map:
            return

        tool_name, check_fn = phase_tool_map[phase]
        if check_fn():
            # Tool call already arrived — nothing to do
            return

        if self._nudge_count >= MAX_NUDGES:
            print(
                f"SUPERVISOR: max nudges reached for {phase}, skipping",
                file=sys.stderr,
                flush=True,
            )
            return

        self._nudge_count += 1
        print(
            f"SUPERVISOR: prompt completed but no {tool_name} received, "
            f"nudging decomposer (attempt {self._nudge_count})",
            file=sys.stderr,
            flush=True,
        )
        self.send(
            self._decomposer,
            {
                "type": "nudge",
                "expected_tool": tool_name,
            },
        )

    def _handle_tool_call(self, message):
        """Route MCP tool call to appropriate handler."""
        tool = message.get("tool", "")
        args = message.get("arguments", {})
        self._nudge_count = 0  # Reset on successful tool call

        if tool == "submit_outline":
            self._outline = args
            unit_ids = [
                wu.get("id", "") for wu in args.get("work_units", []) if isinstance(wu, dict)
            ]
            outline_json = json.dumps(args)

            self.send(
                self._decomposer,
                {
                    "type": "detail_request",
                    "unit_ids": unit_ids,
                    "outline_json": outline_json,
                    "flight_plan_content": self._initial_payload.get("flight_plan_content", ""),
                    "verification_properties": self._initial_payload.get(
                        "verification_properties", ""
                    ),
                },
            )

        elif tool == "submit_details":
            self._details = args
            self._specs = self._merge_to_specs()
            self.send(
                self._validator,
                {
                    "type": "validate",
                    "specs": self._specs,
                },
            )

        elif tool == "submit_fix":
            if args.get("work_units"):
                self._outline = {"work_units": args["work_units"]}
            if args.get("details"):
                self._details = {"details": args["details"]}
            self._specs = self._merge_to_specs()
            self.send(
                self._validator,
                {
                    "type": "validate",
                    "specs": self._specs,
                },
            )

    def _handle_validation(self, message):
        """Route validation result."""
        if message.get("passed"):
            deps = self._extract_deps()
            self.send(
                self._bead_creator,
                {
                    "type": "create_beads",
                    "specs": self._specs,
                    "deps": deps,
                },
            )
        elif self._fix_rounds < MAX_FIX_ROUNDS:
            self._fix_rounds += 1
            gaps = message.get("gaps", [])
            enriched = self._enrich_gaps(gaps)
            self.send(
                self._decomposer,
                {
                    "type": "fix_request",
                    "coverage_gaps": enriched,
                    "overloaded": message.get("overloaded", []),
                },
            )
        else:
            # Exhausted — proceed with what we have
            deps = self._extract_deps()
            self.send(
                self._bead_creator,
                {
                    "type": "create_beads",
                    "specs": self._specs,
                    "deps": deps,
                },
            )

    def _handle_beads_created(self, message):
        """Decomposition complete — shutdown agents, reply to workflow."""
        if self._decomposer:
            self.send(self._decomposer, {"type": "shutdown"})
        if self._workflow_sender:
            self.send(
                self._workflow_sender,
                {
                    "type": "complete",
                    "success": message.get("success", False),
                    "epic_id": message.get("epic_id", ""),
                    "bead_count": message.get("bead_count", 0),
                    "specs": self._specs,
                    "fix_rounds": self._fix_rounds,
                },
            )

    def _handle_error(self, error_msg):
        """Report error to workflow — shutdown agents first."""
        if self._decomposer:
            self.send(self._decomposer, {"type": "shutdown"})
        if self._workflow_sender:
            self.send(
                self._workflow_sender,
                {
                    "type": "complete",
                    "success": False,
                    "error": error_msg,
                    "specs": self._specs,
                    "fix_rounds": self._fix_rounds,
                },
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _merge_to_specs(self):
        """Merge outline + details into WorkUnitSpec list."""
        from maverick.workflows.refuel_maverick.models import WorkUnitSpec

        work_units = self._outline.get("work_units", []) if self._outline else []
        details = self._details.get("details", []) if self._details else []

        detail_map = {}
        for d in details:
            if isinstance(d, dict):
                detail_map[d.get("id", "")] = d

        specs = []
        for wu in work_units:
            if not isinstance(wu, dict):
                continue
            wu_id = wu.get("id", "")
            detail = detail_map.get(wu_id, {})
            merged = {
                "id": wu_id,
                "task": wu.get("task", ""),
                "sequence": wu.get("sequence", 0),
                "parallel_group": wu.get("parallel_group"),
                "depends_on": wu.get("depends_on", []),
                "file_scope": wu.get("file_scope", {}),
                "instructions": detail.get("instructions", ""),
                "acceptance_criteria": detail.get("acceptance_criteria", []),
                "verification": detail.get("verification", []),
                "test_specification": detail.get("test_specification", ""),
            }
            try:
                specs.append(WorkUnitSpec.model_validate(merged))
            except Exception:
                specs.append(merged)
        return specs

    def _extract_deps(self):
        deps = []
        for spec in self._specs:
            sid = spec.id if hasattr(spec, "id") else spec.get("id", "")
            dep_list = (
                spec.depends_on if hasattr(spec, "depends_on") else spec.get("depends_on", [])
            )
            for dep_id in dep_list:
                deps.append([sid, dep_id])
        return deps

    def _enrich_gaps(self, gaps):
        flight_plan = self._config.get("flight_plan")
        if not flight_plan:
            return gaps

        sc_list = getattr(flight_plan, "success_criteria", [])
        sc_map = {}
        for i, sc in enumerate(sc_list):
            ref = getattr(sc, "ref", None) or f"SC-{i + 1:03d}"
            text = getattr(sc, "text", str(sc))
            sc_map[ref] = text

        enriched = []
        for gap in gaps:
            for ref, text in sc_map.items():
                if ref in gap:
                    gap = f"{gap} — Full text: {text}"
                    break
            enriched.append(gap)
        return enriched
