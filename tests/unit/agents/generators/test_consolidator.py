"""Tests for ConsolidatorAgent."""

from __future__ import annotations

from maverick.agents.generators.consolidator import ConsolidatorAgent


class TestConsolidatorBuildPrompt:
    """Tests for ConsolidatorAgent.build_prompt."""

    def test_build_prompt_with_all_fields(self) -> None:
        """Prompt should include outcomes, findings, existing summary."""
        agent = ConsolidatorAgent()
        context = {
            "existing_summary": "# Existing Insights\nSome content.",
            "bead_outcomes": [
                {"bead_id": "b1", "title": "Test", "validation_passed": True}
            ],
            "review_findings": [
                {"finding_id": "F1", "severity": "major", "category": "correctness"}
            ],
            "fix_attempts": [
                {"attempt_id": "A1", "succeeded": False, "failure_reason": "timeout"}
            ],
        }

        prompt = agent.build_prompt(context)

        assert "Existing Summary" in prompt
        assert "Existing Insights" in prompt
        assert "Bead Outcomes (1 records)" in prompt
        assert "b1" in prompt
        assert "Review Findings (1 records)" in prompt
        assert "F1" in prompt
        assert "Fix Attempts (1 records)" in prompt
        assert "A1" in prompt

    def test_build_prompt_without_existing_summary(self) -> None:
        """Prompt should handle None existing summary gracefully."""
        agent = ConsolidatorAgent()
        context = {
            "existing_summary": None,
            "bead_outcomes": [{"bead_id": "b1"}],
            "review_findings": [],
            "fix_attempts": [],
        }

        prompt = agent.build_prompt(context)

        assert "Existing Summary" not in prompt
        assert "Bead Outcomes" in prompt

    def test_build_prompt_empty_data(self) -> None:
        """Prompt should handle all empty data."""
        agent = ConsolidatorAgent()
        context = {
            "existing_summary": None,
            "bead_outcomes": [],
            "review_findings": [],
            "fix_attempts": [],
        }

        prompt = agent.build_prompt(context)

        assert "No episodic data" in prompt

    def test_system_prompt_content(self) -> None:
        """System prompt should mention the required sections."""
        agent = ConsolidatorAgent()

        assert "Validation Failure Patterns" in agent.system_prompt
        assert "Recurring Review Findings" in agent.system_prompt
        assert "Successful Implementation Patterns" in agent.system_prompt
        assert "Frequently Problematic Files" in agent.system_prompt


class TestConsolidatorParseSummary:
    """Tests for ConsolidatorAgent.parse_summary."""

    def test_parse_summary_plain_markdown(self) -> None:
        """Plain markdown should pass through unchanged (stripped)."""
        result = ConsolidatorAgent.parse_summary("# Insights\n\nSome content.\n")
        assert result == "# Insights\n\nSome content."

    def test_parse_summary_strips_fences(self) -> None:
        """Markdown code fences should be stripped."""
        raw = "```markdown\n# Insights\n\nContent here.\n```"
        result = ConsolidatorAgent.parse_summary(raw)
        assert result == "# Insights\n\nContent here."
        assert "```" not in result

    def test_parse_summary_strips_plain_fences(self) -> None:
        """Plain ``` fences should also be stripped."""
        raw = "```\n# Insights\n\nContent.\n```"
        result = ConsolidatorAgent.parse_summary(raw)
        assert result == "# Insights\n\nContent."

    def test_parse_summary_empty(self) -> None:
        """Empty input should return empty string."""
        assert ConsolidatorAgent.parse_summary("") == ""
        assert ConsolidatorAgent.parse_summary("  \n  ") == ""


class TestConsolidatorInit:
    """Tests for ConsolidatorAgent initialization."""

    def test_name(self) -> None:
        agent = ConsolidatorAgent()
        assert agent.name == "consolidator"

    def test_temperature(self) -> None:
        agent = ConsolidatorAgent()
        assert agent._temperature == 0.0

    def test_allowed_tools_empty(self) -> None:
        agent = ConsolidatorAgent()
        assert agent.allowed_tools == []
