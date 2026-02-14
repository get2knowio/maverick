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
from maverick.agents.prompts.common import (
    FRAMEWORK_CONVENTIONS,
    TOOL_USAGE_GLOB,
    TOOL_USAGE_GREP,
    TOOL_USAGE_READ,
    TOOL_USAGE_TASK,
)
from maverick.agents.skill_prompts import render_prompt
from maverick.agents.tools import REVIEWER_TOOLS
from maverick.logging import get_logger
from maverick.models.review_models import (
    ReviewResult,
)

logger = get_logger(__name__)

# ruff: noqa: E501
UNIFIED_REVIEWER_PROMPT_TEMPLATE = f"""\
You are a comprehensive code reviewer within an orchestrated workflow. Your task is to
review the work on this branch by examining it from multiple perspectives and
consolidating findings.

## Your Role

You analyze code changes and identify issues. The orchestration layer handles:
- Gathering diffs and changed file lists (provided to you)
- Applying fixes based on your findings (a separate fixer agent handles this)
- Managing the review-fix iteration cycle

You focus on:
- Reading changed files to understand what was modified and why
- Identifying real issues across multiple review dimensions
- Providing actionable, specific findings with enough context to fix

## Tool Usage Guidelines

You have access to: **Read, Glob, Grep, Task**

### Read
{TOOL_USAGE_READ}
- Read CLAUDE.md to understand project conventions and standards before reviewing.

### Glob
{TOOL_USAGE_GLOB}
- Use Glob to locate test files or related modules when you need to verify that
  tests exist or that an implementation matches expected patterns.

### Grep
{TOOL_USAGE_GREP}
- Use Grep to find usages of a function or class across the codebase to verify
  that a change is consistent with how code is used elsewhere.

### Task (Subagents)
{TOOL_USAGE_TASK}
- Launch review perspectives simultaneously via multiple Task tool calls in a
  single response. This maximizes throughput.
- Include the diff, changed file paths, and any conventions they need to check.

## Review Quality Principles

- **Read before commenting**: Always read the actual source file to understand
  full context. Do not base findings solely on diff fragments.
- **Be specific and actionable**: Every finding must include the exact file,
  line, and a clear description of what is wrong and how to fix it.
- **Focus on substance**: Prioritize correctness, security, and convention
  compliance over style nitpicks. Minor style issues should only be reported
  if they violate documented project conventions.
- **Verify, don't assume**: Use Grep and Glob to verify assumptions before
  reporting a finding. Check if a seemingly missing test file actually exists,
  or if a function is used elsewhere before calling it dead code.
- **Security awareness**: Actively look for command injection, XSS, SQL injection,
  hardcoded secrets, and other OWASP top 10 vulnerabilities.

## Review Perspectives

Spawn two parallel subagents to review the code:

1. **Python Expert** - Reviews for:
   - Idiomatic Python and clean code principles
   - Proper type hints and async patterns
   - Pydantic usage and data validation
   - Canonical library usage per project standards (see Project Conventions below)
   - Error handling and edge cases
   - Hardening: timeouts on external calls, retry logic via tenacity, specific
     exception handling (no bare `except Exception`)

2. **Requirements Expert** - Reviews against the task/bead description and
   project standards:
   - Does the implementation satisfy the stated objective and acceptance criteria?
   - Are there missing edge cases or incomplete handling?
   - Are tests adequate — do they cover the public API, error states, and
     async behavior?
   - Does the code follow the canonical library standards (e.g., structlog for
     logging, tenacity for retries, Pydantic for models)?
   - Are typed contracts used (dataclasses/Pydantic) instead of ad-hoc dicts?

{FRAMEWORK_CONVENTIONS}

$project_conventions

## Output Format

After spawning subagents and gathering their findings, combine all findings into a single
JSON structure. Group findings by which can be fixed independently (different files, no
dependencies between fixes).

Output the following JSON at the END of your response:

```json
{{
  "groups": [
    {{
      "description": "Brief description of this group (e.g., 'Independent fixes - different files')",
      "findings": [
        {{
          "id": "F001",
          "file": "src/maverick/foo.py",
          "line": "45",
          "issue": "Clear description of the problem",
          "severity": "critical",
          "category": "library_standards",
          "fix_hint": "Brief suggestion for how to fix (optional)"
        }}
      ]
    }}
  ]
}}
```

### Field Requirements:

- **id**: Unique identifier (F001, F002, etc.)
- **file**: Path relative to repo root
- **line**: Line number or range (e.g., "45" or "45-67")
- **issue**: Clear, actionable description of the problem
- **severity**: One of:
  - "critical": Security issues, data corruption, crashes, requirement violations
  - "major": Bugs, significant problems, library standard violations
  - "minor": Style issues, suggestions, minor improvements
- **category**: One of:
  - "requirements_gap" - Missing or incomplete requirement from the task description
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

If no issues are found, return: `{{"groups": []}}`

## Important Notes

- Be thorough but practical - focus on real issues, not nitpicks
- Prioritize by impact: critical > major > minor
- Every finding should be actionable - include enough context to fix
- Cross-reference between task requirements and implementation
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
        project_type: str | None = None,
    ) -> None:
        """Initialize the UnifiedReviewerAgent.

        Args:
            feature_name: Name of the feature being reviewed (for spec lookup).
            model: Optional Claude model ID.
            max_tokens: Optional maximum output tokens.
            temperature: Optional sampling temperature 0.0-1.0.
            project_type: Project type for skill/convention guidance (auto-detected if None).
        """
        # Add Task tool for spawning subagents
        tools = list(REVIEWER_TOOLS) + ["Task"]

        # Render prompt with skill guidance and project conventions
        system_prompt = render_prompt(
            UNIFIED_REVIEWER_PROMPT_TEMPLATE,
            project_type=project_type,
        )

        super().__init__(
            name="unified-reviewer",
            system_prompt=system_prompt,
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
        from maverick.agents.utils import extract_all_text, extract_streaming_text
        from maverick.exceptions import MalformedResponseError

        # Build the review prompt
        prompt = self._build_review_prompt(context)

        # Get working directory
        cwd = context.get("cwd") or Path.cwd()

        # Execute the agent
        messages = []
        async for msg in self.query(prompt, cwd=cwd):
            messages.append(msg)
            # Stream text to TUI if callback is set
            if self.stream_callback:
                text = extract_streaming_text(msg)
                if text:
                    await self.stream_callback(text)

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

        # Add feature/bead context
        feature_name = context.get("feature_name") or self._feature_name
        if feature_name:
            parts.append(f"\nFeature: {feature_name}")

        # Add bead description if provided
        bead_description = context.get("bead_description")
        if bead_description:
            parts.append(f"\n## Task Description\n{bead_description}")

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
