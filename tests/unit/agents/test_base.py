"""Unit tests for MaverickAgent base class."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.agents.base import BUILTIN_TOOLS, DEFAULT_MODEL, MaverickAgent
from maverick.agents.context import AgentContext
from maverick.agents.result import AgentResult, AgentUsage
from maverick.exceptions import (
    AgentError,
    CLINotFoundError,
    InvalidToolError,
    MalformedResponseError,
    NetworkError,
    ProcessError,
    StreamingError,
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


# =============================================================================
# MaverickAgent Initialization Tests
# =============================================================================


class TestMaverickAgentInitialization:
    """Tests for MaverickAgent initialization."""

    def test_initialization_with_required_parameters(self) -> None:
        """Test agent creation with only required parameters."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="You are a test agent.",
            allowed_tools=["Read", "Write"],
        )

        assert agent.name == "test-agent"
        assert agent.system_prompt == "You are a test agent."
        assert agent.allowed_tools == ["Read", "Write"]
        assert agent.model == DEFAULT_MODEL
        assert agent.mcp_servers == {}

    def test_name_property(self) -> None:
        """Test name property returns correct value."""
        agent = ConcreteTestAgent(
            name="my-agent",
            system_prompt="Test prompt",
            allowed_tools=[],
        )

        assert agent.name == "my-agent"

    def test_system_prompt_property(self) -> None:
        """Test system_prompt property returns correct value."""
        prompt = "You are a specialized test agent."
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt=prompt,
            allowed_tools=[],
        )

        assert agent.system_prompt == prompt

    def test_allowed_tools_property_returns_copy(self) -> None:
        """Test allowed_tools property returns a copy, not reference."""
        original_tools = ["Read", "Write"]
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
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
            system_prompt="Test prompt",
            allowed_tools=[],
        )

        assert agent.model == DEFAULT_MODEL
        assert agent.model == "claude-sonnet-4-5-20250929"

    def test_model_can_be_overridden(self) -> None:
        """Test model can be overridden with custom value."""
        custom_model = "claude-opus-4-5-20251101"
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=[],
            model=custom_model,
        )

        assert agent.model == custom_model

    def test_mcp_servers_defaults_to_empty_dict(self) -> None:
        """Test mcp_servers defaults to empty dict when not specified."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=[],
        )

        assert agent.mcp_servers == {}

    def test_mcp_servers_returns_copy(self) -> None:
        """Test mcp_servers property returns a copy, not reference."""
        servers = {"github": {"url": "http://example.com"}}
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
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
            system_prompt="Test prompt",
            allowed_tools=list(BUILTIN_TOOLS),
        )

        assert len(agent.allowed_tools) == len(BUILTIN_TOOLS)

    def test_validates_individual_builtin_tools(self) -> None:
        """Test validates individual builtin tools."""
        for tool in BUILTIN_TOOLS:
            # Should not raise
            agent = ConcreteTestAgent(
                name="test-agent",
                system_prompt="Test prompt",
                allowed_tools=[tool],
            )
            assert tool in agent.allowed_tools

    def test_validates_mcp_tool_patterns(self) -> None:
        """Test validates MCP tool patterns (mcp__server__tool)."""
        # Should not raise
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=["mcp__github__create_pr", "mcp__github__list_issues"],
            mcp_servers={"github": {"url": "http://example.com"}},
        )

        assert "mcp__github__create_pr" in agent.allowed_tools
        assert "mcp__github__list_issues" in agent.allowed_tools

    def test_raises_invalid_tool_error_for_unknown_tool(self) -> None:
        """Test raises InvalidToolError for unknown tool."""
        with pytest.raises(InvalidToolError) as exc_info:
            ConcreteTestAgent(
                name="test-agent",
                system_prompt="Test prompt",
                allowed_tools=["UnknownTool"],
            )

        error = exc_info.value
        assert error.tool_name == "UnknownTool"
        assert isinstance(error.available_tools, list)
        assert "UnknownTool" in str(error)

    def test_allows_mcp_tools_when_server_is_in_mcp_servers(self) -> None:
        """Test allows MCP tools when corresponding server is configured."""
        servers = {
            "github": {"url": "http://example.com"},
            "gitlab": {"url": "http://gitlab.com"},
        }

        # Should not raise
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=[
                "mcp__github__create_pr",
                "mcp__gitlab__merge_request",
            ],
            mcp_servers=servers,
        )

        assert "mcp__github__create_pr" in agent.allowed_tools
        assert "mcp__gitlab__merge_request" in agent.allowed_tools

    def test_raises_invalid_tool_error_for_mcp_tool_without_server(self) -> None:
        """Test raises InvalidToolError for MCP tool when server is not configured."""
        with pytest.raises(InvalidToolError) as exc_info:
            ConcreteTestAgent(
                name="test-agent",
                system_prompt="Test prompt",
                allowed_tools=["mcp__github__create_pr"],
                mcp_servers={},  # No servers configured
            )

        error = exc_info.value
        assert error.tool_name == "mcp__github__create_pr"

    def test_mixed_builtin_and_mcp_tools(self) -> None:
        """Test validates mixed builtin and MCP tools."""
        # Should not raise
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=["Read", "Write", "mcp__github__create_pr"],
            mcp_servers={"github": {"url": "http://example.com"}},
        )

        assert "Read" in agent.allowed_tools
        assert "Write" in agent.allowed_tools
        assert "mcp__github__create_pr" in agent.allowed_tools


# =============================================================================
# _build_options Tests
# =============================================================================


class TestBuildOptions:
    """Tests for _build_options method."""

    def test_returns_claude_agent_options(self) -> None:
        """Test returns ClaudeAgentOptions instance."""
        mock_options_class = MagicMock()
        mock_instance = MagicMock()
        mock_options_class.return_value = mock_instance

        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=["Read"],
        )

        with patch.dict(
            "sys.modules",
            {"claude_agent_sdk": MagicMock(ClaudeAgentOptions=mock_options_class)},
        ):
            result = agent._build_options()

        assert result == mock_instance
        mock_options_class.assert_called_once()

    def test_passes_correct_parameters_to_options(self) -> None:
        """Test passes correct parameters to ClaudeAgentOptions."""
        mock_options_class = MagicMock()

        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=["Read", "Write"],
            model="custom-model",
            mcp_servers={"github": {"url": "http://example.com"}},
        )

        with patch.dict(
            "sys.modules",
            {"claude_agent_sdk": MagicMock(ClaudeAgentOptions=mock_options_class)},
        ):
            agent._build_options(cwd="/workspace/test")

        mock_options_class.assert_called_once_with(
            allowed_tools=["Read", "Write"],
            system_prompt="Test prompt",
            model="custom-model",
            permission_mode="acceptEdits",
            mcp_servers={"github": {"url": "http://example.com"}},
            cwd="/workspace/test",
            extra_args={},
            include_partial_messages=True,
        )

    def test_cwd_none_when_not_specified(self) -> None:
        """Test cwd is None when not specified."""
        mock_options_class = MagicMock()

        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=[],
        )

        with patch.dict(
            "sys.modules",
            {"claude_agent_sdk": MagicMock(ClaudeAgentOptions=mock_options_class)},
        ):
            agent._build_options()

        # Get the call args
        call_args = mock_options_class.call_args
        assert call_args is not None
        assert call_args.kwargs["cwd"] is None

    def test_cwd_converted_to_string_from_path(self) -> None:
        """Test cwd is converted to string when Path is provided."""
        mock_options_class = MagicMock()

        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=[],
        )

        with patch.dict(
            "sys.modules",
            {"claude_agent_sdk": MagicMock(ClaudeAgentOptions=mock_options_class)},
        ):
            agent._build_options(cwd=Path("/workspace/project"))

        call_args = mock_options_class.call_args
        assert call_args is not None
        assert call_args.kwargs["cwd"] == "/workspace/project"

    def test_passes_max_tokens_in_extra_args(self) -> None:
        """Test passes max_tokens in extra_args when specified (line 226)."""
        mock_options_class = MagicMock()

        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=[],
            max_tokens=4096,
        )

        with patch.dict(
            "sys.modules",
            {"claude_agent_sdk": MagicMock(ClaudeAgentOptions=mock_options_class)},
        ):
            agent._build_options()

        call_args = mock_options_class.call_args
        assert call_args is not None
        assert call_args.kwargs["extra_args"]["max_tokens"] == "4096"

    def test_passes_temperature_in_extra_args(self) -> None:
        """Test passes temperature in extra_args when specified (line 228)."""
        mock_options_class = MagicMock()

        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=[],
            temperature=0.7,
        )

        with patch.dict(
            "sys.modules",
            {"claude_agent_sdk": MagicMock(ClaudeAgentOptions=mock_options_class)},
        ):
            agent._build_options()

        call_args = mock_options_class.call_args
        assert call_args is not None
        assert call_args.kwargs["extra_args"]["temperature"] == "0.7"


# =============================================================================
# _wrap_sdk_error Tests
# =============================================================================


class TestWrapSDKError:
    """Tests for _wrap_sdk_error method."""

    def test_wraps_cli_not_found_error(self) -> None:
        """Test wraps CLINotFoundError from SDK."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=[],
        )

        # Create a mock SDK error
        sdk_error = MagicMock()
        sdk_error.__class__.__name__ = "CLINotFoundError"
        sdk_error.cli_path = "/usr/bin/claude"

        result = agent._wrap_sdk_error(sdk_error)

        assert isinstance(result, CLINotFoundError)
        assert result.cli_path == "/usr/bin/claude"

    def test_wraps_process_error_with_exit_code_and_stderr(self) -> None:
        """Test wraps ProcessError with exit_code and stderr."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=[],
        )

        # Create a mock SDK error
        sdk_error = MagicMock()
        sdk_error.__class__.__name__ = "ProcessError"
        sdk_error.exit_code = 1
        sdk_error.stderr = "Command failed"
        sdk_error.__str__ = MagicMock(return_value="Process error occurred")

        result = agent._wrap_sdk_error(sdk_error)

        assert isinstance(result, ProcessError)
        assert result.exit_code == 1
        assert result.stderr == "Command failed"
        assert "Process error occurred" in result.message

    def test_wraps_cli_connection_error_to_network_error(self) -> None:
        """Test wraps CLIConnectionError to NetworkError."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=[],
        )

        # Create a mock SDK error
        sdk_error = MagicMock()
        sdk_error.__class__.__name__ = "CLIConnectionError"
        sdk_error.__str__ = MagicMock(return_value="Connection failed")

        result = agent._wrap_sdk_error(sdk_error)

        assert isinstance(result, NetworkError)
        assert "Connection failed" in result.message

    def test_wraps_cli_json_decode_error_to_malformed_response_error(self) -> None:
        """Test wraps CLIJSONDecodeError to MalformedResponseError."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=[],
        )

        # Create a mock SDK error
        sdk_error = MagicMock()
        sdk_error.__class__.__name__ = "CLIJSONDecodeError"
        sdk_error.raw = '{"invalid": json}'
        sdk_error.__str__ = MagicMock(return_value="Invalid JSON")

        result = agent._wrap_sdk_error(sdk_error)

        assert isinstance(result, MalformedResponseError)
        assert result.raw_response == '{"invalid": json}'
        assert "Invalid JSON" in result.message

    def test_wraps_timeout_error_to_maverick_timeout_error(self) -> None:
        """Test wraps TimeoutError to MaverickTimeoutError (line 271)."""
        from maverick.exceptions import MaverickTimeoutError

        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=[],
        )

        # Create a mock TimeoutError
        sdk_error = MagicMock()
        sdk_error.__class__.__name__ = "TimeoutError"
        sdk_error.timeout_seconds = 30
        sdk_error.__str__ = MagicMock(return_value="Operation timed out")

        result = agent._wrap_sdk_error(sdk_error)

        assert isinstance(result, MaverickTimeoutError)
        assert result.timeout_seconds == 30
        assert "Operation timed out" in result.message

    def test_wraps_generic_errors_to_agent_error(self) -> None:
        """Test wraps generic errors to AgentError."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=[],
        )

        # Create a generic error
        sdk_error = ValueError("Something went wrong")

        result = agent._wrap_sdk_error(sdk_error)

        assert isinstance(result, AgentError)
        assert "Something went wrong" in result.message
        assert result.agent_name == "test-agent"

    def test_wraps_unknown_sdk_error_types_to_agent_error(self) -> None:
        """Test wraps unknown SDK error types to AgentError."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=[],
        )

        # Create a mock unknown SDK error
        sdk_error = MagicMock()
        sdk_error.__class__.__name__ = "UnknownSDKError"
        sdk_error.__str__ = MagicMock(return_value="Unknown error")

        result = agent._wrap_sdk_error(sdk_error)

        assert isinstance(result, AgentError)
        assert "Unknown error" in result.message
        assert result.agent_name == "test-agent"


# =============================================================================
# _extract_usage Tests
# =============================================================================


class TestExtractUsage:
    """Tests for _extract_usage method."""

    def test_extracts_usage_from_result_message(self) -> None:
        """Test extracts usage from ResultMessage."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=[],
        )

        # Create a mock ResultMessage
        result_msg = MagicMock()
        result_msg.__class__.__name__ = "ResultMessage"
        result_msg.usage = {
            "input_tokens": 150,
            "output_tokens": 250,
        }
        result_msg.total_cost_usd = 0.005
        result_msg.duration_ms = 2000

        # Create a mock TextMessage
        text_msg = MagicMock()
        text_msg.__class__.__name__ = "TextMessage"

        messages = [text_msg, result_msg]

        usage = agent._extract_usage(messages)

        assert isinstance(usage, AgentUsage)
        assert usage.input_tokens == 150
        assert usage.output_tokens == 250
        assert usage.total_cost_usd == 0.005
        assert usage.duration_ms == 2000

    def test_returns_zeros_when_no_result_message(self) -> None:
        """Test returns zeros when no ResultMessage is found."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=[],
        )

        # Create mock messages without ResultMessage
        text_msg1 = MagicMock()
        text_msg1.__class__.__name__ = "TextMessage"

        text_msg2 = MagicMock()
        text_msg2.__class__.__name__ = "TextMessage"

        messages = [text_msg1, text_msg2]

        usage = agent._extract_usage(messages)

        assert isinstance(usage, AgentUsage)
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.total_cost_usd is None
        assert usage.duration_ms == 0

    def test_handles_empty_message_list(self) -> None:
        """Test handles empty message list."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=[],
        )

        usage = agent._extract_usage([])

        assert isinstance(usage, AgentUsage)
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.total_cost_usd is None
        assert usage.duration_ms == 0

    def test_handles_result_message_without_usage(self) -> None:
        """Test handles ResultMessage without usage attribute."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=[],
        )

        # Create a mock ResultMessage without usage
        result_msg = MagicMock()
        result_msg.__class__.__name__ = "ResultMessage"
        result_msg.usage = None
        result_msg.total_cost_usd = None
        result_msg.duration_ms = 1000

        messages = [result_msg]

        usage = agent._extract_usage(messages)

        assert isinstance(usage, AgentUsage)
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.total_cost_usd is None
        assert usage.duration_ms == 1000

    def test_handles_partial_usage_data(self) -> None:
        """Test handles partial usage data in ResultMessage."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=[],
        )

        # Create a mock ResultMessage with partial usage
        result_msg = MagicMock()
        result_msg.__class__.__name__ = "ResultMessage"
        result_msg.usage = {
            "input_tokens": 100,
            # output_tokens missing
        }
        result_msg.total_cost_usd = None
        result_msg.duration_ms = 0

        messages = [result_msg]

        usage = agent._extract_usage(messages)

        assert isinstance(usage, AgentUsage)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 0  # Should default to 0


