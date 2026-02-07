"""Unit tests for Notification MCP tools.

Tests the notification tools functionality including:
- send_workflow_update with stage mappings
- send_notification with custom parameters
- Error handling and validation
- Retry logic and graceful degradation
- MCP server factory
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest
from aiolimiter import AsyncLimiter

from maverick.config import NotificationConfig
from maverick.tools.notification import (
    DEFAULT_NTFY_RATE_LIMIT,
    DEFAULT_NTFY_RATE_PERIOD,
    DEFAULT_TIMEOUT,
    NTFY_PRIORITIES,
    SERVER_NAME,
    SERVER_VERSION,
    STAGE_MAPPING,
    _error_response,
    _send_ntfy_request,
    _success_response,
    create_notification_tools_server,
)

# =============================================================================
# Test Fixtures (T051)
# =============================================================================


@pytest.fixture
def mock_config() -> NotificationConfig:
    """Create a test notification configuration."""
    return NotificationConfig(
        enabled=True,
        server="https://ntfy.sh",
        topic="test-topic",
    )


@pytest.fixture
def mock_disabled_config() -> NotificationConfig:
    """Create a disabled notification configuration (no topic)."""
    return NotificationConfig(
        enabled=False,
        server="https://ntfy.sh",
        topic=None,
    )


@pytest.fixture
def mock_aiohttp_response() -> Mock:
    """Create a mock aiohttp response."""
    mock_response = Mock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"id": "test-notification-id"})
    mock_response.text = AsyncMock(return_value="OK")
    return mock_response


class MockClientSession:
    """Mock aiohttp ClientSession for testing."""

    def __init__(self, response: Mock, *args: Any, **kwargs: Any) -> None:
        self.response = response
        self.post_calls: list[tuple[Any, ...]] = []

    async def __aenter__(self) -> MockClientSession:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    def post(self, *args: Any, **kwargs: Any) -> MockResponse:
        self.post_calls.append((args, kwargs))
        return MockResponse(self.response)


class MockResponse:
    """Mock aiohttp response for testing."""

    def __init__(self, response: Mock) -> None:
        self._response = response

    async def __aenter__(self) -> Mock:
        return self._response

    async def __aexit__(self, *args: Any) -> None:
        pass


@pytest.fixture
def mock_aiohttp_session(mock_aiohttp_response: Mock) -> MockClientSession:
    """Create a mock aiohttp session for testing."""
    return MockClientSession(mock_aiohttp_response)


@pytest.fixture
def notification_tools(mock_config: NotificationConfig) -> dict[str, Any]:
    """Create notification tools with test config."""
    server_dict = create_notification_tools_server(config=mock_config)
    # Access tools via _tools key added by factory for testing
    return server_dict["_tools"]


@pytest.fixture
def disabled_notification_tools(
    mock_disabled_config: NotificationConfig,
) -> dict[str, Any]:
    """Create notification tools with disabled config."""
    server_dict = create_notification_tools_server(config=mock_disabled_config)
    return server_dict["_tools"]


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for internal helper functions."""

    def test_success_response_format(self) -> None:
        """Verify success response follows MCP format."""
        data = {"success": True, "message": "Test message"}
        result = _success_response(data)

        assert "content" in result
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"

        parsed = json.loads(result["content"][0]["text"])
        assert parsed == data

    def test_error_response_format(self) -> None:
        """Verify error response follows MCP format."""
        result = _error_response(
            message="Test error",
            error_code="TEST_ERROR",
        )

        assert "content" in result
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["message"] == "Test error"
        assert parsed["error_code"] == "TEST_ERROR"
        assert "retry_after_seconds" not in parsed

    def test_error_response_with_retry(self) -> None:
        """Verify error response includes retry_after_seconds when provided."""
        result = _error_response(
            message="Rate limited",
            error_code="RATE_LIMIT",
            retry_after_seconds=60,
        )

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["retry_after_seconds"] == 60


# =============================================================================
# send_ntfy_request Tests
# =============================================================================


