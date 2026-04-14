"""Unit tests for Pre-Flight Briefing Room agents."""

from __future__ import annotations

from maverick.agents.base import BUILTIN_TOOLS
from maverick.agents.preflight_briefing.codebase_analyst import (
    CODEBASE_ANALYST_SYSTEM_PROMPT,
    CodebaseAnalystAgent,
)
from maverick.agents.preflight_briefing.contrarian import (
    PREFLIGHT_CONTRARIAN_SYSTEM_PROMPT,
    PreFlightContrarianAgent,
)
from maverick.agents.preflight_briefing.criteria_writer import (
    CRITERIA_WRITER_SYSTEM_PROMPT,
    CriteriaWriterAgent,
)
from maverick.agents.preflight_briefing.scopist import (
    SCOPIST_SYSTEM_PROMPT,
    ScopistAgent,
)
from maverick.agents.tools import PLANNER_TOOLS


class TestScopistAgent:
    def test_default_instantiation(self) -> None:
        agent = ScopistAgent()
        assert agent.name == "scopist"

    def test_allowed_tools_match_planner_tools(self) -> None:
        agent = ScopistAgent()
        assert set(agent.allowed_tools) == set(PLANNER_TOOLS)

    def test_tools_are_read_only(self) -> None:
        agent = ScopistAgent()
        tools = set(agent.allowed_tools)
        assert "Write" not in tools
        assert "Edit" not in tools
        assert "Bash" not in tools

    def test_tools_are_valid_builtins(self) -> None:
        agent = ScopistAgent()
        assert set(agent.allowed_tools).issubset(BUILTIN_TOOLS)

    def test_build_prompt_passthrough(self) -> None:
        agent = ScopistAgent()
        assert agent.build_prompt("hello") == "hello"

    def test_system_prompt_mentions_scope(self) -> None:
        assert "scope" in SCOPIST_SYSTEM_PROMPT.lower()

    def test_custom_model(self) -> None:
        agent = ScopistAgent(model="claude-sonnet-4-6-20250514")
        assert agent.model == "claude-sonnet-4-6-20250514"


class TestCodebaseAnalystAgent:
    def test_default_instantiation(self) -> None:
        agent = CodebaseAnalystAgent()
        assert agent.name == "codebase_analyst"

    def test_allowed_tools_match_planner_tools(self) -> None:
        agent = CodebaseAnalystAgent()
        assert set(agent.allowed_tools) == set(PLANNER_TOOLS)

    def test_tools_are_valid_builtins(self) -> None:
        agent = CodebaseAnalystAgent()
        assert set(agent.allowed_tools).issubset(BUILTIN_TOOLS)

    def test_build_prompt_passthrough(self) -> None:
        agent = CodebaseAnalystAgent()
        assert agent.build_prompt("test") == "test"

    def test_system_prompt_mentions_codebase(self) -> None:
        assert "codebase" in CODEBASE_ANALYST_SYSTEM_PROMPT.lower()


class TestCriteriaWriterAgent:
    def test_default_instantiation(self) -> None:
        agent = CriteriaWriterAgent()
        assert agent.name == "criteria_writer"

    def test_allowed_tools_match_planner_tools(self) -> None:
        agent = CriteriaWriterAgent()
        assert set(agent.allowed_tools) == set(PLANNER_TOOLS)

    def test_tools_are_valid_builtins(self) -> None:
        agent = CriteriaWriterAgent()
        assert set(agent.allowed_tools).issubset(BUILTIN_TOOLS)

    def test_build_prompt_passthrough(self) -> None:
        agent = CriteriaWriterAgent()
        assert agent.build_prompt("prompt") == "prompt"

    def test_system_prompt_mentions_criteria(self) -> None:
        assert "criteria" in CRITERIA_WRITER_SYSTEM_PROMPT.lower()


class TestPreFlightContrarianAgent:
    def test_default_instantiation(self) -> None:
        agent = PreFlightContrarianAgent()
        assert agent.name == "preflight_contrarian"

    def test_allowed_tools_match_planner_tools(self) -> None:
        agent = PreFlightContrarianAgent()
        assert set(agent.allowed_tools) == set(PLANNER_TOOLS)

    def test_tools_are_valid_builtins(self) -> None:
        agent = PreFlightContrarianAgent()
        assert set(agent.allowed_tools).issubset(BUILTIN_TOOLS)

    def test_build_prompt_passthrough(self) -> None:
        agent = PreFlightContrarianAgent()
        assert agent.build_prompt("challenge") == "challenge"

    def test_system_prompt_mentions_challenge(self) -> None:
        assert "challenge" in PREFLIGHT_CONTRARIAN_SYSTEM_PROMPT.lower()

    def test_system_prompt_mentions_consensus(self) -> None:
        assert "consensus" in PREFLIGHT_CONTRARIAN_SYSTEM_PROMPT.lower()
