"""Unified Code Reviewer Agent.

This agent performs comprehensive code review by spawning parallel subagents
for different areas of expertise (Python best practices, spec compliance),
then consolidates findings into a prioritized, grouped list.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.tools import REVIEWER_TOOLS
from maverick.logging import get_logger
from maverick.models.review_models import (
    ReviewResult,
)

logger = get_logger(__name__)

# ruff: noqa: E501
UNIFIED_REVIEWER_PROMPT = """\
You are a comprehensive code reviewer. Your task is to review the work on this branch
by examining it from multiple perspectives and consolidating findings.

## Review Perspectives

Spawn two parallel subagents to review the code:

1. **Python Expert** - Reviews for:
   - Idiomatic Python and clean code principles
   - Proper type hints and async patterns
   - Pydantic usage and data validation
   - Third-party library usage per project standards (CLAUDE.md)
   - Error handling and edge cases

2. **Speckit Expert** - Reviews against the feature specification:
   - Feature completeness vs spec requirements
   - Data model compliance
   - API contracts and integration points
   - Task completion from tasks.md

## Output Format

After spawning subagents and gathering their findings, combine all findings into a single
JSON structure. Group findings by which can be fixed independently (different files, no
dependencies between fixes).

Output the following JSON at the END of your response:

```json
{
  "groups": [
    {
      "description": "Brief description of this group (e.g., 'Independent fixes - different files')",
      "findings": [
        {
          "id": "F001",
          "file": "src/maverick/foo.py",
          "line": "45",
          "issue": "Clear description of the problem",
          "severity": "critical",
          "category": "library_standards",
          "fix_hint": "Brief suggestion for how to fix (optional)"
        }
      ]
    }
  ]
}
```

### Field Requirements:

- **id**: Unique identifier (F001, F002, etc.)
- **file**: Path relative to repo root
- **line**: Line number or range (e.g., "45" or "45-67")
- **issue**: Clear, actionable description of the problem
- **severity**: One of:
  - "critical": Security issues, data corruption, crashes, spec violations
  - "major": Bugs, significant problems, library standard violations
  - "minor": Style issues, suggestions, minor improvements
- **category**: One of:
  - "spec_gap" - Missing or incomplete spec requirement
  - "library_standards" - Violates project library standards (CLAUDE.md)
  - "clean_code" - Code quality, maintainability issues
  - "type_hints" - Missing or incorrect type hints
  - "testing" - Missing tests, test quality issues
  - "data_model" - Data model issues, validation gaps
  - "security" - Security vulnerabilities
  - "performance" - Performance issues
- **fix_hint**: Optional suggestion for fixing (recommended for complex issues)

### Grouping Guidelines:

Group findings that can be worked on in parallel:
- Different files with no shared dependencies → same group
- Same file but different functions → same group if no interaction
- Dependent changes (e.g., interface change + callers) → different groups

If no issues are found, return: `{"groups": []}`

## Important Notes

