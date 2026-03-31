"""Unit tests for FlightPlanGeneratorAgent."""

from __future__ import annotations

from maverick.agents.base import BUILTIN_TOOLS
from maverick.agents.flight_plan_generator import (
    FLIGHT_PLAN_GENERATOR_SYSTEM_PROMPT,
    FlightPlanGeneratorAgent,
)
from maverick.agents.tools import PLANNER_TOOLS


class TestFlightPlanGeneratorAgentInit:
    """Tests for agent instantiation and configuration."""

    def test_default_instantiation(self) -> None:
        """Agent can be instantiated with no arguments."""
        agent = FlightPlanGeneratorAgent()
        assert agent.name == "flight_plan_generator"

    def test_allowed_tools_match_planner_tools(self) -> None:
        """Agent's allowed_tools match the PLANNER_TOOLS constant."""
        agent = FlightPlanGeneratorAgent()
        assert set(agent.allowed_tools) == set(PLANNER_TOOLS)

    def test_tools_are_read_only(self) -> None:
        """Agent does not have write or execute tools."""
        agent = FlightPlanGeneratorAgent()
        tools = set(agent.allowed_tools)
        assert "Write" not in tools
        assert "Edit" not in tools
        assert "Bash" not in tools

    def test_tools_are_valid_builtins(self) -> None:
        """All agent tools are valid builtins."""
        agent = FlightPlanGeneratorAgent()
        assert set(agent.allowed_tools).issubset(BUILTIN_TOOLS)

    def test_output_model_is_flight_plan_output(self) -> None:
        """Agent sets output_model for SDK structured output."""
        from maverick.workflows.generate_flight_plan.models import (
            FlightPlanOutput,
        )

        agent = FlightPlanGeneratorAgent()
        assert agent._output_model is FlightPlanOutput
        assert agent._output_format is not None
        assert agent._output_format["type"] == "json_schema"

    def test_custom_model(self) -> None:
        """Agent accepts a custom model."""
        agent = FlightPlanGeneratorAgent(model="claude-sonnet-4-5-20250929")
        assert agent.model == "claude-sonnet-4-5-20250929"

    def test_system_prompt_mentions_prd(self) -> None:
        """System prompt mentions PRD conversion."""
        assert "PRD" in FLIGHT_PLAN_GENERATOR_SYSTEM_PROMPT
        assert "flight plan" in FLIGHT_PLAN_GENERATOR_SYSTEM_PROMPT.lower()

    def test_system_prompt_mentions_read_only(self) -> None:
        """System prompt states the agent is read-only."""
        assert "read-only" in FLIGHT_PLAN_GENERATOR_SYSTEM_PROMPT.lower()


class TestDecomposerAgentInit:
    """Tests for DecomposerAgent instantiation and configuration."""

    def test_default_instantiation(self) -> None:
        """Agent can be instantiated with no arguments."""
        from maverick.agents.decomposer import DecomposerAgent

        agent = DecomposerAgent()
        assert agent.name == "decomposer"

    def test_allowed_tools_include_planner_plus_write(self) -> None:
        """Agent's allowed_tools include PLANNER_TOOLS + Write."""
        from maverick.agents.decomposer import DecomposerAgent

        agent = DecomposerAgent()
        assert set(agent.allowed_tools) == set(PLANNER_TOOLS) | {"Write"}

    def test_tools_are_valid_builtins(self) -> None:
        """All agent tools are valid builtins."""
        from maverick.agents.decomposer import DecomposerAgent

        agent = DecomposerAgent()
        assert set(agent.allowed_tools).issubset(BUILTIN_TOOLS)

    def test_output_model_is_decomposition_output(self) -> None:
        """Agent sets output_model for SDK structured output."""
        from maverick.agents.decomposer import DecomposerAgent
        from maverick.workflows.refuel_maverick.models import (
            DecompositionOutput,
        )

        agent = DecomposerAgent()
        assert agent._output_model is DecompositionOutput
        assert agent._output_format is not None
        assert agent._output_format["type"] == "json_schema"
