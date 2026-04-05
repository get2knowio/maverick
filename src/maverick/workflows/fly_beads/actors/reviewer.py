"""ReviewerActor — agent actor that reviews code changes.

Maintains a persistent ACP session for the bead's lifetime.  On
follow-up reviews, the reviewer can reference its own prior findings
because the conversation history is preserved in the session.

This eliminates the review oscillation problem: instead of doing a
fresh review each time (finding different issues), the reviewer checks
"were my previous findings addressed?" and only flags genuinely new
issues.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maverick.executor.config import StepConfig
from maverick.logging import get_logger
from maverick.workflows.fly_beads.actors.protocol import (
    Message,
    MessageType,
)
from maverick.workflows.fly_beads.session_registry import BeadSessionRegistry

logger = get_logger(__name__)


class ReviewerActor:
    """Agent actor that reviews code for completeness and correctness.

    Handles:
    - REVIEW_REQUEST: Review the current code state

    On the first review, does a full review of the diff.  On subsequent
    reviews (same session), checks whether prior findings were addressed
    and only flags new critical/major issues.

    The session persists for the bead's lifetime, so the reviewer
    remembers exactly what it said before.
    """

    def __init__(
        self,
        *,
        session_registry: BeadSessionRegistry,
        executor: Any,  # AcpStepExecutor
        cwd: Path | None = None,
        config: StepConfig | None = None,
        bead_description: str = "",
    ) -> None:
        self._registry = session_registry
        self._executor = executor
        self._cwd = cwd
        self._config = config
        self._bead_description = bead_description
        self._review_count: int = 0
        self._prior_findings: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "reviewer"

    async def receive(self, message: Message) -> list[Message]:
        if message.msg_type != MessageType.REVIEW_REQUEST:
            logger.warning(
                "reviewer_actor.unexpected_message", msg_type=message.msg_type
            )
            return []

        self._review_count += 1

        if self._review_count == 1:
            return await self._initial_review(message)
        else:
            return await self._followup_review(message)

    async def _initial_review(self, message: Message) -> list[Message]:
        """First review — full review of the code changes."""
        # Get the current diff from the workspace
        diff = await self._get_workspace_diff()

        prompt_text = (
            "Review the following code changes for completeness and "
            "correctness.\n\n"
            f"## Task Description\n\n{self._bead_description}\n\n"
            f"## Diff\n\n```diff\n{diff}\n```\n\n"
            "## Instructions\n\n"
            "1. Check that the implementation satisfies the task description "
            "and acceptance criteria.\n"
            "2. Check for bugs, security issues, and correctness problems.\n"
            "3. Do NOT flag style preferences or minor suggestions.\n"
            "4. Only flag issues that are CRITICAL (runtime crash, security, "
            "data corruption) or MAJOR (bugs, missing required behavior).\n\n"
            "Respond with:\n"
            "- APPROVED if no critical/major issues\n"
            "- FINDINGS: followed by a numbered list of issues, each with "
            "severity (CRITICAL/MAJOR), file:line, and description\n"
        )

        session_id = await self._registry.get_or_create(
            self.name,
            self._executor,
            cwd=self._cwd,
            config=self._config,
        )

        result = await self._executor.prompt_session(
            session_id=session_id,
            prompt_text=prompt_text,
            provider=self._registry.get_provider(self.name),
            config=self._config,
            step_name="review",
            agent_name="reviewer",
        )

        text = result.output if isinstance(result.output, str) else ""
        approved, findings = self._parse_review_response(text)
        self._prior_findings = findings

        return [
            Message(
                msg_type=MessageType.REVIEW_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload={
                    "approved": approved,
                    "findings": findings,
                    "findings_count": len(findings),
                    "review_round": self._review_count,
                },
                in_reply_to=message.sequence,
            )
        ]

    async def _followup_review(self, message: Message) -> list[Message]:
        """Follow-up review — check if prior findings were addressed."""
        diff = await self._get_workspace_diff()

        # Build a targeted prompt referencing prior findings
        prior_list = "\n".join(
            f"{i+1}. [{f.get('severity', 'MAJOR')}] "
            f"`{f.get('file', '?')}:{f.get('line', '?')}`: "
            f"{f.get('issue', '?')}"
            for i, f in enumerate(self._prior_findings)
        )

        prompt_text = (
            "The implementer has made changes to address your previous "
            "findings. Review ONLY whether your previous findings were "
            "addressed. Do NOT do a fresh full review.\n\n"
            f"## Your Previous Findings\n\n{prior_list}\n\n"
            f"## Updated Diff\n\n```diff\n{diff}\n```\n\n"
            "## Instructions\n\n"
            "For each previous finding, state:\n"
            "- ADDRESSED: if the issue is fixed\n"
            "- STILL PRESENT: if the issue remains (explain briefly)\n"
            "- ACCEPTED: if the implementer's approach is valid (you "
            "changed your mind or it was a style preference)\n\n"
            "Then state APPROVED if all findings are addressed/accepted, "
            "or list any STILL PRESENT items.\n\n"
            "IMPORTANT: Do NOT introduce new findings that weren't in "
            "your previous review. Only evaluate the items above.\n"
        )

        session_id = self._registry.get_session(self.name)
        if not session_id:
            session_id = await self._registry.get_or_create(
                self.name,
                self._executor,
                cwd=self._cwd,
                config=self._config,
            )

        result = await self._executor.prompt_session(
            session_id=session_id,
            prompt_text=prompt_text,
            provider=self._registry.get_provider(self.name),
            config=self._config,
            step_name="review_followup",
            agent_name="reviewer",
        )

        text = result.output if isinstance(result.output, str) else ""
        approved, findings = self._parse_review_response(text)
        self._prior_findings = findings

        return [
            Message(
                msg_type=MessageType.REVIEW_RESULT,
                sender=self.name,
                recipient="supervisor",
                payload={
                    "approved": approved,
                    "findings": findings,
                    "findings_count": len(findings),
                    "review_round": self._review_count,
                },
                in_reply_to=message.sequence,
            )
        ]

    async def _get_workspace_diff(self) -> str:
        """Get the current workspace diff for review."""
        from maverick.runners.command import CommandRunner

        cwd = self._cwd or Path.cwd()
        runner = CommandRunner(cwd=cwd, timeout=30.0)
        result = await runner.run(
            ["git", "diff", "--no-color", "HEAD"],
            cwd=cwd,
        )
        diff = result.output.strip() if result.success else ""
        # Truncate very large diffs
        if len(diff) > 50000:
            diff = diff[:50000] + "\n... (truncated)"
        return diff

    def _parse_review_response(
        self, text: str
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Parse review response into (approved, findings).

        Simple heuristic parsing — looks for APPROVED or FINDINGS markers.
        Falls back to: if text contains CRITICAL or MAJOR, not approved.
        """
        text_upper = text.upper()

        # Check for explicit approval
        if "APPROVED" in text_upper and "FINDINGS" not in text_upper:
            return True, []

        # Extract findings heuristically
        findings: list[dict[str, Any]] = []
        for line in text.split("\n"):
            line_stripped = line.strip()
            # Look for patterns like "1. [CRITICAL] file:line: description"
            if any(
                sev in line_stripped.upper()
                for sev in ["CRITICAL", "MAJOR", "STILL PRESENT"]
            ):
                findings.append({
                    "severity": (
                        "critical"
                        if "CRITICAL" in line_stripped.upper()
                        else "major"
                    ),
                    "issue": line_stripped,
                    "file": "",
                    "line": "",
                })

        if not findings:
            # No explicit findings and no APPROVED marker — treat as approved
            # (the reviewer didn't flag anything specific)
            return True, []

        return False, findings

    def get_state_snapshot(self) -> dict[str, Any]:
        return {
            "review_count": self._review_count,
            "prior_findings": self._prior_findings,
        }

    def restore_state(self, snapshot: dict[str, Any]) -> None:
        self._review_count = snapshot.get("review_count", 0)
        self._prior_findings = snapshot.get("prior_findings", [])
