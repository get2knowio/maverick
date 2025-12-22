"""Security utilities for scrubbing secrets from text.

This module provides functions to detect and redact sensitive information
such as API keys, tokens, passwords, and other credentials from text that
might be logged or displayed.
"""

from __future__ import annotations

import re

# Compiled regex patterns for various secret types
_GITHUB_PAT_PATTERN = re.compile(r"gh[ps]_[a-zA-Z0-9]{36,}")
_OPENAI_ANTHROPIC_KEY_PATTERN = re.compile(r"sk-[a-zA-Z0-9]{32,}")
_AWS_KEY_PATTERN = re.compile(r"AKIA[0-9A-Z]{16}")
_BEARER_TOKEN_PATTERN = re.compile(
    r"(?i)(bearer\s+|authorization:\s*bearer\s+)[a-zA-Z0-9._\-]+", re.IGNORECASE
)

# Generic credential patterns (case-insensitive)
_CREDENTIAL_PATTERNS = [
    # API key patterns
    re.compile(r"(?i)(api[_\-]?key)\s*[:=]\s*([a-zA-Z0-9_\-]{8,})", re.IGNORECASE),
    re.compile(r"(?i)(apikey)\s*[:=]\s*([a-zA-Z0-9_\-]{8,})", re.IGNORECASE),
    # Secret patterns
    re.compile(r"(?i)(secret)\s*[:=]\s*([a-zA-Z0-9_\-@!#$%^&*]{8,})", re.IGNORECASE),
    # Token patterns
    re.compile(r"(?i)(token)\s*[:=]\s*([a-zA-Z0-9_\-]{8,})", re.IGNORECASE),
    # Password patterns
    re.compile(
        r"(?i)(password|passwd|pwd)\s*[:=]\s*([a-zA-Z0-9_\-@!#$%^&*]{6,})",
        re.IGNORECASE,
    ),
    # Credentials pattern
    re.compile(r"(?i)(credentials)\s*[:=]\s*([a-zA-Z0-9_\-]{8,})", re.IGNORECASE),
]


def scrub_secrets(text: str) -> str:
    """Remove potential secrets from text.

    This function replaces various types of secrets with redaction markers:
    - GitHub PATs (ghp_, ghs_, gho_) -> ***GITHUB_TOKEN***
    - OpenAI/Anthropic API keys (sk-...) -> ***API_KEY***
    - AWS access keys (AKIA...) -> ***AWS_KEY***
    - Generic credentials (api_key=, password=, etc.) -> ***REDACTED***
    - Bearer tokens -> ***REDACTED***

    Args:
        text: The text to scrub

    Returns:
        The text with secrets replaced by redaction markers

    Example:
        >>> scrub_secrets("token=ghp_1234567890abcdefghijklmnopqrstuvwxyz")
        'token=***GITHUB_TOKEN***'
        >>> scrub_secrets("api_key=sk-test123456789abcdefghijk")
        'api_key=***API_KEY***'
    """
    if not text:
        return text

    result = text

    # Scrub GitHub PATs
    result = _GITHUB_PAT_PATTERN.sub("***GITHUB_TOKEN***", result)

    # Scrub OpenAI/Anthropic API keys
    result = _OPENAI_ANTHROPIC_KEY_PATTERN.sub("***API_KEY***", result)

    # Scrub AWS keys
    result = _AWS_KEY_PATTERN.sub("***AWS_KEY***", result)

    # Scrub bearer tokens (preserve the "bearer" or "Authorization: Bearer" prefix)
    result = _BEARER_TOKEN_PATTERN.sub(r"\1***REDACTED***", result)

    # Scrub generic credential patterns (preserve the key name and separator)
    for pattern in _CREDENTIAL_PATTERNS:
        # Replace with group 1 (key name) + separator + redacted marker
        result = pattern.sub(r"\1=***REDACTED***", result)

    return result


def is_potentially_secret(text: str) -> bool:
    """Detect if text contains potential secrets.

    This function checks if the text matches any known secret patterns:
    - GitHub PATs (ghp_, ghs_, gho_)
    - OpenAI/Anthropic API keys (sk-...)
    - AWS access keys (AKIA...)
    - Generic credentials (api_key=, password=, token=, etc.)
    - Bearer tokens

    Args:
        text: The text to check

    Returns:
        True if the text appears to contain secrets, False otherwise

    Example:
        >>> is_potentially_secret("ghp_1234567890abcdefghijklmnopqrstuvwxyz")
        True
        >>> is_potentially_secret("This is a normal description")
        False
    """
    if not text:
        return False

    # Check GitHub PATs
    if _GITHUB_PAT_PATTERN.search(text):
        return True

    # Check OpenAI/Anthropic API keys
    if _OPENAI_ANTHROPIC_KEY_PATTERN.search(text):
        return True

    # Check AWS keys
    if _AWS_KEY_PATTERN.search(text):
        return True

    # Check bearer tokens
    if _BEARER_TOKEN_PATTERN.search(text):
        return True

    # Check generic credential patterns
    return any(pattern.search(text) for pattern in _CREDENTIAL_PATTERNS)
