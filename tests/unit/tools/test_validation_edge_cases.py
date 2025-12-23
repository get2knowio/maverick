"""Unit tests for Validation MCP tools edge cases.

Covers:
- Commands writing to both stdout and stderr simultaneously
- Interleaved stdout/stderr handling (concatenation behavior)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from maverick.config import ValidationConfig
from maverick.tools.validation import create_validation_tools_server


@pytest.fixture
def mock_process() -> Mock:
    """Create a mock subprocess."""
    process = Mock()
    process.returncode = 0
    process.communicate = AsyncMock(return_value=(b"", b""))
    process.kill = Mock()
    return process


@pytest.fixture
def mock_subprocess_exec(mock_process: Mock) -> AsyncMock:
    """Create a mock for asyncio.create_subprocess_exec."""
    return AsyncMock(return_value=mock_process)


@pytest.fixture
def validation_config() -> ValidationConfig:
    """Create a basic ValidationConfig."""
    return ValidationConfig()


@pytest.mark.asyncio
async def test_stdout_and_stderr_simultaneous(
    mock_subprocess_exec: AsyncMock,
    mock_process: Mock,
    validation_config: ValidationConfig,
) -> None:
    """Test commands that write to both stdout AND stderr simultaneously."""
    # Simulate both streams having data
    stdout_data = b"Standard Output"
    stderr_data = b"Error Output"
    mock_process.communicate.return_value = (stdout_data, stderr_data)
    mock_process.returncode = 1  # Usually stderr implies some issue

    server = create_validation_tools_server(config=validation_config)
    # Access tools directly
    run_validation = server["_tools"]["run_validation"]

    with patch("asyncio.create_subprocess_exec", mock_subprocess_exec):
        response = await run_validation.handler({"types": ["test"]})

    response_data = json.loads(response["content"][0]["text"])
    result = response_data["results"][0]

    # Check that both outputs are present in the result
    assert "Standard Output" in result["output"]
    assert "Error Output" in result["output"]
    # Verify concatenation order (implementation detail: stdout then stderr)
    assert result["output"] == "Standard Output\nError Output"


@pytest.mark.asyncio
async def test_interleaved_output_handling(
    mock_subprocess_exec: AsyncMock,
    mock_process: Mock,
    validation_config: ValidationConfig,
) -> None:
    """Test commands that produce 'interleaved' output (captured separately).

    Since communicate() separates streams, we verify that we capture large amounts
    of data on both streams without hanging or losing data.
    """
    # Simulate large output on both
    large_stdout = b"out\n" * 1000
    large_stderr = b"err\n" * 1000
    mock_process.communicate.return_value = (large_stdout, large_stderr)

    server = create_validation_tools_server(config=validation_config)
    run_validation = server["_tools"]["run_validation"]

    with patch("asyncio.create_subprocess_exec", mock_subprocess_exec):
        response = await run_validation.handler({"types": ["test"]})

    response_data = json.loads(response["content"][0]["text"])
    result = response_data["results"][0]

    assert len(result["output"]) >= len(large_stdout) + len(large_stderr)
    assert result["output"].startswith("out\n")
    assert result["output"].endswith("err")
