"""Unit tests for Git MCP tools edge cases.

Covers:
- Unicode characters in output
- Large output handling
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.tools.git import create_git_tools_server, _run_git_command

# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_subprocess() -> MagicMock:
    """Create a mock subprocess."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    return mock_proc

@pytest.fixture
def mock_create_subprocess_exec(mock_subprocess: MagicMock) -> AsyncMock:
    """Create a mock for asyncio.create_subprocess_exec."""
    return AsyncMock(return_value=mock_subprocess)


# =============================================================================
# Edge Case Tests
# =============================================================================

@pytest.mark.asyncio
async def test_git_output_unicode(
    mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
) -> None:
    """Test git command with unicode characters in output."""
    # Unicode chars: Emoji, CJK, etc.
    unicode_output = "Files changed: 📝 README.md, 測試.py"
    mock_subprocess.communicate.return_value = (unicode_output.encode("utf-8"), b"")
    mock_subprocess.returncode = 0

    with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
        stdout, stderr, returncode = await _run_git_command("status")

    assert stdout == unicode_output
    assert returncode == 0


@pytest.mark.asyncio
async def test_git_output_large(
    mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
) -> None:
    """Test git command with very large output."""
    # Generate 1MB of output
    large_output = "line\n" * 100000
    mock_subprocess.communicate.return_value = (large_output.encode("utf-8"), b"")
    mock_subprocess.returncode = 0

    with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
        stdout, stderr, returncode = await _run_git_command("log")

    assert len(stdout) == len(large_output.strip())
    assert stdout == large_output.strip()

@pytest.mark.asyncio
async def test_git_commit_unicode_message(
    mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
) -> None:
    """Test creating a commit with unicode message."""
    unicode_message = "feat: add 🚀 support"
    
    # Mock successful commit
    mock_subprocess.communicate.side_effect = [
        (f"[main 1234567] {unicode_message}\n".encode("utf-8"), b""), # commit output
        (b"1234567\n", b"") # rev-parse output
    ]
    
    with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
        server = create_git_tools_server()
        result = await server["tools"]["git_commit"].handler(
            {"message": "add 🚀 support", "type": "feat"}
        )

    parsed = json.loads(result["content"][0]["text"])
    assert parsed["success"] is True
    assert parsed["message"] == unicode_message

