"""Tests for briefing-aware review in UnifiedReviewerAgent."""

from __future__ import annotations

from maverick.agents.reviewers.unified_reviewer import UnifiedReviewerAgent


class TestBriefingContextInPrompt:
    """Verify that briefing context is included in the review prompt."""

    def test_prompt_includes_briefing_context(self) -> None:
        agent = UnifiedReviewerAgent()
        context = {
            "changed_files": ["src/foo.py"],
            "diff": "--- a/src/foo.py\n+++ b/src/foo.py\n@@ -1 +1 @@\n-old\n+new",
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
        agent = UnifiedReviewerAgent()
        context = {
            "changed_files": ["src/foo.py"],
            "diff": "some diff",
        }
        prompt = agent.build_prompt(context)
        assert "Briefing Expectations" not in prompt

    def test_prompt_truncates_large_briefing(self) -> None:
        agent = UnifiedReviewerAgent()
        large_briefing = "x" * 25000
        context = {
            "changed_files": ["src/foo.py"],
            "diff": "some diff",
            "briefing_context": large_briefing,
        }
        prompt = agent.build_prompt(context)
        assert "... (truncated)" in prompt
        # Should be truncated to 20000 chars + truncation message
        assert len(large_briefing) > 20000

    def test_prompt_empty_briefing_excluded(self) -> None:
        agent = UnifiedReviewerAgent()
        context = {
            "changed_files": ["src/foo.py"],
            "diff": "some diff",
            "briefing_context": "",
        }
        prompt = agent.build_prompt(context)
        assert "Briefing Expectations" not in prompt


class TestSystemPromptMentionsBriefing:
    """Verify the system prompt references briefing expectations."""

    def test_requirements_expert_mentions_briefing(self) -> None:
        agent = UnifiedReviewerAgent()
        assert "Briefing Expectations" in agent.instructions
        assert "architecture decisions" in agent.instructions