class TestSendNtfyRequest:
    """Tests for _send_ntfy_request helper function."""

    @pytest.mark.asyncio
    async def test_send_request_disabled_config(
        self, mock_disabled_config: NotificationConfig
    ) -> None:
        """Test graceful handling when notifications disabled (no topic)."""
        success, message, notification_id = await _send_ntfy_request(
            config=mock_disabled_config,
            message="Test message",
            title="Test title",
        )

        assert success is True
        assert message == "Notifications disabled"
        assert notification_id is None

    @pytest.mark.asyncio
    async def test_send_request_success(
        self,
        mock_config: NotificationConfig,
        mock_aiohttp_response: Mock,
    ) -> None:
        """Test successful notification send."""
        mock_session = MockClientSession(mock_aiohttp_response)

        with patch(
            "maverick.tools.notification.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            success, message, notification_id = await _send_ntfy_request(
                config=mock_config,
                message="Test notification body",
                title="Test Title",
                priority="high",
                tags=["warning", "rocket"],
            )

            # Verify result
            assert success is True
            assert message == "Notification sent"
            assert notification_id == "test-notification-id"

            # Verify POST request
            assert len(mock_session.post_calls) == 1
            call_args, call_kwargs = mock_session.post_calls[0]

            # Verify URL
            assert call_args[0] == "https://ntfy.sh/test-topic"

            # Verify body
            assert call_kwargs["data"] == "Test notification body"

            # Verify headers
            headers = call_kwargs["headers"]
            assert headers["Priority"] == str(NTFY_PRIORITIES["high"])
            assert headers["Title"] == "Test Title"
            assert headers["Tags"] == "warning,rocket"

    @pytest.mark.asyncio
    async def test_send_request_retry_on_timeout(
        self,
        mock_config: NotificationConfig,
    ) -> None:
        """Test retry logic when request times out (T054)."""
        # Create successful response for third attempt
        success_response = Mock()
        success_response.status = 200
        success_response.json = AsyncMock(return_value={"id": "retry-success-id"})

        call_count = 0

        class RetryMockClientSession:
            """Mock that fails twice then succeeds."""

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> RetryMockClientSession:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

            def post(self, *args: Any, **kwargs: Any) -> Any:
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    raise aiohttp.ClientError("Connection error")
                return MockResponse(success_response)

        # Mock tenacity's async sleep to avoid delays in tests
        with (
            patch(
                "maverick.tools.notification.aiohttp.ClientSession",
                RetryMockClientSession,
            ),
            patch("tenacity.nap.sleep", new_callable=AsyncMock),
        ):
            success, message, notification_id = await _send_ntfy_request(
                config=mock_config,
                message="Test retry",
                max_retries=2,
            )

            # Verify result
            assert success is True
            assert message == "Notification sent"
            assert notification_id == "retry-success-id"

            # Verify retries happened (3 total attempts)
            assert call_count == 3

    @pytest.mark.asyncio
    async def test_send_request_graceful_degradation(
        self,
        mock_config: NotificationConfig,
    ) -> None:
        """Test graceful degradation when server unreachable after retries (T056)."""
        call_count = 0

        class FailingMockClientSession:
            """Mock that always fails."""

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> FailingMockClientSession:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

            def post(self, *args: Any, **kwargs: Any) -> Any:
                nonlocal call_count
                call_count += 1
                raise aiohttp.ClientError("Server unreachable")

        # Mock tenacity's async sleep to avoid delays
        with (
            patch(
                "maverick.tools.notification.aiohttp.ClientSession",
                FailingMockClientSession,
            ),
            patch("tenacity.nap.sleep", new_callable=AsyncMock),
        ):
            success, message, notification_id = await _send_ntfy_request(
                config=mock_config,
                message="Test degradation",
                max_retries=2,
            )

            # Verify graceful degradation
            assert success is True  # Still returns success
            assert message == "Notification not delivered"
            assert notification_id is None

            # Verify all retries were attempted (3 total: initial + 2 retries)
            assert call_count == 3

    @pytest.mark.asyncio
    async def test_send_request_http_error(
        self,
        mock_config: NotificationConfig,
    ) -> None:
        """Test handling of HTTP error responses."""
        # Configure response with error status
        error_response = Mock()
        error_response.status = 429  # Rate limited
        error_response.text = AsyncMock(return_value="Rate limit exceeded")

        mock_session = MockClientSession(error_response)

        # Mock tenacity's async sleep to avoid delays
        with (
            patch(
                "maverick.tools.notification.aiohttp.ClientSession",
                return_value=mock_session,
            ),
            patch("tenacity.nap.sleep", new_callable=AsyncMock),
        ):
            success, message, notification_id = await _send_ntfy_request(
                config=mock_config,
                message="Test HTTP error",
                max_retries=2,
            )

            # Verify graceful degradation on HTTP errors
            assert success is True
            assert message == "Notification not delivered"
            assert notification_id is None

            # Verify all retries were attempted
            assert len(mock_session.post_calls) == 3


