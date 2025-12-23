"""Unit tests for GitHub tools helper functions.

Tests: error_response, success_response, classify_error, parse_rate_limit_wait.
"""

from __future__ import annotations

import json

from maverick.tools.github.errors import classify_error as _classify_error
from maverick.tools.github.errors import parse_rate_limit_wait as _parse_rate_limit_wait
from maverick.tools.github.responses import error_response as _error_response
from maverick.tools.github.responses import success_response as _success_response


class TestHelperFunctions:
    """Tests for helper functions in github tools module (T010)."""

    # -------------------------------------------------------------------------
    # _parse_rate_limit_wait tests
    # -------------------------------------------------------------------------

    def test_parse_rate_limit_retry_after_pattern(self) -> None:
        """Test parsing 'retry after N' pattern."""
        stderr = "API rate limit exceeded. retry after 120 seconds"
        result = _parse_rate_limit_wait(stderr)
        assert result == 120

    def test_parse_rate_limit_wait_pattern(self) -> None:
        """Test parsing 'wait Ns' pattern."""
        stderr = "Rate limit hit, please wait 60s before retrying"
        result = _parse_rate_limit_wait(stderr)
        assert result == 60

    def test_parse_rate_limit_seconds_pattern(self) -> None:
        """Test parsing 'N seconds' pattern."""
        stderr = "GitHub API rate limit. Try again in 45 seconds"
        result = _parse_rate_limit_wait(stderr)
        assert result == 45

    def test_parse_rate_limit_no_match_returns_default(self) -> None:
        """Test rate limit present but no time returns default 60s."""
        stderr = "API rate limit exceeded"
        result = _parse_rate_limit_wait(stderr)
        assert result == 60

    def test_parse_rate_limit_non_rate_limit_error(self) -> None:
        """Test non-rate-limit message returns None."""
        stderr = "Authentication required"
        result = _parse_rate_limit_wait(stderr)
        assert result is None

    # -------------------------------------------------------------------------
    # _success_response tests
    # -------------------------------------------------------------------------

    def test_success_response_format(self) -> None:
        """Test success response has correct MCP format with content array."""
        data = {"pr_number": 123, "url": "https://github.com/owner/repo/pull/123"}
        result = _success_response(data)

        # Verify MCP structure
        assert "content" in result
        assert isinstance(result["content"], list)
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert "text" in result["content"][0]

        # Verify data is JSON serialized
        parsed = json.loads(result["content"][0]["text"])
        assert parsed == data

    def test_success_response_json_serialization(self) -> None:
        """Test success response correctly serializes complex data."""
        data = {
            "issues": [
                {"number": 1, "title": "Bug", "labels": ["bug", "priority-high"]},
                {"number": 2, "title": "Feature", "labels": []},
            ],
            "count": 2,
        }
        result = _success_response(data)

        # Verify JSON round-trip
        parsed = json.loads(result["content"][0]["text"])
        assert parsed == data
        assert len(parsed["issues"]) == 2
        assert parsed["issues"][0]["labels"] == ["bug", "priority-high"]

    # -------------------------------------------------------------------------
    # _error_response tests
    # -------------------------------------------------------------------------

    def test_error_response_basic(self) -> None:
        """Test error response basic structure."""
        message = "Issue not found"
        error_code = "NOT_FOUND"
        result = _error_response(message, error_code)

        # Verify MCP structure
        assert "content" in result
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"

        # Parse error data
        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["message"] == message
        assert error_data["error_code"] == error_code
        assert "retry_after_seconds" not in error_data

    def test_error_response_with_retry_after(self) -> None:
        """Test error response includes retry_after when provided."""
        message = "Rate limit exceeded"
        error_code = "RATE_LIMIT"
        retry_after = 120
        result = _error_response(message, error_code, retry_after_seconds=retry_after)

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["message"] == message
        assert error_data["error_code"] == error_code
        assert error_data["retry_after_seconds"] == 120

    def test_error_response_without_retry_after(self) -> None:
        """Test error response excludes retry_after when None."""
        message = "Network error"
        error_code = "NETWORK_ERROR"
        result = _error_response(message, error_code, retry_after_seconds=None)

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == error_code
        assert "retry_after_seconds" not in error_data

    # -------------------------------------------------------------------------
    # _classify_error tests
    # -------------------------------------------------------------------------

    def test_classify_error_not_found(self) -> None:
        """Test classification of 'not found' errors."""
        stderr = "could not find pull request #999"
        message, error_code, retry_after = _classify_error(stderr)

        assert error_code == "NOT_FOUND"
        assert "not found" in message.lower() or "could not find" in message.lower()
        assert retry_after is None

    def test_classify_error_rate_limit(self) -> None:
        """Test classification of rate limit errors with retry_after."""
        stderr = "API rate limit exceeded. retry after 90 seconds"
        message, error_code, retry_after = _classify_error(stderr)

        assert error_code == "RATE_LIMIT"
        assert "rate limit" in message.lower()
        assert retry_after == 90
        assert "90" in message

    def test_classify_error_auth(self) -> None:
        """Test classification of authentication errors."""
        stderr = "authentication required - please login"
        message, error_code, retry_after = _classify_error(stderr)

        assert error_code == "AUTH_ERROR"
        assert "gh auth login" in message
        assert retry_after is None

    def test_classify_error_network(self) -> None:
        """Test classification of network errors."""
        stderr = "network error: connection refused"
        message, error_code, retry_after = _classify_error(stderr)

        assert error_code == "NETWORK_ERROR"
        assert "network" in message.lower()
        assert retry_after is None

    def test_classify_error_network_connection(self) -> None:
        """Test classification of connection errors."""
        stderr = "connection timeout - unable to reach server"
        message, error_code, retry_after = _classify_error(stderr)

        assert error_code == "NETWORK_ERROR"
        assert "connection" in message.lower()
        assert retry_after is None

    def test_classify_error_timeout(self) -> None:
        """Test classification of timeout errors."""
        stderr = "request timeout after 30 seconds"
        message, error_code, retry_after = _classify_error(stderr)

        assert error_code == "TIMEOUT"
        assert "timeout" in message.lower()
        assert retry_after is None

    def test_classify_error_internal(self) -> None:
        """Test classification of unknown/internal errors."""
        stderr = "unexpected server error occurred"
        message, error_code, retry_after = _classify_error(stderr)

        assert error_code == "INTERNAL_ERROR"
        assert message == stderr
        assert retry_after is None

    def test_classify_error_uses_stdout_when_stderr_empty(self) -> None:
        """Test error classification uses stdout when stderr is empty."""
        stdout = "not found"
        stderr = ""
        message, error_code, retry_after = _classify_error(stderr, stdout)

        assert error_code == "NOT_FOUND"
        assert message == stdout

    def test_classify_error_unauthorized(self) -> None:
        """Test classification of unauthorized errors."""
        stderr = "unauthorized access - invalid credentials"
        message, error_code, retry_after = _classify_error(stderr)

        assert error_code == "AUTH_ERROR"
        assert "gh auth login" in message
        assert retry_after is None

    def test_classify_error_case_insensitive(self) -> None:
        """Test error classification is case-insensitive."""
        stderr = "RATE LIMIT EXCEEDED. RETRY AFTER 60 SECONDS"
        message, error_code, retry_after = _classify_error(stderr)

        assert error_code == "RATE_LIMIT"
        assert retry_after == 60


# =============================================================================
# T009: Prerequisite Verification Tests
# =============================================================================
