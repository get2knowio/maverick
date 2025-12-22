"""Example agent unit tests demonstrating mock fixture patterns.

This test file demonstrates best practices for testing agents using
the mock fixtures provided in tests.fixtures.agents.

Patterns demonstrated:
- Using mock_text_message and mock_result_message factories
- Using mock_sdk_client for agent interaction testing
- Async test patterns with pytest.mark.asyncio
- Testing message streaming and query tracking
- Error handling in agent tests
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from tests.fixtures.agents import MockMessage, MockSDKClient


class TestMockFixtures:
    """Example tests demonstrating mock fixture usage patterns."""

    def test_mock_text_message_factory(
        self, mock_text_message: Callable[..., MockMessage]
    ) -> None:
        """Test creating text messages with the factory fixture.

        Demonstrates:
        - Using the mock_text_message factory
        - Default text value
        - Custom text value
        - Message type verification
        """
        # Create with default text
        msg1 = mock_text_message()
        assert msg1.message_type == "TextMessage"
        assert msg1.text == "Response"
        assert msg1.usage is None

        # Create with custom text
        msg2 = mock_text_message("Custom message content")
        assert msg2.message_type == "TextMessage"
        assert msg2.text == "Custom message content"

    def test_mock_result_message_factory(
        self, mock_result_message: Callable[..., MockMessage]
    ) -> None:
        """Test creating result messages with the factory fixture.

        Demonstrates:
        - Using the mock_result_message factory
        - Default token usage and cost values
        - Custom values for tokens, cost, and duration
        - Accessing usage dictionary
        """
        # Create with default values
        msg1 = mock_result_message()
        assert msg1.message_type == "ResultMessage"
        assert msg1.usage == {"input_tokens": 100, "output_tokens": 200}
        assert msg1.total_cost_usd == 0.005
        assert msg1.duration_ms == 1500
        assert msg1.text is None

        # Create with custom values
        msg2 = mock_result_message(
            input_tokens=500,
            output_tokens=300,
            total_cost_usd=0.015,
            duration_ms=2000,
        )
        assert msg2.usage == {"input_tokens": 500, "output_tokens": 300}
        assert msg2.total_cost_usd == 0.015
        assert msg2.duration_ms == 2000

    @pytest.mark.asyncio
    async def test_mock_sdk_client_queue_response(
        self,
        mock_sdk_client: MockSDKClient,
        mock_text_message: Callable[..., MockMessage],
        mock_result_message: Callable[..., MockMessage],
    ) -> None:
        """Test queuing and receiving responses from mock SDK client.

        Demonstrates:
        - Queuing response sequences
        - Streaming messages via receive_response()
        - Processing both text and result messages
        - Multiple response sequences
        """
        # Queue a response sequence
        mock_sdk_client.queue_response(
            [
                mock_text_message("First response"),
                mock_text_message("Second response"),
                mock_result_message(input_tokens=150, output_tokens=250),
            ]
        )

        # Collect all messages from the stream
        messages = []
        async for msg in mock_sdk_client.receive_response():
            messages.append(msg)

        # Verify the sequence
        assert len(messages) == 3
        assert messages[0].message_type == "TextMessage"
        assert messages[0].text == "First response"
        assert messages[1].text == "Second response"
        assert messages[2].message_type == "ResultMessage"
        assert messages[2].usage["input_tokens"] == 150

    @pytest.mark.asyncio
    async def test_mock_sdk_client_query_tracking(
        self, mock_sdk_client: MockSDKClient
    ) -> None:
        """Test that queries are tracked by the mock SDK client.

        Demonstrates:
        - Using query() method
        - Tracking multiple queries
        - Verifying query_calls list
        """
        # Send queries to the client
        await mock_sdk_client.query("First prompt")
        await mock_sdk_client.query("Second prompt")
        await mock_sdk_client.query("Third prompt")

        # Verify all queries were tracked
        assert len(mock_sdk_client.query_calls) == 3
        assert mock_sdk_client.query_calls[0] == "First prompt"
        assert mock_sdk_client.query_calls[1] == "Second prompt"
        assert mock_sdk_client.query_calls[2] == "Third prompt"

    @pytest.mark.asyncio
    async def test_mock_sdk_client_error_handling(
        self,
        mock_sdk_client: MockSDKClient,
        mock_text_message: Callable[..., MockMessage],
    ) -> None:
        """Test error queue functionality in mock SDK client.

        Demonstrates:
        - Queuing errors with queue_error()
        - Errors raised during receive_response()
        - Error handling in async context
        - Messages yielded before error is raised
        """
        # Queue a response with messages followed by an error
        mock_sdk_client.queue_response(
            [
                mock_text_message("Message before error"),
            ]
        )
        mock_sdk_client.queue_error(ValueError("Simulated API error"))

        # Collect messages until error
        messages = []
        with pytest.raises(ValueError, match="Simulated API error"):
            async for msg in mock_sdk_client.receive_response():
                messages.append(msg)

        # Verify message was received before error
        assert len(messages) == 1
        assert messages[0].text == "Message before error"

    @pytest.mark.asyncio
    async def test_mock_sdk_client_multiple_response_sequences(
        self,
        mock_sdk_client: MockSDKClient,
        mock_text_message: Callable[..., MockMessage],
        mock_result_message: Callable[..., MockMessage],
    ) -> None:
        """Test handling multiple queued response sequences.

        Demonstrates:
        - Queuing multiple response sequences
        - Each receive_response() call consumes one sequence
        - Order preservation across sequences
        """
        # Queue multiple response sequences
        mock_sdk_client.queue_response([mock_text_message("First sequence")])
        mock_sdk_client.queue_response([mock_text_message("Second sequence")])
        mock_sdk_client.queue_response(
            [
                mock_text_message("Third sequence start"),
                mock_result_message(),
            ]
        )

        # First call to receive_response() gets first sequence
        messages1 = []
        async for msg in mock_sdk_client.receive_response():
            messages1.append(msg)
        assert len(messages1) == 1
        assert messages1[0].text == "First sequence"

        # Second call gets second sequence
        messages2 = []
        async for msg in mock_sdk_client.receive_response():
            messages2.append(msg)
        assert len(messages2) == 1
        assert messages2[0].text == "Second sequence"

        # Third call gets third sequence (multiple messages)
        messages3 = []
        async for msg in mock_sdk_client.receive_response():
            messages3.append(msg)
        assert len(messages3) == 2
        assert messages3[0].text == "Third sequence start"
        assert messages3[1].message_type == "ResultMessage"

    @pytest.mark.asyncio
    async def test_mock_sdk_client_context_manager(
        self, mock_sdk_client: MockSDKClient
    ) -> None:
        """Test using mock SDK client as async context manager.

        Demonstrates:
        - Using async with statement
        - Context manager entry and exit
        - Client usability within context
        """
        # Use client as async context manager
        async with mock_sdk_client as client:
            await client.query("Test prompt")
            assert len(client.query_calls) == 1

        # Client is still usable after context exit
        await mock_sdk_client.query("After context")
        assert len(mock_sdk_client.query_calls) == 2

    def test_mock_sdk_client_reset(
        self,
        mock_sdk_client: MockSDKClient,
        mock_text_message: Callable[..., MockMessage],
    ) -> None:
        """Test resetting mock SDK client state.

        Demonstrates:
        - reset() method for test isolation
        - Clearing all state (queries, responses, errors)
        - Reusability after reset
        """
        # Populate client with state
        mock_sdk_client.query_calls.append("Some query")
        mock_sdk_client.queue_response([mock_text_message("Response")])
        mock_sdk_client.queue_error(ValueError("Error"))

        # Reset should clear everything
        mock_sdk_client.reset()

        assert mock_sdk_client.query_calls == []
        assert mock_sdk_client._responses == []
        assert mock_sdk_client._errors == []
        assert mock_sdk_client._response_index == 0
        assert mock_sdk_client.options_used is None