# =============================================================================
# send_workflow_update Tests (T052, T053)
# =============================================================================


class TestSendWorkflowUpdate:
    """Tests for send_workflow_update MCP tool."""

    @pytest.mark.asyncio
    async def test_send_workflow_update_success(
        self,
        notification_tools: dict[str, Any],
        mock_aiohttp_session: MockClientSession,
    ) -> None:
        """Test successful workflow update notification with all parameters (T052)."""
        send_workflow_update = notification_tools["send_workflow_update"]

        with patch(
            "maverick.tools.notification.aiohttp.ClientSession",
            return_value=mock_aiohttp_session,
        ):
            # Test each stage mapping
            for stage, _expected_config in STAGE_MAPPING.items():
                result = await send_workflow_update.handler(
                    {
                        "stage": stage,
                        "message": f"Testing {stage} stage",
                        "workflow_name": "TestWorkflow",
                    }
                )

                # Verify MCP response structure
                assert "content" in result
                assert len(result["content"]) == 1
                assert result["content"][0]["type"] == "text"

                # Parse response data
                response_data = json.loads(result["content"][0]["text"])
                assert response_data["success"] is True
                assert response_data["message"] == "Notification sent"
                assert response_data["notification_id"] == "test-notification-id"

            # Verify POST was called for each stage
            assert len(mock_aiohttp_session.post_calls) == len(STAGE_MAPPING)

    @pytest.mark.asyncio
    async def test_send_workflow_update_stage_mappings(
        self,
        notification_tools: dict[str, Any],
        mock_aiohttp_session: MockClientSession,
    ) -> None:
        """Test all stage mappings produce correct priority and tags."""
        send_workflow_update = notification_tools["send_workflow_update"]

        with patch(
            "maverick.tools.notification.aiohttp.ClientSession",
            return_value=mock_aiohttp_session,
        ):
            # Test start stage
            await send_workflow_update.handler(
                {
                    "stage": "start",
                    "message": "Workflow starting",
                    "workflow_name": "FlyWorkflow",
                }
            )

            # Verify headers for start stage
            last_call_args, last_call_kwargs = mock_aiohttp_session.post_calls[-1]
            headers = last_call_kwargs["headers"]
            assert headers["Priority"] == str(NTFY_PRIORITIES["default"])
            assert headers["Tags"] == "rocket"
            assert "🚀 FlyWorkflow Started" in headers["Title"]

            # Test complete stage
            await send_workflow_update.handler(
                {
                    "stage": "complete",
                    "message": "All tasks finished",
                    "workflow_name": "RefuelWorkflow",
                }
            )

            last_call_args, last_call_kwargs = mock_aiohttp_session.post_calls[-1]
            headers = last_call_kwargs["headers"]
            assert headers["Priority"] == str(NTFY_PRIORITIES["high"])
            assert headers["Tags"] == "tada"
            assert "🎉 RefuelWorkflow Complete" in headers["Title"]

            # Test error stage
            await send_workflow_update.handler(
                {
                    "stage": "error",
                    "message": "Something went wrong",
                    "workflow_name": "TestWorkflow",
                }
            )

            last_call_args, last_call_kwargs = mock_aiohttp_session.post_calls[-1]
            headers = last_call_kwargs["headers"]
            assert headers["Priority"] == str(NTFY_PRIORITIES["urgent"])
            assert headers["Tags"] == "x,warning"
            assert "❌ TestWorkflow Error" in headers["Title"]

    @pytest.mark.asyncio
    async def test_send_workflow_update_disabled(
        self,
        disabled_notification_tools: dict[str, Any],
    ) -> None:
        """Test graceful handling when notifications disabled (T053)."""
        send_workflow_update = disabled_notification_tools["send_workflow_update"]

        result = await send_workflow_update.handler(
            {
                "stage": "start",
                "message": "This should not be sent",
                "workflow_name": "TestWorkflow",
            }
        )

        # Verify response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is True
        assert (
            response_data["message"] == "Notifications disabled (no topic configured)"
        )
        assert "notification_id" not in response_data

    @pytest.mark.asyncio
    async def test_send_workflow_update_invalid_stage(
        self,
        notification_tools: dict[str, Any],
    ) -> None:
        """Test error handling for invalid stage."""
        send_workflow_update = notification_tools["send_workflow_update"]

        result = await send_workflow_update.handler(
            {
                "stage": "invalid_stage",
                "message": "Test message",
                "workflow_name": "TestWorkflow",
            }
        )

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert "Invalid stage" in response_data["message"]
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "start" in response_data["message"]  # Lists valid stages

    @pytest.mark.asyncio
    async def test_send_workflow_update_retry(
        self,
        notification_tools: dict[str, Any],
    ) -> None:
        """Test retry logic when server temporarily unreachable (T054)."""
        send_workflow_update = notification_tools["send_workflow_update"]

        # Create successful response for third attempt
        success_response = Mock()
        success_response.status = 200
        success_response.json = AsyncMock(return_value={"id": "retry-id"})

        call_count = 0

        class RetryMockClientSession:
            """Mock that fails twice then succeeds."""

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> RetryMockClientSession:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

            def post(self, *args: Any, **kwargs: Any) -> Any:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise aiohttp.ClientError("Temporary error")
                return MockResponse(success_response)

        with (
            patch(
                "maverick.tools.notification.aiohttp.ClientSession",
                RetryMockClientSession,
            ),
            patch("tenacity.nap.sleep", new_callable=AsyncMock),
        ):
            result = await send_workflow_update.handler(
                {
                    "stage": "start",
                    "message": "Test retry",
                    "workflow_name": "TestWorkflow",
                }
            )

            # Verify successful after retry
            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True
            assert response_data["notification_id"] == "retry-id"

    @pytest.mark.asyncio
    async def test_send_workflow_update_default_workflow_name(
        self,
        notification_tools: dict[str, Any],
        mock_aiohttp_session: MockClientSession,
    ) -> None:
        """Test workflow update with default workflow name."""
        send_workflow_update = notification_tools["send_workflow_update"]

        with patch(
            "maverick.tools.notification.aiohttp.ClientSession",
            return_value=mock_aiohttp_session,
        ):
            # Don't provide workflow_name
            result = await send_workflow_update.handler(
                {
                    "stage": "start",
                    "message": "Starting workflow",
                }
            )

            # Verify default name used
            last_call_args, last_call_kwargs = mock_aiohttp_session.post_calls[-1]
            headers = last_call_kwargs["headers"]
            assert "Workflow" in headers["Title"]

            # Verify response
            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True


