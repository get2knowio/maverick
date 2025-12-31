from unittest.mock import patch

import pytest

from maverick.hooks.safety import (
    SafetyConfig,
    validate_bash_command,
    validate_file_write,
)


@pytest.mark.asyncio
async def test_validate_bash_command_fail_open():
    """Test validate_bash_command fails open on exception by default."""
    # Arrange
    input_data = {"tool_input": {"command": "ls -la"}}
    config = SafetyConfig(fail_closed=False)

    # Mock normalize_command to raise an exception
    with patch(
        "maverick.hooks.safety.normalize_command",
        side_effect=Exception("Unexpected error"),
    ):
        # Act
        result = await validate_bash_command(input_data, "tool-1", None, config=config)

        # Assert
        assert result == {}  # Empty dict means allow


@pytest.mark.asyncio
async def test_validate_bash_command_fail_closed():
    """Test validate_bash_command fails closed on exception when configured."""
    # Arrange
    input_data = {"tool_input": {"command": "ls -la"}}
    config = SafetyConfig(fail_closed=True)

    # Mock normalize_command to raise an exception
    with patch(
        "maverick.hooks.safety.normalize_command",
        side_effect=Exception("Unexpected error"),
    ):
        # Act
        result = await validate_bash_command(input_data, "tool-1", None, config=config)

        # Assert
        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert result["hookSpecificOutput"]["permissionDecisionReason"].startswith(
            "Hook validation error"
        )


@pytest.mark.asyncio
async def test_validate_file_write_fail_open():
    """Test validate_file_write fails open on exception by default."""
    # Arrange
    input_data = {"tool_input": {"file_path": "/some/path"}}
    config = SafetyConfig(fail_closed=False)

    # Mock normalize_path to raise an exception
    with patch(
        "maverick.hooks.safety.normalize_path",
        side_effect=Exception("Unexpected error"),
    ):
        # Act
        result = await validate_file_write(input_data, "tool-1", None, config=config)

        # Assert
        assert result == {}  # Empty dict means allow


@pytest.mark.asyncio
async def test_validate_file_write_fail_closed():
    """Test validate_file_write fails closed on exception when configured."""
    # Arrange
    input_data = {"tool_input": {"file_path": "/some/path"}}
    config = SafetyConfig(fail_closed=True)

    # Mock normalize_path to raise an exception
    with patch(
        "maverick.hooks.safety.normalize_path",
        side_effect=Exception("Unexpected error"),
    ):
        # Act
        result = await validate_file_write(input_data, "tool-1", None, config=config)

        # Assert
        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert result["hookSpecificOutput"]["permissionDecisionReason"].startswith(
            "Hook validation error"
        )
