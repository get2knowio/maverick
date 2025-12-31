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
from maverick.agents.result import AgentUsage
from maverick.exceptions import GeneratorError
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
            You are a PR description generator. Generate clear,
            comprehensive pull request descriptions in markdown format.

            Your output MUST follow this structure using markdown headers (##):

            {sections_list}

            Guidelines:
            - Use ## markdown headers for each section
            - Summary: Provide a high-level overview of what this PR accomplishes
            - Changes: List key changes, grouped logically if needed
            - Testing: Describe validation status, any failures, and test coverage
            - Be concise but thorough
            - Focus on WHY changes were made, not just WHAT changed
            - If validation failed, clearly state failures and their impact

            Format the output as a markdown document that can be used directly
            as a PR description.
        """).strip()

    async def generate(
        self,
        context: dict[str, Any],
        return_usage: bool = False,
    ) -> str | tuple[str, AgentUsage]:
        """Generate PR description from context.

        Args:
            context: Input context containing:
                - commits (list[str]): Commit messages (REQUIRED, non-empty)
                - task_summary (str): Summary of the task/feature (REQUIRED, non-empty)
                - diff_stats (dict): File change statistics (OPTIONAL)
                - validation_results (dict): Test/lint results (OPTIONAL)
            return_usage: If True, return (text, usage) tuple.

        Returns:
            Markdown PR description with configured sections,
            or (description, usage) if return_usage is True.

        Raises:
            GeneratorError: If commits or task_summary is missing/empty,
                or generation fails.
        """
        logger.debug(
            "Generator '%s' generating PR description from context with %d keys",
            self.name,
            len(context),
        )

        # Validate required fields (FR-015)
        commits = context.get("commits")
        if not commits or not isinstance(commits, list) or len(commits) == 0:
            raise GeneratorError(
                message="commits must be a non-empty list",
                generator_name=self.name,
                input_context={"commits": commits},
            )

        if not all(isinstance(c, str) for c in commits):
            raise GeneratorError(
                message="All commits must be strings",
                generator_name=self.name,
                input_context=context,
            )

        task_summary = context.get("task_summary")
        if (
            not task_summary
            or not isinstance(task_summary, str)
            or not task_summary.strip()
        ):
            raise GeneratorError(
                "task_summary must be a non-empty string",
                generator_name=self.name,
                input_context={"task_summary": task_summary},
            )

        # Build prompt from context
        prompt = self._build_prompt(context)

        # Execute query and return result
        if return_usage:
            return await self._query_with_usage(prompt)
        return await self._query(prompt)

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
            f"\n\nGenerate a PR description with these sections: {sections_str}"
        )

        return "\n".join(prompt_parts)
