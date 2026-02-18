"""Unit tests for CuratorAgent.

Tests the curator agent including:
- Initialization and tool set
- Plan parsing (valid, empty, invalid JSON)
- System prompt content
"""

from __future__ import annotations

import pytest

from maverick.agents.curator import SYSTEM_PROMPT, CuratorAgent
from maverick.agents.tools import CURATOR_TOOLS


class TestCuratorInit:
    """Tests for CuratorAgent initialization."""

    def test_curator_name(self) -> None:
        """Curator has the correct name."""
        agent = CuratorAgent()
        assert agent.name == "curator"

    def test_curator_system_prompt(self) -> None:
        """Curator system prompt mentions jj and JSON."""
        agent = CuratorAgent()
        assert "jj" in agent.system_prompt.lower() or "jj" in agent.system_prompt
        assert "JSON" in agent.system_prompt

    def test_curator_uses_generator_tools(self) -> None:
        """Curator tool set is empty (CURATOR_TOOLS)."""
        assert frozenset() == CURATOR_TOOLS
        agent = CuratorAgent()
        # Generator-based agent — tools come via base class
        assert agent._options.allowed_tools == []

    def test_system_prompt_constant(self) -> None:
        """SYSTEM_PROMPT module constant matches agent's prompt."""
        agent = CuratorAgent()
        assert agent.system_prompt == SYSTEM_PROMPT


class TestCuratorParsePlan:
    """Tests for CuratorAgent.parse_plan()."""

    def test_parse_valid_plan(self) -> None:
        """Parses a well-formed JSON plan."""
        agent = CuratorAgent()
        raw = (
            '[{"command": "squash", "args": ["-r", "abc123"],'
            ' "reason": "Fix into parent"}]'
        )
        plan = agent.parse_plan(raw)
        assert len(plan) == 1
        assert plan[0]["command"] == "squash"
        assert plan[0]["args"] == ["-r", "abc123"]
        assert plan[0]["reason"] == "Fix into parent"

    def test_parse_empty_plan(self) -> None:
        """Parses an empty JSON array as no-op."""
        agent = CuratorAgent()
        plan = agent.parse_plan("[]")
        assert plan == []

    def test_parse_multiple_steps(self) -> None:
        """Parses a multi-step plan."""
        agent = CuratorAgent()
        raw = (
            "["
            '{"command":"squash","args":["-r","a1"],"reason":"fix"},'
            '{"command":"describe","args":["-r","b2","-m","feat: auth"],'
            '"reason":"better msg"},'
            '{"command":"rebase","args":["-r","c3","--after","a1"],'
            '"reason":"reorder"}'
            "]"
        )
        plan = agent.parse_plan(raw)
        assert len(plan) == 3
        assert plan[0]["command"] == "squash"
        assert plan[1]["command"] == "describe"
        assert plan[2]["command"] == "rebase"

    def test_parse_handles_markdown_fences(self) -> None:
        """Strips markdown code fences from LLM output."""
        agent = CuratorAgent()
        raw = (
            "```json\n"
            '[{"command": "squash", "args": ["-r", "x"],'
            ' "reason": "fix"}]\n```'
        )
        plan = agent.parse_plan(raw)
        assert len(plan) == 1
        assert plan[0]["command"] == "squash"

    def test_parse_handles_invalid_json(self) -> None:
        """Returns empty list on malformed JSON."""
        agent = CuratorAgent()
        plan = agent.parse_plan("this is not json at all")
        assert plan == []

    def test_parse_handles_non_array_json(self) -> None:
        """Returns empty list when JSON is an object instead of array."""
        agent = CuratorAgent()
        plan = agent.parse_plan('{"command": "squash"}')
        assert plan == []

    def test_parse_skips_invalid_commands(self) -> None:
        """Skips steps with unrecognized commands."""
        agent = CuratorAgent()
        raw = """[
            {"command": "squash", "args": ["-r", "a1"], "reason": "ok"},
            {"command": "delete", "args": [], "reason": "not a valid command"},
            {"command": "describe", "args": ["-r", "b2", "-m", "x"], "reason": "ok"}
        ]"""
        plan = agent.parse_plan(raw)
        assert len(plan) == 2
        assert plan[0]["command"] == "squash"
        assert plan[1]["command"] == "describe"

    def test_parse_skips_non_dict_entries(self) -> None:
        """Skips entries that are not dicts."""
        agent = CuratorAgent()
        raw = '[{"command": "squash", "args": [], "reason": "ok"}, "not a dict", 42]'
        plan = agent.parse_plan(raw)
        assert len(plan) == 1

    def test_parse_adds_default_args_and_reason(self) -> None:
        """Missing args/reason default to empty."""
        agent = CuratorAgent()
        raw = '[{"command": "squash"}]'
        plan = agent.parse_plan(raw)
        assert len(plan) == 1
        assert plan[0]["args"] == []
        assert plan[0]["reason"] == ""


class TestCuratorGenerate:
    """Tests for CuratorAgent.generate()."""

    @pytest.mark.asyncio
    async def test_generate_empty_commits(self) -> None:
        """Returns empty array when no commits provided."""
        agent = CuratorAgent()
        result = await agent.generate({"commits": [], "log_summary": ""})
        assert result == "[]"

    @pytest.mark.asyncio
    async def test_generate_empty_commits_with_usage(self) -> None:
        """Returns empty array with zero usage when no commits."""
        agent = CuratorAgent()
        text, usage = await agent.generate(
            {"commits": [], "log_summary": ""},
            return_usage=True,
        )
        assert text == "[]"
        assert usage.total_tokens == 0
