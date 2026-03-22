"""ReviewFixerAgent for fixing code review findings.

This agent fixes code review findings with parallel execution for independent
issues. It receives grouped findings and spawns subagents to work on them
concurrently where possible.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from maverick.agents.base import MaverickAgent
from maverick.agents.contracts import validate_output
from maverick.agents.tools import ISSUE_FIXER_TOOLS
from maverick.logging import get_logger
from maverick.models.review_models import (
    Finding,
    FindingGroup,
    FixOutcome,
)

logger = get_logger(__name__)


class _FixOutcomesWrapper(BaseModel):
    """Wrapper for validating fix outcomes JSON output."""

    outcomes: list[FixOutcome]


# ruff: noqa: E501
SIMPLE_FIXER_PROMPT = """\
You are a code fixer within an orchestrated workflow. You will receive a list of
findings grouped by parallelization opportunity. For each group of independent
findings, you may spawn subagents to fix them in parallel.

## Your Role

You fix code review findings by modifying source files. The orchestration layer handles:
- Running validation pipelines after your changes
- Tracking fix iterations and overall progress
- Managing the review-fix cycle

You focus on:
- Reading files to understand context before making changes
- Applying targeted, minimal fixes for each finding
- Reporting outcomes accurately for every finding

## Tool Usage Guidelines

You have access to: **Read, Write, Edit, Glob, Grep, Task**

### Read
- Use Read to examine files before modifying them. You MUST read a file before
  using Edit on it.
- Read the file around the reported line number to understand context before
  applying any fix.

### Edit
- Use Edit for targeted replacements in existing files. This is your primary
  tool for applying fixes.
- You MUST Read a file before using Edit on it. Edit will fail otherwise.
- The `old_string` must be unique in the file. If it is not unique, include
  more surrounding context to disambiguate.
- Preserve exact indentation (tabs/spaces) from the file content.

### Write
- Use Write to create **new** files or when a complete file rewrite is needed.
  Prefer Edit for targeted fixes.
- Do NOT create files unless they are necessary. Prefer editing existing files.

### Glob
- Use Glob to find files by name or pattern (e.g., `**/*.py`).
- Use Glob instead of guessing file paths when the finding references a file
  you need to locate.

### Grep
- Use Grep to search file contents by regex pattern.
- Use Grep to find usages, imports, or related code when a fix requires
  understanding how a function or class is used elsewhere.

### Task (Subagents)
- Use Task to spawn subagents for parallel work. Each subagent operates
  independently with its own context.
- When findings are in the same group (independent), launch them simultaneously
  via multiple Task tool calls in a single response.
- Provide clear, detailed prompts to subagents since they start with no context.
  Include file paths, the finding details, and any conventions they need to follow.

## Code Quality Principles

- **Minimal changes only**: Make only the changes necessary to fix the stated
  finding. Do not refactor surrounding code.
- **No feature additions**: Do not add features, improvements, or enhancements
  beyond what is needed to resolve the finding.
- **Security awareness**: Do not introduce command injection, XSS, SQL injection,
  or other vulnerabilities when applying fixes.
- **Read before writing**: Always read and understand the file before modifying
  it. Do not guess at file contents or structure.
- **Match existing style**: Preserve the coding style, naming conventions, and
  formatting of the surrounding code.

## Outcomes

For each finding, report one of these outcomes:

- **fixed**: Code changes made successfully. Include brief description of what changed.
- **blocked**: Cannot fix due to valid technical reason:
  - Missing dependency or package
  - Architectural constraint requiring design discussion
  - Conflicts with other code that needs human decision
  - File was deleted or moved
- **deferred**: Need more context or hit unexpected issue. Will retry in next iteration.

## Important Rules

1. **You MUST report on EVERY finding** - No silent skipping allowed
2. **Fixed means actually fixed** - Make the code changes, don't just describe them
3. **Blocked requires valid justification** - "Too hard" or "don't know how" = deferred, not blocked
4. **Deferred items get retried** - Use deferred if you need more context or hit a snag

## Output Format

After fixing (or attempting to fix) all findings, output JSON at the END:

```json
{
  "outcomes": [
    {
      "id": "F001",
      "outcome": "fixed",
      "explanation": "Replaced subprocess.run with CommandRunner"
    },
    {
      "id": "F002",
      "outcome": "blocked",
      "explanation": "File was deleted in previous commit"
    },
    {
      "id": "F003",
      "outcome": "deferred",
      "explanation": "Need to understand the existing validation logic first"
    }
  ]
}
```

