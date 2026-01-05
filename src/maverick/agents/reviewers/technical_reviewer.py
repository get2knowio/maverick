"""Technical Quality Reviewer Agent.

This agent reviews code changes for technical quality, focusing on:

- Code correctness and potential bugs
- Security vulnerabilities
- Performance considerations
- Best practices and patterns
- Maintainability and readability
"""

from __future__ import annotations

from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.prompts.reviewer_output import (
    REVIEWER_OUTPUT_SCHEMA,
    TECH_REVIEWER_ID_PREFIX,
)
from maverick.agents.reviewers.utils import parse_findings, validate_findings
from maverick.agents.skill_prompts import render_prompt
from maverick.agents.tools import REVIEWER_TOOLS
from maverick.logging import get_logger

logger = get_logger(__name__)

TECHNICAL_REVIEWER_PROMPT_TEMPLATE = """\
You are a Technical Quality Reviewer. Your role is to review code changes for
technical excellence, identifying issues and suggesting improvements.

$skill_guidance

## Your Focus Areas

1. **Correctness**
   - Logic errors and potential bugs
   - Edge cases not handled
   - Race conditions in concurrent code
   - Incorrect error handling

2. **Security**
   - Input validation issues
   - Injection vulnerabilities (SQL, command, etc.)
   - Authentication/authorization gaps
   - Sensitive data exposure
   - Insecure dependencies

3. **Performance**
   - Inefficient algorithms (O(n²) when O(n) possible)
   - Unnecessary database queries (N+1 problems)
   - Memory leaks or excessive allocation
   - Missing caching opportunities
   - Blocking operations in async code

4. **Best Practices**
   - SOLID principles violations
   - DRY violations (duplicated code)
   - Proper error handling patterns
   - Appropriate abstraction levels
   - Clear naming and code organization

5. **Maintainability**
   - Code clarity and readability
   - Appropriate comments (not too few, not too many)
   - Test coverage for new code
   - Documentation for public APIs

## Review Process

1. Examine the diff to understand what changed
2. Consider the context of surrounding code
3. Identify issues by category
4. Prioritize by severity (critical > major > minor > suggestion)
5. Provide specific, actionable feedback

## Review Analysis

Provide your review analysis including:

### Technical Review Summary

**Overall Quality**: [EXCELLENT | GOOD | NEEDS_WORK | POOR]

### Critical Issues (must fix)
- Issue description with file:line reference
- Suggested fix

### Major Issues (should fix)
- Issue description with file:line reference
- Suggested fix

### Minor Issues (nice to fix)
- Issue description
- Suggested improvement

### Positive Observations
- Well-done aspects worth noting

Be specific and constructive. Reference exact file paths and line numbers.
Explain WHY something is an issue, not just WHAT is wrong.

{output_schema}
"""

# Build the complete prompt template with structured output schema
_TECH_REVIEWER_PROMPT_WITH_SCHEMA = TECHNICAL_REVIEWER_PROMPT_TEMPLATE.format(
    output_schema=REVIEWER_OUTPUT_SCHEMA
)


