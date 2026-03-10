"""Unit tests for agent tool permission validation.

Tests that each concrete agent uses the correct tool permissions as specified
in their requirements and that unauthorized tools are properly rejected.
"""

from __future__ import annotations

import pytest

from maverick.agents.implementer import ImplementerAgent
from maverick.agents.reviewers import (
    CompletenessReviewerAgent,
    CorrectnessReviewerAgent,
    SimpleFixerAgent,
)
from maverick.agents.tools import (
    IMPLEMENTER_TOOLS,
    REVIEWER_TOOLS,
)
from maverick.exceptions import InvalidToolError

# =============================================================================
# Agent Tool Permission Tests
# =============================================================================


class TestImplementerAgentToolPermissions:
    """Tests for ImplementerAgent tool permissions."""

    def test_implementer_agent_uses_implementer_tools(self) -> None:
        """Test ImplementerAgent initializes with IMPLEMENTER_TOOLS."""
        agent = ImplementerAgent()

        assert set(agent.allowed_tools) == IMPLEMENTER_TOOLS

    def test_implementer_agent_has_expected_tools(self) -> None:
        """Test ImplementerAgent has Read, Write, Edit, Glob, Grep, Task, Bash."""
        agent = ImplementerAgent()

        expected_tools = {"Read", "Write", "Edit", "Glob", "Grep", "Task", "Bash"}
        assert set(agent.allowed_tools) == expected_tools

    def test_implementer_agent_has_read_capability(self) -> None:
        """Test ImplementerAgent has Read tool."""
        agent = ImplementerAgent()

        assert "Read" in agent.allowed_tools

    def test_implementer_agent_has_write_capabilities(self) -> None:
        """Test ImplementerAgent has Write and Edit tools."""
        agent = ImplementerAgent()

        assert "Write" in agent.allowed_tools
        assert "Edit" in agent.allowed_tools

    def test_implementer_agent_has_search_capabilities(self) -> None:
        """Test ImplementerAgent has Glob and Grep tools."""
        agent = ImplementerAgent()

        assert "Glob" in agent.allowed_tools
        assert "Grep" in agent.allowed_tools

    def test_implementer_agent_has_bash(self) -> None:
        """Test ImplementerAgent has Bash tool for running commands."""
        agent = ImplementerAgent()
        assert "Bash" in agent.allowed_tools

    def test_implementer_agent_tools_match_constant(self) -> None:
        """Test ImplementerAgent tools match IMPLEMENTER_TOOLS exactly."""
        agent = ImplementerAgent()
        assert set(agent.allowed_tools) == IMPLEMENTER_TOOLS

    def test_implementer_agent_with_validation_commands(self) -> None:
        """Test validation commands are injected into the system prompt."""
        commands = {"test_cmd": ["pytest", "-x"], "lint_cmd": ["ruff", "check", "."]}
        agent = ImplementerAgent(validation_commands=commands)
        assert "pytest -x" in agent.instructions
        assert "ruff check ." in agent.instructions


class TestCompletenessReviewerToolPermissions:
    """Tests for CompletenessReviewerAgent tool permissions."""

    def test_completeness_reviewer_uses_reviewer_tools(self) -> None:
        """Test CompletenessReviewerAgent initializes with REVIEWER_TOOLS."""
        agent = CompletenessReviewerAgent()

        assert set(agent.allowed_tools) == REVIEWER_TOOLS

    def test_completeness_reviewer_has_read_glob_grep(self) -> None:
        """Test CompletenessReviewerAgent has exactly Read, Glob, Grep."""
        agent = CompletenessReviewerAgent()

        expected_tools = {"Read", "Glob", "Grep"}
        assert set(agent.allowed_tools) == expected_tools

    def test_completeness_reviewer_is_read_only(self) -> None:
        """Test CompletenessReviewerAgent has no write tools."""
        agent = CompletenessReviewerAgent()

        write_tools = {"Write", "Edit", "NotebookEdit"}
        assert not set(agent.allowed_tools).intersection(write_tools)

    def test_completeness_reviewer_has_no_bash(self) -> None:
        """Test CompletenessReviewerAgent does not have Bash tool."""
        agent = CompletenessReviewerAgent()

        assert "Bash" not in agent.allowed_tools


class TestCorrectnessReviewerToolPermissions:
    """Tests for CorrectnessReviewerAgent tool permissions."""

    def test_correctness_reviewer_uses_reviewer_tools(self) -> None:
        """Test CorrectnessReviewerAgent initializes with REVIEWER_TOOLS."""
        agent = CorrectnessReviewerAgent()

        assert set(agent.allowed_tools) == REVIEWER_TOOLS

    def test_correctness_reviewer_is_read_only(self) -> None:
        """Test CorrectnessReviewerAgent has no write tools."""
        agent = CorrectnessReviewerAgent()

        write_tools = {"Write", "Edit", "NotebookEdit"}
        assert not set(agent.allowed_tools).intersection(write_tools)

    def test_correctness_reviewer_has_no_bash(self) -> None:
        """Test CorrectnessReviewerAgent does not have Bash tool."""
        agent = CorrectnessReviewerAgent()

        assert "Bash" not in agent.allowed_tools


