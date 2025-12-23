"""Unit tests for Git MCP tools edge cases.

Covers:
- Unicode characters in output
- Large output handling

These tests mock GitRunner to isolate the MCP tools layer.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.runners.git import DiffStats, GitResult
from maverick.tools.git import create_git_tools_server

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_git_runner() -> MagicMock:
    """Create a mock GitRunner for testing git tools."""
    runner = MagicMock()
    # Default to successful results
    runner.is_inside_repo = AsyncMock(return_value=True)
    runner.add = AsyncMock(
        return_value=GitResult(success=True, output="", error=None, duration_ms=10)
    )
    runner.commit = AsyncMock(
        return_value=GitResult(success=True, output="", error=None, duration_ms=10)
    )
    runner.get_head_sha = AsyncMock(return_value="abc123def456")
    runner.get_current_branch = AsyncMock(return_value="main")
    runner.push = AsyncMock(
        return_value=GitResult(
            success=True, output="main -> main", error=None, duration_ms=100
        )
    )
    runner.get_diff_stats = AsyncMock(
        return_value=DiffStats(files_changed=0, insertions=0, deletions=0, per_file={})
    )
    runner.create_branch = AsyncMock(
        return_value=GitResult(
            success=True, output="Switched to a new branch", error=None, duration_ms=10
        )
    )
    return runner


# =============================================================================
# Edge Case Tests
# =============================================================================


@pytest.mark.asyncio
async def test_git_commit_unicode_message(mock_git_runner: MagicMock) -> None:
    """Test creating a commit with unicode message."""
    unicode_message = "feat: add 🚀 support"

    mock_git_runner.get_head_sha = AsyncMock(return_value="1234567")

    with patch("maverick.tools.git.GitRunner", return_value=mock_git_runner):
        server = create_git_tools_server()
        result = await server["tools"]["git_commit"].handler(
            {"message": "add 🚀 support", "type": "feat"}
        )

    parsed = json.loads(result["content"][0]["text"])
    assert parsed["success"] is True
    assert parsed["message"] == unicode_message
