"""Unit tests for agent system prompts - verify constrained role patterns (T026).

This module tests that agent system prompts follow the constrained role pattern
where agents operate on pre-gathered context and do not attempt to execute
commands, create PRs, or perform API operations directly.

See specs/021-agent-tool-permissions/research.md for prompt patterns.
"""

from __future__ import annotations

from maverick.agents.code_reviewer import CodeReviewerAgent
from maverick.agents.generators.base import GeneratorAgent
from maverick.agents.implementer import ImplementerAgent
from maverick.agents.issue_fixer import IssueFixerAgent


# Concrete generator implementation for testing
class TestGenerator(GeneratorAgent):
    """Test implementation of GeneratorAgent."""

    async def generate(self, context: dict) -> str:
        """Simple test implementation."""
        return "test"


class TestPromptsDoNotMentionGitOperations:
    """Test that agent prompts do not mention direct git operations (T026)."""

    def test_implementer_does_not_mention_git_commands(self) -> None:
        """Test ImplementerAgent prompt doesn't mention running git commands.

        The orchestration layer handles git operations. The agent should
        focus on code implementation, not git execution.
        """
        agent = ImplementerAgent()
        prompt = agent.system_prompt.lower()

        # Should NOT mention running git commands
        assert "run git" not in prompt
        assert "execute git" not in prompt
        assert "git commit" not in prompt  # Should not instruct to run git commit
        assert "git push" not in prompt

    def test_code_reviewer_does_not_mention_git_commands(self) -> None:
        """Test CodeReviewerAgent prompt doesn't mention running git commands.

        Git diffs are pre-gathered by orchestration. The agent should
        analyze provided diffs, not execute git commands.
        """
        agent = CodeReviewerAgent()
        prompt = agent.system_prompt.lower()

        # Should NOT mention running git commands
        # (unless as negative guidance "don't")
        assert "run git" not in prompt
        # Allow "don't execute git" or "do not attempt to execute git"
        # as negative guidance
        if "execute git" in prompt:
            assert "do not" in prompt or "don't" in prompt
        # If git diff is mentioned, should clarify it's provided
        if "git diff" in prompt:
            assert (
                "provided" in prompt
                or "pre-gathered" in prompt
                or "orchestration" in prompt
            )

    def test_issue_fixer_does_not_mention_git_commands(self) -> None:
        """Test IssueFixerAgent prompt doesn't mention running git commands.

        Git operations are handled by orchestration. The agent should
        focus on implementing the fix.
        """
        agent = IssueFixerAgent()
        prompt = agent.system_prompt.lower()

        # Should NOT mention running git commands
        assert "run git" not in prompt
        assert "execute git" not in prompt
        assert "git commit" not in prompt  # Should not instruct to run git commit
        assert "git push" not in prompt


class TestPromptsDoNotMentionPROperations:
    """Test that agent prompts do not mention direct PR operations (T026)."""

    def test_implementer_does_not_mention_pr_creation(self) -> None:
        """Test ImplementerAgent prompt doesn't mention creating PRs.

        PR creation is handled by orchestration/workflow layer.
        """
        agent = ImplementerAgent()
        prompt = agent.system_prompt.lower()

        assert "create pr" not in prompt
        assert "create pull request" not in prompt
        assert "open pr" not in prompt
        assert "gh pr create" not in prompt

    def test_code_reviewer_does_not_mention_pr_creation(self) -> None:
        """Test CodeReviewerAgent prompt doesn't mention creating PRs.

        Reviewers analyze code, they don't create PRs.
        """
        agent = CodeReviewerAgent()
        prompt = agent.system_prompt.lower()

        assert "create pr" not in prompt
        assert "create pull request" not in prompt
        assert "open pr" not in prompt
        assert "gh pr create" not in prompt

    def test_issue_fixer_does_not_mention_pr_creation(self) -> None:
        """Test IssueFixerAgent prompt doesn't mention creating PRs.

        PR creation is handled by orchestration/workflow layer.
        """
        agent = IssueFixerAgent()
        prompt = agent.system_prompt.lower()

        assert "create pr" not in prompt
        assert "create pull request" not in prompt
        assert "open pr" not in prompt
        assert "gh pr create" not in prompt


