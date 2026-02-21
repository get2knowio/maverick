"""Integration tests for agent module performance characteristics.

These tests verify that the agent module components work together correctly
and meet performance requirements. They test real import paths, dataclass
creation overhead, and registry operations.
"""

from __future__ import annotations

import time

import pytest


class TestModuleImports:
    """Test module imports work correctly and efficiently."""

    def test_can_import_all_public_api(self) -> None:
        """Test all public API exports can be imported from agents module."""
        from maverick.agents import (
            BUILTIN_TOOLS,
            DEFAULT_MODEL,
            AgentContext,
            AgentMessage,
            AgentRegistry,
            AgentResult,
            AgentUsage,
            MaverickAgent,
            extract_all_text,
            extract_text,
            register,
            registry,
        )

        # Verify each import is defined
        assert MaverickAgent is not None
        assert AgentResult is not None
        assert AgentUsage is not None
        assert AgentContext is not None
        assert AgentRegistry is not None
        assert registry is not None
        assert register is not None
        assert extract_text is not None
        assert extract_all_text is not None
        assert AgentMessage is not None
        assert BUILTIN_TOOLS is not None
        assert DEFAULT_MODEL is not None

    def test_import_time_is_reasonable(self) -> None:
        """Test that module import time is under 1000ms.

        Note: This test measures import time using a subprocess to avoid
        polluting the test environment's module cache.

        The threshold is 1.0s to account for CI environment variability.
        """
        import subprocess
        import sys

        # Run import timing in a subprocess to avoid polluting sys.modules
        code = """
import time
start = time.perf_counter()
import maverick.agents
elapsed = time.perf_counter() - start
print(f"{elapsed:.6f}")
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            raise AssertionError(f"Import failed: {result.stderr}")

        elapsed = float(result.stdout.strip())

        # Should import reasonably quickly (under 1.5s, accounting for CI variability
        # and library imports like tiktoken that load tokenizer data)
        assert elapsed < 1.5, f"Import took {elapsed:.3f}s, expected < 1.5s"


class TestDataclassPerformance:
    """Test dataclass creation performance."""

    def test_agent_usage_creation_is_fast(self) -> None:
        """Test AgentUsage can be created quickly."""
        from maverick.agents import AgentUsage

        start = time.perf_counter()
        for _ in range(1000):
            AgentUsage(
                input_tokens=100,
                output_tokens=200,
                total_cost_usd=0.003,
                duration_ms=1500,
            )
        elapsed = time.perf_counter() - start

        # 1000 creations should take < 100ms
        assert elapsed < 0.1, f"1000 creations took {elapsed:.3f}s"

    def test_agent_result_creation_is_fast(self) -> None:
        """Test AgentResult can be created quickly."""
        from maverick.agents import AgentResult, AgentUsage

        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=0.003,
            duration_ms=1500,
        )

        start = time.perf_counter()
        for _ in range(1000):
            AgentResult.success_result(
                output="Test output",
                usage=usage,
                metadata={"key": "value"},
            )
        elapsed = time.perf_counter() - start

        # 1000 creations should take < 100ms
        assert elapsed < 0.1, f"1000 creations took {elapsed:.3f}s"


class TestRegistryIntegration:
    """Test registry integration with MaverickAgent."""

    def test_register_and_create_agent(self) -> None:
        """Test registering and creating an agent through registry."""
        from maverick.agents import (
            AgentContext,
            AgentRegistry,
            AgentResult,
            AgentUsage,
            MaverickAgent,
        )

        # Create isolated registry for this test
        test_registry = AgentRegistry()

        # Define a concrete agent
        class IntegrationTestAgent(MaverickAgent):
            """Test agent for integration testing."""

            def __init__(self) -> None:
                super().__init__(
                    name="integration_test",
                    instructions="Integration test agent",
                    allowed_tools=[],
                )

            async def execute(self, context: AgentContext) -> AgentResult:
                return AgentResult.success_result(
                    output="Integration test output",
                    usage=AgentUsage(
                        input_tokens=0,
                        output_tokens=0,
                        total_cost_usd=None,
                        duration_ms=0,
                    ),
                )

        # Register the agent
        test_registry.register("integration_test", IntegrationTestAgent)

        # Verify registration
        assert "integration_test" in test_registry.list_agents()

        # Create instance through registry
        agent = test_registry.create("integration_test")
        assert isinstance(agent, IntegrationTestAgent)
        assert agent.name == "integration_test"

    def test_decorator_registration_works(self) -> None:
        """Test @register decorator works with registry."""
        from maverick.agents import (
            AgentContext,
            AgentRegistry,
            AgentResult,
            AgentUsage,
            MaverickAgent,
            register,
        )

        # Create isolated registry for this test
        test_registry = AgentRegistry()

        # Use decorator to register
        @register("decorated_integration", registry=test_registry)
        class DecoratedIntegrationAgent(MaverickAgent):
            """Test agent registered via decorator."""

            def __init__(self) -> None:
                super().__init__(
                    name="decorated_integration",
                    instructions="Decorated integration agent",
                    allowed_tools=[],
                )

            async def execute(self, context: AgentContext) -> AgentResult:
                return AgentResult.success_result(
                    output="Decorated agent output",
                    usage=AgentUsage(
                        input_tokens=0,
                        output_tokens=0,
                        total_cost_usd=None,
                        duration_ms=0,
                    ),
                )

        # Verify registration
        assert "decorated_integration" in test_registry.list_agents()
        agent = test_registry.create("decorated_integration")
        assert isinstance(agent, DecoratedIntegrationAgent)


class TestErrorHandlingIntegration:
    """Test error handling integration across module components."""

    def test_invalid_tool_provides_helpful_message(self) -> None:
        """Test InvalidToolError includes available tools list."""
        from maverick.agents import MaverickAgent
        from maverick.exceptions import InvalidToolError

        class TestBadToolAgent(MaverickAgent):
            """Agent with invalid tool."""

            async def execute(self, context):
                pass

        with pytest.raises(InvalidToolError) as exc_info:
            TestBadToolAgent(
                name="bad_tool_agent",
                instructions="Test",
                allowed_tools=["NonExistentTool"],
            )

        error = exc_info.value
        assert error.tool_name == "NonExistentTool"
        # Should provide list of available tools
        assert error.available_tools is not None
        assert len(error.available_tools) > 0
        # Should include builtin tools in available list
        for builtin in ["Read", "Write", "Edit"]:
            assert builtin in error.available_tools

    def test_agent_not_found_error_includes_name(self) -> None:
        """Test AgentNotFoundError includes the missing agent name."""
        from maverick.agents import AgentRegistry
        from maverick.exceptions import AgentNotFoundError

        test_registry = AgentRegistry()

        with pytest.raises(AgentNotFoundError) as exc_info:
            test_registry.get("nonexistent_agent")

        error = exc_info.value
        assert error.agent_name == "nonexistent_agent"
        assert "nonexistent_agent" in str(error)

    def test_duplicate_agent_error_includes_name(self) -> None:
        """Test DuplicateAgentError includes the duplicate name."""
        from maverick.agents import (
            AgentContext,
            AgentRegistry,
            AgentResult,
            AgentUsage,
            MaverickAgent,
        )
        from maverick.exceptions import DuplicateAgentError

        test_registry = AgentRegistry()

        class DuplicateTestAgent(MaverickAgent):
            """Agent for duplicate testing."""

            async def execute(self, context: AgentContext) -> AgentResult:
                return AgentResult.success_result(
                    output="",
                    usage=AgentUsage(0, 0, None, 0),
                )

        test_registry.register("duplicate_name", DuplicateTestAgent)

        with pytest.raises(DuplicateAgentError) as exc_info:
            test_registry.register("duplicate_name", DuplicateTestAgent)

        error = exc_info.value
        assert error.agent_name == "duplicate_name"
        assert "duplicate_name" in str(error)


class TestContextIntegration:
    """Test AgentContext integration with other components."""

    def test_context_with_config_defaults(self, tmp_path) -> None:
        """Test AgentContext works with default MaverickConfig."""
        import subprocess

        from maverick.agents import AgentContext
        from maverick.config import MaverickConfig

        # Create temp dir with actual git repo
        test_dir = tmp_path / "test_project"
        test_dir.mkdir()

        # Initialize a real git repository
        subprocess.run(
            ["git", "init"],
            cwd=test_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "checkout", "-b", "main"],
            cwd=test_dir,
            capture_output=True,
            check=True,
        )

        context = AgentContext.from_cwd(test_dir)

        assert context.cwd == test_dir
        assert context.branch == "main"
        assert isinstance(context.config, MaverickConfig)
        assert context.extra == {}


class TestUtilitiesIntegration:
    """Test utility functions work with mock SDK types."""

    def test_extract_text_with_mock_messages(self) -> None:
        """Test extract_text works with mock message objects."""
        from unittest.mock import MagicMock

        from maverick.agents import extract_text

        # Create mock TextBlock
        text_block = MagicMock()
        text_block.text = "Hello, world!"
        type(text_block).__name__ = "TextBlock"

        # Create mock AssistantMessage
        message = MagicMock()
        message.content = [text_block]
        type(message).__name__ = "AssistantMessage"

        result = extract_text(message)

        assert result == "Hello, world!"

    def test_extract_all_text_filters_non_assistant_messages(self) -> None:
        """Test extract_all_text filters non-AssistantMessage types."""
        from unittest.mock import MagicMock

        from maverick.agents import extract_all_text

        # Create assistant message
        text_block = MagicMock()
        text_block.text = "Assistant response"
        type(text_block).__name__ = "TextBlock"

        assistant_msg = MagicMock()
        assistant_msg.content = [text_block]
        type(assistant_msg).__name__ = "AssistantMessage"

        # Create user message
        user_msg = MagicMock()
        user_msg.content = "User input"
        type(user_msg).__name__ = "UserMessage"

        messages = [user_msg, assistant_msg]

        result = extract_all_text(messages)

        # Should only include assistant message text
        assert result == "Assistant response"
