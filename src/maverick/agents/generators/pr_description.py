"""PRDescriptionGenerator for generating pull request descriptions.

This module provides a generator that creates markdown PR descriptions with
configurable sections (Summary, Changes, Testing by default). It uses commit
history, diff statistics, task summaries, and validation results to produce
comprehensive PR descriptions.
"""

from __future__ import annotations

from textwrap import dedent
from typing import Any

from maverick.agents.generators.base import (
    DEFAULT_MODEL,
    DEFAULT_PR_SECTIONS,
    GeneratorAgent,
)
from maverick.logging import get_logger

# =============================================================================
# Module Logger
# =============================================================================

logger = get_logger(__name__)


# =============================================================================
# PRDescriptionGenerator
# =============================================================================


class PRDescriptionGenerator(GeneratorAgent):
    """Generator for creating pull request descriptions.

    Generates markdown PR descriptions with configurable sections. Default
    sections are Summary, Changes, and Testing. Accepts commit history,
    diff statistics, task summaries, and validation results as input.

    Attributes:
        name: Fixed identifier "pr-description-generator".
        system_prompt: Enforces markdown section format.
        model: Claude model ID (default: claude-sonnet-4-5-20250929).
        sections: Tuple of section names to include in output.

    Example:
        ```python
        generator = PRDescriptionGenerator()
        context = {
            "commits": ["feat: add auth", "fix: login bug"],
            "diff_stats": {"files_changed": 5, "insertions": 120, "deletions": 30},
            "task_summary": "Implement user authentication",
            "validation_results": {"passed": True, "failures": []},
        }
        description = await generator.generate(context)
        print(description)
        # ## Summary
        # Implement user authentication
        #
        # ## Changes
        # - Added authentication endpoints
        # - Fixed login bug
        #
        # ## Testing
        # All validation checks passed
        ```
    """

    def __init__(
        self,
        sections: tuple[str, ...] = DEFAULT_PR_SECTIONS,
        model: str = DEFAULT_MODEL,
    ) -> None:
        """Initialize the PR description generator.

        Args:
            sections: Tuple of section names to include
                (default: Summary, Changes, Testing).
            model: Claude model ID.

        Raises:
            ValueError: If sections is empty or contains invalid section names.
        """
        if not sections:
            raise ValueError("sections must be non-empty")
        if not all(isinstance(s, str) and s.strip() for s in sections):
            raise ValueError("All section names must be non-empty strings")

        self._sections = sections
        system_prompt = self._build_system_prompt()

        super().__init__(
            name="pr-description-generator",
            system_prompt=system_prompt,
            model=model,
        )

    @property
    def sections(self) -> tuple[str, ...]:
        """Section names to include in the PR description."""
        return self._sections

    def _build_system_prompt(self) -> str:
        """Build system prompt enforcing markdown section format.

        Returns:
            System prompt string with section requirements.
        """
        sections_list = "\n".join(f"- {section}" for section in self._sections)

        return dedent(f"""
            You are a PR description generator. Your ONLY output is a markdown
            PR description. Do NOT include any preamble, explanation, or
            conversational text. Start directly with the first markdown header.

            Your output MUST follow this exact structure:

            {sections_list}

            Guidelines:
            - Start immediately with "## Summary" - no intro text
            - Use ## markdown headers for each section
            - Summary: High-level overview of what this PR accomplishes
            - Changes: List key changes, grouped logically if needed
            - Testing: Describe validation status, any failures, and test coverage
            - Be concise but thorough
            - Focus on WHY changes were made, not just WHAT changed

            CRITICAL: Output ONLY the markdown. No "I'll analyze...", no "Here is...",
            no explanations. Just the raw markdown starting with ## Summary.
        """).strip()

    def build_prompt(self, context: dict[str, Any]) -> str:
        """Construct the prompt string from context (FR-017).

        Args:
            context: Input context containing:
                - commits (list[str]): Commit messages (REQUIRED, non-empty)
                - task_summary (str): Summary of the task/feature (REQUIRED, non-empty)
                - diff_stats (dict): File change statistics (OPTIONAL)
                - validation_results (dict): Test/lint results (OPTIONAL)

        Returns:
            Complete prompt text ready for the ACP agent.
        """
        return self._build_prompt(context)

    def _build_prompt(self, context: dict[str, Any]) -> str:
        """Build prompt from context.

        Args:
            context: Input context dictionary.

        Returns:
            Formatted prompt string for Claude.
        """
        commits = context["commits"]
        task_summary = context["task_summary"]
        diff_stats = context.get("diff_stats")
        validation_results = context.get("validation_results")

        # Build prompt sections
        prompt_parts = [
            "Generate a pull request description based on the following context:\n",
            f"**Task Summary**:\n{task_summary}\n",
            "\n**Commits**:\n" + "\n".join(f"- {commit}" for commit in commits),
        ]

        # Add diff stats if provided
        if diff_stats:
            stats_str = ", ".join(f"{k}: {v}" for k, v in diff_stats.items())
            prompt_parts.append(f"\n**Diff Statistics**:\n{stats_str}")

        # Add validation results if provided
        if validation_results:
            passed = validation_results.get("passed", True)
            failures = validation_results.get("failures", [])

            if passed:
                prompt_parts.append("\n**Validation Status**:\nAll checks passed")
            else:
                failures_str = "\n".join(f"- {failure}" for failure in failures)
                prompt_parts.append(
                    f"\n**Validation Status**:\n"
                    f"Validation FAILED with errors:\n{failures_str}"
                )

        sections_str = ", ".join(self._sections)
        prompt_parts.append(
            f"\n\nGenerate a PR description with these sections: {sections_str}\n"
            "Output ONLY the markdown, starting with ## Summary. No preamble."
        )

        return "\n".join(prompt_parts)
