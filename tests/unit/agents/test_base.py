"""Unit tests for MaverickAgent base class."""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.agents.base import BUILTIN_TOOLS, DEFAULT_MODEL, MaverickAgent
from maverick.agents.context import AgentContext
from maverick.agents.result import AgentResult, AgentUsage
from maverick.exceptions import (
    InvalidToolError,
)

# =============================================================================
# Test Agent Implementation
# =============================================================================


class ConcreteTestAgent(MaverickAgent):
    """Concrete test agent for testing MaverickAgent functionality."""

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute method implementation for testing.

        Args:
            context: Agent execution context.

        Returns:
            AgentResult with test output.
        """
        return AgentResult.success_result(
            output="test output",
            usage=AgentUsage(
                input_tokens=100,
                output_tokens=200,
                total_cost_usd=0.003,
                duration_ms=1500,
            ),
        )

    def build_prompt(self, context: AgentContext) -> str:
        """Build prompt for testing.

        Args:
            context: Agent execution context.

        Returns:
            Test prompt string.
        """
        return "test prompt"


# =============================================================================
# MaverickAgent Initialization Tests
# =============================================================================


class TestMaverickAgentInitialization:
    """Tests for MaverickAgent initialization."""

    def test_initialization_with_required_parameters(self) -> None:
        """Test agent creation with only required parameters."""
        agent = ConcreteTestAgent(
            name="test-agent",
            instructions="You are a test agent.",
            allowed_tools=["Read", "Write"],
        )

        assert agent.name == "test-agent"
        assert agent.instructions == "You are a test agent."
        assert agent.allowed_tools == ["Read", "Write"]
        assert agent.model == DEFAULT_MODEL
        assert agent.mcp_servers == {}

    def test_name_property(self) -> None:
        """Test name property returns correct value."""
        agent = ConcreteTestAgent(
            name="my-agent",
            instructions="Test prompt",
            allowed_tools=[],
        )

        assert agent.name == "my-agent"

    def test_instructions_property(self) -> None:
        """Test instructions property returns correct value."""
        prompt = "You are a specialized test agent."
        agent = ConcreteTestAgent(
            name="test-agent",
            instructions=prompt,
            allowed_tools=[],
        )

        assert agent.instructions == prompt

    def test_instructions_property_is_read_only(self) -> None:
        """Test instructions property cannot be set (contract invariant #3)."""
        agent = ConcreteTestAgent(
            name="test-agent",
            instructions="Original instructions",
            allowed_tools=[],
        )

        with pytest.raises(AttributeError):
            agent.instructions = "New instructions"  # type: ignore[misc]

    def test_allowed_tools_property_returns_copy(self) -> None:
        """Test allowed_tools property returns a copy, not reference."""
        original_tools = ["Read", "Write"]
        agent = ConcreteTestAgent(
            name="test-agent",
            instructions="Test prompt",
            allowed_tools=original_tools,
        )

        # Get the tools
        tools = agent.allowed_tools

        # Modify the returned list
        tools.append("Edit")

        # Original agent's tools should be unchanged
        assert agent.allowed_tools == ["Read", "Write"]
        assert "Edit" not in agent.allowed_tools

    def test_model_defaults_to_default_model(self) -> None:
        """Test model defaults to DEFAULT_MODEL when not specified."""
        agent = ConcreteTestAgent(
            name="test-agent",
            instructions="Test prompt",
            allowed_tools=[],
        )

        assert agent.model == DEFAULT_MODEL
        assert agent.model == "claude-sonnet-4-5-20250929"

    def test_model_can_be_overridden(self) -> None:
        """Test model can be overridden with custom value."""
        custom_model = "claude-opus-4-5-20251101"
        agent = ConcreteTestAgent(
            name="test-agent",
            instructions="Test prompt",
            allowed_tools=[],
            model=custom_model,
        )

        assert agent.model == custom_model

    def test_mcp_servers_defaults_to_empty_dict(self) -> None:
        """Test mcp_servers defaults to empty dict when not specified."""
        agent = ConcreteTestAgent(
            name="test-agent",
            instructions="Test prompt",
            allowed_tools=[],
        )

        assert agent.mcp_servers == {}

    def test_mcp_servers_returns_copy(self) -> None:
        """Test mcp_servers property returns a copy, not reference."""
        servers = {"github": {"url": "http://example.com"}}
        agent = ConcreteTestAgent(
            name="test-agent",
            instructions="Test prompt",
            allowed_tools=[],
            mcp_servers=servers,
        )

        # Get the servers
        retrieved = agent.mcp_servers

        # Modify the returned dict
        retrieved["newserver"] = {"url": "http://new.com"}

        # Original agent's servers should be unchanged
        assert agent.mcp_servers == {"github": {"url": "http://example.com"}}
        assert "newserver" not in agent.mcp_servers


# =============================================================================
# _validate_tools Tests
# =============================================================================


class TestValidateTools:
    """Tests for _validate_tools method."""

    def test_validates_builtin_tools_successfully(self) -> None:
        """Test validates all builtin tools without error."""
        # Should not raise
        agent = ConcreteTestAgent(
            name="test-agent",
            instructions="Test prompt",
            allowed_tools=list(BUILTIN_TOOLS),
        )

        assert len(agent.allowed_tools) == len(BUILTIN_TOOLS)

    def test_validates_individual_builtin_tools(self) -> None:
        """Test validates individual builtin tools."""
        for tool in BUILTIN_TOOLS:
            # Should not raise
            agent = ConcreteTestAgent(
                name="test-agent",
                instructions="Test prompt",
                allowed_tools=[tool],
            )
            assert tool in agent.allowed_tools

    def test_validates_mcp_tool_patterns(self) -> None:
        """Test validates MCP tool patterns (mcp__server__tool)."""
        # Should not raise when server is configured
        agent = ConcreteTestAgent(
            name="test-agent",
            instructions="Test prompt",
            allowed_tools=["mcp__github__create_pr"],
            mcp_servers={"github": {"url": "http://example.com"}},
        )

        assert "mcp__github__create_pr" in agent.allowed_tools

    def test_raises_invalid_tool_error_for_unknown_tool(self) -> None:
        """Test raises InvalidToolError for unknown tools."""
        with pytest.raises(InvalidToolError) as exc_info:
            ConcreteTestAgent(
                name="test-agent",
                instructions="Test prompt",
                allowed_tools=["UnknownTool123"],
            )

        assert exc_info.value.tool_name == "UnknownTool123"

    def test_raises_invalid_tool_error_for_mcp_tool_without_server(self) -> None:
        """Test raises InvalidToolError for MCP tool when server is not configured."""
        with pytest.raises(InvalidToolError) as exc_info:
            ConcreteTestAgent(
                name="test-agent",
                instructions="Test prompt",
                allowed_tools=["mcp__github__create_pr"],
                mcp_servers={},  # No MCP servers configured
            )

        assert "github" in exc_info.value.tool_name or "mcp__github__create_pr" in str(
            exc_info.value
        )

    def test_validates_empty_tools_list(self) -> None:
        """Test validates empty allowed_tools list."""
        # Should not raise
        agent = ConcreteTestAgent(
            name="test-agent",
            instructions="Test prompt",
            allowed_tools=[],
        )

        assert agent.allowed_tools == []

    def test_mixed_builtin_and_mcp_tools(self) -> None:
        """Test validates mix of builtin and MCP tools."""
        # Should not raise when MCP servers are configured
        agent = ConcreteTestAgent(
            name="test-agent",
            instructions="Test prompt",
            allowed_tools=["Read", "Write", "mcp__github__create_pr"],
            mcp_servers={"github": {"url": "http://example.com"}},
        )

        assert "Read" in agent.allowed_tools
        assert "Write" in agent.allowed_tools
        assert "mcp__github__create_pr" in agent.allowed_tools


# =============================================================================
# Execute Method Tests
# =============================================================================
# NOTE: TestBuildOptions, TestExtractUsage, TestQuery, TestExtractStructuredOutput,
# and TestWrapSDKError were removed because they tested SDK-coupled methods
# (_build_options, _extract_usage, query, _extract_structured_output, _wrap_sdk_error)
# that were intentionally removed as part of the ACP migration (T044).
# =============================================================================


class TestExecuteMethod:
    """Tests for execute method (abstract method implementation)."""

    @pytest.mark.asyncio
    async def test_concrete_agent_can_execute(self) -> None:
        """Test concrete agent implementation can execute successfully."""
        agent = ConcreteTestAgent(
            name="test-agent",
            instructions="Test prompt",
            allowed_tools=[],
        )

        # Create a mock context
        from maverick.config import MaverickConfig

        context = AgentContext(
            cwd=Path("/workspace"),
            branch="main",
            config=MaverickConfig(),
        )

        result = await agent.execute(context)

        assert isinstance(result, AgentResult)
        assert result.success is True
        assert result.output == "test output"
        assert isinstance(result.usage, AgentUsage)
        assert result.usage.input_tokens == 100
        assert result.usage.output_tokens == 200


# =============================================================================
# output_model Parameter Wiring Tests
# =============================================================================


class TestOutputModelWiring:
    """Tests for output_model parameter and _output_format construction."""

    def test_output_format_is_none_when_output_model_is_none(self) -> None:
        """Test _output_format is None when output_model is not provided."""
        agent = ConcreteTestAgent(
            name="test-agent",
            instructions="Test prompt",
            allowed_tools=[],
            output_model=None,
        )

        assert agent._output_format is None

    def test_output_format_is_none_by_default(self) -> None:
        """Test _output_format is None when output_model is omitted entirely."""
        agent = ConcreteTestAgent(
            name="test-agent",
            instructions="Test prompt",
            allowed_tools=[],
        )

        assert agent._output_format is None

    def test_output_format_has_correct_structure_with_model(self) -> None:
        """_output_format has json_schema type when output_model is set."""
        from pydantic import BaseModel

        class SomeModel(BaseModel):
            status: str
            score: int

        agent = ConcreteTestAgent(
            name="test-agent",
            instructions="Test prompt",
            allowed_tools=[],
            output_model=SomeModel,
        )

        assert agent._output_format is not None
        assert agent._output_format["type"] == "json_schema"
        assert agent._output_format["schema"] == SomeModel.model_json_schema()

        # Verify the schema contains expected keys from the model
        schema = agent._output_format["schema"]
        assert "properties" in schema
        assert "status" in schema["properties"]
        assert "score" in schema["properties"]

    def test_output_model_stored_on_agent(self) -> None:
        """Test output_model is stored as _output_model on the agent instance."""
        from pydantic import BaseModel

        class MyModel(BaseModel):
            value: str

        agent = ConcreteTestAgent(
            name="test-agent",
            instructions="Test prompt",
            allowed_tools=[],
            output_model=MyModel,
        )

        assert agent._output_model is MyModel
