"""Tests for CompletenessReviewerAgent."""

from __future__ import annotations

from maverick.agents.reviewers.completeness_reviewer import CompletenessReviewerAgent


class TestCompletenessReviewerInit:
    """Verify agent initialization."""

    def test_name(self) -> None:
        agent = CompletenessReviewerAgent()
        assert agent.name == "completeness-reviewer"

    def test_tools_are_read_only(self) -> None:
        agent = CompletenessReviewerAgent()
        assert "Read" in agent.allowed_tools
        assert "Glob" in agent.allowed_tools
        assert "Grep" in agent.allowed_tools
        # No write tools, no Task
        assert "Write" not in agent.allowed_tools
        assert "Edit" not in agent.allowed_tools
        assert "Task" not in agent.allowed_tools

    def test_custom_model(self) -> None:
        agent = CompletenessReviewerAgent(model="gpt-5.4")
        assert agent.model == "gpt-5.4"


class TestCompletenessReviewerPrompt:
    """Verify prompt construction."""

    def test_prompt_includes_task_description(self) -> None:
        agent = CompletenessReviewerAgent()
        context = {
            "changed_files": ["src/foo.py"],
            "diff": "some diff",
            "bead_description": "Implement feature X with acceptance criteria Y",
        }
        prompt = agent.build_prompt(context)
        assert "Implement feature X" in prompt
        assert "## Task Description" in prompt

    def test_prompt_includes_briefing_context(self) -> None:
        agent = CompletenessReviewerAgent()
        context = {
            "changed_files": ["src/foo.py"],
            "diff": "some diff",
            "briefing_context": (
                "## Key Decisions\n- Use Pydantic for validation\n"
                "## Key Risks\n- API breakage risk"
            ),
        }
        prompt = agent.build_prompt(context)
        assert "## Briefing Expectations" in prompt
        assert "Use Pydantic for validation" in prompt
        assert "API breakage risk" in prompt

    def test_prompt_without_briefing_context(self) -> None:
        agent = CompletenessReviewerAgent()
        context = {
            "changed_files": ["src/foo.py"],
            "diff": "some diff",
        }
        prompt = agent.build_prompt(context)
        assert "Briefing Expectations" not in prompt

    def test_prompt_truncates_large_briefing(self) -> None:
        agent = CompletenessReviewerAgent()
        large_briefing = "x" * 25000
        context = {
            "changed_files": ["src/foo.py"],
            "diff": "some diff",
            "briefing_context": large_briefing,
        }
        prompt = agent.build_prompt(context)
        assert "... (truncated)" in prompt

    def test_prompt_empty_briefing_excluded(self) -> None:
        agent = CompletenessReviewerAgent()
        context = {
            "changed_files": ["src/foo.py"],
            "diff": "some diff",
            "briefing_context": "",
        }
        prompt = agent.build_prompt(context)
        assert "Briefing Expectations" not in prompt

    def test_prompt_includes_feature_name(self) -> None:
        agent = CompletenessReviewerAgent(feature_name="my-feature")
        context = {"changed_files": [], "diff": ""}
        prompt = agent.build_prompt(context)
        assert "my-feature" in prompt

    def test_prompt_includes_changed_files(self) -> None:
        agent = CompletenessReviewerAgent()
        context = {
            "changed_files": ["src/a.py", "src/b.py"],
            "diff": "some diff",
        }
        prompt = agent.build_prompt(context)
        assert "src/a.py" in prompt
        assert "src/b.py" in prompt


class TestCompletenessSystemPrompt:
    """Verify system prompt content."""

    def test_focuses_on_requirements(self) -> None:
        agent = CompletenessReviewerAgent()
        assert "acceptance criteria" in agent.instructions.lower()
        assert "requirement" in agent.instructions.lower()

    def test_mentions_briefing_expectations(self) -> None:
        agent = CompletenessReviewerAgent()
        assert "Briefing Expectations" in agent.instructions

    def test_does_not_mention_task_tool(self) -> None:
        agent = CompletenessReviewerAgent()
        # Completeness reviewer should not reference Task tool
        assert "### Task" not in agent.instructions
