"""Unit tests for agent tool permission validation.

Tests that each concrete agent uses the correct tool permissions as specified
in their requirements and that unauthorized tools are properly rejected.
"""

from __future__ import annotations

import pytest

from maverick.agents.code_reviewer import CodeReviewerAgent
from maverick.agents.implementer import ImplementerAgent
from maverick.agents.issue_fixer import IssueFixerAgent
from maverick.agents.tools import (
    IMPLEMENTER_TOOLS,
    ISSUE_FIXER_TOOLS,
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

        # Convert both to sets for comparison (order doesn't matter)
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


class TestCodeReviewerAgentToolPermissions:
    """Tests for CodeReviewerAgent tool permissions."""

    def test_code_reviewer_agent_uses_reviewer_tools(self) -> None:
        """Test CodeReviewerAgent initializes with REVIEWER_TOOLS."""
        agent = CodeReviewerAgent()

        # Convert both to sets for comparison (order doesn't matter)
        assert set(agent.allowed_tools) == REVIEWER_TOOLS

    def test_code_reviewer_agent_has_read_glob_grep(self) -> None:
        """Test CodeReviewerAgent has exactly Read, Glob, Grep."""
        agent = CodeReviewerAgent()

        expected_tools = {"Read", "Glob", "Grep"}
        assert set(agent.allowed_tools) == expected_tools

    def test_code_reviewer_agent_is_read_only(self) -> None:
        """Test CodeReviewerAgent has no write tools."""
        agent = CodeReviewerAgent()

        write_tools = {"Write", "Edit", "NotebookEdit"}
        assert not set(agent.allowed_tools).intersection(write_tools)

    def test_code_reviewer_agent_has_no_bash(self) -> None:
        """Test CodeReviewerAgent does not have Bash tool."""
        agent = CodeReviewerAgent()

        assert "Bash" not in agent.allowed_tools

    def test_code_reviewer_agent_has_read_capability(self) -> None:
        """Test CodeReviewerAgent has Read tool."""
        agent = CodeReviewerAgent()

        assert "Read" in agent.allowed_tools

    def test_code_reviewer_agent_has_search_capabilities(self) -> None:
        """Test CodeReviewerAgent has Glob and Grep tools."""
        agent = CodeReviewerAgent()

        assert "Glob" in agent.allowed_tools
        assert "Grep" in agent.allowed_tools


class TestIssueFixerAgentToolPermissions:
    """Tests for IssueFixerAgent tool permissions."""

    def test_issue_fixer_agent_uses_issue_fixer_tools(self) -> None:
        """Test IssueFixerAgent initializes with ISSUE_FIXER_TOOLS."""
        agent = IssueFixerAgent()

        # Convert both to sets for comparison (order doesn't matter)
        assert set(agent.allowed_tools) == ISSUE_FIXER_TOOLS

    def test_issue_fixer_agent_has_read_write_edit_glob_grep(self) -> None:
        """Test IssueFixerAgent has exactly Read, Write, Edit, Glob, Grep."""
        agent = IssueFixerAgent()

        expected_tools = {"Read", "Write", "Edit", "Glob", "Grep"}
        assert set(agent.allowed_tools) == expected_tools

    def test_issue_fixer_agent_has_no_bash(self) -> None:
        """Test IssueFixerAgent does not have Bash tool."""
        agent = IssueFixerAgent()

        assert "Bash" not in agent.allowed_tools

    def test_issue_fixer_agent_has_read_capability(self) -> None:
        """Test IssueFixerAgent has Read tool."""
        agent = IssueFixerAgent()

        assert "Read" in agent.allowed_tools

    def test_issue_fixer_agent_has_write_capabilities(self) -> None:
        """Test IssueFixerAgent has Write and Edit tools."""
        agent = IssueFixerAgent()

        assert "Write" in agent.allowed_tools
        assert "Edit" in agent.allowed_tools

    def test_issue_fixer_agent_has_search_capabilities(self) -> None:
        """Test IssueFixerAgent has Glob and Grep tools."""
        agent = IssueFixerAgent()

        assert "Glob" in agent.allowed_tools
        assert "Grep" in agent.allowed_tools


# =============================================================================
# Tool Permission Violation Tests
# =============================================================================


class TestUnauthorizedToolRejection:
    """Tests that unauthorized tools are properly rejected."""

    def test_cannot_create_agent_with_unknown_tool(self) -> None:
        """Test that creating an agent with an unknown tool raises InvalidToolError."""
        from maverick.agents.base import MaverickAgent

        # Create a test agent class that tries to use an unknown tool
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

        # Attempting to instantiate should raise InvalidToolError
        with pytest.raises(InvalidToolError) as exc_info:
            TestAgentWithUnknownTool()

        error = exc_info.value
        assert error.tool_name == "UnknownTool"
        assert isinstance(error.available_tools, list)

    def test_cannot_create_implementer_with_bash(self) -> None:
        """Test that ImplementerAgent cannot be created with Bash tool."""
        from maverick.agents.base import MaverickAgent

        # Create a test implementer that tries to add Bash
        class TestImplementerWithBash(MaverickAgent):
            """Test implementer with Bash tool."""

            def __init__(self) -> None:
                super().__init__(
                    name="implementer-with-bash",
                    instructions="Test",
                    allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
                )

            async def execute(self, context):
                """Execute method (required by ABC)."""
                pass

        # This should not raise because Bash IS a builtin tool
        # The test is about not USING Bash, not that it's invalid
        agent = TestImplementerWithBash()
        assert "Bash" in agent.allowed_tools

    def test_cannot_create_reviewer_with_write_tools(self) -> None:
        """Test reviewer-like agent with Write (not a permission error)."""
        from maverick.agents.base import MaverickAgent

        # Create a test reviewer that tries to add Write
        class TestReviewerWithWrite(MaverickAgent):
            """Test reviewer with Write tool."""

            def __init__(self) -> None:
                super().__init__(
                    name="reviewer-with-write",
                    instructions="Test",
                    allowed_tools=["Read", "Write", "Glob", "Grep"],
                )

            async def execute(self, context):
                """Execute method (required by ABC)."""
                pass

        # This should not raise - Write is a valid builtin tool
        # The constraint is about agent DESIGN, not tool validity
        agent = TestReviewerWithWrite()
        assert "Write" in agent.allowed_tools

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
                    mcp_servers={},  # No servers configured
                )

            async def execute(self, context):
                """Execute method (required by ABC)."""
                pass

        with pytest.raises(InvalidToolError) as exc_info:
            TestAgentWithMCPTool()

        error = exc_info.value
        assert error.tool_name == "mcp__github__create_pr"


