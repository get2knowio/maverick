"""Unit tests for copilot_help activity function."""

from unittest.mock import AsyncMock, patch

import pytest

from src.models.prereq import PrereqCheckResult


@pytest.mark.asyncio
async def test_copilot_help_available():
    """Test copilot help when copilot binary is available."""
    from src.activities.copilot_help import check_copilot_help

    with patch('asyncio.create_subprocess_exec') as mock_exec:
        # Mock successful copilot help
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"GitHub Copilot CLI\n\nUsage:\n  copilot [command]\n",
            b""
        )
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        result = await check_copilot_help()

        assert isinstance(result, PrereqCheckResult)
        assert result.tool == "copilot"
        assert result.status == "pass"
        assert "available" in result.message.lower() or "ready" in result.message.lower()
        assert result.remediation is None or result.remediation == ""


@pytest.mark.asyncio
async def test_copilot_help_not_installed():
    """Test when copilot command is not found."""
    from src.activities.copilot_help import check_copilot_help

    with patch('asyncio.create_subprocess_exec') as mock_exec:
        # Mock command not found
        mock_exec.side_effect = FileNotFoundError("copilot command not found")

        result = await check_copilot_help()

        assert isinstance(result, PrereqCheckResult)
        assert result.tool == "copilot"
        assert result.status == "fail"
        assert "not installed" in result.message.lower() or "not found" in result.message.lower()
        assert result.remediation is not None
        assert "install" in result.remediation.lower()
        assert len(result.remediation) > 0


@pytest.mark.asyncio
async def test_copilot_help_command_fails():
    """Test when copilot help returns non-zero exit code."""
    from src.activities.copilot_help import check_copilot_help

    with patch('asyncio.create_subprocess_exec') as mock_exec:
        # Mock copilot help failure
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"",
            b"error: unknown command\n"
        )
        mock_process.returncode = 1
        mock_exec.return_value = mock_process

        result = await check_copilot_help()

        assert isinstance(result, PrereqCheckResult)
        assert result.tool == "copilot"
        assert result.status == "fail"
        assert "failed" in result.message.lower() or "error" in result.message.lower()


@pytest.mark.asyncio
async def test_copilot_help_timeout():
    """Test copilot command timeout handling."""
    from src.activities.copilot_help import check_copilot_help

    with patch('asyncio.create_subprocess_exec') as mock_exec:
        # Mock timeout
        mock_exec.side_effect = TimeoutError("Command timed out")

        result = await check_copilot_help()

        assert isinstance(result, PrereqCheckResult)
        assert result.tool == "copilot"
        assert result.status == "fail"
        assert "timeout" in result.message.lower() or "timed out" in result.message.lower()


@pytest.mark.asyncio
async def test_copilot_help_unexpected_error():
    """Test handling of unexpected errors."""
    from src.activities.copilot_help import check_copilot_help

    with patch('asyncio.create_subprocess_exec') as mock_exec:
        # Mock unexpected error
        mock_exec.side_effect = Exception("Unexpected error")

        result = await check_copilot_help()

        assert isinstance(result, PrereqCheckResult)
        assert result.tool == "copilot"
        assert result.status == "fail"
        assert "error" in result.message.lower()