# =============================================================================
# send_notification Tests (T055, T056)
# =============================================================================


class TestSendNotification:
    """Tests for send_notification MCP tool."""

    @pytest.mark.asyncio
    async def test_send_notification_success(
        self,
        notification_tools: dict[str, Any],
        mock_aiohttp_session: MockClientSession,
    ) -> None:
        """Test successful custom notification with title, priority, tags (T055)."""
        send_notification = notification_tools["send_notification"]

        with patch(
            "maverick.tools.notification.aiohttp.ClientSession",
            return_value=mock_aiohttp_session,
        ):
            result = await send_notification.handler(
                {
                    "message": "Custom notification body",
                    "title": "Security Alert",
                    "priority": "urgent",
                    "tags": ["warning", "security"],
                }
            )

            # Verify MCP response
            assert "content" in result
            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True
            assert response_data["message"] == "Notification sent"
            assert response_data["notification_id"] == "test-notification-id"

            # Verify POST request
            assert len(mock_aiohttp_session.post_calls) == 1
            call_args, call_kwargs = mock_aiohttp_session.post_calls[0]

            # Verify URL and body
            assert call_args[0] == "https://ntfy.sh/test-topic"
            assert call_kwargs["data"] == "Custom notification body"

            # Verify headers
            headers = call_kwargs["headers"]
            assert headers["Title"] == "Security Alert"
            assert headers["Priority"] == str(NTFY_PRIORITIES["urgent"])
            assert headers["Tags"] == "warning,security"

    @pytest.mark.asyncio
    async def test_send_notification_minimal_params(
        self,
        notification_tools: dict[str, Any],
        mock_aiohttp_session: MockClientSession,
    ) -> None:
        """Test notification with only required message parameter."""
        send_notification = notification_tools["send_notification"]

        with patch(
            "maverick.tools.notification.aiohttp.ClientSession",
            return_value=mock_aiohttp_session,
        ):
            result = await send_notification.handler({"message": "Simple notification"})

            # Verify response
            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True

            # Verify headers use defaults
            last_call_args, last_call_kwargs = mock_aiohttp_session.post_calls[-1]
            headers = last_call_kwargs["headers"]
            assert headers["Priority"] == str(NTFY_PRIORITIES["default"])
            assert "Title" not in headers  # No title provided
            assert "Tags" not in headers  # No tags provided

    @pytest.mark.asyncio
    async def test_send_notification_empty_message(
        self,
        notification_tools: dict[str, Any],
    ) -> None:
        """Test error handling for empty message."""
        send_notification = notification_tools["send_notification"]

        result = await send_notification.handler({"message": ""})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert "cannot be empty" in response_data["message"]
        assert response_data["error_code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_send_notification_whitespace_message(
        self,
        notification_tools: dict[str, Any],
    ) -> None:
        """Test error handling for whitespace-only message."""
        send_notification = notification_tools["send_notification"]

        result = await send_notification.handler({"message": "   \n\t  "})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert "cannot be empty" in response_data["message"]

    @pytest.mark.asyncio
    async def test_send_notification_invalid_priority(
        self,
        notification_tools: dict[str, Any],
    ) -> None:
        """Test error handling for invalid priority value (T055)."""
        send_notification = notification_tools["send_notification"]

        result = await send_notification.handler(
            {
                "message": "Test message",
                "priority": "super_critical",  # Invalid
            }
        )

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert "Invalid priority" in response_data["message"]
        assert response_data["error_code"] == "INVALID_INPUT"
        # Should list valid priorities
        assert "min" in response_data["message"]
        assert "low" in response_data["message"]
        assert "default" in response_data["message"]
        assert "high" in response_data["message"]
        assert "urgent" in response_data["message"]

    @pytest.mark.asyncio
    async def test_send_notification_invalid_tags_type(
        self,
        notification_tools: dict[str, Any],
    ) -> None:
        """Test error handling for invalid tags type."""
        send_notification = notification_tools["send_notification"]

        result = await send_notification.handler(
            {
                "message": "Test message",
                "tags": "not-a-list",  # Should be list
            }
        )

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert "must be a list" in response_data["message"]
        assert response_data["error_code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_send_notification_graceful_degradation(
        self,
        notification_tools: dict[str, Any],
    ) -> None:
        """Test graceful degradation when server unreachable (T056)."""
        send_notification = notification_tools["send_notification"]

        # Use MockClientSession which properly supports async context manager
        error_response = Mock()
        error_response.status = 500
        error_response.text = AsyncMock(return_value="Server down")

        mock_session = MockClientSession(error_response)

        with (
            patch(
                "maverick.tools.notification.aiohttp.ClientSession",
                return_value=mock_session,
            ),
        ):
            result = await send_notification.handler(
                {"message": "This will fail", "priority": "high"}
            )

            # Verify graceful degradation
            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True  # Still success
            assert response_data["message"] == "Notification not delivered"
            assert "warning" in response_data
            assert "unreachable" in response_data["warning"]

    @pytest.mark.asyncio
    async def test_send_notification_disabled(
        self,
        disabled_notification_tools: dict[str, Any],
    ) -> None:
        """Test graceful handling when notifications disabled."""
        send_notification = disabled_notification_tools["send_notification"]

        result = await send_notification.handler(
            {"message": "This should not be sent", "priority": "urgent"}
        )

        # Verify response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is True
        assert (
            response_data["message"] == "Notifications disabled (no topic configured)"
        )
        assert "notification_id" not in response_data

    @pytest.mark.asyncio
    async def test_send_notification_priority_case_insensitive(
        self,
        notification_tools: dict[str, Any],
        mock_aiohttp_session: MockClientSession,
    ) -> None:
        """Test priority parameter is case-insensitive."""
        send_notification = notification_tools["send_notification"]

        with patch(
            "maverick.tools.notification.aiohttp.ClientSession",
            return_value=mock_aiohttp_session,
        ):
            # Test uppercase priority
            result = await send_notification.handler(
                {"message": "Test", "priority": "HIGH"}
            )

            # Verify success
            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True

            # Verify priority was converted correctly
            last_call_args, last_call_kwargs = mock_aiohttp_session.post_calls[-1]
            headers = last_call_kwargs["headers"]
            assert headers["Priority"] == str(NTFY_PRIORITIES["high"])

    @pytest.mark.asyncio
    async def test_send_notification_tags_conversion(
        self,
        notification_tools: dict[str, Any],
        mock_aiohttp_session: MockClientSession,
    ) -> None:
        """Test tags are converted to strings."""
        send_notification = notification_tools["send_notification"]

        with patch(
            "maverick.tools.notification.aiohttp.ClientSession",
            return_value=mock_aiohttp_session,
        ):
            # Test with mixed tag types
            result = await send_notification.handler(
                {
                    "message": "Test",
                    "tags": ["string", 123, True],  # Mixed types
                }
            )

            # Verify success
            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True

            # Verify tags were converted to strings
            last_call_args, last_call_kwargs = mock_aiohttp_session.post_calls[-1]
            headers = last_call_kwargs["headers"]
            assert headers["Tags"] == "string,123,True"