# =============================================================================
# query Tests
# =============================================================================


class TestQuery:
    """Tests for query method."""

    @pytest.mark.asyncio
    async def test_streams_messages_from_client(self) -> None:
        """Test streams messages from ClaudeSDKClient."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=["Read"],
        )

        # Create mock messages
        msg1 = MagicMock()
        msg1.__class__.__name__ = "TextMessage"

        msg2 = MagicMock()
        msg2.__class__.__name__ = "TextMessage"

        msg3 = MagicMock()
        msg3.__class__.__name__ = "ResultMessage"

        # Create mock client
        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            for msg in [msg1, msg2, msg3]:
                yield msg

        mock_client.receive_response = mock_receive
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_sdk = MagicMock()
        mock_sdk.ClaudeSDKClient = MagicMock(return_value=mock_client)
        mock_sdk.ClaudeAgentOptions = MagicMock()

        with patch.dict("sys.modules", {"claude_agent_sdk": mock_sdk}):
            messages = []
            async for message in agent.query("Test prompt", cwd="/workspace"):
                messages.append(message)

        assert len(messages) == 3
        assert messages[0] == msg1
        assert messages[1] == msg2
        assert messages[2] == msg3

        mock_client.query.assert_awaited_once_with("Test prompt")

    @pytest.mark.asyncio
    async def test_raises_streaming_error_with_partial_messages_on_mid_stream_failure(
        self,
    ) -> None:
        """Test raises StreamingError with partial messages on mid-stream failure."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=["Read"],
        )

        # Create mock messages
        msg1 = MagicMock()
        msg1.__class__.__name__ = "TextMessage"

        msg2 = MagicMock()
        msg2.__class__.__name__ = "TextMessage"

        # Create mock client that fails mid-stream
        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield msg1
            yield msg2
            raise ValueError("Stream interrupted")

        mock_client.receive_response = mock_receive
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_sdk = MagicMock()
        mock_sdk.ClaudeSDKClient = MagicMock(return_value=mock_client)
        mock_sdk.ClaudeAgentOptions = MagicMock()

        with patch.dict("sys.modules", {"claude_agent_sdk": mock_sdk}):
            with pytest.raises(StreamingError) as exc_info:
                messages = []
                async for message in agent.query("Test prompt"):
                    messages.append(message)

        error = exc_info.value
        assert isinstance(error, StreamingError)
        assert len(error.partial_messages) == 2
        assert error.partial_messages[0] == msg1
        assert error.partial_messages[1] == msg2
        assert "Stream interrupted" in error.message

    @pytest.mark.asyncio
    async def test_wraps_sdk_errors_when_no_partial_messages(self) -> None:
        """Test wraps SDK errors when no partial messages have been received."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=["Read"],
        )

        # Create mock client that fails immediately
        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            # Fail immediately without yielding any messages
            raise ValueError("Connection failed")
            yield  # Make it a generator

        mock_client.receive_response = MagicMock(return_value=mock_receive())
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_sdk = MagicMock()
        mock_sdk.ClaudeSDKClient = MagicMock(return_value=mock_client)
        mock_sdk.ClaudeAgentOptions = MagicMock()

        with patch.dict("sys.modules", {"claude_agent_sdk": mock_sdk}):
            with pytest.raises(AgentError) as exc_info:
                async for _ in agent.query("Test prompt"):
                    pass

        error = exc_info.value
        assert isinstance(error, AgentError)
        assert "Connection failed" in error.message
        assert error.agent_name == "test-agent"

    @pytest.mark.asyncio
    async def test_wraps_cli_not_found_error_from_sdk(self) -> None:
        """Test wraps CLINotFoundError from SDK during query."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=["Read"],
        )

        # Create a real exception class that mimics CLINotFoundError
        class MockCLINotFoundError(Exception):
            """Mock CLI not found error."""

            def __init__(self) -> None:
                self.cli_path = "/usr/bin/claude"
                super().__init__("CLI not found")

        # Override class name to simulate SDK error type
        MockCLINotFoundError.__name__ = "CLINotFoundError"
        sdk_error = MockCLINotFoundError()

        # Create mock client that raises SDK error
        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            raise sdk_error
            yield  # Make it a generator

        mock_client.receive_response = MagicMock(return_value=mock_receive())
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_sdk = MagicMock()
        mock_sdk.ClaudeSDKClient = MagicMock(return_value=mock_client)
        mock_sdk.ClaudeAgentOptions = MagicMock()

        with patch.dict("sys.modules", {"claude_agent_sdk": mock_sdk}):
            with pytest.raises(CLINotFoundError) as exc_info:
                async for _ in agent.query("Test prompt"):
                    pass

        error = exc_info.value
        assert isinstance(error, CLINotFoundError)
        assert error.cli_path == "/usr/bin/claude"

    @pytest.mark.asyncio
    async def test_builds_options_with_provided_cwd(self) -> None:
        """Test builds options with provided cwd parameter."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=["Read"],
        )

        # Create mock client
        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            return
            yield  # Empty async generator

        mock_client.receive_response = mock_receive
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_sdk_client = MagicMock(return_value=mock_client)
        mock_options_class = MagicMock()
        mock_sdk = MagicMock()
        mock_sdk.ClaudeSDKClient = mock_sdk_client
        mock_sdk.ClaudeAgentOptions = mock_options_class

        with patch.dict("sys.modules", {"claude_agent_sdk": mock_sdk}):
            async for _ in agent.query("Test prompt", cwd="/workspace/custom"):
                pass

            # Verify ClaudeAgentOptions was called with correct cwd
            assert mock_options_class.call_count == 1
            call_kwargs = mock_options_class.call_args.kwargs
            assert call_kwargs["cwd"] == "/workspace/custom"

    @pytest.mark.asyncio
    async def test_handles_path_object_for_cwd(self) -> None:
        """Test handles Path object for cwd parameter."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
            allowed_tools=["Read"],
        )

        # Create mock client
        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            return
            yield  # Empty async generator

        mock_client.receive_response = mock_receive
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_sdk_client = MagicMock(return_value=mock_client)
        mock_options_class = MagicMock()
        mock_sdk = MagicMock()
        mock_sdk.ClaudeSDKClient = mock_sdk_client
        mock_sdk.ClaudeAgentOptions = mock_options_class

        with patch.dict("sys.modules", {"claude_agent_sdk": mock_sdk}):
            async for _ in agent.query("Test prompt", cwd=Path("/workspace/path")):
                pass

            # Verify cwd was converted to string
            assert mock_options_class.call_count == 1
            call_kwargs = mock_options_class.call_args.kwargs
            assert call_kwargs["cwd"] == "/workspace/path"
            assert isinstance(call_kwargs["cwd"], str)


# =============================================================================
# Execute Method Tests
# =============================================================================


class TestExecuteMethod:
    """Tests for execute method (abstract method implementation)."""

    @pytest.mark.asyncio
    async def test_concrete_agent_can_execute(self) -> None:
        """Test concrete agent implementation can execute successfully."""
        agent = ConcreteTestAgent(
            name="test-agent",
            system_prompt="Test prompt",
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
