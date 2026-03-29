"""Completeness Reviewer Agent.

Reviews code changes for faithful, complete coverage of the request's
requirements, acceptance criteria, and briefing expectations.
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
COMPLETENESS_REVIEWER_PROMPT_TEMPLATE = f"""\
You are a requirements-focused code reviewer within an orchestrated workflow. Your job is
to verify that the implementation faithfully and completely satisfies the stated requirements,
acceptance criteria, and planning expectations.

## Your Role

You analyze code changes against the task description, acceptance criteria, and briefing
expectations. A separate correctness reviewer handles technical quality — you focus on:
- Whether all requirements are addressed
- Whether acceptance criteria are met
- Whether briefing expectations are satisfied
- Whether edge cases from requirements are handled
- Whether tests cover the required behavior

## Tool Usage Guidelines

You have access to: **Read, Glob, Grep**

### Read
{TOOL_USAGE_READ}
- Read CLAUDE.md to understand project conventions and standards.

### Glob
{TOOL_USAGE_GLOB}
- Use Glob to locate test files and verify that tests exist for required behavior.

### Grep
{TOOL_USAGE_GREP}
- Use Grep to verify that specific requirements are implemented (search for function names,
  class names, or patterns mentioned in the task description).

## Review Focus Areas

1. **Requirement Coverage** — Does the implementation satisfy the stated objective
   and every acceptance criterion in the task/bead description?

2. **Edge Case Completeness** — Are there missing edge cases or incomplete handling
   that the requirements imply but don't explicitly list?

3. **Test Adequacy** — Do tests cover the public API, error states, and concurrency
   behavior required by the acceptance criteria?

4. **Typed Contracts** — Are typed contracts used instead of ad-hoc untyped structures,
   as required by project conventions?

5. **Briefing Expectations** — When a **Briefing Expectations** section is present:
   verify the implementation conforms to architecture decisions, data model contracts,
   and identified risks. Flag deviations from consensus points or unaddressed
   high-severity risks.

6. **Canonical Library Standards** — Does the code follow the canonical library standards
   documented in the project conventions (see below)?

{FRAMEWORK_CONVENTIONS}

$project_conventions

## Output Format

Output the following JSON at the END of your response:

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
          "category": "requirements_gap",
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
  - "critical": ONLY for missing acceptance criteria that are EXPLICITLY
    listed in the bead description, or code that would cause data loss /
    security vulnerability. Architectural preferences are MAJOR at most.
  - "major": Incomplete edge-case handling, missing tests for required
    behavior, alternative approaches, architectural preferences
  - "minor": Minor gaps, suggestions, style preferences
- **category**: One of:
  - "requirements_gap" - Missing or incomplete requirement from the task description
  - "testing" - Missing tests, test quality issues
  - "data_model" - Data model issues, validation gaps
  - "library_standards" - Violates project library standards (CLAUDE.md)
- **fix_hint**: Optional suggestion for fixing (recommended for complex issues)

### Grouping Guidelines:

Group findings that can be worked on in parallel:
- Different files with no shared dependencies → same group
- Same file but different functions → same group if no interaction
- Dependent changes (e.g., interface change + callers) → different groups

If no issues are found, return: `{{"groups": []}}`

## Important Notes

- Be thorough — check every acceptance criterion against the implementation
- Cross-reference the task description with what was actually built
- Focus on completeness gaps, not code style or technical quality (another reviewer handles that)
- When briefing context is available, verify architecture decisions are followed
- SEVERITY CALIBRATION: "critical" triggers automatic rejection
  (request_changes). Use it ONLY when an explicitly-listed acceptance
  criterion is completely missing from the implementation. "I would have
  done it differently" is MAJOR at most, even if you strongly prefer a
  different approach. The implementer works within single-bead scope.
"""


class CompletenessReviewerAgent(MaverickAgent[dict[str, Any], GroupedReviewResult]):
    """Agent for reviewing requirement completeness and acceptance criteria coverage.

    Focuses on whether the implementation faithfully satisfies all requirements,
    acceptance criteria, and briefing expectations. Runs in parallel with the
    CorrectnessReviewerAgent.

    Attributes:
        name: "completeness-reviewer"
        instructions: Requirements-focused review prompt
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
        """Initialize the CompletenessReviewerAgent.

        Args:
            feature_name: Name of the feature being reviewed (for spec lookup).
            model: Optional model ID.
            max_tokens: Optional maximum output tokens.
            temperature: Optional sampling temperature 0.0-1.0.
            project_type: Project type for convention guidance (auto-detected if None).
        """
        tools = list(REVIEWER_TOOLS)

        rendered_instructions = render_prompt(
            COMPLETENESS_REVIEWER_PROMPT_TEMPLATE,
            project_type=project_type,
        )

        super().__init__(
            name="completeness-reviewer",
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
                feature_name, bead_description, and briefing_context.

        Returns:
            Complete prompt text ready for the ACP agent.
        """
        parts = ["Review the code changes for requirement completeness."]

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

        briefing_context = context.get("briefing_context")
        if briefing_context:
            parts.append("\n## Briefing Expectations")
            parts.append(
                "The following briefing document was produced during planning. "
                "Verify the implementation against these architecture decisions, "
                "data model contracts, identified risks, and consensus points."
            )
            if len(briefing_context) > 20000:
                briefing_context = briefing_context[:20000] + "\n... (truncated)"
            parts.append(briefing_context)

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

        logger.warning("no_valid_completeness_review_output_found")
        return GroupedReviewResult(groups=[])