class TechnicalReviewerAgent(MaverickAgent[dict[str, Any], dict[str, Any]]):
    """Agent for reviewing code technical quality.

    This agent examines code changes for correctness, security, performance,
    best practices, and maintainability.

    Attributes:
        name: "technical-reviewer"
        system_prompt: Focused on technical quality
        allowed_tools: Read-only tools for examining code
    """

    def __init__(
        self,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        project_type: str | None = None,
    ) -> None:
        """Initialize the TechnicalReviewerAgent.

        Args:
            model: Optional Claude model ID.
            max_tokens: Optional maximum output tokens.
            temperature: Optional sampling temperature 0.0-1.0.
            project_type: Optional project type for skill guidance.
                If None, reads from maverick.yaml.
        """
        # Render prompt with skill guidance for this project type
        system_prompt = render_prompt(
            _TECH_REVIEWER_PROMPT_WITH_SCHEMA,
            project_type=project_type,
        )
        super().__init__(
            name="technical-reviewer",
            system_prompt=system_prompt,
            allowed_tools=list(REVIEWER_TOOLS),
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        self._id_prefix = TECH_REVIEWER_ID_PREFIX

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute technical quality review.

        Args:
            context: Review context containing:
                - pr_metadata: PR information
                - changed_files: List of changed files
                - diff: Full diff content
                - commits: Commit messages
                - base_branch: Base branch name

        Returns:
            Review result with quality assessment and structured findings.
        """
        # Build the review prompt from context
        prompt = self._build_review_prompt(context)

        # Execute the agent
        result = await self._run_agent(prompt)

        # Parse structured findings from the response
        structured_findings = self._extract_structured_findings(result)

        return {
            "reviewer": "technical",
            "quality": self._extract_quality(result),
            "has_critical": "CRITICAL" in result.upper(),
            "findings": result,
            "structured_findings": structured_findings,
            "context_used": list(context.keys()),
        }

    def _extract_structured_findings(self, response: str) -> list[dict[str, Any]]:
        """Extract structured findings from reviewer response.

        Parses the JSON findings block from the response and validates them.
        Returns empty list if parsing fails (backward compatible).

        Args:
            response: Full reviewer response text.

        Returns:
            List of validated finding dictionaries.
        """
        try:
            raw_findings = parse_findings(response, self._id_prefix)
            valid_findings, errors = validate_findings(raw_findings)
            if errors:
                logger.warning(
                    "findings_validation_errors",
                    reviewer="technical",
                    errors=errors,
                    raw_count=len(raw_findings),
                    valid_count=len(valid_findings),
                )
            return valid_findings
        except ValueError as e:
            logger.warning(
                "findings_parse_failed",
                reviewer="technical",
                error=str(e),
            )
            return []

    def _build_review_prompt(self, context: dict[str, Any]) -> str:
        """Build the review prompt from context."""
        parts = ["Please review the following code changes for technical quality.\n"]

        # Add PR metadata
        pr_metadata = context.get("pr_metadata", {})
        if pr_metadata:
            parts.append(f"## PR: {pr_metadata.get('title', 'Unknown')}\n")
            if pr_metadata.get("body"):
                parts.append(f"{pr_metadata['body']}\n")

        # Add commit messages for context
        commits = context.get("commits", [])
        if commits:
            parts.append("## Commits\n")
            for commit in commits[:10]:  # Limit to first 10
                if isinstance(commit, dict):
                    parts.append(f"- {commit.get('message', str(commit))}\n")
                else:
                    parts.append(f"- {commit}\n")

        # Add changed files summary
        changed_files = context.get("changed_files", [])
        if changed_files:
            parts.append(f"## Changed Files ({len(changed_files)} files)\n")
            for f in changed_files[:20]:  # Limit to first 20
                parts.append(f"- {f}\n")
            if len(changed_files) > 20:
                parts.append(f"- ... and {len(changed_files) - 20} more\n")

        # Add diff
        diff = context.get("diff", "")
        if diff:
            # Truncate if too long
            max_diff_len = 50000
            if len(diff) > max_diff_len:
                diff = diff[:max_diff_len] + "\n... [truncated]"
            parts.append(f"## Diff\n```diff\n{diff}\n```\n")

        parts.append("\nPlease provide your technical quality review.")
        return "\n".join(parts)

    def _extract_quality(self, result: str) -> str:
        """Extract the overall quality assessment from the review result."""
        result_upper = result.upper()
        if "POOR" in result_upper:
            return "POOR"
        elif "NEEDS_WORK" in result_upper or "NEEDS WORK" in result_upper:
            return "NEEDS_WORK"
        elif "EXCELLENT" in result_upper:
            return "EXCELLENT"
        elif "GOOD" in result_upper:
            return "GOOD"
        return "UNKNOWN"

    async def _run_agent(self, prompt: str) -> str:
        """Run the agent with the given prompt."""
        from maverick.agents.utils import extract_all_text

        messages = []
        async for msg in self.query(prompt):
            messages.append(msg)
        return extract_all_text(messages)
