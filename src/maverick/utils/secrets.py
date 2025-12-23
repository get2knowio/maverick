"""Secret detection utilities for Maverick.

This module provides secret detection functionality to scan text content
for potential secrets like API keys, tokens, and passwords.
"""

from __future__ import annotations

import re

__all__ = [
    "SECRET_PATTERNS",
    "detect_secrets",
]

# Secret detection patterns (high precision, low false positives)
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "api_key",
        re.compile(r"(?:api[_-]?key|apikey)\s*[:=]\s*['\"]?[\w-]{20,}", re.IGNORECASE),
    ),
    (
        "bearer_token",
        re.compile(r"(?:bearer|authorization)\s*[:=]\s*['\"]?[\w.-]+", re.IGNORECASE),
    ),
    ("aws_key", re.compile(r"(?:AKIA|ABIA|ACCA|ASIA)[A-Z0-9]{16}")),
    (
        "secret_password",
        re.compile(
            r"(?:secret|password|passwd|pwd)\s*[:=]\s*['\"]?[^\s'\"]{8,}",
            re.IGNORECASE,
        ),
    ),
    ("private_key", re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----")),
]


def detect_secrets(content: str) -> list[tuple[int, str]]:
    """Detect potential secrets in content.

    Scans content for common secret patterns like API keys, tokens,
    and passwords. Returns line numbers and pattern names for logging.

    Args:
        content: Text content to scan for secrets.

    Returns:
        List of (line_number, pattern_name) tuples for each detected secret.
        Line numbers are 1-indexed.

    Example:
        >>> detect_secrets("api_key = 'sk-12345678901234567890'")
        [(1, 'api_key')]
    """
    findings: list[tuple[int, str]] = []
    lines = content.splitlines()

    for line_num, line in enumerate(lines, start=1):
        for pattern_name, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append((line_num, pattern_name))
                break  # One match per line is enough

    return findings
