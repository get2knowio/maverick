"""Correctness Reviewer Agent.

Reviews code changes for technical accuracy, best practices, security,
and idiomatic patterns for the project's language/framework.
"""

from __future__ import annotations

from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.contracts import validate_output
from maverick.agents.prompts.common import (
    FRAMEWORK_CONVENTIONS,
    TOOL_USAGE_GLOB,
    TOOL_USAGE_GREP,
    TOOL_USAGE_READ,
)
from maverick.agents.skill_prompts import render_prompt
from maverick.agents.tools import REVIEWER_TOOLS
from maverick.logging import get_logger
from maverick.models.review_models import (
    GroupedReviewResult,
)

logger = get_logger(__name__)

# ruff: noqa: E501
CORRECTNESS_REVIEWER_PROMPT_TEMPLATE = f"""\
You are a technical code reviewer within an orchestrated workflow. Your job is to review
code changes for technical correctness, best practices, security, and idiomatic patterns.

## Your Role

You analyze code changes for technical quality. A separate completeness reviewer checks
requirement coverage — you focus on:
- Whether the code is technically correct and robust
- Whether it follows language/framework best practices
- Whether there are security vulnerabilities
- Whether error handling is appropriate
- Whether the code is idiomatic for the project's stack

## Tool Usage Guidelines

You have access to: **Read, Glob, Grep**

### Read
{TOOL_USAGE_READ}
- Read CLAUDE.md to understand project conventions and standards before reviewing.

### Glob
{TOOL_USAGE_GLOB}
- Use Glob to locate related modules when you need to verify consistency with
  existing patterns.

### Grep
{TOOL_USAGE_GREP}
- Use Grep to find usages of a function or class across the codebase to verify
  that a change is consistent with how code is used elsewhere.

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

## Review Focus Areas

1. **$project_type_name Idioms** — Is the code idiomatic and clean for the
   project's language/stack? Does it follow established patterns?

2. **Type System** — Proper use of the language's type system: complete type hints,
   correct generics, no unnecessary `Any` or `cast()`.

3. **Canonical Library Usage** — Does the code use the project's canonical libraries
   correctly per project standards (see Project Conventions below)?

4. **Error Handling** — Are errors handled specifically (no overly broad catch-all
   patterns)? Are edge cases covered?

5. **Hardening** — Timeouts on external calls, retry logic with exponential backoff,
   specific exception handling for network/subprocess operations.

6. **Security** — No command injection, no hardcoded secrets, proper input validation
   at boundaries.

7. **Dead Code & Completeness** — No unused imports, functions, variables, or
   files left behind by this change. No TODO/FIXME/HACK comments that defer
   work to "later". No shims, compatibility wrappers, or backwards-compat
   code that could be cleaned up now. If the change makes existing code
   unreachable, that code must be removed in this same bead.

{FRAMEWORK_CONVENTIONS}

$project_conventions

## Output Format

IMPORTANT: Write your findings as JSON to the file path specified in
the review context field `findings_output_path` using the Write tool.
Do NOT embed JSON in your text response — write it to the file.
If no `findings_output_path` is provided, output JSON at the END of
your response as a ```json code block.

The JSON schema:

```json
{{
  "groups": [
    {{
      "description": "Brief description of this group",
      "findings": [
        {{
          "id": "F001",
          "file": "src/maverick/foo.py",
          "line": "45",
          "issue": "Clear description of the problem",
          "severity": "critical",
          "category": "clean_code",
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
  - "critical": ONLY for runtime crashes, security vulnerabilities
    (injection, hardcoded secrets, auth bypass), data corruption, or type
    errors the compiler would miss. NOT for performance or style.
  - "major": Bugs that degrade but don't crash, library standard
    violations, performance concerns, missing edge-case error handling
  - "minor": Style issues, suggestions, alternative approaches
- **category**: One of:
  - "clean_code" - Code quality, maintainability issues
  - "type_hints" - Missing or incorrect type hints
  - "library_standards" - Violates project library standards (CLAUDE.md)
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

- Be thorough but practical — focus on real issues, not nitpicks
- Prioritize by impact: critical > major > minor
- Every finding should be actionable — include enough context to fix
- Focus on technical quality, not requirement completeness (another reviewer handles that)
- SEVERITY CALIBRATION: "critical" triggers automatic rejection
  (request_changes). Reserve it for defects that would cause runtime
  crashes, security vulnerabilities, or data corruption. Performance
  concerns, style preferences, and "better way to do this" suggestions
  are MAJOR at most.
"""


class CorrectnessReviewerAgent(MaverickAgent[dict[str, Any], GroupedReviewResult]):
    """Agent for reviewing technical correctness and best practices.

    Focuses on code quality, security, idiomatic patterns, and proper use of
    the project's canonical libraries. Runs in parallel with the
    CompletenessReviewerAgent.

    Attributes:
        name: "correctness-reviewer"
        instructions: Technical review prompt
        allowed_tools: Read-only tools (Read, Glob, Grep)
    """

    def __init__(
        self,
        feature_name: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        project_type: str | None = None,
    ) -> None:
        """Initialize the CorrectnessReviewerAgent.

        Args:
            feature_name: Name of the feature being reviewed (for spec lookup).
            model: Optional model ID.
            max_tokens: Optional maximum output tokens.
            temperature: Optional sampling temperature 0.0-1.0.
            project_type: Project type for convention guidance (auto-detected if None).
        """
        tools = list(REVIEWER_TOOLS) + ["Write"]

        rendered_instructions = render_prompt(
            CORRECTNESS_REVIEWER_PROMPT_TEMPLATE,
            project_type=project_type,
        )

        super().__init__(
            name="correctness-reviewer",
            instructions=rendered_instructions,
            allowed_tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            output_model=GroupedReviewResult,
        )
        self._feature_name = feature_name

    def build_prompt(self, context: dict[str, Any]) -> str:
        """Construct the prompt string from context.

        Args:
            context: Review context containing cwd, changed_files, diff,
                and feature_name.

        Returns:
            Complete prompt text ready for the ACP agent.
        """
        parts = ["Review the code changes for technical correctness."]

        feature_name = context.get("feature_name") or self._feature_name
        if feature_name:
            parts.append(f"\nFeature: {feature_name}")

        bead_description = context.get("bead_description")
        if bead_description:
            parts.append(f"\n## Task Description\n{bead_description}")

        changed_files = context.get("changed_files")
        if changed_files:
            parts.append("\n## Changed Files")
            for f in changed_files[:50]:
                parts.append(f"- {f}")
            if len(changed_files) > 50:
                parts.append(f"- ... and {len(changed_files) - 50} more")

        diff = context.get("diff")
        if diff:
            if len(diff) > 50000:
                diff = diff[:50000] + "\n... (truncated)"
            parts.append("\n## Diff")
            parts.append("```diff")
            parts.append(diff)
            parts.append("```")

        review_meta = context.get("review_metadata", context.get("pr_metadata"))
        if review_meta:
            parts.append("\n## Review Context")
            if review_meta.get("title"):
                parts.append(f"Title: {review_meta['title']}")
            if review_meta.get("description"):
                parts.append(f"Description: {review_meta['description'][:1000]}")

        return "\n".join(parts)

    def _parse_review_output(self, text: str) -> GroupedReviewResult:
        """Parse JSON output from review response.

        Args:
            text: Full response text containing JSON block.

        Returns:
            Parsed GroupedReviewResult, or empty result if extraction fails.
        """
        result = validate_output(text, GroupedReviewResult, strict=False)
        if result is not None:
            return result

        logger.warning("no_valid_correctness_review_output_found")
        return GroupedReviewResult(groups=[])
