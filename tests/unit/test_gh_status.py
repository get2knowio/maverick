"""Unit tests for gh_status activity function."""

import pytest
from unittest.mock import AsyncMock, patch
from src.models.prereq import PrereqCheckResult, CheckStatus


@pytest.mark.asyncio
async def test_gh_status_authenticated():
    """Test gh auth status when authenticated successfully."""
    from src.activities.gh_status import check_gh_status
    
    with patch('asyncio.create_subprocess_exec') as mock_exec:
        # Mock successful gh auth status
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"Logged in to github.com as testuser\n",
            b""
        )
        mock_process.returncode = 0
        mock_exec.return_value = mock_process
        
        result = await check_gh_status()
        
        assert isinstance(result, PrereqCheckResult)
        assert result.tool == "gh"
        assert result.status == CheckStatus.PASS
        assert "authenticated" in result.message.lower() or "logged in" in result.message.lower()
        assert result.remediation is None or result.remediation == ""


@pytest.mark.asyncio
async def test_gh_status_not_authenticated():
    """Test gh auth status when not authenticated."""
    from src.activities.gh_status import check_gh_status
    
    with patch('asyncio.create_subprocess_exec') as mock_exec:
        # Mock unauthenticated gh auth status
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"",
            b"You are not logged into any GitHub hosts. Run gh auth login to authenticate.\n"
        )
        mock_process.returncode = 1
        mock_exec.return_value = mock_process
        
        result = await check_gh_status()
        
        assert isinstance(result, PrereqCheckResult)
        assert result.tool == "gh"
        assert result.status == CheckStatus.FAIL
        assert "not authenticated" in result.message.lower() or "not logged in" in result.message.lower()
        assert result.remediation is not None
        assert len(result.remediation) > 0
        assert "gh auth login" in result.remediation


@pytest.mark.asyncio
async def test_gh_status_not_installed():
    """Test when gh command is not found."""
    from src.activities.gh_status import check_gh_status
    
    with patch('asyncio.create_subprocess_exec') as mock_exec:
        # Mock command not found
        mock_exec.side_effect = FileNotFoundError("gh command not found")
        
        result = await check_gh_status()
        
        assert isinstance(result, PrereqCheckResult)
        assert result.tool == "gh"
        assert result.status == CheckStatus.FAIL
        assert "not installed" in result.message.lower() or "not found" in result.message.lower()
        assert result.remediation is not None
        assert "install" in result.remediation.lower()


@pytest.mark.asyncio
async def test_gh_status_timeout():
    """Test gh command timeout handling."""
    from src.activities.gh_status import check_gh_status
    
    with patch('asyncio.create_subprocess_exec') as mock_exec:
        # Mock timeout
        mock_exec.side_effect = TimeoutError("Command timed out")
        
        result = await check_gh_status()
        
        assert isinstance(result, PrereqCheckResult)
        assert result.tool == "gh"
        assert result.status == CheckStatus.FAIL
        assert "timeout" in result.message.lower() or "timed out" in result.message.lower()


@pytest.mark.asyncio
async def test_gh_status_unexpected_error():
    """Test handling of unexpected errors."""
    from src.activities.gh_status import check_gh_status
    
    with patch('asyncio.create_subprocess_exec') as mock_exec:
        # Mock unexpected error
        mock_exec.side_effect = Exception("Unexpected error")
        
        result = await check_gh_status()
        
        assert isinstance(result, PrereqCheckResult)
        assert result.tool == "gh"
        assert result.status == CheckStatus.FAIL
        assert "error" in result.message.lower()
