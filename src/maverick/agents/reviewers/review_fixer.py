"""Review Fixer Agent.

This agent receives consolidated findings from dual-agent code review
(spec + technical) and fixes issues with full accountability tracking.
Every issue must be reported on - no silent skipping allowed.
"""

from __future__ import annotations

import json
import re
from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.prompts.review_fixer import format_system_prompt
from maverick.agents.tools import ISSUE_FIXER_TOOLS
from maverick.logging import get_logger
from maverick.models.fixer_io import (
    FixerInput,
    FixerInputItem,
    FixerOutput,
    FixerOutputItem,
)

logger = get_logger(__name__)

#: Maximum length for review report before truncation
MAX_REVIEW_REPORT_LENGTH = 10_000


class ReviewFixerAgent(MaverickAgent[FixerInput, FixerOutput]):
    """Agent for fixing code review findings with full accountability.

    This agent receives all issues from the dual-agent review and must
    report on every single issue. It uses the accountability-focused
    system prompt that:
    - Requires reporting on every issue
    - Rejects invalid justifications
    - Re-sends deferred items in subsequent iterations
    - Documents valid blocked reasons

    For legacy dict-based contexts, use build_fixer_input_from_legacy()
    to convert to FixerInput before calling execute().

    Attributes:
        name: "review-fixer"
        system_prompt: Accountability-focused prompt
        allowed_tools: File operations + search for context
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
        # Start with no previous attempts; will update per-execution
        system_prompt = format_system_prompt(has_previous_attempts=False)
        super().__init__(
            name="review-fixer",
            system_prompt=system_prompt,
            allowed_tools=list(ISSUE_FIXER_TOOLS),
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def execute(self, context: FixerInput) -> FixerOutput:
        """Execute review fixes with accountability tracking.

        Args:
            context: FixerInput containing all findings to address.

        Returns:
            FixerOutput with status for every input item.
        """
        return await self._execute_accountability(context)

    async def _execute_accountability(self, context: FixerInput) -> FixerOutput:
        """Execute review fixes with full accountability tracking.

        Args:
            context: FixerInput containing items to fix with their history.

        Returns:
            FixerOutput with status for every input item.
        """
        # Check if any items have previous attempts
        has_previous = any(len(item.previous_attempts) > 0 for item in context.items)

        # Update system prompt based on whether there are previous attempts
        self._system_prompt = format_system_prompt(has_previous_attempts=has_previous)

        # Build the user prompt with all issues
        prompt = self._build_prompt(context)

        # Execute the agent
        raw_output = await self._run_agent(prompt)

        # Parse the output
        try:
            fixer_output = self._parse_output(raw_output)
        except ValueError as e:
            logger.warning(
                "Failed to parse fixer output, auto-deferring all",
                error=str(e),
            )
            # Create empty output that will be filled with auto-defers
            fixer_output = FixerOutput(items=(), summary="Parse error - auto-deferred")

        # Fill in any missing items with auto-defer
        fixer_output = self._fill_missing(fixer_output, context)

        return fixer_output

    def _build_prompt(self, fixer_input: FixerInput) -> str:
        """Build the user prompt with all issues and their history.

        Args:
            fixer_input: The fixer input with all items to address.

        Returns:
            Formatted user prompt.
        """
        parts: list[str] = []

        # Header with iteration info
        parts.append(f"# Fix Loop Iteration {fixer_input.iteration}")
        parts.append("")
        parts.append(
            f"You have {len(fixer_input.items)} issue(s) to address. "
            "You MUST report on ALL of them."
        )
        parts.append("")

        # Add context if provided
        if fixer_input.context:
            parts.append("## Context")
            parts.append(fixer_input.context)
            parts.append("")

        # Add each issue
        parts.append("## Issues to Address")
        parts.append("")

        for item in fixer_input.items:
            parts.append(f"### {item.finding_id}: {item.title}")
            parts.append(f"**Severity**: {item.severity}")
            parts.append(f"**Description**: {item.description}")

            if item.file_path:
                parts.append(f"**File**: {item.file_path}")
                if item.line_range:
                    start, end = item.line_range
                    parts.append(f"**Lines**: {start}-{end}")

            if item.suggested_fix:
                parts.append(f"**Suggested Fix**: {item.suggested_fix}")

            # Add previous attempt history if any
            if item.previous_attempts:
                parts.append("")
                parts.append("**Previous Attempts** (you must make progress!):")
                for i, attempt in enumerate(item.previous_attempts, 1):
                    outcome = attempt.get("outcome", "unknown")
                    justification = attempt.get("justification", "No justification")
                    iteration = attempt.get("iteration", "?")
                    parts.append(
                        f"  - Attempt {i} (iteration {iteration}): "
                        f"{outcome} - {justification}"
                    )

            parts.append("")

        # Reminder about accountability
        parts.append("---")
        parts.append("")
        parts.append("**REMINDER**: You must provide a JSON response with an entry for")
        parts.append("EVERY issue listed above. Missing items will be auto-deferred.")
        parts.append("")

        return "\n".join(parts)

    def _parse_output(self, response: str) -> FixerOutput:
        """Parse the fixer agent's JSON output.

        Args:
            response: Full agent response text.

        Returns:
            FixerOutput with parsed items.

        Raises:
            ValueError: If JSON cannot be parsed.
        """
        # Look for ```json ... ``` block first
        json_block_pattern = r"```json\s*([\s\S]*?)\s*```"
        matches = re.findall(json_block_pattern, response)

        json_str: str | None = None

        if matches:
            # Use the last JSON block (most likely to be the final output)
            json_str = matches[-1].strip()
        else:
            # Try to find raw JSON object with "items" key
            # Look for { "items": ... } pattern
            json_pattern = (
                r'\{\s*"items"\s*:\s*\[[\s\S]*?\]\s*'
                r'(?:,\s*"summary"\s*:\s*"[^"]*")?\s*\}'
            )
            raw_matches = re.findall(json_pattern, response)
            if raw_matches:
                json_str = raw_matches[-1].strip()

        if not json_str:
            raise ValueError("No JSON output found in response")

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e

        if not isinstance(data, dict):
            raise ValueError("JSON output is not a dictionary")

        if "items" not in data:
            raise ValueError("JSON output missing 'items' key")

        items_data = data["items"]
        if not isinstance(items_data, list):
            raise ValueError("'items' is not a list")

        items: list[FixerOutputItem] = []
        for item_data in items_data:
            if not isinstance(item_data, dict):
                logger.warning("Skipping non-dict item in output")
                continue

            finding_id = item_data.get("finding_id", "")
            status = item_data.get("status", "deferred")
            justification = item_data.get("justification")
            changes_made = item_data.get("changes_made")

            if not finding_id:
                logger.warning("Skipping item with missing finding_id")
                continue

            items.append(
                FixerOutputItem(
                    finding_id=finding_id,
                    status=status,
                    justification=justification,
                    changes_made=changes_made,
                )
            )

        summary = data.get("summary")

        return FixerOutput(items=tuple(items), summary=summary)

    def _fill_missing(
        self, fixer_output: FixerOutput, fixer_input: FixerInput
    ) -> FixerOutput:
        """Fill in missing items with auto-defer status.

        Any input items not present in output are auto-deferred with
        justification "Agent did not provide status".

        Args:
            fixer_output: The parsed fixer output.
            fixer_input: The original input.

        Returns:
            FixerOutput with all input items accounted for.
        """
        # Build set of finding IDs already in output
        output_ids = {item.finding_id for item in fixer_output.items}

        # Find missing items
        missing_items: list[FixerOutputItem] = []
        for input_item in fixer_input.items:
            if input_item.finding_id not in output_ids:
                logger.warning(
                    "Auto-deferring missing item",
                    finding_id=input_item.finding_id,
                )
                missing_items.append(
                    FixerOutputItem(
                        finding_id=input_item.finding_id,
                        status="deferred",
                        justification="Agent did not provide status",
                        changes_made=None,
                    )
                )

        if not missing_items:
            return fixer_output

        # Combine existing and missing items
        all_items = list(fixer_output.items) + missing_items

        # Update summary if we added missing items
        summary = fixer_output.summary
        if summary:
            summary = f"{summary} ({len(missing_items)} items auto-deferred)"
        else:
            summary = f"{len(missing_items)} items auto-deferred"

        return FixerOutput(items=tuple(all_items), summary=summary)

    async def _run_agent(self, prompt: str) -> str:
        """Run the agent with the given prompt."""
        from maverick.agents.utils import extract_all_text

        messages = []
        async for msg in self.query(prompt):
            messages.append(msg)
        return extract_all_text(messages)


def build_fixer_input(
    findings: list[dict[str, Any]],
    iteration: int,
    context: str = "",
) -> FixerInput:
    """Build a FixerInput from a list of finding dictionaries.

    This is a helper function for constructing FixerInput from
    the review registry or other sources.

    Args:
        findings: List of finding dictionaries with keys:
            - finding_id: Unique ID (e.g., RS001)
            - severity: Severity level
            - title: Short title
            - description: Detailed description
            - file_path: Optional file path
            - line_start/line_end: Optional line range
            - suggested_fix: Optional suggested fix
            - previous_attempts: Optional list of attempt dicts
        iteration: Current iteration number (1-indexed for display).
        context: Additional context string.

    Returns:
        FixerInput ready for the agent.
    """
    items: list[FixerInputItem] = []

    for finding in findings:
        line_range: tuple[int, int] | None = None
        line_start = finding.get("line_start")
        if line_start is not None:
            line_end = finding.get("line_end") or line_start
            line_range = (int(line_start), int(line_end))

        previous_attempts = finding.get("previous_attempts", [])
        if not isinstance(previous_attempts, (list, tuple)):
            previous_attempts = []

        items.append(
            FixerInputItem(
                finding_id=finding.get("finding_id", finding.get("id", "")),
                severity=finding.get("severity", "unknown"),
                title=finding.get("title", ""),
                description=finding.get("description", ""),
                file_path=finding.get("file_path"),
                line_range=line_range,
                suggested_fix=finding.get("suggested_fix"),
                previous_attempts=tuple(previous_attempts),
            )
        )

    return FixerInput(
        iteration=iteration,
        items=tuple(items),
        context=context,
    )


def build_fixer_input_from_legacy(
    legacy_context: dict[str, Any],
    iteration: int = 1,
) -> FixerInput:
    """Convert legacy dict context to FixerInput.

    This function bridges the legacy dict-based interface to the new typed
    FixerInput model. Use this at API boundaries when receiving untyped data.

    Args:
        legacy_context: Legacy context dict containing:
            - review_report: Combined review report from both reviewers
            - issues: List of issue dicts to fix
            - recommendation: Current review recommendation
            - changed_files: List of files changed in the PR
        iteration: Current iteration number (1-indexed for display).

    Returns:
        FixerInput ready for the ReviewFixerAgent.

    Example:
        ```python
        # At API boundary, convert dict to typed model
        fixer_input = build_fixer_input_from_legacy(legacy_context)
        result = await agent.execute(fixer_input)
        ```
    """
    issues = legacy_context.get("issues", [])
    review_report = legacy_context.get("review_report", "")
    changed_files = legacy_context.get("changed_files", [])

    # Build item list
    item_list: list[FixerInputItem] = []

    # If no structured issues, create a single item from the report
    if not issues and review_report:
        # Create a synthetic finding from the review report
        item_list.append(
            FixerInputItem(
                finding_id="LEGACY001",
                severity="major",
                title="Issues from review report",
                description=review_report[:2000],  # Truncate long reports
                file_path=None,
                line_range=None,
                suggested_fix=None,
                previous_attempts=(),
            )
        )
    else:
        # Convert issues list to FixerInputItem tuples
        for i, issue in enumerate(issues, start=1):
            if not isinstance(issue, dict):
                continue

            line_range: tuple[int, int] | None = None
            line_start = issue.get("line_start") or issue.get("line_number")
            if line_start is not None:
                line_end = issue.get("line_end") or line_start
                line_range = (int(line_start), int(line_end))

            # Ensure finding_id is always a string
            raw_id = issue.get("finding_id") or issue.get("id") or f"L{i:03d}"
            finding_id = str(raw_id) if raw_id else f"L{i:03d}"

            item_list.append(
                FixerInputItem(
                    finding_id=finding_id,
                    severity=issue.get("severity", "major"),
                    title=issue.get("title", issue.get("description", "")[:80]),
                    description=issue.get("description", ""),
                    file_path=issue.get("file_path"),
                    line_range=line_range,
                    suggested_fix=issue.get("suggested_fix"),
                    previous_attempts=(),
                )
            )

    items: tuple[FixerInputItem, ...] = tuple(item_list)

    # Build context string from available information
    context_parts: list[str] = []
    if changed_files:
        files_preview = changed_files[:10]
        context_parts.append(f"Changed files: {', '.join(files_preview)}")
        if len(changed_files) > 10:
            context_parts.append(f"... and {len(changed_files) - 10} more files")

    recommendation = legacy_context.get("recommendation", "")
    if recommendation:
        context_parts.append(f"Review recommendation: {recommendation}")

    context = "\n".join(context_parts) if context_parts else ""

    return FixerInput(
        iteration=iteration,
        items=items,
        context=context,
    )
