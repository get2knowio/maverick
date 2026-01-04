"""Spec Compliance Reviewer Agent.

This agent reviews code changes for compliance with the project specification
and completeness of implementation. It focuses on:

- Does the implementation match the spec requirements?
- Are all tasks from tasks.md addressed?
- Are there gaps or missing functionality?
- Does the implementation follow the spec's design decisions?
"""

from __future__ import annotations

from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.tools import REVIEWER_TOOLS
from maverick.logging import get_logger

logger = get_logger(__name__)

SPEC_REVIEWER_PROMPT_TEMPLATE = """\
You are a Spec Compliance Reviewer. Your role is to review code changes and verify
they correctly implement the project specification.

## Your Focus Areas

1. **Requirement Coverage**
   - Does the implementation address all requirements in spec.md?
   - Are there missing features or incomplete implementations?
   - Are optional vs required features properly distinguished?

2. **Task Completion**
   - Have all tasks in tasks.md been completed?
   - Are tasks marked as done actually implemented?
   - Are there orphaned tasks not reflected in the code?

3. **Design Compliance**
   - Does the implementation follow the design decisions in plan.md?
   - Are the specified interfaces and contracts implemented correctly?
   - Does the architecture match what was planned?

4. **Spec Deviations**
   - Are there intentional deviations from the spec? If so, are they justified?
   - Are there unintentional deviations that need correction?
   - Has the implementation scope crept beyond the spec?

## Review Process

1. First, read and understand the spec files (spec.md, plan.md, tasks.md)
2. Examine the code changes in the diff
3. Cross-reference implementation against spec requirements
4. Identify gaps, deviations, and missing pieces
5. Note any areas where the spec itself may need updates

## Output Format

Provide your review as structured findings:

```
## Spec Compliance Summary

**Overall Assessment**: [COMPLIANT | PARTIAL | NON-COMPLIANT]

### Requirements Coverage
- [x] Requirement 1: Implemented correctly
- [ ] Requirement 2: Missing or incomplete
- [~] Requirement 3: Partially implemented

### Task Completion
- List of completed tasks
- List of incomplete tasks
- List of tasks not found in code

### Deviations
- Intentional deviations with justification
- Unintentional deviations needing attention

### Recommendations
- Specific actions to achieve full compliance
```

Be thorough but constructive. The goal is to ensure the implementation
faithfully represents what was specified, not to find fault.
"""


class SpecReviewerAgent(MaverickAgent[dict[str, Any], dict[str, Any]]):
    """Agent for reviewing code compliance with project specifications.

    This agent examines code changes against the project spec (spec.md, plan.md,
    tasks.md) to verify the implementation is complete and correct.

    Attributes:
        name: "spec-reviewer"
        system_prompt: Focused on spec compliance and completeness
        allowed_tools: Read-only tools for examining code and specs
    """

    def __init__(
        self,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        """Initialize the SpecReviewerAgent.

        Args:
            model: Optional Claude model ID.
            max_tokens: Optional maximum output tokens.
            temperature: Optional sampling temperature 0.0-1.0.
        """
        super().__init__(
            name="spec-reviewer",
            system_prompt=SPEC_REVIEWER_PROMPT_TEMPLATE,
            allowed_tools=list(REVIEWER_TOOLS),
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute spec compliance review.

        Args:
            context: Review context containing:
                - pr_metadata: PR information
                - changed_files: List of changed files
                - diff: Full diff content
                - spec_files: Spec file contents (spec.md, plan.md, tasks.md)
                - base_branch: Base branch name

        Returns:
            Review result with compliance assessment and findings.
        """
        # Build the review prompt from context
        prompt = self._build_review_prompt(context)

        # Execute the agent
        result = await self._run_agent(prompt)

        return {
            "reviewer": "spec",
            "assessment": self._extract_assessment(result),
            "findings": result,
            "context_used": list(context.keys()),
        }

    def _build_review_prompt(self, context: dict[str, Any]) -> str:
        """Build the review prompt from context."""
        parts = ["Please review the following code changes for spec compliance.\n"]

        # Add spec files if available
        spec_files = context.get("spec_files", {})
        if spec_files:
            parts.append("## Specification Files\n")
            for name, content in spec_files.items():
                parts.append(f"### {name}\n```\n{content}\n```\n")

        # Add PR metadata
        pr_metadata = context.get("pr_metadata", {})
        if pr_metadata:
            parts.append(f"## PR: {pr_metadata.get('title', 'Unknown')}\n")
            if pr_metadata.get("body"):
                parts.append(f"{pr_metadata['body']}\n")

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

        parts.append("\nPlease provide your spec compliance review.")
        return "\n".join(parts)

    def _extract_assessment(self, result: str) -> str:
        """Extract the overall assessment from the review result."""
        result_upper = result.upper()
        if "NON-COMPLIANT" in result_upper:
            return "NON-COMPLIANT"
        elif "PARTIAL" in result_upper:
            return "PARTIAL"
        elif "COMPLIANT" in result_upper:
            return "COMPLIANT"
        return "UNKNOWN"

    async def _run_agent(self, prompt: str) -> str:
        """Run the agent with the given prompt.

        This delegates to the parent class's execute_prompt method or
        uses the Claude SDK directly.
        """
        # Use the base class's query mechanism
        from maverick.agents.utils import extract_all_text

        messages = []
        async for msg in self.query(prompt):
            messages.append(msg)
        return extract_all_text(messages)
