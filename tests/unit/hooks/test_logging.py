from __future__ import annotations

from datetime import datetime

import pytest

from maverick.hooks.config import LoggingConfig
from maverick.hooks.logging import (
    log_tool_execution,
    sanitize_inputs,
    sanitize_string,
    truncate_output,
)


class TestSanitizeString:
    """Tests for sensitive pattern sanitization."""

    def test_sanitizes_password(self) -> None:
        """Test password redaction."""
        text = "password=secret123"
        result = sanitize_string(text)
        assert "secret123" not in result
        assert "REDACTED" in result

    def test_sanitizes_api_key(self) -> None:
        """Test API key redaction."""
        text = "api_key=my_super_secret_key"
        result = sanitize_string(text)
        assert "my_super_secret_key" not in result
        assert "REDACTED" in result

    def test_sanitizes_bearer_token(self) -> None:
        """Test bearer token redaction."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIs"
        result = sanitize_string(text)
        assert "eyJhbGciOiJIUzI1NiIs" not in result
        assert "REDACTED" in result

    def test_sanitizes_github_token(self) -> None:
        """Test GitHub PAT redaction."""
        text = "token: ghp_abcdefghijklmnopqrstuvwxyz123456ABCD"
        result = sanitize_string(text)
        assert "ghp_" not in result
        assert "GITHUB_TOKEN" in result

    def test_sanitizes_aws_key(self) -> None:
        """Test AWS key redaction."""
        text = "aws_key: AKIAIOSFODNN7EXAMPLE"
        result = sanitize_string(text)
        assert "AKIAIOSFODNN7" not in result
        assert "AWS_KEY" in result

    def test_preserves_normal_text(self) -> None:
        """Test that normal text is preserved."""
        text = "This is a normal message without secrets"
        result = sanitize_string(text)
        assert result == text

    def test_custom_patterns(self) -> None:
        """Test custom sanitization patterns."""
        config = LoggingConfig(sensitive_patterns=[r"custom_\w+"])
        text = "data: custom_secret_value"
        result = sanitize_string(text, config)
        assert "custom_secret_value" not in result
        assert "CUSTOM_REDACTED" in result


class TestTruncateOutput:
    """Tests for output truncation."""

    def test_short_text_unchanged(self) -> None:
        """Test that short text is not truncated."""
        text = "Short output"
        result = truncate_output(text, max_length=100)
        assert result == text

    def test_long_text_truncated(self) -> None:
        """Test that long text is truncated."""
        text = "x" * 2000
        result = truncate_output(text, max_length=100)
        assert len(result) < 200
        assert "truncated" in result
        assert "1900 chars" in result

    def test_none_returns_none(self) -> None:
        """Test that None input returns None."""
        result = truncate_output(None)
        assert result is None


class TestSanitizeInputs:
    """Tests for input dict sanitization."""

    def test_sanitizes_string_values(self) -> None:
        """Test sanitizing string values in dict."""
        inputs = {"command": "export API_KEY=secret123"}
        result = sanitize_inputs(inputs)
        assert "secret123" not in str(result)

    def test_sanitizes_nested_dicts(self) -> None:
        """Test sanitizing nested dictionaries."""
        inputs = {"config": {"password": "secret"}}
        result = sanitize_inputs(inputs)
        assert "secret" not in str(result)

    def test_preserves_non_string_values(self) -> None:
        """Test that non-string values are preserved."""
        inputs = {"count": 42, "enabled": True}
        result = sanitize_inputs(inputs)
        assert result["count"] == 42
        assert result["enabled"] is True

    def test_respects_disabled_sanitization(self) -> None:
        """Test that sanitization can be disabled."""
        config = LoggingConfig(sanitize_inputs=False)
        inputs = {"password": "secret123"}
        result = sanitize_inputs(inputs, config)
        assert result["password"] == "secret123"


class TestLogToolExecution:
    """Tests for log entry creation."""

    @pytest.mark.asyncio
    async def test_creates_log_entry(self) -> None:
        """Test basic log entry creation."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "output": "total 16...",
            "status": "success",
        }
        result = await log_tool_execution(input_data, "123", None)
        assert result == {}  # Hook returns empty dict

    @pytest.mark.asyncio
    async def test_sanitizes_log_inputs(self) -> None:
        """Test that log inputs are sanitized."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "export PASSWORD=secret123"},
            "output": "",
            "status": "success",
        }
        # This should not raise and should sanitize
        result = await log_tool_execution(input_data, None, None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_truncates_long_output(self) -> None:
        """Test that long output is truncated."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "cat large_file"},
            "output": "x" * 5000,
            "status": "success",
        }
        result = await log_tool_execution(input_data, None, None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_handles_error_status(self) -> None:
        """Test handling error status."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "invalid"},
            "output": "command not found",
            "status": "error",
        }
        result = await log_tool_execution(input_data, None, None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_respects_disabled_logging(self) -> None:
        """Test that logging can be disabled."""
        config = LoggingConfig(enabled=False)
        input_data = {
            "tool_name": "Bash",
            "tool_input": {},
            "status": "success",
        }
        result = await log_tool_execution(input_data, None, None, config=config)
        assert result == {}

    @pytest.mark.asyncio
    async def test_calculates_duration(self) -> None:
        """Test duration calculation."""
        input_data = {
            "tool_name": "Bash",
            "tool_input": {},
            "status": "success",
        }
        start = datetime.now()
        result = await log_tool_execution(input_data, None, None, start_time=start)
        assert result == {}
