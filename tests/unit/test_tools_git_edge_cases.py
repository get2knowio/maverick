import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio
from maverick.tools.git import create_git_tools_server, GitToolsError

@pytest.fixture
def git_tools():
    server = create_git_tools_server()
    return server["tools"]

@pytest.mark.asyncio
async def test_git_commit_timeout(git_tools):
    """Test git_commit handles timeout gracefully."""
    with patch("maverick.tools.git._verify_git_prerequisites", new_callable=AsyncMock), \
         patch("maverick.tools.git._run_git_command", side_effect=asyncio.TimeoutError):
        
        result = await git_tools["git_commit"].handler(
            {"message": "test", "type": "feat"}
        )
        
        response = result["content"][0]["text"]
        assert '"isError": true' in response
        assert "TIMEOUT" in response

@pytest.mark.asyncio
async def test_git_push_detached_head(git_tools):
    """Test git_push fails when in detached HEAD state."""
    with patch("maverick.tools.git._verify_git_prerequisites", new_callable=AsyncMock), \
         patch("maverick.tools.git._run_git_command") as mock_run:
        
        # Mock rev-parse returning HEAD (detached)
        mock_run.return_value = ("HEAD", "", 0)
        
        result = await git_tools["git_push"].handler({})
        
        response = result["content"][0]["text"]
        assert '"isError": true' in response
        assert "DETACHED_HEAD" in response

@pytest.mark.asyncio
async def test_git_create_branch_invalid_name(git_tools):
    """Test git_create_branch validates branch name."""
    with patch("maverick.tools.git._verify_git_prerequisites", new_callable=AsyncMock):
        
        # Test space
        result = await git_tools["git_create_branch"].handler({"name": "invalid name"})
        assert "INVALID_INPUT" in result["content"][0]["text"]
        
        # Test start with dot
        result = await git_tools["git_create_branch"].handler({"name": ".invalid"})
        assert "INVALID_INPUT" in result["content"][0]["text"]
        
        # Test control char
        result = await git_tools["git_create_branch"].handler({"name": "invalid\nname"})
        assert "INVALID_INPUT" in result["content"][0]["text"]

@pytest.mark.asyncio
async def test_git_push_auth_failure(git_tools):
    """Test git_push handles authentication failure."""
    with patch("maverick.tools.git._verify_git_prerequisites", new_callable=AsyncMock), \
         patch("maverick.tools.git._run_git_command") as mock_run:
        
        # First call gets branch (success)
        # Second call pushes (failure)
        mock_run.side_effect = [
            ("main", "", 0),
            ("", "Authentication failed", 128)
        ]
        
        result = await git_tools["git_push"].handler({})
        
        response = result["content"][0]["text"]
        assert '"isError": true' in response
        assert "AUTHENTICATION_REQUIRED" in response

@pytest.mark.asyncio
async def test_git_diff_stats_error(git_tools):
    """Test git_diff_stats handles errors."""
    with patch("maverick.tools.git._verify_git_prerequisites", new_callable=AsyncMock), \
         patch("maverick.tools.git._run_git_command") as mock_run:
        
        mock_run.return_value = ("", "Some error", 1)
        
        result = await git_tools["git_diff_stats"].handler({})
        
        response = result["content"][0]["text"]
        assert '"isError": true' in response
        assert "GIT_ERROR" in response