class TestPromptsDoNotMentionAPIOperations:
    """Test that agent prompts do not mention direct API operations (T026)."""

    def test_implementer_does_not_mention_api_calls(self) -> None:
        """Test ImplementerAgent prompt doesn't mention making API calls.

        External integrations are handled by orchestration/tools layer.
        """
        agent = ImplementerAgent()
        prompt = agent.system_prompt.lower()

        assert "api call" not in prompt
        assert "http request" not in prompt
        assert "github api" not in prompt

    def test_code_reviewer_does_not_mention_api_calls(self) -> None:
        """Test CodeReviewerAgent prompt doesn't mention making API calls.

        Issue/PR data is pre-fetched by orchestration.
        """
        agent = CodeReviewerAgent()
        prompt = agent.system_prompt.lower()

        assert "api call" not in prompt
        assert "http request" not in prompt
        assert "github api" not in prompt

    def test_issue_fixer_does_not_mention_api_calls(self) -> None:
        """Test IssueFixerAgent prompt doesn't mention making API calls.

        Issue data is pre-fetched by orchestration.
        """
        agent = IssueFixerAgent()
        prompt = agent.system_prompt.lower()

        assert "api call" not in prompt
        assert "http request" not in prompt
        assert "github api" not in prompt

    def test_generator_does_not_mention_api_calls(self) -> None:
        """Test GeneratorAgent doesn't mention making API calls.

        Generators work with provided context only.
        """
        agent = TestGenerator(name="test", system_prompt="You generate text.")
        prompt = agent.system_prompt.lower()

        # Generators should have simple, focused prompts
        assert "api call" not in prompt
        assert "http request" not in prompt


class TestPromptsDoNotMentionBashExecution:
    """Test that agent prompts do not instruct Bash execution.

    For orchestrated tasks (T026).
    """

    def test_implementer_does_not_instruct_bash_for_validation(self) -> None:
        """Test ImplementerAgent prompt doesn't instruct running validation via Bash.

        Validation is run by orchestration layer, not by agent executing bash.
        While agent has Bash tool, prompt should not instruct it to run validation.
        """
        agent = ImplementerAgent()
        prompt = agent.system_prompt.lower()

        # Should NOT instruct to run validation commands
        assert "run validation" not in prompt or "orchestration" in prompt
        assert "execute tests" not in prompt or "orchestration" in prompt
        # NOTE: Agent may mention validation exists,
        # but shouldn't say "run pytest" directly

    def test_code_reviewer_does_not_instruct_bash_execution(self) -> None:
        """Test CodeReviewerAgent prompt doesn't instruct executing commands.

        Reviewer analyzes pre-gathered context, doesn't execute commands.
        """
        agent = CodeReviewerAgent()
        prompt = agent.system_prompt.lower()

        # Should NOT instruct to execute commands for analysis
        assert "execute command" not in prompt or "orchestration" in prompt
        assert "run command" not in prompt or "orchestration" in prompt

    def test_issue_fixer_does_not_instruct_bash_for_validation(self) -> None:
        """Test IssueFixerAgent prompt doesn't instruct running validation via Bash.

        Validation is run by orchestration layer.
        """
        agent = IssueFixerAgent()
        prompt = agent.system_prompt.lower()

        # Should NOT instruct to run validation commands
        assert "run validation" not in prompt or "orchestration" in prompt
        assert "execute tests" not in prompt or "orchestration" in prompt


class TestPromptsExplainConstrainedRole:
    """Test that prompts explain the agent's constrained role (T026)."""

    def test_implementer_explains_orchestration_context(self) -> None:
        """Test ImplementerAgent prompt explains orchestration handles certain tasks.

        Should clarify what the agent does vs what orchestration does.
        """
        agent = ImplementerAgent()
        prompt = agent.system_prompt.lower()

        # Should mention orchestration or that some tasks are handled externally
        assert "orchestration" in prompt or "orchestrated" in prompt

    def test_code_reviewer_explains_pre_gathered_context(self) -> None:
        """Test CodeReviewerAgent prompt explains context is pre-gathered.

        Should clarify that diffs and files are provided by orchestration.
        """
        agent = CodeReviewerAgent()
        prompt = agent.system_prompt.lower()

        # Should mention that context is provided/pre-gathered
        has_context_explanation = any(
            [
                "provided" in prompt,
                "pre-gathered" in prompt,
                "orchestration" in prompt,
            ]
        )
        assert has_context_explanation

    def test_generator_explains_context_is_provided(self) -> None:
        """Test GeneratorAgent clarifies all context is provided in prompt.

        Generators have no tools, all input comes via prompt.
        """
        agent = TestGenerator(
            name="test",
            system_prompt="You generate text from provided context.",
        )
        prompt = agent.system_prompt.lower()

        # Should mention that context is provided
        assert "provided" in prompt
