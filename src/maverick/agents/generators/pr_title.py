"""PRTitleGenerator for generating pull request titles.

This module provides a generator that creates concise PR titles following
conventional commit format. It uses commit messages, branch names, and
task summaries to produce titles in the format: type(scope): description
"""

from __future__ import annotations

from typing import Any

from maverick.agents.generators.base import DEFAULT_MODEL, GeneratorAgent
from maverick.agents.result import AgentUsage
from maverick.exceptions import GeneratorError
from maverick.logging import get_logger

# =============================================================================
# Module Logger
# =============================================================================

logger = get_logger(__name__)

# =============================================================================
# System Prompt
# =============================================================================

PR_TITLE_SYSTEM_PROMPT = """You are a PR title generator that creates \
concise pull request titles following conventional commit format.

You MUST follow the conventional commit format exactly:

**Format**: type(scope): description

**Valid Types**:
- feat: A new feature
- fix: A bug fix
- docs: Documentation only changes
- style: Changes that don't affect code meaning (formatting, whitespace)
- refactor: Code change that neither fixes a bug nor adds a feature
- perf: Performance improvement
- test: Adding or updating tests
- build: Changes to build system or dependencies
- ci: Changes to CI configuration
- chore: Other changes that don't modify src or test files
- revert: Reverts a previous commit

**Rules**:
1. Use imperative mood ("add feature" not "added feature" or "adds feature")
2. Keep description lowercase
3. No period at the end
4. Total length under 72 characters
5. Choose the most appropriate type based on the changes
6. Scope should reflect the component/module being changed
7. Description should be concise and clear
8. The title should summarize the main purpose of the PR

**Examples**:
- feat(library): add builtin workflow library
- fix(api): handle null user in login endpoint
- docs(readme): update installation instructions
- refactor(agents): simplify error handling logic
- test(auth): add password validation tests

Your response should ONLY contain the PR title, nothing else.
"""

# =============================================================================
# PRTitleGenerator
# =============================================================================


class PRTitleGenerator(GeneratorAgent):
    """Generator for PR titles in conventional commit format.

    Creates concise PR titles following the conventional commit format based on
    commit messages, branch names, and task summaries. Automatically selects
    appropriate commit type and scope based on the changes.

    Attributes:
        name: Always "pr-title-generator".
        system_prompt: Enforces conventional commit format for titles.
        model: Claude model ID (default: claude-sonnet-4-5-20250929).

    Example:
        ```python
        generator = PRTitleGenerator()

        context = {
            "commits": ["feat: add workflow library", "test: add library tests"],
            "branch_name": "025-builtin-workflow-library",
            "task_summary": "Implement built-in workflow library",
            "diff_overview": "5 files changed, +200 additions, -10 deletions",
        }

        title = await generator.generate(context)
        # Returns: "feat(library): add builtin workflow library"
        ```
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        """Initialize the PRTitleGenerator.

        Args:
            model: Claude model ID (default: claude-sonnet-4-5-20250929).
        """
        super().__init__(
            name="pr-title-generator",
            system_prompt=PR_TITLE_SYSTEM_PROMPT,
            model=model,
        )

    async def generate(
        self,
        context: dict[str, Any],
        return_usage: bool = False,
    ) -> str | tuple[str, AgentUsage]:
        """Generate PR title from context.

        Args:
            context: Input context containing:
                - commits (list[str]): Commit messages (REQUIRED, non-empty)
                - branch_name (str): Branch name (OPTIONAL)
                - task_summary (str): Task summary (OPTIONAL)
                - diff_overview (str): Brief change overview (OPTIONAL)
            return_usage: If True, return (text, usage) tuple.

        Returns:
            PR title in conventional commit format,
            or (title, usage) if return_usage is True.

        Raises:
            GeneratorError: If commits is missing/empty or generation fails.
        """
        logger.debug(
            "Generator '%s' generating PR title from context with %d keys",
            self.name,
            len(context),
        )

        # Validate required field
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

        # Build prompt from context
        prompt = self._build_prompt(context)

        # Execute query and get result with usage if requested
        if return_usage:
            result, usage = await self._query_with_usage(prompt)
        else:
            result = await self._query(prompt)

        # Ensure result is not too long
        if len(result) > 72:
            logger.warning(
                "Generated PR title exceeds 72 characters (%d), truncating", len(result)
            )
            result = result[:69] + "..."

        if return_usage:
            return result, usage
        return result

    def _build_prompt(self, context: dict[str, Any]) -> str:
        """Build prompt from context.

        Args:
            context: Input context dictionary.

        Returns:
            Formatted prompt string for Claude.
        """
        commits = context["commits"]
        branch_name = context.get("branch_name", "")
        task_summary = context.get("task_summary", "")
        diff_overview = context.get("diff_overview", "")

        prompt_parts = ["Generate a concise PR title for these changes:\n"]

        # Add commits
        prompt_parts.append("\n**Commits:**")
        for commit in commits[:10]:  # Limit to first 10 commits
            prompt_parts.append(f"- {commit}")

        # Add branch name if available
        if branch_name:
            prompt_parts.append(f"\n**Branch:** {branch_name}")

        # Add task summary if available
        if task_summary:
            prompt_parts.append(f"\n**Task Summary:** {task_summary}")

        # Add diff overview if available
        if diff_overview:
            prompt_parts.append(f"\n**Changes:** {diff_overview}")

        prompt_parts.append(
            "\nGenerate a PR title that summarizes the main purpose of these changes "
            "in conventional commit format."
        )

        return "\n".join(prompt_parts)
