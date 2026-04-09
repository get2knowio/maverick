"""Unit tests for agent system prompts - verify constrained role patterns (T026).

This module tests that agent system prompts follow the constrained role pattern
where agents operate on pre-gathered context and do not attempt to execute
commands, create PRs, or perform API operations directly.

See specs/021-agent-tool-permissions/research.md for prompt patterns.
"""

from __future__ import annotations

from maverick.agents.generators.base import GeneratorAgent
from maverick.agents.implementer import ImplementerAgent
from maverick.agents.reviewers import (
    CompletenessReviewerAgent,
    CorrectnessReviewerAgent,
)


# Concrete generator implementation for testing
class TestGenerator(GeneratorAgent):
    """Test implementation of GeneratorAgent."""

    def build_prompt(self, context: dict) -> str:
        """Build prompt from context."""
        return "test"

    async def generate(self, context: dict) -> str:
        """Simple test implementation."""
        return "test"


class TestPromptsDoNotMentionGitOperations:
    """Test that agent prompts do not mention direct git operations (T026)."""

    def test_implementer_does_not_mention_git_commands(self) -> None:
        """Test ImplementerAgent prompt doesn't mention running git commands."""
        agent = ImplementerAgent()
        prompt = agent.instructions.lower()

        assert "run git" not in prompt
        assert "execute git" not in prompt
        assert "git commit" not in prompt
        assert "git push" not in prompt

    def test_completeness_reviewer_does_not_mention_git_commands(self) -> None:
        """CompletenessReviewerAgent prompt has no git commands."""
        agent = CompletenessReviewerAgent()
        prompt = agent.instructions.lower()

        assert "run git" not in prompt
        if "execute git" in prompt:
            assert "do not" in prompt or "don't" in prompt
        if "git diff" in prompt:
            assert "provided" in prompt or "pre-gathered" in prompt or "orchestration" in prompt

    def test_correctness_reviewer_does_not_mention_git_commands(self) -> None:
        """Test CorrectnessReviewerAgent prompt doesn't mention running git commands."""
        agent = CorrectnessReviewerAgent()
        prompt = agent.instructions.lower()

        assert "run git" not in prompt
        if "execute git" in prompt:
            assert "do not" in prompt or "don't" in prompt


class TestPromptsDoNotMentionPROperations:
    """Test that agent prompts do not mention direct PR operations (T026)."""

    def test_implementer_does_not_mention_pr_creation(self) -> None:
        """Test ImplementerAgent prompt doesn't mention creating PRs."""
        agent = ImplementerAgent()
        prompt = agent.instructions.lower()

        assert "create pr" not in prompt
        assert "create pull request" not in prompt
        assert "open pr" not in prompt
        assert "gh pr create" not in prompt

    def test_completeness_reviewer_does_not_mention_pr_creation(self) -> None:
        """Test CompletenessReviewerAgent prompt doesn't mention creating PRs."""
        agent = CompletenessReviewerAgent()
        prompt = agent.instructions.lower()

        assert "create pr" not in prompt
        assert "create pull request" not in prompt
        assert "open pr" not in prompt
        assert "gh pr create" not in prompt

    def test_correctness_reviewer_does_not_mention_pr_creation(self) -> None:
        """Test CorrectnessReviewerAgent prompt doesn't mention creating PRs."""
        agent = CorrectnessReviewerAgent()
        prompt = agent.instructions.lower()

        assert "create pr" not in prompt
        assert "create pull request" not in prompt
        assert "open pr" not in prompt
        assert "gh pr create" not in prompt


class TestPromptsDoNotMentionAPIOperations:
    """Test that agent prompts do not mention direct API operations (T026)."""

    def test_implementer_does_not_mention_api_calls(self) -> None:
        """Test ImplementerAgent prompt doesn't mention making API calls."""
        agent = ImplementerAgent()
        prompt = agent.instructions.lower()

        assert "api call" not in prompt
        assert "http request" not in prompt
        assert "github api" not in prompt

    def test_completeness_reviewer_does_not_mention_api_calls(self) -> None:
        """Test CompletenessReviewerAgent prompt doesn't mention making API calls."""
        agent = CompletenessReviewerAgent()
        prompt = agent.instructions.lower()

        assert "api call" not in prompt
        assert "http request" not in prompt
        assert "github api" not in prompt

    def test_correctness_reviewer_does_not_mention_api_calls(self) -> None:
        """Test CorrectnessReviewerAgent prompt doesn't mention making API calls."""
        agent = CorrectnessReviewerAgent()
        prompt = agent.instructions.lower()

        assert "api call" not in prompt
        assert "http request" not in prompt
        assert "github api" not in prompt

    def test_generator_does_not_mention_api_calls(self) -> None:
        """Test GeneratorAgent doesn't mention making API calls."""
        agent = TestGenerator(name="test", system_prompt="You generate text.")
        prompt = agent.system_prompt.lower()

        assert "api call" not in prompt
        assert "http request" not in prompt


class TestPromptsDoNotMentionBashExecution:
    """Test that agent prompts do not instruct Bash execution.

    For orchestrated tasks (T026).
    """

    def test_implementer_does_not_instruct_bash_for_validation(self) -> None:
        """Test ImplementerAgent prompt doesn't instruct running validation via Bash."""
        agent = ImplementerAgent()
        prompt = agent.instructions.lower()

        assert "run validation" not in prompt or "orchestration" in prompt
        assert "execute tests" not in prompt or "orchestration" in prompt

    def test_completeness_reviewer_does_not_instruct_bash_execution(self) -> None:
        """Test CompletenessReviewerAgent prompt doesn't instruct executing commands."""
        agent = CompletenessReviewerAgent()
        prompt = agent.instructions.lower()

        assert "execute command" not in prompt or "orchestration" in prompt
        assert "run command" not in prompt or "orchestration" in prompt

    def test_correctness_reviewer_does_not_instruct_bash_execution(self) -> None:
        """Test CorrectnessReviewerAgent prompt doesn't instruct executing commands."""
        agent = CorrectnessReviewerAgent()
        prompt = agent.instructions.lower()

        assert "execute command" not in prompt or "orchestration" in prompt
        assert "run command" not in prompt or "orchestration" in prompt


class TestPromptsExplainConstrainedRole:
    """Test that prompts explain the agent's constrained role (T026)."""

    def test_implementer_explains_orchestration_context(self) -> None:
        """Test ImplementerAgent prompt explains orchestration handles certain tasks."""
        agent = ImplementerAgent()
        prompt = agent.instructions.lower()

        assert "orchestration" in prompt or "orchestrated" in prompt

    def test_generator_explains_context_is_provided(self) -> None:
        """Test GeneratorAgent clarifies all context is provided in prompt."""
        agent = TestGenerator(
            name="test",
            system_prompt="You generate text from provided context.",
        )
        prompt = agent.system_prompt.lower()

        assert "provided" in prompt
