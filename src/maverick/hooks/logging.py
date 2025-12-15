from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from maverick.hooks.config import LoggingConfig
from maverick.hooks.types import ToolExecutionLog

logger = logging.getLogger(__name__)

# Default sensitive patterns for sanitization (FR-013)
# Order matters - more specific patterns first
DEFAULT_SENSITIVE_PATTERNS: list[tuple[str, str]] = [
    # GitHub PAT (must come before generic token pattern)
    (r"ghp_[a-zA-Z0-9]{36}", "***GITHUB_TOKEN***"),
    # OpenAI/Anthropic API keys
    (r"sk-[a-zA-Z0-9]{48}", "***API_KEY***"),
    # AWS keys
    (r"AKIA[0-9A-Z]{16}", "***AWS_KEY***"),
    # Auth headers
    (r"(bearer|authorization)\s+\S+", r"\1 ***REDACTED***"),
    # Password assignments
    (r"(password|passwd|pwd)\s*[=:]\s*\S+", r"\1=***REDACTED***"),
    # API keys
    (r"(api[_-]?key|apikey)\s*[=:]\s*\S+", r"\1=***REDACTED***"),
    # Tokens and secrets
    (r"(secret|token)\s*[=:]\s*\S+", r"\1=***REDACTED***"),
    # Base64 encoded secrets (long strings) - last as it's very broad
    (r"[a-zA-Z0-9+/]{40,}={0,2}", "***BASE64_REDACTED***"),
]

# Sensitive key names that should have their values redacted
SENSITIVE_KEYS = {
    "password",
    "passwd",
    "pwd",
    "api_key",
    "apikey",
    "api-key",
    "secret",
    "token",
    "authorization",
    "auth",
    "bearer",
    "access_token",
    "refresh_token",
    "private_key",
    "secret_key",
}


def sanitize_string(text: str, config: LoggingConfig | None = None) -> str:
    """Sanitize sensitive data from a string.

    Args:
        text: Text to sanitize.
        config: Optional logging configuration with custom patterns.

    Returns:
        Text with sensitive data redacted.
    """
    config = config or LoggingConfig()
    result = text

    # Apply specific token patterns first (GitHub, AWS, API keys)
    # First 3 patterns are specific tokens
    for pattern, replacement in DEFAULT_SENSITIVE_PATTERNS[:3]:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    # Apply generic patterns (password, api_key, secret, token assignments)
    # Use a custom function to skip already-redacted values
    for pattern, replacement in DEFAULT_SENSITIVE_PATTERNS[3:]:
        # Capture replacement in default arg to avoid late binding issue
        def replace_if_not_redacted(
            match: re.Match[str], repl: str = replacement
        ) -> str:
            # If the matched text contains ***...*** it's already redacted
            if "***" in match.group(0):
                return match.group(0)
            # Otherwise apply the replacement
            return match.expand(repl)

        result = re.sub(pattern, replace_if_not_redacted, result, flags=re.IGNORECASE)

    # Apply custom patterns
    for pattern in config.sensitive_patterns:
        try:
            result = re.sub(
                pattern, "***CUSTOM_REDACTED***", result, flags=re.IGNORECASE
            )
        except re.error:
            logger.warning(f"Invalid custom sanitization pattern: {pattern}")

    return result


def sanitize_inputs(
    inputs: dict[str, Any], config: LoggingConfig | None = None
) -> dict[str, Any]:
    """Sanitize sensitive data from input dict.

    Args:
        inputs: Input dict to sanitize.
        config: Optional logging configuration.

    Returns:
        Sanitized input dict.
    """
    config = config or LoggingConfig()

    if not config.sanitize_inputs:
        return inputs

    result: dict[str, Any] = {}
    for key, value in inputs.items():
        # Check if the key itself is sensitive
        key_lower = key.lower().replace("-", "_")
        is_sensitive_key = key_lower in SENSITIVE_KEYS

        if isinstance(value, str):
            # If key is sensitive, redact the entire value
            if is_sensitive_key:
                result[key] = "***REDACTED***"
            else:
                result[key] = sanitize_string(value, config)
        elif isinstance(value, dict):
            result[key] = sanitize_inputs(value, config)
        elif isinstance(value, list):
            result[key] = [
                sanitize_string(v, config) if isinstance(v, str) else v for v in value
            ]
        else:
            result[key] = value

    return result


def truncate_output(text: str | None, max_length: int = 1000) -> str | None:
    """Truncate output to max length with indicator.

    Args:
        text: Text to truncate.
        max_length: Maximum length.

    Returns:
        Truncated text or original if shorter.
    """
    if text is None:
        return None
    if len(text) <= max_length:
        return text
    return text[:max_length] + f"... [truncated {len(text) - max_length} chars]"


async def log_tool_execution(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
    *,
    config: LoggingConfig | None = None,
    start_time: datetime | None = None,
) -> dict[str, Any]:
    """Log tool execution with sanitized data.

    Args:
        input_data: Contains tool_name, tool_input, output, status.
        tool_use_id: SDK tool use identifier.
        context: Hook context from SDK.
        config: Optional logging configuration.
        start_time: When execution started (for duration calculation).

    Returns:
        Empty dict (no modification to flow).
    """
    config = config or LoggingConfig()

    if not config.enabled:
        return {}

    try:
        # Extract data from input
        tool_name = input_data.get("tool_name", "unknown")
        tool_input = input_data.get("tool_input", {})
        output = input_data.get("output", "")
        status = input_data.get("status", "unknown")

        # Calculate duration if start_time provided
        now = datetime.now()
        duration_ms = 0.0
        if start_time:
            duration_ms = (now - start_time).total_seconds() * 1000

        # Sanitize inputs
        sanitized = sanitize_inputs(tool_input, config)

        # Truncate output
        output_summary = truncate_output(
            str(output) if output else None, config.max_output_length
        )

        # Create log entry
        log_entry = ToolExecutionLog(
            tool_name=tool_name,
            tool_use_id=tool_use_id,
            timestamp=now,
            duration_ms=duration_ms,
            success=status == "success",
            sanitized_inputs=sanitized,
            output_summary=output_summary,
            error_summary=str(output) if status == "error" else None,
        )

        # Get the configured logger
        output_logger = logging.getLogger(config.output_destination)
        log_level = getattr(logging, config.log_level, logging.INFO)

        # Log the entry
        output_logger.log(
            log_level,
            f"Tool execution: {log_entry.tool_name} "
            f"[{log_entry.duration_ms:.1f}ms] "
            f"status={status}",
        )

        # Log detailed info at DEBUG level
        output_logger.debug(f"  Inputs: {log_entry.sanitized_inputs}")
        if output_summary:
            output_logger.debug(f"  Output: {output_summary[:100]}...")

        return {}

    except Exception as e:
        logger.error(f"Error logging tool execution: {e}")
        return {}  # Don't fail the hook, just log the error
