"""Unit tests for FixerAgent.

Tests the fixer agent's functionality including:
- Initialization and configuration (T031)
- System prompt verification (T032)
- build_prompt method (ACP-native interface, T033)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.agents.context import AgentContext
from maverick.agents.fixer import (
    FIXER_SYSTEM_PROMPT,
    FixerAgent,
)
from maverick.agents.tools import FIXER_TOOLS
from maverick.config import MaverickConfig
from maverick.models.fixer import FixerResult

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

    def test_output_model_set(self, agent: FixerAgent) -> None:
        """Test output_model is set to FixerResult."""
        assert agent._output_model is FixerResult


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

    def test_instructions_does_not_request_json_output(self, agent: FixerAgent) -> None:
        """Test instructions does not ask for JSON output (T032).

        The fixer applies fixes via tools; success is determined by
        re-running validation, not by the agent's self-report.
        """
        prompt = agent.instructions
        assert "json" not in prompt.lower()


# =============================================================================
# T033: build_prompt Tests (ACP-native interface)
# =============================================================================


class TestBuildPrompt:
    """Tests for FixerAgent.build_prompt (ACP-native interface, T033)."""

    def test_build_prompt_returns_prompt_from_context(
        self, agent: FixerAgent, fix_context: AgentContext
    ) -> None:
        """Test build_prompt extracts prompt from context.extra['prompt']."""
        result = agent.build_prompt(fix_context)

        assert "Fix the following validation error" in result
        assert "Ruff E501" in result

    def test_build_prompt_returns_empty_when_no_prompt(
        self, agent: FixerAgent, tmp_path: Path
    ) -> None:
        """Test build_prompt returns empty string when no prompt in context."""
        context = AgentContext(
            cwd=tmp_path,
            branch="feature/fix",
            config=MaverickConfig(),
            extra={},
        )

        result = agent.build_prompt(context)

        assert result == ""

    def test_build_prompt_returns_string(
        self, agent: FixerAgent, fix_context: AgentContext
    ) -> None:
        """Test build_prompt returns a string."""
        result = agent.build_prompt(fix_context)
        assert isinstance(result, str)

    def test_build_prompt_passes_through_full_prompt(
        self, agent: FixerAgent, tmp_path: Path
    ) -> None:
        """Test build_prompt returns the full prompt text unmodified."""
        expected_prompt = "Fix line 42: E501 line too long."
        context = AgentContext(
            cwd=tmp_path,
            branch="feature/fix",
            config=MaverickConfig(),
            extra={"prompt": expected_prompt},
        )

        result = agent.build_prompt(context)

        assert result == expected_prompt
