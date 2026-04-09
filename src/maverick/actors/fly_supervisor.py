"""FlySupervisorActor — Thespian actor for bead-driven development.

Owns the entire fly lifecycle: bead selection, per-bead routing
(implement → gate → review → commit), and bead loop management.
All actors persist for the fly session; agent actors create new
ACP sessions per bead.
"""

import asyncio
import sys
from pathlib import Path

from thespian.actors import Actor

MAX_REVIEW_ROUNDS = 3
MAX_GATE_FIX_ATTEMPTS = 2
MAX_SPEC_FIX_ATTEMPTS = 2


class FlySupervisorActor(Actor):
    """Orchestrates the full fly bead loop."""

    def receiveMessage(self, message, sender):
        msg_preview = str(message)[:120] if message else "None"
        print(
            f"FLY_SUPERVISOR: msg from={sender} preview={msg_preview}",
            file=sys.stderr,
            flush=True,
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
                file=sys.stderr,
                flush=True,
            )
            self._escalate_to_human(f"Agent prompt error: {message.get('error', 'unknown')}")
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

        # Aggregate review result (post-flight)
        if isinstance(message, dict) and message.get("type") == "aggregate_review_complete":
            self._handle_aggregate_review_complete(message)
            return

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def _init(self, message, sender):
        self._epic_id = message.get("epic_id", "")
        self._cwd = message.get("cwd")
        self._config = message.get("config", {})
        self._watch_mode = message.get("watch", False)
        self._watch_interval = message.get("watch_interval", 30)
        self._max_idle_polls = message.get("max_idle_polls", 60)  # 30min at 30s

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
        self._completed_titles = []
        self._bead_events = []
        self._current_bead = None
        self._current_work_unit_md = ""
        self._briefing_context = ""
        self._flight_plan_name = ""
        self._review_rounds = 0
        self._gate_fix_attempts = 0
        self._spec_fix_attempts = 0
        self._last_review_findings = []
        self._in_aggregate_review = False
        self._idle_polls = 0

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
                file=sys.stderr,
                flush=True,
            )
            self._complete()
            return

        if select_result.get("done") or not select_result.get("found"):
            if self._watch_mode and self._idle_polls < self._max_idle_polls:
                self._idle_polls += 1
                print(
                    f"FLY_SUPERVISOR: no beads ready, waiting "
                    f"({self._idle_polls}/{self._max_idle_polls})...",
                    file=sys.stderr,
                    flush=True,
                )
                import time

                time.sleep(self._watch_interval)
                self._next_bead()
                return

            print(
                "FLY_SUPERVISOR: no more beads",
                file=sys.stderr,
                flush=True,
            )
            self._complete()
            return

        # Reset idle counter when we find work
        self._idle_polls = 0

        bead_id = select_result["bead_id"]
        if bead_id in self._completed_beads:
            # Skip already completed
            self._next_bead()
            return

        self._current_bead = select_result
        self._review_rounds = 0
        self._gate_fix_attempts = 0
        self._spec_fix_attempts = 0

        # Resolve flight plan name from bead selection
        if not self._flight_plan_name:
            self._flight_plan_name = select_result.get("flight_plan_name", "")

        # Load enriched context for this bead
        self._load_bead_context(bead_id)

        print(
            f"FLY_SUPERVISOR: processing bead {bead_id}: {select_result.get('title', '')[:60]}",
            file=sys.stderr,
            flush=True,
        )

        # Tell agent actors to create new sessions for this bead
        self.send(self._implementer, {"type": "new_bead"})
        self.send(self._reviewer, {"type": "new_bead"})

        # Start implementation
        self._start_implement()

    def _load_bead_context(self, bead_id):
        """Load work unit markdown and briefing context for enriched reviews."""
        if not self._flight_plan_name or not self._cwd:
            return

        plans_dir = Path(self._cwd) / ".maverick" / "plans" / self._flight_plan_name

        # Load all work unit files (keyed by work-unit ID from frontmatter)
        # and match against the bead's title/description.
        self._current_work_unit_md = ""
        bead_title = self._current_bead.get("title", "")
        self._current_bead.get("description", "")

        try:
            work_units = {}
            for md_file in sorted(plans_dir.glob("[0-9]*.md")):
                content = md_file.read_text(encoding="utf-8")
                # Extract work-unit ID from YAML frontmatter
                wu_id = ""
                for line in content.split("\n"):
                    if line.startswith("work-unit:"):
                        wu_id = line.split(":", 1)[1].strip()
                        break
                if wu_id:
                    work_units[wu_id] = content

            # Match: check if bead title contains the work unit ID
            # (bead titles are the task description which often includes
            # the work unit's key terms)
            for wu_id, content in work_units.items():
                # Extract the ## Task line for matching
                task_line = ""
                in_task = False
                for line in content.split("\n"):
                    if line.startswith("## Task"):
                        in_task = True
                        continue
                    if in_task and line.strip():
                        task_line = line.strip()
                        break

                # Match if bead title starts with the task description
                # or task description starts with the bead title
                if task_line and bead_title:
                    if bead_title[:60] in task_line or task_line[:60] in bead_title:
                        self._current_work_unit_md = content
                        print(
                            f"FLY_SUPERVISOR: matched work unit '{wu_id}' for bead",
                            file=sys.stderr,
                            flush=True,
                        )
                        break

            if not self._current_work_unit_md and work_units:
                print(
                    f"FLY_SUPERVISOR: no work unit match for "
                    f"'{bead_title[:50]}', using all as context",
                    file=sys.stderr,
                    flush=True,
                )
                # Fallback: concatenate all work units so the agent
                # has full context and can pick the right one
                self._current_work_unit_md = "\n\n---\n\n".join(work_units.values())
        except Exception as exc:
            print(
                f"FLY_SUPERVISOR: failed to load work unit: {exc}",
                file=sys.stderr,
                flush=True,
            )

        # Load briefing context (once, cached across beads)
        if not self._briefing_context:
            for briefing_name in ("refuel-briefing.md", "briefing.md"):
                briefing_path = plans_dir / briefing_name
                if briefing_path.exists():
                    try:
                        self._briefing_context = briefing_path.read_text(encoding="utf-8")[
                            :8000
                        ]  # Cap at 8KB to avoid prompt bloat
                        print(
                            f"FLY_SUPERVISOR: loaded briefing ({len(self._briefing_context)} chars)",
                            file=sys.stderr,
                            flush=True,
                        )
                    except Exception:
                        pass
                    break

    def _start_implement(self):
        """Send implement request to implementer."""
        bead = self._current_bead
        desc = bead.get("description", bead.get("title", ""))

        # Enrich implementer prompt with work unit spec if available
        runway_hint = (
            "\n\n## Historical Context (Runway)\n\n"
            "The `.maverick/runway/` directory contains project knowledge:\n"
            "- `episodic/bead-outcomes.jsonl` — outcomes from previous beads\n"
            "- `episodic/review-findings.jsonl` — review findings and resolutions\n"
            "- `episodic/fix-attempts.jsonl` — what was tried and whether it worked\n"
            "- `semantic/` — architecture notes and decision records\n"
            "- `index.json` — store metadata and suppressed patterns\n\n"
            "Read these files if they exist — they contain lessons learned "
            "that may prevent repeating past mistakes."
        )

        if self._current_work_unit_md:
            prompt = (
                f"## Work Unit Specification\n\n{self._current_work_unit_md}\n\n"
                f"Implement this task. Read the relevant files, make changes, "
                f"and run tests to verify."
                f"{runway_hint}"
            )
        else:
            prompt = (
                f"## Task\n\n{desc}\n\n"
                f"Implement this task. Read the relevant files, make changes, "
                f"and run tests to verify."
                f"{runway_hint}"
            )

        self.send(
            self._implementer,
            {
                "type": "implement",
                "prompt": prompt,
            },
        )

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
            self.send(
                self._gate,
                {
                    "type": "gate",
                    "cwd": self._cwd,
                },
            )

        elif tool == "submit_fix_result":
            print("FLY_SUPERVISOR: fix result submitted", file=sys.stderr, flush=True)
            self.send(
                self._gate,
                {
                    "type": "gate",
                    "cwd": self._cwd,
                },
            )

        elif tool == "submit_review":
            # Route differently if this is the aggregate review
            if self._in_aggregate_review:
                findings = args.get("findings", [])
                print(
                    f"FLY_SUPERVISOR: aggregate review submitted ({len(findings)} findings)",
                    file=sys.stderr,
                    flush=True,
                )
                self._handle_aggregate_review_complete(
                    {
                        "findings": findings,
                    }
                )
                return

            approved = args.get("approved", True)
            findings = args.get("findings", [])
            self._last_review_findings = findings
            print(
                f"FLY_SUPERVISOR: review {'approved' if approved else f'rejected ({len(findings)} findings)'}",
                file=sys.stderr,
                flush=True,
            )

            if approved:
                self._commit_bead()
            elif self._review_rounds < MAX_REVIEW_ROUNDS:
                self._review_rounds += 1
                self._record_review_findings(findings)
                # Send findings to implementer for fix
                prompt = "Please fix the following review findings:\n\n"
                for f in findings:
                    severity = f.get("severity", "major")
                    issue = f.get("issue", "")
                    file = f.get("file", "")
                    prompt += f"- **{severity}** `{file}`: {issue}\n"

                self.send(
                    self._implementer,
                    {
                        "type": "fix",
                        "prompt": prompt,
                    },
                )
            else:
                self._escalate_to_human(
                    "Review rounds exhausted",
                    [f.get("issue", "") for f in findings],
                )

    def _handle_gate_result(self, message):
        passed = message.get("passed", False)
        if passed:
            # Gate passed → AC check
            self.send(
                self._ac,
                {
                    "type": "ac_check",
                    "description": self._current_bead.get("description", ""),
                    "cwd": self._cwd,
                },
            )
        elif self._gate_fix_attempts < MAX_GATE_FIX_ATTEMPTS:
            self._gate_fix_attempts += 1
            summary = message.get("summary", "Gate failed")
            self.send(
                self._implementer,
                {
                    "type": "fix",
                    "prompt": f"Gate check failed:\n\n{summary}\n\nFix the issues.",
                },
            )
        else:
            summary = message.get("summary", "Gate failed")
            self._escalate_to_human("Gate fix attempts exhausted", [summary])

    def _handle_ac_result(self, message):
        passed = message.get("passed", False)
        if passed:
            self.send(
                self._spec,
                {
                    "type": "spec_check",
                    "cwd": self._cwd,
                },
            )
        else:
            reasons = message.get("reasons", [])
            self.send(
                self._implementer,
                {
                    "type": "fix",
                    "prompt": "AC check failed:\n\n" + "\n".join(f"- {r}" for r in reasons),
                },
            )

    def _handle_spec_result(self, message):
        passed = message.get("passed", False)
        if passed:
            # Spec passed → review with enriched context
            self.send(
                self._reviewer,
                {
                    "type": "review",
                    "bead_description": self._current_bead.get("description", ""),
                    "work_unit_md": self._current_work_unit_md,
                    "briefing_context": self._briefing_context,
                },
            )
        elif self._spec_fix_attempts < MAX_SPEC_FIX_ATTEMPTS:
            self._spec_fix_attempts += 1
            findings = message.get("findings", [])
            prompt = "Spec compliance check found issues:\n\n"
            for f in findings:
                prompt += f"- {f}\n"
            prompt += "\nFix these issues."
            self.send(
                self._implementer,
                {
                    "type": "fix",
                    "prompt": prompt,
                },
            )
        else:
            findings = message.get("findings", [])
            self._escalate_to_human("Spec compliance fix attempts exhausted", findings)

    def _commit_bead(self, tag=None):
        bead = self._current_bead
        self.send(
            self._committer,
            {
                "type": "commit",
                "bead_id": bead.get("bead_id", ""),
                "title": bead.get("title", ""),
                "cwd": self._cwd,
                "tag": tag,
            },
        )

    def _handle_commit_result(self, message):
        bead = self._current_bead
        bead_id = bead.get("bead_id", "")
        self._completed_beads.append(bead_id)
        self._completed_titles.append(bead.get("title", bead_id))

        # Build structured bead event
        bead_event = {
            "bead_id": bead_id,
            "epic_id": self._epic_id,
            "title": bead.get("title", ""),
            "flight_plan": self._flight_plan_name,
            "success": message.get("success", False),
            "commit_sha": message.get("commit_sha", ""),
            "tag": message.get("tag"),
            "review_rounds": self._review_rounds,
            "gate_fix_attempts": self._gate_fix_attempts,
            "spec_fix_attempts": self._spec_fix_attempts,
        }
        self._bead_events.append(bead_event)

        # Record to runway (best-effort)
        self._record_bead_outcome(message)

        print(
            f"FLY_SUPERVISOR: bead {bead_id} committed (total: {len(self._completed_beads)})",
            file=sys.stderr,
            flush=True,
        )
        # Next bead
        self._next_bead()

    # ------------------------------------------------------------------
    # Post-flight aggregate review
    # ------------------------------------------------------------------

    def _complete(self):
        """All beads done — run aggregate review if multiple beads, then report."""
        if len(self._completed_beads) > 1:
            print(
                f"FLY_SUPERVISOR: running aggregate review across "
                f"{len(self._completed_beads)} beads",
                file=sys.stderr,
                flush=True,
            )
            self._run_aggregate_review()
        else:
            self._finalize()

    def _run_aggregate_review(self):
        """Send aggregate review request to reviewer."""
        self._in_aggregate_review = True
        import subprocess

        # Get diff stats from baseline to HEAD
        diff_stat = ""
        try:
            result = subprocess.run(
                ["git", "diff", "--stat", "HEAD~" + str(len(self._completed_beads))],
                capture_output=True,
                text=True,
                cwd=self._cwd,
                timeout=30,
            )
            diff_stat = result.stdout[:4000] if result.stdout else "(no diff)"
        except Exception:
            diff_stat = "(could not generate diff)"

        bead_list = "\n".join(f"- {title}" for title in self._completed_titles)

        self.send(
            self._reviewer,
            {
                "type": "aggregate_review",
                "objective": self._flight_plan_name,
                "bead_list": bead_list,
                "diff_stat": diff_stat,
                "bead_count": len(self._completed_beads),
            },
        )

    def _handle_aggregate_review_complete(self, message):
        """Aggregate review done — finalize with findings attached."""
        findings = message.get("findings", [])
        if findings:
            print(
                f"FLY_SUPERVISOR: aggregate review flagged {len(findings)} cross-bead concerns",
                file=sys.stderr,
                flush=True,
            )

        self._aggregate_findings = findings
        self._finalize()

    def _finalize(self):
        """Shutdown agents, report to workflow."""
        if self._implementer:
            self.send(self._implementer, {"type": "shutdown"})
        if self._reviewer:
            self.send(self._reviewer, {"type": "shutdown"})

        aggregate = getattr(self, "_aggregate_findings", [])
        has_concerns = len(aggregate) > 0

        print(
            f"FLY_SUPERVISOR: complete ({len(self._completed_beads)} beads"
            f"{', ' + str(len(aggregate)) + ' aggregate concerns' if has_concerns else ''})",
            file=sys.stderr,
            flush=True,
        )
        if self._workflow_sender:
            self.send(
                self._workflow_sender,
                {
                    "type": "complete",
                    "success": True,
                    "beads_completed": len(self._completed_beads),
                    "completed_bead_ids": self._completed_beads,
                    "bead_events": self._bead_events,
                    "aggregate_review": aggregate,
                    "needs_human_review": has_concerns,
                },
            )

    # ------------------------------------------------------------------
    # Runway recording (best-effort)
    # ------------------------------------------------------------------

    def _record_bead_outcome(self, commit_result):
        """Record bead outcome to runway store."""
        try:
            asyncio.run(self._async_record_outcome(commit_result))
        except Exception as exc:
            print(
                f"FLY_SUPERVISOR: runway record failed: {exc}",
                file=sys.stderr,
                flush=True,
            )

    async def _async_record_outcome(self, commit_result):
        from maverick.library.actions.runway import record_bead_outcome

        bead = self._current_bead
        review_result = {
            "issues_found": self._review_rounds,
            "issues_fixed": (self._review_rounds if commit_result.get("success") else 0),
        }

        await record_bead_outcome(
            bead_id=bead.get("bead_id", ""),
            epic_id=self._epic_id,
            title=bead.get("title", ""),
            flight_plan=self._flight_plan_name,
            validation_result={"passed": True},
            review_result=review_result,
            mistakes_caught=[
                f.get("issue", "")
                for f in self._last_review_findings
                if f.get("severity") in ("critical", "major")
            ]
            or None,
            cwd=self._cwd,
        )

    def _record_review_findings(self, findings):
        """Record review findings to runway store."""
        if not findings:
            return
        try:
            asyncio.run(self._async_record_review(findings))
        except Exception as exc:
            print(
                f"FLY_SUPERVISOR: runway review record failed: {exc}",
                file=sys.stderr,
                flush=True,
            )

    async def _async_record_review(self, findings):
        from maverick.library.actions.runway import record_review_findings

        review_result = {
            "findings": [
                {
                    "severity": f.get("severity", "major"),
                    "category": "code_review",
                    "file_path": f.get("file", ""),
                    "description": f.get("issue", ""),
                }
                for f in findings
            ],
        }
        await record_review_findings(
            bead_id=self._current_bead.get("bead_id", ""),
            review_result=review_result,
            cwd=self._cwd,
        )

    # ------------------------------------------------------------------
    # Human-in-the-loop escalation
    # ------------------------------------------------------------------

    def _escalate_to_human(self, reason, findings=None):
        """Create a human-assigned review bead and commit optimistically."""
        try:
            asyncio.run(self._async_create_human_bead(reason, findings))
        except Exception as exc:
            print(
                f"FLY_SUPERVISOR: human bead creation failed: {exc}",
                file=sys.stderr,
                flush=True,
            )
        # Commit optimistically — human bead is independent, not blocking
        self._commit_bead(tag="needs-human-review")

    async def _async_create_human_bead(self, reason, findings):
        from maverick.beads.client import BeadClient
        from maverick.beads.models import (
            BeadCategory,
            BeadDefinition,
            BeadType,
        )

        client = BeadClient(cwd=Path(self._cwd))
        bead = self._current_bead
        bead_id = bead.get("bead_id", "")
        bead_title = bead.get("title", bead_id)

        findings_text = "\n".join(f"- {f}" for f in (findings or [])) if findings else "None"

        review_def = BeadDefinition(
            title=f"Review: {bead_title[:150]}",
            bead_type=BeadType.TASK,
            priority=1,
            category=BeadCategory.REVIEW,
            description=(
                f"## Escalation Reason\n\n{reason}\n\n"
                f"## What Was Tried\n\n"
                f"Gate fix attempts: {self._gate_fix_attempts}\n"
                f"Spec fix attempts: {self._spec_fix_attempts}\n"
                f"Review rounds: {self._review_rounds}\n\n"
                f"## Findings\n\n{findings_text}"
            ),
            assignee="human",
            labels=["assumption-review", "needs-human-review"],
        )

        created = await client.create_bead(review_def, parent_id=self._epic_id)

        # Record context as state metadata
        await client.set_state(
            created.bd_id,
            {
                "source_bead": bead_id,
                "escalation_type": "fix_exhaustion",
                "flight_plan": self._flight_plan_name,
            },
            reason=f"Escalated from {bead_id}",
        )

        print(
            f"FLY_SUPERVISOR: created human review bead {created.bd_id} for {bead_id}",
            file=sys.stderr,
            flush=True,
        )
