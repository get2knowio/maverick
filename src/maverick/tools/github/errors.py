from __future__ import annotations

import re

from maverick.utils.security import scrub_secrets


def parse_rate_limit_wait(stderr: str) -> int | None:
    """Parse rate limit wait time from error message (T006).

    Args:
        stderr: Standard error output from gh command.

    Returns:
        Seconds to wait, or None if not a rate limit error.
    """
    patterns = [
        r"retry after (\d+)",
        r"wait (\d+)\s*s",
        r"(\d+)\s*seconds",
    ]

    stderr_lower = stderr.lower()
    if "rate limit" not in stderr_lower:
        return None

    for pattern in patterns:
        match = re.search(pattern, stderr_lower)
        if match:
            return int(match.group(1))

    # Default wait time if rate limited but no specific time given
    return 60


def classify_error(stderr: str, stdout: str = "") -> tuple[str, str, int | None]:
    """Classify gh CLI error and return (message, error_code, retry_after).

    Args:
        stderr: Standard error output.
        stdout: Standard output (sometimes contains error info).

    Returns:
        Tuple of (message, error_code, retry_after_seconds).

    Note:
        Error messages are scrubbed to prevent leaking secrets that might
        appear in command output.
    """
    error_text = (stderr or stdout).lower()

    if "not found" in error_text or "could not find" in error_text:
        return (
            scrub_secrets(stderr or stdout or "Resource not found"),
            "NOT_FOUND",
            None,
        )

    if "rate limit" in error_text:
        retry_after = parse_rate_limit_wait(stderr or stdout)
        msg = f"GitHub API rate limit exceeded. Retry after {retry_after} seconds"
        return msg, "RATE_LIMIT", retry_after

    if "authentication" in error_text or "unauthorized" in error_text:
        return "GitHub CLI not authenticated. Run: gh auth login", "AUTH_ERROR", None

    if "network" in error_text or "connection" in error_text:
        return (
            f"Network error: {scrub_secrets(stderr or stdout)}",
            "NETWORK_ERROR",
            None,
        )

    if "timeout" in error_text:
        return (
            f"Operation timed out: {scrub_secrets(stderr or stdout)}",
            "TIMEOUT",
            None,
        )

    # Generic error
    return scrub_secrets(stderr or stdout or "Unknown error"), "INTERNAL_ERROR", None