- Be thorough but practical - focus on real issues, not nitpicks
- Prioritize by impact: critical > major > minor
- Every finding should be actionable - include enough context to fix
- Cross-reference between spec requirements and implementation
"""


class UnifiedReviewerAgent(MaverickAgent[dict[str, Any], ReviewResult]):
    """Agent for comprehensive code review with parallel expertise.

    This agent reviews code from multiple perspectives (Python best practices,
    spec compliance) and consolidates findings into grouped, prioritized output.

    The agent is instructed to spawn subagents for different review perspectives,
    leveraging Claude's native parallel task execution.

    Attributes:
        name: "unified-reviewer"
        system_prompt: Combined review prompt covering all perspectives
        allowed_tools: Read-only tools plus Task for spawning subagents
    """

    def __init__(
        self,
        feature_name: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        """Initialize the UnifiedReviewerAgent.

        Args:
            feature_name: Name of the feature being reviewed (for spec lookup).
            model: Optional Claude model ID.
            max_tokens: Optional maximum output tokens.
            temperature: Optional sampling temperature 0.0-1.0.
        """
        # Add Task tool for spawning subagents
        tools = list(REVIEWER_TOOLS) + ["Task"]

        super().__init__(
            name="unified-reviewer",
            system_prompt=UNIFIED_REVIEWER_PROMPT,
            allowed_tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        self._feature_name = feature_name

    async def execute(self, context: dict[str, Any]) -> ReviewResult:
        """Execute comprehensive code review.

        Args:
            context: Review context containing:
                - cwd: Working directory (repo root)
                - pr_metadata: Optional PR information
                - changed_files: Optional list of changed files
                - diff: Optional diff content
                - feature_name: Optional feature name for spec lookup

        Returns:
            ReviewResult with grouped findings.

        Raises:
            AgentError: On review failure.
            MalformedResponseError: If JSON output cannot be parsed.
        """
        from maverick.agents.utils import extract_all_text
        from maverick.exceptions import MalformedResponseError

        # Build the review prompt
        prompt = self._build_review_prompt(context)

        # Get working directory
        cwd = context.get("cwd") or Path.cwd()

        # Execute the agent
        messages = []
        async for msg in self.query(prompt, cwd=cwd):
            messages.append(msg)

        # Extract text and parse JSON output
        text = extract_all_text(messages)

        try:
            result = self._parse_review_output(text)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(
                "failed_to_parse_review_output",
                error=str(e),
                raw_text=text[:500],
            )
            raise MalformedResponseError(
                message=f"Failed to parse review output: {e}",
                raw_response=text,
            ) from e

        logger.info(
            "review_complete",
            total_findings=result.total_count,
            groups=len(result.groups),
        )

        return result

    def _build_review_prompt(self, context: dict[str, Any]) -> str:
        """Build the review prompt from context.

        Args:
            context: Review context dictionary.

        Returns:
            Formatted prompt string.
        """
        parts = ["Review the code changes on this branch."]

        # Add feature name for spec lookup
        feature_name = context.get("feature_name") or self._feature_name
        if feature_name:
            parts.append(f"\nFeature: {feature_name}")
            parts.append(f"Spec location: specs/{feature_name}/")

        # Add changed files if provided
        changed_files = context.get("changed_files")
        if changed_files:
            parts.append("\n## Changed Files")
            for f in changed_files[:50]:  # Limit to avoid huge prompts
                parts.append(f"- {f}")
            if len(changed_files) > 50:
                parts.append(f"- ... and {len(changed_files) - 50} more")

        # Add diff summary if provided
        diff = context.get("diff")
        if diff:
            # Truncate very large diffs
            if len(diff) > 50000:
                diff = diff[:50000] + "\n... (truncated)"
            parts.append("\n## Diff")
            parts.append("```diff")
            parts.append(diff)
            parts.append("```")

        # Add PR metadata if provided
        pr_metadata = context.get("pr_metadata")
        if pr_metadata:
            parts.append("\n## PR Information")
            if pr_metadata.get("title"):
                parts.append(f"Title: {pr_metadata['title']}")
            if pr_metadata.get("body"):
                parts.append(f"Description: {pr_metadata['body'][:1000]}")

        return "\n".join(parts)

    def _parse_review_output(self, text: str) -> ReviewResult:
        """Parse JSON output from review response.

        Args:
            text: Full response text containing JSON block.

        Returns:
            Parsed ReviewResult.

        Raises:
            json.JSONDecodeError: If JSON is malformed.
            KeyError: If required fields are missing.
        """
        # Find JSON block in response
        json_match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON object
            json_match = re.search(r"(\{[^{}]*\"groups\"[^{}]*\})", text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # No findings - return empty result
                logger.warning("no_json_found_in_review_output")
                return ReviewResult(groups=())

        data = json.loads(json_str)

        # Handle empty or missing groups
        if not data.get("groups"):
            return ReviewResult(groups=())

        return ReviewResult.from_dict(data)
