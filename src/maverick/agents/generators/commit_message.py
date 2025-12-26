"""CommitMessageGenerator for creating conventional commit messages.

This module provides the CommitMessageGenerator class that creates conventional
commit messages from git diffs and file statistics.
"""

from __future__ import annotations

from typing import Any

from maverick.agents.generators.base import (
    DEFAULT_MODEL,
    MAX_DIFF_SIZE,
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
# System Prompt
# =============================================================================

COMMIT_MESSAGE_SYSTEM_PROMPT = """You are a commit message generator that creates \
conventional commit messages.

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

**Examples**:
- feat(auth): add password reset functionality
- fix(api): handle null user in login
- docs(readme): update installation instructions
- refactor(core): simplify error handling logic
- test(auth): add tests for password validation

Your response should ONLY contain the commit message, nothing else.
"""

# =============================================================================
# CommitMessageGenerator
# =============================================================================


class CommitMessageGenerator(GeneratorAgent):
    """Generator for conventional commit messages.

    Creates commit messages following the conventional commit format based on
    git diffs and file statistics. Automatically selects appropriate commit type
    and scope based on the changes.

    Attributes:
        name: Always "commit-message-generator".
        system_prompt: Enforces conventional commit format.
        model: Claude model ID (default: claude-sonnet-4-5-20250929).

    Example:
        ```python
        generator = CommitMessageGenerator()

        context = {
            "diff": "diff --git a/auth.py b/auth.py\n+def reset_password():\n+    pass",
            "file_stats": {"auth.py": {"additions": 2, "deletions": 0}},
            "scope_hint": "auth",  # Optional
        }

        message = await generator.generate(context)
        # Returns: "feat(auth): add password reset functionality"
        ```
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        """Initialize the CommitMessageGenerator.

        Args:
            model: Claude model ID (default: claude-sonnet-4-5-20250929).
        """
        super().__init__(
            name="commit-message-generator",
            system_prompt=COMMIT_MESSAGE_SYSTEM_PROMPT,
            model=model,
        )

    async def generate(
        self,
        context: dict[str, Any],
        return_usage: bool = False,
    ) -> str | tuple[str, AgentUsage]:
        """Generate a conventional commit message from context.

        Args:
            context: Input context containing:
                - diff (str): Git diff showing changes (required)
                - file_stats (dict): File statistics with additions/deletions (optional)
                - scope_hint (str): Suggested scope for commit message (optional)
            return_usage: If True, return (text, usage) tuple.

        Returns:
            Conventional commit message in format: type(scope): description,
            or (message, usage) if return_usage is True.

        Raises:
            GeneratorError: If diff is empty or generation fails.
        """
        logger.debug(
            "CommitMessageGenerator.generate called with context keys: %s",
            list(context.keys()),
        )

        # Validate required fields
        diff = context.get("diff", "")
        if not diff or not diff.strip():
            raise GeneratorError(
                message="Diff cannot be empty",
                generator_name=self._name,
                input_context={"diff_length": len(diff)},
            )

        # Extract optional fields
        file_stats = context.get("file_stats", {})
        scope_hint = context.get("scope_hint")

        # Truncate diff if needed (per FR-017)
        truncated_diff = self._truncate_input(diff, MAX_DIFF_SIZE, "diff")

        # Build prompt
        prompt = self._build_prompt(truncated_diff, file_stats, scope_hint)

        # Query Claude
        logger.debug("Generating commit message")
        if return_usage:
            result, usage = await self._query_with_usage(prompt)
            logger.debug("Generated commit message: %s", result)
            return result, usage
        else:
            result = await self._query(prompt)
            logger.debug("Generated commit message: %s", result)
            return result

    def _build_prompt(
        self,
        diff: str,
        file_stats: dict[str, Any] | None,
        scope_hint: str | None,
    ) -> str:
        """Build the user prompt for commit message generation.

        Args:
            diff: Git diff (already truncated if needed).
            file_stats: File statistics with additions/deletions.
            scope_hint: Optional suggested scope.

        Returns:
            Formatted prompt for Claude.
        """
        prompt_parts = [
            "Generate a conventional commit message for the following changes:\n"
        ]

        # Add scope hint if provided
        if scope_hint:
            prompt_parts.append(f"\n**Suggested Scope**: {scope_hint}\n")

        # Add file statistics if available
        if file_stats:
            prompt_parts.append("\n**Files Changed**:")
            for file_path, stats in file_stats.items():
                if isinstance(stats, dict):
                    additions = stats.get("additions", 0)
                    deletions = stats.get("deletions", 0)
                else:
                    additions = deletions = 0
                prompt_parts.append(f"- {file_path}: +{additions}/-{deletions}")
            prompt_parts.append("")

        # Add the diff
        prompt_parts.append("\n**Git Diff**:")
        prompt_parts.append("```")
        prompt_parts.append(diff)
        prompt_parts.append("```")

        prompt_parts.append("\nProvide ONLY the commit message, nothing else.")

        return "\n".join(prompt_parts)
