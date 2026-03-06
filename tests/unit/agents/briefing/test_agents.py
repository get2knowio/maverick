"""Unit tests for Briefing Room agents."""

from __future__ import annotations

from maverick.agents.base import BUILTIN_TOOLS
from maverick.agents.briefing.contrarian import (
    CONTRARIAN_SYSTEM_PROMPT,
    ContrarianAgent,
)
from maverick.agents.briefing.navigator import (
    NAVIGATOR_SYSTEM_PROMPT,
    NavigatorAgent,
)
from maverick.agents.briefing.recon import (
    RECON_SYSTEM_PROMPT,
    ReconAgent,
)
from maverick.agents.briefing.structuralist import (
    STRUCTURALIST_SYSTEM_PROMPT,
    StructuralistAgent,
)
from maverick.agents.tools import PLANNER_TOOLS
from maverick.briefing.models import (
    ContrarianBrief,
    NavigatorBrief,
    ReconBrief,
    StructuralistBrief,
)


class TestNavigatorAgent:
    def test_default_instantiation(self) -> None:
        agent = NavigatorAgent()
        assert agent.name == "navigator"

    def test_allowed_tools_match_planner_tools(self) -> None:
        agent = NavigatorAgent()
        assert set(agent.allowed_tools) == set(PLANNER_TOOLS)

    def test_tools_are_read_only(self) -> None:
        agent = NavigatorAgent()
        tools = set(agent.allowed_tools)
        assert "Write" not in tools
        assert "Edit" not in tools
        assert "Bash" not in tools

    def test_tools_are_valid_builtins(self) -> None:
        agent = NavigatorAgent()
        assert set(agent.allowed_tools).issubset(BUILTIN_TOOLS)

    def test_output_model(self) -> None:
        agent = NavigatorAgent()
        assert agent._output_model is NavigatorBrief
        assert agent._output_format is not None
        assert agent._output_format["type"] == "json_schema"

    def test_build_prompt_passthrough(self) -> None:
        agent = NavigatorAgent()
        assert agent.build_prompt("hello") == "hello"

    def test_system_prompt_mentions_architecture(self) -> None:
        assert "architecture" in NAVIGATOR_SYSTEM_PROMPT.lower()

    def test_custom_model(self) -> None:
        agent = NavigatorAgent(model="claude-sonnet-4-5-20250929")
        assert agent.model == "claude-sonnet-4-5-20250929"


class TestStructuralistAgent:
    def test_default_instantiation(self) -> None:
        agent = StructuralistAgent()
        assert agent.name == "structuralist"

    def test_allowed_tools_match_planner_tools(self) -> None:
        agent = StructuralistAgent()
        assert set(agent.allowed_tools) == set(PLANNER_TOOLS)

    def test_tools_are_valid_builtins(self) -> None:
        agent = StructuralistAgent()
        assert set(agent.allowed_tools).issubset(BUILTIN_TOOLS)

    def test_output_model(self) -> None:
        agent = StructuralistAgent()
        assert agent._output_model is StructuralistBrief
        assert agent._output_format is not None
        assert agent._output_format["type"] == "json_schema"

    def test_build_prompt_passthrough(self) -> None:
        agent = StructuralistAgent()
        assert agent.build_prompt("test") == "test"

    def test_system_prompt_mentions_data_model(self) -> None:
        assert "data model" in STRUCTURALIST_SYSTEM_PROMPT.lower()


class TestReconAgent:
    def test_default_instantiation(self) -> None:
        agent = ReconAgent()
        assert agent.name == "recon"

    def test_allowed_tools_match_planner_tools(self) -> None:
        agent = ReconAgent()
        assert set(agent.allowed_tools) == set(PLANNER_TOOLS)

    def test_tools_are_valid_builtins(self) -> None:
        agent = ReconAgent()
        assert set(agent.allowed_tools).issubset(BUILTIN_TOOLS)

    def test_output_model(self) -> None:
        agent = ReconAgent()
        assert agent._output_model is ReconBrief
        assert agent._output_format is not None
        assert agent._output_format["type"] == "json_schema"

    def test_build_prompt_passthrough(self) -> None:
        agent = ReconAgent()
        assert agent.build_prompt("prompt") == "prompt"

    def test_system_prompt_mentions_risk(self) -> None:
        assert "risk" in RECON_SYSTEM_PROMPT.lower()


class TestContrarianAgent:
    def test_default_instantiation(self) -> None:
        agent = ContrarianAgent()
        assert agent.name == "contrarian"

    def test_allowed_tools_match_planner_tools(self) -> None:
        agent = ContrarianAgent()
        assert set(agent.allowed_tools) == set(PLANNER_TOOLS)

    def test_tools_are_valid_builtins(self) -> None:
        agent = ContrarianAgent()
        assert set(agent.allowed_tools).issubset(BUILTIN_TOOLS)

    def test_output_model(self) -> None:
        agent = ContrarianAgent()
        assert agent._output_model is ContrarianBrief
        assert agent._output_format is not None
        assert agent._output_format["type"] == "json_schema"

    def test_build_prompt_passthrough(self) -> None:
        agent = ContrarianAgent()
        assert agent.build_prompt("challenge") == "challenge"

    def test_system_prompt_mentions_challenge(self) -> None:
        assert "challenge" in CONTRARIAN_SYSTEM_PROMPT.lower()

    def test_system_prompt_mentions_simplif(self) -> None:
        assert "simpl" in CONTRARIAN_SYSTEM_PROMPT.lower()
