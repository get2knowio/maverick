from datetime import datetime
from unittest.mock import patch

import pytest

from maverick.hooks.logging import LoggingConfig, log_tool_execution


@pytest.mark.asyncio
async def test_log_tool_execution_empty_return_on_error():
    """Test log_tool_execution returns empty dict on error.

    Even if logging fails, the flow should be allowed.
    """
    # Arrange
    input_data = {
        "tool_name": "test_tool",
        "tool_input": {"key": "value"},
        "output": "result",
        "status": "success",
    }
    config = LoggingConfig(enabled=True)

    # Mock sanitize_inputs to raise an exception
    with patch(
        "maverick.hooks.logging.sanitize_inputs", side_effect=Exception("Logging error")
    ):
        # Act
        result = await log_tool_execution(
            input_data, "tool-1", None, config=config, start_time=datetime.now()
        )

        # Assert
        assert result == {}  # Should return empty dict to not interrupt the flow


@pytest.mark.asyncio
async def test_log_tool_execution_disabled():
    """Test that log_tool_execution returns early if disabled."""
    # Arrange
    input_data = {"tool_name": "test"}
    config = LoggingConfig(enabled=False)

    # Act
    result = await log_tool_execution(input_data, "tool-1", None, config=config)

    # Assert
    assert result == {}
