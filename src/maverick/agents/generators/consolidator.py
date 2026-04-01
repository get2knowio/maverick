"""ConsolidatorAgent — one-shot runway knowledge consolidator.

Reads serialized episodic records (bead outcomes, review findings, fix
attempts) and an optional existing summary, then produces an updated
``consolidated-insights.md`` markdown document.

Uses GENERATOR_TOOLS (empty frozenset) — no file system access needed.
All context is provided in the prompt by the consolidation action.
"""

from __future__ import annotations

import json
from typing import Any

from maverick.agents.generators.base import GeneratorAgent
from maverick.logging import get_logger

__all__ = ["ConsolidatorAgent"]

logger = get_logger(__name__)

# Maximum total prompt size (~50KB) to stay within context limits.
_MAX_PROMPT_SIZE: int = 51200

# =============================================================================
# System prompt
# =============================================================================

SYSTEM_PROMPT = """\
You are a knowledge consolidator for an AI-powered development workflow.

You will receive episodic records from past development work (bead outcomes, \
review findings, fix attempts) and optionally an existing consolidated summary. \
Your job is to produce an updated **consolidated-insights.md** document that \
distills the episodic data into high-quality, actionable insights.

## Output format

Return ONLY the markdown content for consolidated-insights.md. Do NOT wrap it \
in code fences. The document must have these four sections:

### Validation Failure Patterns
Identify recurring validation failures — common error types, root causes, \
which tools/stages fail most, and proven fixes.

### Recurring Review Findings
Summarize review findings by category and severity. Note patterns in what \
reviewers flag repeatedly (security, correctness, style, etc.).

### Successful Implementation Patterns
Highlight approaches that consistently led to clean validation and review. \
Note effective strategies, tools used well, and good decision patterns.

### Frequently Problematic Files
Identify files that appear repeatedly in failures, findings, or fix attempts. \
Note hotspots where extra care is warranted.

### Implementation Timing Patterns
Analyze average bead implementation time, trends across runs, and correlation \
between bead complexity (SC count, file scope size) and duration. Identify \
beads that consistently take longer than average.

### Retry and Convergence Patterns
Analyze retry rates per bead, issue count trajectories across attempts \
(converging vs oscillating), escalation chain depths, and which bead types \
exhaust retries most often. Note whether prior-attempt context improves \
convergence.

### Spec Compliance Patterns
Identify which verification properties pass/fail most often, common assertion \
mismatches (e.g., exact string differences), and whether spec compliance \
reduces overall retry count compared to reviewer-gated runs.

## Guidelines

- If an existing summary is provided, UPDATE it with new information rather \
than starting from scratch. Preserve valid insights from the existing summary.
- Be specific — include file names, error messages, and concrete patterns.
- Quantify when possible (e.g., "3 out of 5 beads failed lint").
- Omit sections that have no relevant data (but keep the heading with "No data").
- Keep the document concise — aim for 200-500 lines.
"""


# =============================================================================
# Agent class
# =============================================================================


class ConsolidatorAgent(GeneratorAgent):
    """One-shot agent that consolidates runway episodic data into summaries.

    Receives serialized episodic records and an optional existing summary.
    Returns updated markdown for ``consolidated-insights.md``.

    Uses GENERATOR_TOOLS (empty) — no file system access needed.
    All context is pre-gathered and passed in the prompt.
    """

    def __init__(self, model: str | None = None) -> None:
        from maverick.constants import DEFAULT_MODEL

        super().__init__(
            name="consolidator",
            system_prompt=SYSTEM_PROMPT,
            model=model or DEFAULT_MODEL,
            temperature=0.0,
        )

    def build_prompt(self, context: dict[str, Any]) -> str:
        """Construct the prompt from episodic records and existing summary.

        Args:
            context: Dict with:
                - existing_summary: str | None — current consolidated-insights.md
                - bead_outcomes: list[dict] — serialized BeadOutcome records
                - review_findings: list[dict] — serialized RunwayReviewFinding records
                - fix_attempts: list[dict] — serialized FixAttemptRecord records

        Returns:
            Complete prompt text ready for the agent.
        """
        existing_summary = context.get("existing_summary")
        bead_outcomes = context.get("bead_outcomes", [])
        review_findings = context.get("review_findings", [])
        fix_attempts = context.get("fix_attempts", [])

        parts: list[str] = []

        if existing_summary:
            parts.append("## Existing Summary\n")
            parts.append(
                self._truncate_input(
                    existing_summary, _MAX_PROMPT_SIZE // 4, "existing_summary"
                )
            )
            parts.append("")

        if bead_outcomes:
            outcomes_json = json.dumps(bead_outcomes, ensure_ascii=False, indent=2)
            parts.append(
                f"## Bead Outcomes ({len(bead_outcomes)} records)\n```json\n"
                + self._truncate_input(
                    outcomes_json, _MAX_PROMPT_SIZE // 3, "bead_outcomes"
                )
                + "\n```\n"
            )

        if review_findings:
            findings_json = json.dumps(review_findings, ensure_ascii=False, indent=2)
            parts.append(
                f"## Review Findings ({len(review_findings)} records)\n```json\n"
                + self._truncate_input(
                    findings_json, _MAX_PROMPT_SIZE // 3, "review_findings"
                )
                + "\n```\n"
            )

        if fix_attempts:
            attempts_json = json.dumps(fix_attempts, ensure_ascii=False, indent=2)
            parts.append(
                f"## Fix Attempts ({len(fix_attempts)} records)\n```json\n"
                + self._truncate_input(
                    attempts_json, _MAX_PROMPT_SIZE // 3, "fix_attempts"
                )
                + "\n```\n"
            )

        if not parts:
            parts.append("No episodic data to consolidate.")

        return "\n".join(parts)

    @staticmethod
    def parse_summary(raw_output: str) -> str:
        """Extract markdown summary from agent output.

        Strips markdown code fences if the model wraps the output.

        Args:
            raw_output: Raw text from the agent.

        Returns:
            Clean markdown content.
        """
        text = raw_output.strip()

        # Strip outer markdown fences (```markdown ... ``` or ``` ... ```)
        if text.startswith("```"):
            lines = text.splitlines()
            # Remove first fence line
            if lines:
                lines = lines[1:]
            # Remove last fence line
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        return text