Every finding ID from the input MUST appear in the output.
"""


class ReviewFixerAgent(MaverickAgent[dict[str, Any], list[FixOutcome]]):
    """Agent for fixing code review findings with parallel execution.

    This agent receives grouped findings and fixes them, spawning subagents
    for parallel work where findings are independent.

    Attributes:
        name: "simple-fixer"
        instructions: Focused on fixing with accountability
        allowed_tools: File operations plus Task for parallel work
    """

    def __init__(
        self,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        """Initialize the ReviewFixerAgent.

        Args:
            model: Optional Claude model ID.
            max_tokens: Optional maximum output tokens.
            temperature: Optional sampling temperature 0.0-1.0.
        """
        # Add Task tool for spawning subagents
        tools = list(ISSUE_FIXER_TOOLS) + ["Task"]

        # output_model is intentionally NOT set here: the agent uses a wrapper
        # model (_FixOutcomesWrapper) that doesn't match the actual return type
        # (list[FixOutcome]), and the validate_output fallback in parse_outcomes
        # handles extraction and per-item graceful degradation.
        super().__init__(
            name="simple-fixer",
            instructions=SIMPLE_FIXER_PROMPT,
            allowed_tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def build_prompt(self, context: dict[str, Any]) -> str:
        """Construct the prompt string from context (FR-017).

        Delegates to the internal _build_prompt method using findings and
        groups extracted from the context dict.

        Args:
            context: Fix context containing findings, groups, and iteration.

        Returns:
            Complete prompt text ready for the ACP agent.
        """
        findings: list[Finding] = context.get("findings", [])
        groups: list[FindingGroup] | None = context.get("groups")
        iteration: int = context.get("iteration", 1)
        return self._build_prompt(findings, groups, iteration)

    def _build_prompt(
        self,
        findings: list[Finding],
        groups: list[FindingGroup] | None,
        iteration: int,
    ) -> str:
        """Build the fix prompt.

        Args:
            findings: All findings to fix.
            groups: Optional groupings for parallelization.
            iteration: Current iteration number.

        Returns:
            Formatted prompt string.
        """
        parts = [f"# Fix Iteration {iteration}"]
        parts.append("")
        parts.append(
            f"You have **{len(findings)} finding(s)** to address. "
            "Report on ALL of them."
        )
        parts.append("")

        if groups:
            # Use provided groups
            for i, group in enumerate(groups, 1):
                parts.append(f"## Group {i}: {group.description}")
                parts.append("")
                for finding in group.findings:
                    parts.extend(self._format_finding(finding))
                parts.append("")
        else:
            # No groups, list all findings
            parts.append("## Findings")
            parts.append("")
            for finding in findings:
                parts.extend(self._format_finding(finding))
            parts.append("")

        parts.append("---")
        parts.append("")
        parts.append(
            "**REMINDER**: Output JSON with an entry for EVERY finding ID above."
        )

        return "\n".join(parts)

    def _format_finding(self, finding: Finding) -> list[str]:
        """Format a single finding for the prompt.

        Args:
            finding: Finding to format.

        Returns:
            List of lines for this finding.
        """
        lines = [
            f"### {finding.id}: {finding.issue}",
            f"- **File**: {finding.file}:{finding.line}",
            f"- **Severity**: {finding.severity}",
            f"- **Category**: {finding.category}",
        ]
        if finding.fix_hint:
            lines.append(f"- **Hint**: {finding.fix_hint}")
        lines.append("")
        return lines

    def parse_outcomes(
        self,
        text: str,
        findings: list[Finding],
    ) -> list[FixOutcome]:
        """Parse JSON outcomes from response using validate_output.

        Uses the centralized ``validate_output`` pipeline to extract and
        validate JSON from the agent's markdown output.  Individual items
        that fail Pydantic validation are gracefully degraded to deferred
        outcomes rather than dropping the entire response.

        Args:
            text: Full response text.
            findings: Input findings for validation.

        Returns:
            List of parsed FixOutcome objects.
        """
        # Try structured validation first (handles ```json blocks)
        wrapper = validate_output(text, _FixOutcomesWrapper, strict=False)
        if wrapper is not None:
            return list(wrapper.outcomes)

        # Fallback for per-item graceful degradation — when validate_output
        # rejects the wrapper (e.g., individual FixOutcome has invalid outcome
        # literal), extract and validate items individually, defaulting invalid
        # ones to 'deferred'.

        # Try code-block extraction
        json_match = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            logger.warning("no_json_found_in_fixer_output")
            return []

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error("json_parse_error", error=str(e))
            return []

        outcomes_raw = data.get("outcomes", [])
        if not isinstance(outcomes_raw, list):
            logger.error("outcomes_not_list")
            return []

        outcomes: list[FixOutcome] = []
        for item in outcomes_raw:
            if not isinstance(item, dict):
                continue
            try:
                outcomes.append(FixOutcome.model_validate(item))
            except ValidationError:
                # Gracefully degrade: keep the id/explanation but force deferred
                finding_id = item.get("id", "unknown")
                explanation = item.get("explanation", "")
                logger.warning(
                    "invalid_fix_outcome_item",
                    finding_id=finding_id,
                    raw_outcome=item.get("outcome"),
                )
                outcomes.append(
                    FixOutcome(
                        id=str(finding_id),
                        outcome="deferred",
                        explanation=explanation or "Invalid outcome from agent",
                    )
                )

        return outcomes

    def _fill_missing(
        self,
        outcomes: list[FixOutcome],
        findings: list[Finding],
    ) -> list[FixOutcome]:
        """Fill in missing findings with auto-defer.

        Args:
            outcomes: Parsed outcomes.
            findings: All input findings.

        Returns:
            Outcomes with missing items filled in.
        """
        outcome_ids = {o.id for o in outcomes}

        missing = []
        for finding in findings:
            if finding.id not in outcome_ids:
                logger.warning(
                    "auto_deferring_missing_finding",
                    finding_id=finding.id,
                )
                missing.append(
                    FixOutcome(
                        id=finding.id,
                        outcome="deferred",
                        explanation="Agent did not report on this finding",
                    )
                )

        return outcomes + missing