# =============================================================================
# Factory Function Tests (T057)
# =============================================================================


class TestCreateNotificationToolsServer:
    """Tests for create_notification_tools_server factory function (T057)."""

    def test_create_server_with_config(
        self,
        mock_config: NotificationConfig,
    ) -> None:
        """Test factory creates server with provided config."""
        server = create_notification_tools_server(config=mock_config)

        # Verify server is created
        assert server is not None

        # Server is returned as a dict with name, instance, type
        assert isinstance(server, dict)
        assert server["name"] == SERVER_NAME
        assert "instance" in server
        assert server["type"] == "sdk"

    def test_create_server_default_config(self) -> None:
        """Test factory creates server with default config."""
        server = create_notification_tools_server()

        # Verify server is created with defaults
        assert server is not None
        assert isinstance(server, dict)
        assert server["name"] == SERVER_NAME
        assert server["type"] == "sdk"

    def test_create_server_tool_metadata(self) -> None:
        """Test server is properly configured."""
        server = create_notification_tools_server()

        # Verify server is created
        assert server is not None
        assert isinstance(server, dict)

        # Verify structure
        assert server["name"] == SERVER_NAME
        assert server["type"] == "sdk"
        assert "instance" in server

        # The tools are registered via the SDK mechanism
        # and can be verified via the MCP protocol
        # For now, just verify the server was created correctly


