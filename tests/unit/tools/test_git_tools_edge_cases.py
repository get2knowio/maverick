"""Unit tests for Git MCP tools edge cases.

Covers:
- Unicode characters in output
- Large output handling

These tests mock AsyncGitRepository to isolate the MCP tools layer.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.git import DiffStats
from maverick.tools.git import create_git_tools_server

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_git_repo() -> MagicMock:
    """Create a mock AsyncGitRepository for testing git tools."""
    repo = MagicMock()
    # Default to successful results
    repo.current_branch = AsyncMock(return_value="main")
    repo.commit = AsyncMock(return_value="abc123def456")
    repo.push = AsyncMock(return_value=None)
    repo.diff_stats = AsyncMock(
        return_value=DiffStats(
            files_changed=0,
            insertions=0,
            deletions=0,
            file_list=(),
            per_file={},
        )
    )
    repo.create_branch = AsyncMock(return_value=None)
    return repo


# =============================================================================
# Edge Case Tests
# =============================================================================


@pytest.mark.asyncio
async def test_git_commit_unicode_message(mock_git_repo: MagicMock) -> None:
    """Test creating a commit with unicode message."""
    unicode_message = "feat: add 🚀 support"

    mock_git_repo.commit = AsyncMock(return_value="1234567")

    with patch(
        "maverick.tools.git.tools.commit.AsyncGitRepository",
        return_value=mock_git_repo,
    ):
        server = create_git_tools_server()
        result = await server["_tools"]["git_commit"].handler(
            {"message": "add 🚀 support", "type": "feat"}
        )

    parsed = json.loads(result["content"][0]["text"])
    assert parsed["success"] is True
    assert parsed["message"] == unicode_message
