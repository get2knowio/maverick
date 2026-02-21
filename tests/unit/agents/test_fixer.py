"""Unit tests for FixerAgent.

Tests the fixer agent's functionality including:
- Initialization and configuration (T031)
- System prompt verification (T032)
- Execute method signature and behavior (T033)
- Targeted fix application
- Error handling
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from maverick.agents.context import AgentContext
from maverick.agents.fixer import (
    FIXER_SYSTEM_PROMPT,
    FixerAgent,
)
from maverick.agents.result import AgentResult, AgentUsage
from maverick.agents.tools import FIXER_TOOLS
from maverick.config import MaverickConfig
from maverick.exceptions import AgentError

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def agent() -> FixerAgent:
    """Create a FixerAgent instance for testing."""
    return FixerAgent()


@pytest.fixture
def fix_context(tmp_path: Path) -> AgentContext:
    """Create a basic AgentContext for testing fix operations."""
    return AgentContext(
        cwd=tmp_path,
        branch="feature/fix",
        config=MaverickConfig(),
        extra={
            "prompt": """Fix the following validation error:

File: src/maverick/agents/implementer.py
Line: 42
Error: Ruff E501: Line too long (120 > 88)

Please fix this error by reformatting the line appropriately."""
        },
    )


@pytest.fixture
def sample_agent_output() -> str:
    """Sample plain-text output from a fixer agent run."""
    return (
        "I've reformatted line 42 in "
        "src/maverick/agents/implementer.py "
        "to comply with the line length limit."
    )


# =============================================================================
# T031: Initialization Tests - allowed_tools
# =============================================================================


class TestFixerAgentInitialization:
    """Tests for FixerAgent initialization (T031)."""

    def test_default_initialization(self, agent: FixerAgent) -> None:
        """Test agent initializes with correct defaults."""
        assert agent.name == "fixer"
        assert agent.instructions == FIXER_SYSTEM_PROMPT
        assert agent.allowed_tools == list(FIXER_TOOLS)

    def test_allowed_tools_matches_contract(self, agent: FixerAgent) -> None:
        """Test allowed tools matches contract exactly (T031).

        Contract: FixerAgent must have exactly Read, Write, Edit (minimal set).
        """
        expected_tools = {"Read", "Write", "Edit"}
        actual_tools = set(agent.allowed_tools)
        assert actual_tools == expected_tools, (
            f"FixerAgent tools mismatch. "
            f"Expected: {expected_tools}, Got: {actual_tools}"
        )

    def test_allowed_tools_is_minimal_set(self, agent: FixerAgent) -> None:
        """Test allowed tools is the smallest viable set (T031)."""
        # Fixer should have the smallest tool set of all agents
        assert len(agent.allowed_tools) == 3
        assert "Read" in agent.allowed_tools
        assert "Write" in agent.allowed_tools
        assert "Edit" in agent.allowed_tools

    def test_allowed_tools_no_search_capabilities(self, agent: FixerAgent) -> None:
        """Test fixer has no search tools (receives explicit paths) (T031)."""
        assert "Glob" not in agent.allowed_tools
        assert "Grep" not in agent.allowed_tools

    def test_allowed_tools_no_bash(self, agent: FixerAgent) -> None:
        """Test fixer cannot execute commands (T031)."""
        assert "Bash" not in agent.allowed_tools

    def test_custom_model(self) -> None:
        """Test agent accepts custom model parameter."""
        custom_agent = FixerAgent(model="claude-3-opus-20240229")
        assert custom_agent.model == "claude-3-opus-20240229"

    def test_mcp_servers_passthrough(self) -> None:
        """Test MCP servers are passed through to base class."""
        mcp_config = {"server1": {"command": "test"}}
        agent = FixerAgent(mcp_servers=mcp_config)
        assert agent.mcp_servers == mcp_config


# =============================================================================
# T032: System Prompt Tests
# =============================================================================


class TestFixerInstructions:
    """Tests for FixerAgent instructions (T032)."""

    def test_instructions_is_defined(self) -> None:
        """Test FIXER_SYSTEM_PROMPT is defined and non-empty (T032)."""
        assert FIXER_SYSTEM_PROMPT
        assert len(FIXER_SYSTEM_PROMPT) > 100

    def test_instructions_emphasizes_targeted_fixes(self, agent: FixerAgent) -> None:
        """Test instructions emphasizes targeted, minimal changes (T032)."""
        prompt = agent.instructions
        assert "targeted" in prompt.lower() or "minimal" in prompt.lower()
        assert "fix" in prompt.lower()

    def test_instructions_lists_available_tools(self, agent: FixerAgent) -> None:
        """Test instructions lists the three available tools (T032)."""
        prompt = agent.instructions
        assert "Read" in prompt
        assert "Write" in prompt
        assert "Edit" in prompt

    def test_instructions_specifies_constraints(self, agent: FixerAgent) -> None:
        """Test instructions specifies agent constraints (T032)."""
        prompt = agent.instructions
        # Should not search for files
        assert "explicit" in prompt.lower() or "receive" in prompt.lower()
        # Should make minimal changes
        assert "minimal" in prompt.lower() or "necessary" in prompt.lower()

    def test_instructions_does_not_request_json_output(
        self, agent: FixerAgent
    ) -> None:
        """Test instructions does not ask for JSON output (T032).

        The fixer applies fixes via tools; success is determined by
        re-running validation, not by the agent's self-report.
        """
        prompt = agent.instructions
        assert "json" not in prompt.lower()


# =============================================================================
# T033: Execute Method Tests
# =============================================================================


class TestExecuteMethod:
    """Tests for the execute method (T033)."""

    @pytest.mark.asyncio
    async def test_execute_returns_agent_result(
        self,
        agent: FixerAgent,
        fix_context: AgentContext,
        sample_agent_output: str,
    ) -> None:
        """Test execute returns AgentResult on success (T033)."""
        # Mock the Claude query
        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_text_block = MagicMock()
        mock_text_block.text = sample_agent_output
        type(mock_text_block).__name__ = "TextBlock"
        mock_message.content = [mock_text_block]
        type(mock_message).__name__ = "AssistantMessage"

        # Mock ResultMessage for usage tracking
        mock_result_msg = MagicMock()
        type(mock_result_msg).__name__ = "ResultMessage"
        mock_result_msg.usage = {"input_tokens": 100, "output_tokens": 50}
        mock_result_msg.total_cost_usd = 0.01
        mock_result_msg.duration_ms = 1000

        async def async_gen(*args, **kwargs):
            yield mock_message
            yield mock_result_msg

        with patch.object(agent, "query", side_effect=async_gen):
            result = await agent.execute(fix_context)

            assert isinstance(result, AgentResult)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_signature_accepts_agent_context(
        self, agent: FixerAgent, fix_context: AgentContext
    ) -> None:
        """Test execute method accepts AgentContext parameter (T033)."""
        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_text_block = MagicMock()
        mock_text_block.text = "Fixed the line length issue."
        type(mock_text_block).__name__ = "TextBlock"
        mock_message.content = [mock_text_block]
        type(mock_message).__name__ = "AssistantMessage"

        async def async_gen(*args, **kwargs):
            yield mock_message

        with patch.object(agent, "query", side_effect=async_gen):
            # Should not raise TypeError
            result = await agent.execute(fix_context)
            assert isinstance(result, AgentResult)

    @pytest.mark.asyncio
    async def test_execute_extracts_prompt_from_context(
        self,
        agent: FixerAgent,
        fix_context: AgentContext,
        sample_agent_output: str,
    ) -> None:
        """Test execute extracts prompt from context.extra (T033)."""
        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_text_block = MagicMock()
        mock_text_block.text = sample_agent_output
        type(mock_text_block).__name__ = "TextBlock"
        mock_message.content = [mock_text_block]
        type(mock_message).__name__ = "AssistantMessage"

        async def async_gen(prompt, **kwargs):
            # Verify the prompt was extracted from context
            assert "Line: 42" in prompt
            assert "Ruff E501" in prompt
            yield mock_message

        with patch.object(agent, "query", side_effect=async_gen):
            result = await agent.execute(fix_context)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_returns_raw_output(
        self,
        agent: FixerAgent,
        fix_context: AgentContext,
        sample_agent_output: str,
    ) -> None:
        """Test execute returns the agent's raw text output (T033)."""
        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_text_block = MagicMock()
        mock_text_block.text = sample_agent_output
        type(mock_text_block).__name__ = "TextBlock"
        mock_message.content = [mock_text_block]
        type(mock_message).__name__ = "AssistantMessage"

        async def async_gen(*args, **kwargs):
            yield mock_message

        with patch.object(agent, "query", side_effect=async_gen):
            result = await agent.execute(fix_context)

            assert result.success is True
            assert result.output == sample_agent_output

    @pytest.mark.asyncio
    async def test_execute_succeeds_with_any_text_output(
        self,
        agent: FixerAgent,
        fix_context: AgentContext,
    ) -> None:
        """Test execute succeeds regardless of output format.

        The fixer's job is to apply fixes via tools. Success is determined
        by whether the agent ran without errors, not by its text output.
        """
        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_text_block = MagicMock()
        mock_text_block.text = "I analyzed the issue and made the necessary edits."
        type(mock_text_block).__name__ = "TextBlock"
        mock_message.content = [mock_text_block]
        type(mock_message).__name__ = "AssistantMessage"

        async def async_gen(*args, **kwargs):
            yield mock_message

        with patch.object(agent, "query", side_effect=async_gen):
            result = await agent.execute(fix_context)

            assert result.success is True
            assert result.output is not None

    @pytest.mark.asyncio
    async def test_execute_includes_usage_statistics(
        self,
        agent: FixerAgent,
        fix_context: AgentContext,
        sample_agent_output: str,
    ) -> None:
        """Test execute includes usage statistics (T033)."""
        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_text_block = MagicMock()
        mock_text_block.text = sample_agent_output
        type(mock_text_block).__name__ = "TextBlock"
        mock_message.content = [mock_text_block]
        type(mock_message).__name__ = "AssistantMessage"

        mock_result_msg = MagicMock()
        type(mock_result_msg).__name__ = "ResultMessage"
        mock_result_msg.usage = {"input_tokens": 150, "output_tokens": 75}
        mock_result_msg.total_cost_usd = 0.02
        mock_result_msg.duration_ms = 1500

        async def async_gen(*args, **kwargs):
            yield mock_message
            yield mock_result_msg

        with patch.object(agent, "query", side_effect=async_gen):
            result = await agent.execute(fix_context)

            assert isinstance(result.usage, AgentUsage)
            assert result.usage.input_tokens == 150
            assert result.usage.output_tokens == 75
            assert result.usage.total_cost_usd == 0.02
            assert result.usage.duration_ms == 1500


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in FixerAgent."""

    @pytest.mark.asyncio
    async def test_execute_handles_agent_error(
        self, agent: FixerAgent, fix_context: AgentContext
    ) -> None:
        """Test execute handles AgentError gracefully."""
        with patch.object(agent, "query") as mock_query:
            mock_query.side_effect = AgentError(
                "Claude API error",
                agent_name="fixer",
            )

            result = await agent.execute(fix_context)

            # Should return failed result, not raise
            assert result.success is False
            assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_execute_handles_missing_prompt(
        self, agent: FixerAgent, tmp_path: Path
    ) -> None:
        """Test execute handles missing prompt in context."""
        context = AgentContext(
            cwd=tmp_path,
            branch="test",
            config=MaverickConfig(),
            extra={},  # No prompt
        )

        result = await agent.execute(context)

        # Should return a failure result
        assert result.success is False
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_execute_handles_unexpected_exception(
        self, agent: FixerAgent, fix_context: AgentContext
    ) -> None:
        """Test execute handles unexpected exceptions gracefully."""
        with patch.object(agent, "query") as mock_query:
            mock_query.side_effect = RuntimeError("Unexpected failure")

            result = await agent.execute(fix_context)

            assert result.success is False
            assert len(result.errors) > 0


# =============================================================================
# Integration-Style Tests
# =============================================================================


class TestFixerBehavior:
    """Integration-style tests for FixerAgent behavior."""

    @pytest.mark.asyncio
    async def test_fixer_preserves_working_directory(
        self,
        agent: FixerAgent,
        fix_context: AgentContext,
        sample_agent_output: str,
    ) -> None:
        """Test fixer uses context.cwd for operations."""
        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_text_block = MagicMock()
        mock_text_block.text = sample_agent_output
        type(mock_text_block).__name__ = "TextBlock"
        mock_message.content = [mock_text_block]
        type(mock_message).__name__ = "AssistantMessage"

        async def async_gen(prompt, cwd=None):
            # Verify cwd was passed through
            assert cwd == fix_context.cwd
            yield mock_message

        with patch.object(agent, "query", side_effect=async_gen):
            await agent.execute(fix_context)

    @pytest.mark.asyncio
    async def test_fixer_output_is_raw_text(
        self,
        agent: FixerAgent,
        fix_context: AgentContext,
        sample_agent_output: str,
    ) -> None:
        """Test fixer output is raw agent text, not structured data."""
        mock_message = MagicMock()
        mock_message.role = "assistant"
        mock_text_block = MagicMock()
        mock_text_block.text = sample_agent_output
        type(mock_text_block).__name__ = "TextBlock"
        mock_message.content = [mock_text_block]
        type(mock_message).__name__ = "AssistantMessage"

        async def async_gen(*args, **kwargs):
            yield mock_message

        with patch.object(agent, "query", side_effect=async_gen):
            result = await agent.execute(fix_context)

            # Output should be the raw text, not parsed/transformed
            assert result.output == sample_agent_output