# =============================================================================
# Constants Tests
# =============================================================================


class TestConstants:
    """Tests for module constants."""

    def test_ntfy_priorities_complete(self) -> None:
        """Test NTFY_PRIORITIES contains all expected priority levels."""
        assert "min" in NTFY_PRIORITIES
        assert "low" in NTFY_PRIORITIES
        assert "default" in NTFY_PRIORITIES
        assert "high" in NTFY_PRIORITIES
        assert "urgent" in NTFY_PRIORITIES

        # Verify numeric values
        assert NTFY_PRIORITIES["min"] == 1
        assert NTFY_PRIORITIES["low"] == 2
        assert NTFY_PRIORITIES["default"] == 3
        assert NTFY_PRIORITIES["high"] == 4
        assert NTFY_PRIORITIES["urgent"] == 5

    def test_stage_mapping_complete(self) -> None:
        """Test STAGE_MAPPING contains all expected stages."""
        expected_stages = {
            "start",
            "implementation",
            "review",
            "validation",
            "complete",
            "error",
        }

        assert set(STAGE_MAPPING.keys()) == expected_stages

        # Verify each stage has required fields
        for _stage, config in STAGE_MAPPING.items():
            assert "priority" in config
            assert "tags" in config
            assert config["priority"] in NTFY_PRIORITIES
            assert isinstance(config["tags"], list)
            assert len(config["tags"]) > 0

    def test_stage_mapping_priorities(self) -> None:
        """Test stage mappings have appropriate priorities."""
        # Error should be urgent
        assert STAGE_MAPPING["error"]["priority"] == "urgent"

        # Complete should be high priority
        assert STAGE_MAPPING["complete"]["priority"] == "high"

        # Regular stages should be default
        assert STAGE_MAPPING["start"]["priority"] == "default"
        assert STAGE_MAPPING["implementation"]["priority"] == "default"
        assert STAGE_MAPPING["review"]["priority"] == "default"
        assert STAGE_MAPPING["validation"]["priority"] == "default"

    def test_server_metadata(self) -> None:
        """Test server metadata constants."""
        assert SERVER_NAME == "notification-tools"
        assert SERVER_VERSION == "1.0.0"
        assert isinstance(DEFAULT_TIMEOUT, float)
        assert DEFAULT_TIMEOUT == 2.0

    def test_rate_limit_constants(self) -> None:
        """Test rate limit constants are defined correctly."""
        assert DEFAULT_NTFY_RATE_LIMIT == 30
        assert DEFAULT_NTFY_RATE_PERIOD == 60.0


