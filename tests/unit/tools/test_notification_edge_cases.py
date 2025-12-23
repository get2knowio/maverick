"""Unit tests for Notification MCP tools edge cases.

Covers:
- ntfy.sh returning non-200 status with valid JSON body
- Response when server returns malformed JSON
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest

from maverick.config import NotificationConfig
from maverick.tools.notification import _send_ntfy_request


@pytest.fixture
def mock_config() -> NotificationConfig:
    """Create a test notification configuration."""
    return NotificationConfig(
        enabled=True,
        server="https://ntfy.sh",
        topic="test-topic",
    )


class MockResponse:
    """Mock aiohttp response for testing."""

    def __init__(self, status: int, json_data: Any = None, text_data: str = "") -> None:
        self.status = status
        self._json_data = json_data
        self._text_data = text_data

    async def __aenter__(self) -> MockResponse:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def json(self) -> Any:
        if self._json_data is None:
            raise aiohttp.ContentTypeError(
                Mock(), Mock(), history=()
            )  # Simulate invalid JSON
        return self._json_data

    async def text(self) -> str:
        return self._text_data


class MockClientSession:
    """Mock aiohttp ClientSession for testing."""

    def __init__(self, response: MockResponse, *args: Any, **kwargs: Any) -> None:
        self.response = response
        self.post_calls: list[tuple[Any, ...]] = []

    async def __aenter__(self) -> MockClientSession:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    def post(self, *args: Any, **kwargs: Any) -> MockResponse:
        self.post_calls.append((args, kwargs))
        return self.response


@pytest.mark.asyncio
async def test_send_request_non_200_with_json(
    mock_config: NotificationConfig,
) -> None:
    """Test ntfy.sh returning non-200 status with valid JSON body."""
    # Simulate 400 Bad Request with JSON body
    error_json = {"code": 40001, "error": "invalid_topic", "link": "..."}
    mock_response = MockResponse(
        status=400,
        json_data=error_json,
        text_data='{"code":40001,"error":"invalid_topic","link":"..."}',
    )
    mock_session = MockClientSession(mock_response)

    # Mock asyncio.sleep to avoid delays
    with (
        patch(
            "maverick.tools.notification.aiohttp.ClientSession",
            return_value=mock_session,
        ),
        patch("maverick.tools.notification.asyncio.sleep", new_callable=AsyncMock),
    ):
        success, message, notification_id = await _send_ntfy_request(
            config=mock_config,
            message="Test message",
            max_retries=1,
        )

        # Should fail gracefully (return success=True but message indicates failure)
        assert success is True
        assert message == "Notification not delivered"
        assert notification_id is None

        # Should have retried
        assert len(mock_session.post_calls) == 2


@pytest.mark.asyncio
async def test_send_request_malformed_json(
    mock_config: NotificationConfig,
) -> None:
    """Test response when server returns malformed JSON on 200 OK."""
    # Simulate 200 OK but json() raises error
    mock_response = MockResponse(status=200, json_data=None, text_data="invalid-json")

    # We need to make sure json() raises exception.
    # MockResponse.json() raises ContentTypeError if _json_data is None

    mock_session = MockClientSession(mock_response)

    with (
        patch(
            "maverick.tools.notification.aiohttp.ClientSession",
            return_value=mock_session,
        ),
        patch("maverick.tools.notification.asyncio.sleep", new_callable=AsyncMock),
    ):
        success, message, notification_id = await _send_ntfy_request(
            config=mock_config,
            message="Test message",
            max_retries=1,
        )

        # Should fail gracefully
        assert success is True
        assert message == "Notification not delivered"
        assert notification_id is None

        # Should have retried
        assert len(mock_session.post_calls) == 2
