"""Review Fixer Agent.

This agent receives consolidated findings from dual-agent code review
(spec + technical) and fixes issues, spawning subagents for parallel work
where possible.
"""

from __future__ import annotations

from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.prompts import render_prompt
from maverick.agents.tools import ISSUE_FIXER_TOOLS
from maverick.logging import get_logger

logger = get_logger(__name__)

REVIEW_FIXER_PROMPT_TEMPLATE = """\
You are a Review Fixer agent. Your role is to address code review findings
by applying fixes to the codebase.

$skill_guidance

## Your Task

You receive consolidated findings from two code reviewers:
1. **Spec Reviewer** - Reviews for specification compliance
2. **Technical Reviewer** - Reviews for code quality and best practices

Your job is to fix the issues they identified.

## Parallelization Strategy

For each issue, determine if it can be fixed in parallel with other issues:

- **Parallel-safe**: Issues affecting DIFFERENT files can be fixed simultaneously
  - Spawn a subagent for each file's issues
  - Process these subagents in parallel using the Task tool

- **Sequential**: Issues affecting the SAME file must be fixed one at a time
  - Fix them in order of severity (critical → major → minor)
  - This prevents conflicting edits to the same file

## Execution Approach

1. **Analyze all issues** - Group by file path and severity
2. **Identify parallel opportunities** - Different files = parallel,
   same file = sequential
3. **Spawn subagents** - Create a subagent for each parallelizable group
4. **Apply fixes** - Each subagent fixes its assigned issues
5. **Verify changes** - Ensure fixes don't break existing functionality

## Issue Severity Priority

Fix in this order within each file:
1. **Critical** - Security vulnerabilities, data corruption risks
2. **Major** - Bugs, spec non-compliance, significant problems
3. **Minor** - Style issues, minor improvements
4. **Suggestions** - Optional enhancements (fix if time permits)

## Fix Guidelines

- Make minimal, focused changes to address each issue
- Preserve existing code style and formatting
- Don't refactor beyond what's needed for the fix
- Add tests if the fix changes behavior
- Document non-obvious fixes with brief comments

## Output Format

After fixing all issues, provide a JSON summary:
```json
{
  "issues_fixed": [
    {"id": "issue_1", "file": "path/to/file.py", "description": "Fixed X"},
    {"id": "issue_2", "file": "path/to/other.py", "description": "Fixed Y"}
  ],
  "issues_skipped": [
    {"id": "issue_3", "reason": "Cannot fix without breaking API"}
  ],
  "files_modified": ["path/to/file.py", "path/to/other.py"],
  "parallel_groups": 3,
  "summary": "Fixed 5 issues across 3 files"
}
```
"""


class ReviewFixerAgent(MaverickAgent[dict[str, Any], dict[str, Any]]):
    """Agent for fixing code review findings.

    This agent receives all issues from the dual-agent review and handles
    the parallelization strategy internally, spawning subagents to fix
    issues affecting different files simultaneously.

    Attributes:
        name: "review-fixer"
        system_prompt: Focused on fixing review issues with parallelization
        allowed_tools: File operations + search for context
    """

    def __init__(
        self,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        project_type: str | None = None,
    ) -> None:
        """Initialize the ReviewFixerAgent.

        Args:
            model: Optional Claude model ID.
            max_tokens: Optional maximum output tokens.
            temperature: Optional sampling temperature 0.0-1.0.
            project_type: Optional project type for skill guidance.
                If None, reads from maverick.yaml.
        """
        # Render prompt with skill guidance for this project type
        system_prompt = render_prompt(
            REVIEW_FIXER_PROMPT_TEMPLATE,
            project_type=project_type,
        )
        super().__init__(
            name="review-fixer",
            system_prompt=system_prompt,
            allowed_tools=list(ISSUE_FIXER_TOOLS),
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute review fixes.

        Args:
            context: Review context containing:
                - review_report: Combined review report from both reviewers
                - issues: List of issues to fix (from analyze_review_findings)
                - recommendation: Current review recommendation
                - changed_files: List of files changed in the PR

        Returns:
            Fix result with issues_fixed, issues_remaining, and summary.
        """
        # Build the fix prompt from context
        prompt = self._build_fix_prompt(context)

        # Execute the agent
        result = await self._run_agent(prompt)

        return {
            "fixer": "review-fixer",
            "raw_output": result,
            "context_used": list(context.keys()),
        }

    def _build_fix_prompt(self, context: dict[str, Any]) -> str:
        """Build the fix prompt from context."""
        parts = ["Fix the following code review issues:\n"]

        # Add review summary
        review_report = context.get("review_report", "")
        if review_report:
            # Truncate if too long
            max_len = 10000
            if len(review_report) > max_len:
                review_report = review_report[:max_len] + "\n... [truncated]"
            parts.append(f"## Review Report\n{review_report}\n")

        # Add structured issues if available
        issues = context.get("issues", [])
        if issues:
            parts.append("## Issues to Fix\n")
            for issue in issues:
                if isinstance(issue, dict):
                    severity = issue.get("severity", "unknown")
                    file_path = issue.get("file_path", "unknown")
                    description = issue.get("description", "No description")
                    parts.append(f"- [{severity}] {file_path}: {description}\n")

        # Add changed files for context
        changed_files = context.get("changed_files", [])
        if changed_files:
            parts.append(f"\n## Changed Files ({len(changed_files)} files)\n")
            for f in changed_files[:20]:
                parts.append(f"- {f}\n")
            if len(changed_files) > 20:
                parts.append(f"- ... and {len(changed_files) - 20} more\n")

        parts.append(
            "\nAnalyze these issues, identify which can be fixed in parallel "
            "(different files), and spawn subagents to apply fixes. "
            "Provide a JSON summary when complete."
        )

        return "\n".join(parts)

    async def _run_agent(self, prompt: str) -> str:
        """Run the agent with the given prompt."""
        from maverick.agents.utils import extract_all_text

        messages = []
        async for msg in self.query(prompt):
            messages.append(msg)
        return extract_all_text(messages)