# =============================================================================
# Rate Limiting Tests
# =============================================================================


class TestRateLimiting:
    """Tests for notification rate limiting functionality."""

    def test_create_server_without_rate_limiting(self) -> None:
        """Test factory creates server without rate limiting by default."""
        config = NotificationConfig(topic="test-topic")
        server = create_notification_tools_server(config=config)

        # Server should be created successfully
        assert server is not None
        assert server["name"] == SERVER_NAME

    def test_create_server_with_rate_limiting(self) -> None:
        """Test factory creates server with rate limiting when specified."""
        config = NotificationConfig(topic="test-topic")
        server = create_notification_tools_server(
            config=config,
            rate_limit=30,
            rate_period=60.0,
        )

        # Server should be created successfully
        assert server is not None
        assert server["name"] == SERVER_NAME

    def test_create_server_with_default_rate_period(self) -> None:
        """Test factory uses default rate period when only limit specified."""
        config = NotificationConfig(topic="test-topic")
        server = create_notification_tools_server(
            config=config,
            rate_limit=DEFAULT_NTFY_RATE_LIMIT,
        )

        # Server should be created successfully
        assert server is not None

    @pytest.mark.asyncio
    async def test_send_ntfy_request_with_rate_limiter(
        self,
        mock_config: NotificationConfig,
        mock_aiohttp_response: Mock,
    ) -> None:
        """Test _send_ntfy_request respects rate limiter."""
        mock_session = MockClientSession(mock_aiohttp_response)

        # Create a rate limiter
        rate_limiter = AsyncLimiter(10, 1.0)

        with patch(
            "maverick.tools.notification.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            success, message, notification_id = await _send_ntfy_request(
                config=mock_config,
                message="Test rate limited notification",
                rate_limiter=rate_limiter,
            )

            assert success is True
            assert message == "Notification sent"
            assert notification_id == "test-notification-id"

    @pytest.mark.asyncio
    async def test_send_ntfy_request_without_rate_limiter(
        self,
        mock_config: NotificationConfig,
        mock_aiohttp_response: Mock,
    ) -> None:
        """Test _send_ntfy_request works without rate limiter (default)."""
        mock_session = MockClientSession(mock_aiohttp_response)

        with patch(
            "maverick.tools.notification.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            success, message, notification_id = await _send_ntfy_request(
                config=mock_config,
                message="Test notification without rate limiter",
                rate_limiter=None,  # Explicitly no rate limiter
            )

            assert success is True
            assert message == "Notification sent"
            assert notification_id == "test-notification-id"

    @pytest.mark.asyncio
    async def test_rate_limited_notifications_with_factory(
        self,
        mock_config: NotificationConfig,
        mock_aiohttp_response: Mock,
    ) -> None:
        """Test notifications through factory with rate limiting enabled."""
        mock_session = MockClientSession(mock_aiohttp_response)

        # Create server with rate limiting
        server = create_notification_tools_server(
            config=mock_config,
            rate_limit=10,
            rate_period=1.0,
        )
        notification_tools = server["_tools"]
        send_notification = notification_tools["send_notification"]

        with patch(
            "maverick.tools.notification.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            result = await send_notification.handler(
                {"message": "Rate limited message", "priority": "default"}
            )

            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True
            assert response_data["message"] == "Notification sent"

    @pytest.mark.asyncio
    async def test_rate_limited_workflow_update_with_factory(
        self,
        mock_config: NotificationConfig,
        mock_aiohttp_response: Mock,
    ) -> None:
        """Test workflow updates through factory with rate limiting enabled."""
        mock_session = MockClientSession(mock_aiohttp_response)

        # Create server with rate limiting
        server = create_notification_tools_server(
            config=mock_config,
            rate_limit=10,
            rate_period=1.0,
        )
        notification_tools = server["_tools"]
        send_workflow_update = notification_tools["send_workflow_update"]

        with patch(
            "maverick.tools.notification.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            result = await send_workflow_update.handler(
                {
                    "stage": "start",
                    "message": "Rate limited workflow start",
                    "workflow_name": "TestWorkflow",
                }
            )

            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True
            assert response_data["message"] == "Notification sent"

    @pytest.mark.asyncio
    async def test_rate_limiter_passed_to_send_function(
        self,
        mock_config: NotificationConfig,
        mock_aiohttp_response: Mock,
    ) -> None:
        """Test that rate limiter is properly passed to _send_ntfy_request."""
        mock_session = MockClientSession(mock_aiohttp_response)

        # Create a rate limiter with very strict limits
        rate_limiter = AsyncLimiter(2, 1.0)

        with patch(
            "maverick.tools.notification.aiohttp.ClientSession",
            return_value=mock_session,
        ):
            # Make multiple requests with rate limiter
            import time

            start = time.monotonic()

            # First two should be immediate
            await _send_ntfy_request(
                config=mock_config,
                message="First",
                rate_limiter=rate_limiter,
            )
            await _send_ntfy_request(
                config=mock_config,
                message="Second",
                rate_limiter=rate_limiter,
            )

            first_two_duration = time.monotonic() - start
            assert first_two_duration < 0.5

            # Third should be delayed
            start = time.monotonic()
            await _send_ntfy_request(
                config=mock_config,
                message="Third",
                rate_limiter=rate_limiter,
            )
            third_duration = time.monotonic() - start

            # Should have waited for rate limit window
            assert third_duration >= 0.3

    @pytest.mark.asyncio
    async def test_rate_limiter_retry_preserves_limiting(
        self,
        mock_config: NotificationConfig,
    ) -> None:
        """Test that rate limiter is applied on retries as well."""
        # Create a response that succeeds on second attempt
        success_response = Mock()
        success_response.status = 200
        success_response.json = AsyncMock(return_value={"id": "success-id"})

        call_count = 0

        class RetryMockClientSession:
            """Mock that fails once then succeeds."""

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> RetryMockClientSession:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

            def post(self, *args: Any, **kwargs: Any) -> Any:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise aiohttp.ClientError("Temporary error")
                return MockResponse(success_response)

        rate_limiter = AsyncLimiter(10, 1.0)

        with (
            patch(
                "maverick.tools.notification.aiohttp.ClientSession",
                RetryMockClientSession,
            ),
            patch("tenacity.nap.sleep", new_callable=AsyncMock),
        ):
            success, message, notification_id = await _send_ntfy_request(
                config=mock_config,
                message="Test retry with rate limiter",
                rate_limiter=rate_limiter,
                max_retries=1,
            )

            assert success is True
            assert message == "Notification sent"
            assert notification_id == "success-id"
            # Should have made 2 attempts
            assert call_count == 2
