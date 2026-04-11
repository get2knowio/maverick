"""FlySupervisorActor — Thespian actor for bead-driven development.

Owns the entire fly lifecycle: bead selection, per-bead routing
(implement → gate → review → commit), and bead loop management.
All actors persist for the fly session; agent actors create new
ACP sessions per bead.

The workflow sends "start" and then drains progress events via
``{"type": "get_events", "since": int}`` polls until the supervisor
marks itself done. The terminal result rides on the final
``done=True`` reply — see ``SupervisorEventBusMixin``.
"""

import asyncio
from datetime import timedelta
from pathlib import Path

from thespian.actors import Actor, WakeupMessage

from maverick.actors.event_bus import SupervisorEventBusMixin
from maverick.logging import get_logger

MAX_REVIEW_ROUNDS = 3
MAX_GATE_FIX_ATTEMPTS = 2
MAX_SPEC_FIX_ATTEMPTS = 2
MAX_BEAD_EVENTS = 500

_SOURCE = "fly-supervisor"

logger = get_logger(__name__)


class FlySupervisorActor(SupervisorEventBusMixin, Actor):
    """Orchestrates the full fly bead loop."""

    def receiveMessage(self, message, sender):
        logger.debug(
            "fly_supervisor.received",
            msg_type=type(message).__name__,
            preview=str(message)[:120] if message else "None",
        )

        if isinstance(message, WakeupMessage):
            self._next_bead()
            return

        if isinstance(message, dict) and message.get("type") == "init":
            self._init(message, sender)
            return

        if isinstance(message, dict) and message.get("type") == "init_ok":
            return

        if isinstance(message, dict) and message.get("type") == "session_ready":
            return

        # Event-bus drain poll (must precede other dict routing)
        if isinstance(message, dict) and message.get("type") == "get_events":
            self._handle_get_events(message, sender)
            return

        if message == "start":
            self._emit_output(
                "fly",
                f"Starting bead loop (epic: {self._epic_id or 'any'})",
                level="info",
                source=_SOURCE,
            )
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
            self._emit_output(
                "fly",
                f"Agent prompt error: {message.get('error', 'unknown')}",
                level="error",
                source=_SOURCE,
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
        self._init_event_bus()
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
        self._work_units_cache: dict[str, dict[str, str]] = {}

        self.send(sender, {"type": "init_ok"})

    # ------------------------------------------------------------------
    # Bead loop
    # ------------------------------------------------------------------

    def _next_bead(self):
        """Select and process the next bead."""
        try:
            select_result = asyncio.run(self._select_next_bead())
        except Exception as exc:
            self._emit_output(
                "fly",
                f"Bead selection failed: {exc}",
                level="error",
                source=_SOURCE,
            )
            self._complete()
            return

        if select_result.get("done") or not select_result.get("found"):
            if self._watch_mode and self._idle_polls < self._max_idle_polls:
                self._idle_polls += 1
                self._emit_output(
                    "fly",
                    f"No beads ready; waiting "
                    f"({self._idle_polls}/{self._max_idle_polls})",
                    level="info",
                    source=_SOURCE,
                )
                self.wakeupAfter(timedelta(seconds=self._watch_interval))
                return

            self._emit_output(
                "fly",
                "No more beads to process",
                level="info",
                source=_SOURCE,
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

        title = select_result.get("title", "")
        self._emit_output(
            "fly",
            f"Processing bead {bead_id}: {title[:80]}",
            level="info",
            source=_SOURCE,
            metadata={"bead_id": bead_id, "title": title},
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
            work_units = self._work_units_cache.get(self._flight_plan_name)
            if work_units is None:
                work_units = {}
                for md_file in sorted(plans_dir.glob("[0-9]*.md")):
                    content = md_file.read_text(encoding="utf-8")
                    wu_id = ""
                    for line in content.split("\n"):
                        if line.startswith("work-unit:"):
                            wu_id = line.split(":", 1)[1].strip()
                            break
                    if wu_id:
                        work_units[wu_id] = content
                self._work_units_cache[self._flight_plan_name] = work_units

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
                        logger.debug(
                            "fly_supervisor.work_unit_matched",
                            work_unit_id=wu_id,
                        )
                        break

            if not self._current_work_unit_md and work_units:
                logger.debug(
                    "fly_supervisor.work_unit_fallback",
                    bead_title=bead_title[:50],
                )
                # Fallback: concatenate all work units so the agent
                # has full context and can pick the right one
                self._current_work_unit_md = "\n\n---\n\n".join(work_units.values())
        except Exception as exc:
            self._emit_output(
                "fly",
                f"Failed to load work unit context: {exc}",
                level="warning",
                source=_SOURCE,
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
                        logger.debug(
                            "fly_supervisor.briefing_loaded",
                            chars=len(self._briefing_context),
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
            self._emit_output(
                "fly",
                "Implementation submitted; running gate",
                level="info",
                source=_SOURCE,
            )
            self.send(
                self._gate,
                {
                    "type": "gate",
                    "cwd": self._cwd,
                },
            )

        elif tool == "submit_fix_result":
            self._emit_output(
                "fly",
                "Fix submitted; re-running gate",
                level="info",
                source=_SOURCE,
            )
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
                self._emit_output(
                    "fly",
                    f"Aggregate review submitted ({len(findings)} findings)",
                    level="warning" if findings else "success",
                    source=_SOURCE,
                    metadata={"finding_count": len(findings)},
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
            if approved:
                self._emit_output(
                    "fly",
                    "Review approved",
                    level="success",
                    source=_SOURCE,
                )
            else:
                self._emit_output(
                    "fly",
                    f"Review found {len(findings)} finding(s) "
                    f"(round {self._review_rounds + 1}/{MAX_REVIEW_ROUNDS})",
                    level="warning",
                    source=_SOURCE,
                    metadata={
                        "finding_count": len(findings),
                        "review_round": self._review_rounds + 1,
                    },
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
            self._emit_output(
                "fly",
                "Gate passed; checking acceptance criteria",
                level="success",
                source=_SOURCE,
            )
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
            self._emit_output(
                "fly",
                f"Gate failed; requesting fix "
                f"(attempt {self._gate_fix_attempts}/{MAX_GATE_FIX_ATTEMPTS})",
                level="warning",
                source=_SOURCE,
                metadata={"gate_fix_attempt": self._gate_fix_attempts},
            )
            self.send(
                self._implementer,
                {
                    "type": "fix",
                    "prompt": f"Gate check failed:\n\n{summary}\n\nFix the issues.",
                },
            )
        else:
            summary = message.get("summary", "Gate failed")
            self._emit_output(
                "fly",
                "Gate fix attempts exhausted; escalating to human",
                level="error",
                source=_SOURCE,
            )
            self._escalate_to_human("Gate fix attempts exhausted", [summary])

    def _handle_ac_result(self, message):
        passed = message.get("passed", False)
        if passed:
            self._emit_output(
                "fly",
                "Acceptance criteria met; running spec compliance check",
                level="success",
                source=_SOURCE,
            )
            self.send(
                self._spec,
                {
                    "type": "spec_check",
                    "cwd": self._cwd,
                },
            )
        else:
            reasons = message.get("reasons", [])
            self._emit_output(
                "fly",
                f"Acceptance criteria failed ({len(reasons)} reason(s)); requesting fix",
                level="warning",
                source=_SOURCE,
            )
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
            self._emit_output(
                "fly",
                "Spec compliance passed; running code review",
                level="success",
                source=_SOURCE,
            )
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
            self._emit_output(
                "fly",
                f"Spec compliance found {len(findings)} issue(s); requesting fix "
                f"(attempt {self._spec_fix_attempts}/{MAX_SPEC_FIX_ATTEMPTS})",
                level="warning",
                source=_SOURCE,
            )
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
            self._emit_output(
                "fly",
                "Spec compliance fix attempts exhausted; escalating to human",
                level="error",
                source=_SOURCE,
            )
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

        # Build structured bead event (kept for back-compat with the
        # workflow's post-run summary rendering)
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
        if len(self._bead_events) > MAX_BEAD_EVENTS:
            del self._bead_events[: len(self._bead_events) - MAX_BEAD_EVENTS]

        # Record to runway (best-effort)
        self._record_bead_outcome(message)

        tag = message.get("tag")
        tag_note = f" [{tag}]" if tag else ""
        self._emit_output(
            "fly",
            f"Bead {bead_id} committed{tag_note} "
            f"(total: {len(self._completed_beads)})",
            level="warning" if tag == "needs-human-review" else "success",
            source=_SOURCE,
            metadata={
                "bead_id": bead_id,
                "commit_sha": message.get("commit_sha", ""),
                "tag": tag,
                "total_completed": len(self._completed_beads),
            },
        )
        # Next bead
        self._next_bead()

    # ------------------------------------------------------------------
    # Post-flight aggregate review
    # ------------------------------------------------------------------

    def _complete(self):
        """All beads done — run aggregate review if multiple beads, then report."""
        if len(self._completed_beads) > 1:
            self._emit_output(
                "fly",
                f"Running aggregate review across {len(self._completed_beads)} beads",
                level="info",
                source=_SOURCE,
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
            self._emit_output(
                "fly",
                f"Aggregate review flagged {len(findings)} cross-bead concern(s)",
                level="warning",
                source=_SOURCE,
                metadata={"concern_count": len(findings)},
            )
        else:
            self._emit_output(
                "fly",
                "Aggregate review passed; no cross-bead concerns",
                level="success",
                source=_SOURCE,
            )

        self._aggregate_findings = findings
        self._finalize()

    def _finalize(self):
        """Shutdown agents, mark done for workflow drain."""
        if self._implementer:
            self.send(self._implementer, {"type": "shutdown"})
        if self._reviewer:
            self.send(self._reviewer, {"type": "shutdown"})

        aggregate = getattr(self, "_aggregate_findings", [])
        has_concerns = len(aggregate) > 0

        concerns_note = (
            f", {len(aggregate)} aggregate concern(s)" if has_concerns else ""
        )
        self._emit_output(
            "fly",
            f"Fly complete: {len(self._completed_beads)} bead(s){concerns_note}",
            level="warning" if has_concerns else "success",
            source=_SOURCE,
            metadata={
                "beads_completed": len(self._completed_beads),
                "aggregate_concern_count": len(aggregate),
            },
        )
        self._mark_done(
            {
                "success": True,
                "beads_completed": len(self._completed_beads),
                "completed_bead_ids": self._completed_beads,
                "bead_events": self._bead_events,
                "aggregate_review": aggregate,
                "needs_human_review": has_concerns,
            }
        )

    # ------------------------------------------------------------------
    # Runway recording (best-effort)
    # ------------------------------------------------------------------

    def _record_bead_outcome(self, commit_result):
        """Record bead outcome to runway store."""
        try:
            asyncio.run(self._async_record_outcome(commit_result))
        except Exception as exc:
            logger.warning("fly_supervisor.runway_record_failed", error=str(exc))

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
            logger.warning(
                "fly_supervisor.runway_review_record_failed", error=str(exc)
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
            self._emit_output(
                "fly",
                f"Human bead creation failed: {exc}",
                level="error",
                source=_SOURCE,
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

        self._emit_output(
            "fly",
            f"Created human review bead {created.bd_id} for {bead_id}",
            level="warning",
            source=_SOURCE,
            metadata={"human_bead_id": created.bd_id, "source_bead": bead_id},
        )
