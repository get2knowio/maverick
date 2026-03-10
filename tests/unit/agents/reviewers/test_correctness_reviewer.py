"""Tests for CorrectnessReviewerAgent."""

from __future__ import annotations

from maverick.agents.reviewers.correctness_reviewer import CorrectnessReviewerAgent


class TestCorrectnessReviewerInit:
    """Verify agent initialization."""

    def test_name(self) -> None:
        agent = CorrectnessReviewerAgent()
        assert agent.name == "correctness-reviewer"

    def test_tools_are_read_only(self) -> None:
        agent = CorrectnessReviewerAgent()
        assert "Read" in agent.allowed_tools
        assert "Glob" in agent.allowed_tools
        assert "Grep" in agent.allowed_tools
        # No write tools, no Task
        assert "Write" not in agent.allowed_tools
        assert "Edit" not in agent.allowed_tools
        assert "Task" not in agent.allowed_tools

    def test_custom_model(self) -> None:
        agent = CorrectnessReviewerAgent(model="claude-sonnet-4-6")
        assert agent.model == "claude-sonnet-4-6"


class TestCorrectnessReviewerPrompt:
    """Verify prompt construction."""

    def test_prompt_includes_task_description(self) -> None:
        agent = CorrectnessReviewerAgent()
        context = {
            "changed_files": ["src/foo.py"],
            "diff": "some diff",
            "bead_description": "Implement feature X",
        }
        prompt = agent.build_prompt(context)
        assert "Implement feature X" in prompt
        assert "## Task Description" in prompt

    def test_prompt_does_not_include_briefing(self) -> None:
        agent = CorrectnessReviewerAgent()
        context = {
            "changed_files": ["src/foo.py"],
            "diff": "some diff",
            "briefing_context": "Some briefing content",
        }
        prompt = agent.build_prompt(context)
        # Correctness reviewer does not process briefing context
        assert "Briefing Expectations" not in prompt

    def test_prompt_includes_feature_name(self) -> None:
        agent = CorrectnessReviewerAgent(feature_name="my-feature")
        context = {"changed_files": [], "diff": ""}
        prompt = agent.build_prompt(context)
        assert "my-feature" in prompt

    def test_prompt_includes_changed_files(self) -> None:
        agent = CorrectnessReviewerAgent()
        context = {
            "changed_files": ["src/a.py", "src/b.py"],
            "diff": "some diff",
        }
        prompt = agent.build_prompt(context)
        assert "src/a.py" in prompt
        assert "src/b.py" in prompt

    def test_prompt_truncates_large_diff(self) -> None:
        agent = CorrectnessReviewerAgent()
        large_diff = "+" * 60000
        context = {"changed_files": ["src/foo.py"], "diff": large_diff}
        prompt = agent.build_prompt(context)
        assert "... (truncated)" in prompt


class TestCorrectnessSystemPrompt:
    """Verify system prompt content."""

    def test_focuses_on_technical_quality(self) -> None:
        agent = CorrectnessReviewerAgent()
        assert "security" in agent.instructions.lower()
        assert "idiomatic" in agent.instructions.lower()
        assert "type system" in agent.instructions.lower()

    def test_mentions_hardening(self) -> None:
        agent = CorrectnessReviewerAgent()
        assert "Hardening" in agent.instructions
        assert "timeout" in agent.instructions.lower()

    def test_does_not_mention_task_tool(self) -> None:
        agent = CorrectnessReviewerAgent()
        assert "### Task" not in agent.instructions
