"""Unit tests for GitHub PR diff MCP tool.

Tests the github_get_pr_diff tool.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from maverick.tools.github import github_get_pr_diff


class TestGitHubGetPRDiff:
    """Tests for github_get_pr_diff tool (T031-T033)."""

    @pytest.mark.asyncio
    async def test_github_get_pr_diff_normal_retrieval(self) -> None:
        """Test getting a PR diff successfully with mocked gh CLI (T031).

        Verifies:
        - Successful diff retrieval
        - Correct command execution
        - Proper response structure
        - truncated=false for small diffs
        """
        pr_number = 123
        mock_diff = """diff --git a/file.py b/file.py
index 1234567..abcdefg 100644
--- a/file.py
+++ b/file.py
@@ -1,3 +1,4 @@
+# New comment
 def hello():
     print("Hello, World!")
"""

        with patch(
            "maverick.tools.github.tools.diffs.run_gh_command", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = (mock_diff, "", 0)

            result = await github_get_pr_diff.handler({"pr_number": pr_number})

            # Verify command execution
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0]
            assert call_args[0] == "pr"
            assert call_args[1] == "diff"
            assert call_args[2] == str(pr_number)

        # Verify success response structure
        assert "content" in result
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"

        # Parse response data
        response_data = json.loads(result["content"][0]["text"])

        # Verify response fields
        assert "diff" in response_data
        assert response_data["diff"] == mock_diff
        assert response_data["truncated"] is False
        assert "warning" not in response_data
        assert "original_size_bytes" not in response_data

    @pytest.mark.asyncio
    async def test_github_get_pr_diff_truncated_case(self) -> None:
        """Test that large diffs are truncated properly with truncated flag (T032).

        Verifies:
        - Diff truncated at max_size boundary
        - truncated=true flag set
        - Warning message included
        - original_size_bytes included
        """
        pr_number = 456
        # Create a large diff (larger than default 100KB)
        large_diff = (
            "diff --git a/file.py b/file.py\n" + ("+" + "x" * 1000 + "\n") * 150
        )  # ~150KB
        max_size = 50000  # 50KB limit

        with patch(
            "maverick.tools.github.tools.diffs.run_gh_command", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = (large_diff, "", 0)

            result = await github_get_pr_diff.handler(
                {"pr_number": pr_number, "max_size": max_size}
            )

            # Verify command execution
            mock_run.assert_called_once()

        # Parse response data
        response_data = json.loads(result["content"][0]["text"])

        # Verify truncation
        assert response_data["truncated"] is True
        assert "warning" in response_data
        assert "truncated" in response_data["warning"].lower()
        assert "original_size_bytes" in response_data
        assert response_data["original_size_bytes"] == len(large_diff.encode("utf-8"))

        # Verify diff was actually truncated
        diff_size = len(response_data["diff"].encode("utf-8"))
        assert diff_size <= max_size
        original_size = response_data["original_size_bytes"]
        assert original_size > max_size

    @pytest.mark.asyncio
    async def test_github_get_pr_diff_not_found(self) -> None:
        """Test error handling when PR doesn't exist (T033).

        Verifies:
        - NOT_FOUND error code
        - Proper error message with PR number
        - Error response structure
        """
        pr_number = 999

        with patch(
            "maverick.tools.github.tools.diffs.run_gh_command", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = ("", "pull request not found", 1)

            result = await github_get_pr_diff.handler({"pr_number": pr_number})

        # Parse error response
        response_data = json.loads(result["content"][0]["text"])

        # Verify error response
        assert response_data["isError"] is True
        assert response_data["error_code"] == "NOT_FOUND"
        assert (
            f"#{pr_number}" in response_data["message"]
            or str(pr_number) in response_data["message"]
        )
        assert "not found" in response_data["message"].lower()

    @pytest.mark.asyncio
    async def test_github_get_pr_diff_utf8_truncation(self) -> None:
        """Test UTF-8 truncation works correctly with multibyte characters.

        Verifies:
        - Diff with multibyte UTF-8 characters truncated at byte boundary
        - No broken characters in truncated output
        - Proper handling of UTF-8 decoding errors
        """
        pr_number = 789
        # Create diff with multibyte UTF-8 characters (emoji, Chinese, etc.)
        unicode_diff = "diff --git a/file.py b/file.py\n"
        unicode_diff += "+# Unicode test: 🚀 火箭 αβγδ " + "x" * 5000 + "\n"
        unicode_diff += "+# More content: 中文字符 " + "y" * 5000 + "\n"

        # Set max_size to potentially split in the middle of multibyte char
        max_size = 5100

        with patch(
            "maverick.tools.github.tools.diffs.run_gh_command", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = (unicode_diff, "", 0)

            result = await github_get_pr_diff.handler(
                {"pr_number": pr_number, "max_size": max_size}
            )

        response_data = json.loads(result["content"][0]["text"])

        # Verify truncation occurred
        assert response_data["truncated"] is True

        # Verify the truncated diff is valid UTF-8 (no broken characters)
        truncated_diff = response_data["diff"]
        # Should be able to encode back to UTF-8 without errors
        encoded = truncated_diff.encode("utf-8")
        assert len(encoded) <= max_size

        # Verify no broken characters by checking we can decode what we encoded
        assert encoded.decode("utf-8") == truncated_diff

    @pytest.mark.asyncio
    async def test_github_get_pr_diff_invalid_pr_number(self) -> None:
        """Test invalid pr_number (<=0) returns INVALID_INPUT error.

        Verifies:
        - Negative PR numbers rejected
        - Zero PR number rejected
        - INVALID_INPUT error code
        - Appropriate error message
        """
        # Test with negative number
        result = await github_get_pr_diff.handler({"pr_number": -1})

        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "positive" in response_data["message"].lower()

        # Test with zero
        result = await github_get_pr_diff.handler({"pr_number": 0})

        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "positive" in response_data["message"].lower()