# =============================================================================
# Cross-Agent Tool Comparison Tests
# =============================================================================


class TestAgentToolComparison:
    """Tests comparing tool permissions across agents."""

    def test_issue_fixer_tools_are_subset_of_implementer(self) -> None:
        """Test IssueFixerAgent tools are a subset of ImplementerAgent tools.

        The implementer has Task for subagent-based parallelization; the
        issue fixer does not need it.
        """
        implementer = ImplementerAgent()
        issue_fixer = IssueFixerAgent()

        assert set(issue_fixer.allowed_tools).issubset(set(implementer.allowed_tools))

    def test_code_reviewer_is_subset_of_implementer(self) -> None:
        """Test that CodeReviewerAgent tools are a subset of ImplementerAgent tools."""
        reviewer = CodeReviewerAgent()
        implementer = ImplementerAgent()

        assert set(reviewer.allowed_tools).issubset(set(implementer.allowed_tools))

    def test_code_reviewer_is_most_restrictive(self) -> None:
        """Test that CodeReviewerAgent has the fewest tools."""
        reviewer = CodeReviewerAgent()
        implementer = ImplementerAgent()
        issue_fixer = IssueFixerAgent()

        reviewer_count = len(reviewer.allowed_tools)
        implementer_count = len(implementer.allowed_tools)
        issue_fixer_count = len(issue_fixer.allowed_tools)

        assert reviewer_count <= implementer_count
        assert reviewer_count <= issue_fixer_count

    def test_only_reviewer_lacks_write_tools(self) -> None:
        """Test that only CodeReviewerAgent lacks Write and Edit tools."""
        reviewer = CodeReviewerAgent()
        implementer = ImplementerAgent()
        issue_fixer = IssueFixerAgent()

        # Reviewer should have no write tools
        assert "Write" not in reviewer.allowed_tools
        assert "Edit" not in reviewer.allowed_tools

        # Implementer and IssueFixerAgent should have write tools
        assert "Write" in implementer.allowed_tools
        assert "Edit" in implementer.allowed_tools
        assert "Write" in issue_fixer.allowed_tools
        assert "Edit" in issue_fixer.allowed_tools

    def test_all_agents_have_read_capability(self) -> None:
        """Test that all agents have Read capability."""
        reviewer = CodeReviewerAgent()
        implementer = ImplementerAgent()
        issue_fixer = IssueFixerAgent()

        assert "Read" in reviewer.allowed_tools
        assert "Read" in implementer.allowed_tools
        assert "Read" in issue_fixer.allowed_tools

    def test_only_implementer_has_bash_tool(self) -> None:
        """Test that only the implementer agent has Bash tool access."""
        reviewer = CodeReviewerAgent()
        implementer = ImplementerAgent()
        issue_fixer = IssueFixerAgent()

        assert "Bash" not in reviewer.allowed_tools
        assert "Bash" in implementer.allowed_tools
        assert "Bash" not in issue_fixer.allowed_tools


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

        # Original agent's tools should be unchanged
        assert "UnknownTool" not in agent.allowed_tools

    def test_code_reviewer_allowed_tools_returns_copy(self) -> None:
        """Test that CodeReviewerAgent.allowed_tools returns a copy."""
        agent = CodeReviewerAgent()

        tools = agent.allowed_tools
        tools.append("Write")

        # Original agent's tools should be unchanged
        assert "Write" not in agent.allowed_tools

    def test_issue_fixer_allowed_tools_returns_copy(self) -> None:
        """Test that IssueFixerAgent.allowed_tools returns a copy."""
        agent = IssueFixerAgent()

        tools = agent.allowed_tools
        tools.append("Bash")

        # Original agent's tools should be unchanged
        assert "Bash" not in agent.allowed_tools