# =============================================================================
# Tool Permission Violation Tests
# =============================================================================


class TestUnauthorizedToolRejection:
    """Tests that unauthorized tools are properly rejected."""

    def test_cannot_create_agent_with_unknown_tool(self) -> None:
        """Test that creating an agent with an unknown tool raises InvalidToolError."""
        from maverick.agents.base import MaverickAgent

        class TestAgentWithUnknownTool(MaverickAgent):
            """Test agent with unauthorized tool."""

            def __init__(self) -> None:
                super().__init__(
                    name="test-agent",
                    instructions="Test",
                    allowed_tools=["Read", "UnknownTool"],
                )

            async def execute(self, context):
                """Execute method (required by ABC)."""
                pass

            def build_prompt(self, context) -> str:
                """Build prompt (required by ABC)."""
                return ""

        with pytest.raises(InvalidToolError) as exc_info:
            TestAgentWithUnknownTool()

        error = exc_info.value
        assert error.tool_name == "UnknownTool"
        assert isinstance(error.available_tools, list)

    def test_cannot_add_tool_not_in_builtin_tools(self) -> None:
        """Test that adding a tool not in BUILTIN_TOOLS raises InvalidToolError."""
        from maverick.agents.base import MaverickAgent

        class TestAgentWithCustomTool(MaverickAgent):
            """Test agent with custom tool."""

            def __init__(self) -> None:
                super().__init__(
                    name="test-agent",
                    instructions="Test",
                    allowed_tools=["Read", "CustomTool"],
                )

            async def execute(self, context):
                """Execute method (required by ABC)."""
                pass

            def build_prompt(self, context) -> str:
                """Build prompt (required by ABC)."""
                return ""

        with pytest.raises(InvalidToolError) as exc_info:
            TestAgentWithCustomTool()

        error = exc_info.value
        assert error.tool_name == "CustomTool"

    def test_mcp_tools_require_configured_server(self) -> None:
        """Test that MCP tools require their server to be configured."""
        from maverick.agents.base import MaverickAgent

        class TestAgentWithMCPTool(MaverickAgent):
            """Test agent with MCP tool but no server."""

            def __init__(self) -> None:
                super().__init__(
                    name="test-agent",
                    instructions="Test",
                    allowed_tools=["Read", "mcp__github__create_pr"],
                    mcp_servers={},
                )

            async def execute(self, context):
                """Execute method (required by ABC)."""
                pass

            def build_prompt(self, context) -> str:
                """Build prompt (required by ABC)."""
                return ""

        with pytest.raises(InvalidToolError) as exc_info:
            TestAgentWithMCPTool()

        error = exc_info.value
        assert error.tool_name == "mcp__github__create_pr"


# =============================================================================
# Cross-Agent Tool Comparison Tests
# =============================================================================


class TestAgentToolComparison:
    """Tests comparing tool permissions across agents."""

    def test_reviewer_tools_are_subset_of_implementer(self) -> None:
        """Test reviewer tools are a subset of implementer tools."""
        implementer = ImplementerAgent()
        reviewer = CompletenessReviewerAgent()

        assert set(reviewer.allowed_tools).issubset(set(implementer.allowed_tools))

    def test_all_agents_have_read_capability(self) -> None:
        """Test that all agents have Read capability."""
        completeness = CompletenessReviewerAgent()
        correctness = CorrectnessReviewerAgent()
        implementer = ImplementerAgent()

        assert "Read" in completeness.allowed_tools
        assert "Read" in correctness.allowed_tools
        assert "Read" in implementer.allowed_tools

    def test_only_implementer_has_bash_tool(self) -> None:
        """Test that only the implementer agent has Bash tool access."""
        completeness = CompletenessReviewerAgent()
        correctness = CorrectnessReviewerAgent()
        implementer = ImplementerAgent()
        fixer = SimpleFixerAgent()

        assert "Bash" not in completeness.allowed_tools
        assert "Bash" not in correctness.allowed_tools
        assert "Bash" in implementer.allowed_tools
        assert "Bash" not in fixer.allowed_tools


# =============================================================================
# Tool Permission Immutability Tests
# =============================================================================


class TestAgentToolImmutability:
    """Tests that agent tool permissions cannot be modified after initialization."""

    def test_implementer_allowed_tools_returns_copy(self) -> None:
        """Test that ImplementerAgent.allowed_tools returns a copy."""
        agent = ImplementerAgent()

        tools = agent.allowed_tools
        tools.append("UnknownTool")

        assert "UnknownTool" not in agent.allowed_tools

    def test_reviewer_allowed_tools_returns_copy(self) -> None:
        """Test that CompletenessReviewerAgent.allowed_tools returns a copy."""
        agent = CompletenessReviewerAgent()

        tools = agent.allowed_tools
        tools.append("Write")

        assert "Write" not in agent.allowed_tools
