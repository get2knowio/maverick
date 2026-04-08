"""FlySupervisorActor — Thespian actor for bead-driven development.

Owns the entire fly lifecycle: bead selection, per-bead routing
(implement → gate → review → commit), and bead loop management.
All actors persist for the fly session; agent actors create new
ACP sessions per bead.
"""

import asyncio
import json
import sys

from thespian.actors import Actor

MAX_REVIEW_ROUNDS = 3
MAX_GATE_FIX_ATTEMPTS = 2


class FlySupervisorActor(Actor):
    """Orchestrates the full fly bead loop."""

    def receiveMessage(self, message, sender):
        msg_preview = str(message)[:120] if message else "None"
        print(
            f"FLY_SUPERVISOR: msg from={sender} preview={msg_preview}",
            file=sys.stderr, flush=True,
        )

        if isinstance(message, dict) and message.get("type") == "init":
            self._init(message, sender)
            return

        if isinstance(message, dict) and message.get("type") == "init_ok":
            return

        if isinstance(message, dict) and message.get("type") == "session_ready":
            return

        if message == "start":
            self._workflow_sender = sender
            self._next_bead()
            return

        # Agent prompt confirmations — check BEFORE tool routing
        # since prompt_sent may contain a "tool" key
        if isinstance(message, dict) and message.get("type") == "prompt_sent":
            return

        # MCP tool calls from agents
        if isinstance(message, dict) and "tool" in message:
            self._handle_tool_call(message)
            return

        if isinstance(message, dict) and message.get("type") == "prompt_error":
            print(
                f"FLY_SUPERVISOR: prompt error: {message.get('error')}",
                file=sys.stderr, flush=True,
            )
            # Treat as gate failure — move on
            self._commit_bead(tag="needs-human-review")
            return

        # Gate result
        if isinstance(message, dict) and message.get("type") == "gate_result":
            self._handle_gate_result(message)
            return

        # AC result
        if isinstance(message, dict) and message.get("type") == "ac_result":
            self._handle_ac_result(message)
            return

        # Spec result
        if isinstance(message, dict) and message.get("type") == "spec_result":
            self._handle_spec_result(message)
            return

        # Commit result
        if isinstance(message, dict) and message.get("type") == "commit_result":
            self._handle_commit_result(message)
            return

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def _init(self, message, sender):
        self._epic_id = message.get("epic_id", "")
        self._cwd = message.get("cwd")
        self._config = message.get("config", {})

        # Actor addresses
        self._implementer = message.get("implementer_addr")
        self._reviewer = message.get("reviewer_addr")
        self._gate = message.get("gate_addr")
        self._ac = message.get("ac_addr")
        self._spec = message.get("spec_addr")
        self._committer = message.get("committer_addr")

        # State
        self._workflow_sender = None
        self._completed_beads = []
        self._current_bead = None
        self._review_rounds = 0
        self._gate_fix_attempts = 0

        self.send(sender, {"type": "init_ok"})

    # ------------------------------------------------------------------
    # Bead loop
    # ------------------------------------------------------------------

    def _next_bead(self):
        """Select and process the next bead."""
        try:
            select_result = asyncio.run(self._select_next_bead())
        except Exception as exc:
            print(
                f"FLY_SUPERVISOR: bead selection failed: {exc}",
                file=sys.stderr, flush=True,
            )
            self._complete()
            return

        if select_result.get("done") or not select_result.get("found"):
            print(
                f"FLY_SUPERVISOR: no more beads",
                file=sys.stderr, flush=True,
            )
            self._complete()
            return

        bead_id = select_result["bead_id"]
        if bead_id in self._completed_beads:
            # Skip already completed
            self._next_bead()
            return

        self._current_bead = select_result
        self._review_rounds = 0
        self._gate_fix_attempts = 0

        print(
            f"FLY_SUPERVISOR: processing bead {bead_id}: "
            f"{select_result.get('title', '')[:60]}",
            file=sys.stderr, flush=True,
        )

        # Tell agent actors to create new sessions for this bead
        self.send(self._implementer, {"type": "new_bead"})
        self.send(self._reviewer, {"type": "new_bead"})

        # Start implementation
        self._start_implement()

    def _start_implement(self):
        """Send implement request to implementer."""
        bead = self._current_bead
        prompt = (
            f"## Task\n\n{bead.get('description', bead.get('title', ''))}\n\n"
            f"Implement this task. Read the relevant files, make changes, "
            f"and run tests to verify."
        )

        self.send(self._implementer, {
            "type": "implement",
            "prompt": prompt,
        })

    async def _select_next_bead(self):
        from maverick.library.actions.beads import select_next_bead

        result = await select_next_bead(epic_id=self._epic_id)
        return result.to_dict()

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def _handle_tool_call(self, message):
        tool = message.get("tool", "")
        args = message.get("arguments", {})

        if tool == "submit_implementation":
            print("FLY_SUPERVISOR: implementation submitted", file=sys.stderr, flush=True)
            self.send(self._gate, {
                "type": "gate",
                "cwd": self._cwd,
            })

        elif tool == "submit_fix_result":
            print("FLY_SUPERVISOR: fix result submitted", file=sys.stderr, flush=True)
            self.send(self._gate, {
                "type": "gate",
                "cwd": self._cwd,
            })

        elif tool == "submit_review":
            approved = args.get("approved", True)
            findings = args.get("findings", [])
            print(
                f"FLY_SUPERVISOR: review {'approved' if approved else f'rejected ({len(findings)} findings)'}",
                file=sys.stderr, flush=True,
            )

            if approved:
                self._commit_bead()
            elif self._review_rounds < MAX_REVIEW_ROUNDS:
                self._review_rounds += 1
                # Send findings to implementer for fix
                prompt = "Please fix the following review findings:\n\n"
                for f in findings:
                    severity = f.get("severity", "major")
                    issue = f.get("issue", "")
                    file = f.get("file", "")
                    prompt += f"- **{severity}** `{file}`: {issue}\n"

                self.send(self._implementer, {
                    "type": "fix",
                    "prompt": prompt,
                })
            else:
                self._commit_bead(tag="needs-human-review")

    def _handle_gate_result(self, message):
        passed = message.get("passed", False)
        if passed:
            # Gate passed → AC check
            self.send(self._ac, {
                "type": "ac_check",
                "description": self._current_bead.get("description", ""),
                "cwd": self._cwd,
            })
        elif self._gate_fix_attempts < MAX_GATE_FIX_ATTEMPTS:
            self._gate_fix_attempts += 1
            summary = message.get("summary", "Gate failed")
            self.send(self._implementer, {
                "type": "fix",
                "prompt": f"Gate check failed:\n\n{summary}\n\nFix the issues.",
            })
        else:
            self._commit_bead(tag="needs-human-review")

    def _handle_ac_result(self, message):
        passed = message.get("passed", False)
        if passed:
            self.send(self._spec, {"type": "spec_check"})
        else:
            reasons = message.get("reasons", [])
            self.send(self._implementer, {
                "type": "fix",
                "prompt": "AC check failed:\n\n" + "\n".join(f"- {r}" for r in reasons),
            })

    def _handle_spec_result(self, message):
        # Spec passed → review
        self.send(self._reviewer, {
            "type": "review",
            "bead_description": self._current_bead.get("description", ""),
        })

    def _commit_bead(self, tag=None):
        bead = self._current_bead
        self.send(self._committer, {
            "type": "commit",
            "bead_id": bead.get("bead_id", ""),
            "title": bead.get("title", ""),
            "cwd": self._cwd,
            "tag": tag,
        })

    def _handle_commit_result(self, message):
        bead_id = self._current_bead.get("bead_id", "")
        self._completed_beads.append(bead_id)
        print(
            f"FLY_SUPERVISOR: bead {bead_id} committed "
            f"(total: {len(self._completed_beads)})",
            file=sys.stderr, flush=True,
        )
        # Next bead
        self._next_bead()

    def _complete(self):
        """All beads done — shutdown agents, report to workflow."""
        # Shutdown agent actors (cleanup ACP subprocesses)
        if self._implementer:
            self.send(self._implementer, {"type": "shutdown"})
        if self._reviewer:
            self.send(self._reviewer, {"type": "shutdown"})

        print(
            f"FLY_SUPERVISOR: complete ({len(self._completed_beads)} beads)",
            file=sys.stderr, flush=True,
        )
        if self._workflow_sender:
            self.send(self._workflow_sender, {
                "type": "complete",
                "success": True,
                "beads_completed": len(self._completed_beads),
                "completed_bead_ids": self._completed_beads,
            })
