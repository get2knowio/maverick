"""Provider quota and rate-limit exceptions."""

from __future__ import annotations

import re

from maverick.exceptions.agent import AgentError

# Patterns that indicate a provider quota / rate-limit exhaustion.
# Matched case-insensitively against the stringified error message.
_QUOTA_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"you'?ve? hit your limit", re.IGNORECASE),
    re.compile(r"you'?re out of extra usage", re.IGNORECASE),
    re.compile(r"you have no quota", re.IGNORECASE),
    re.compile(r"exceeded.*(?:rate|usage|plan)\s*limit", re.IGNORECASE),
    re.compile(r"(?:rate|usage|plan)\s*limit\s*(?:exceeded|reached)", re.IGNORECASE),
    re.compile(r"402.*no quota", re.IGNORECASE),
    re.compile(r"quota\s*(?:exceeded|exhausted)", re.IGNORECASE),
    re.compile(r"resets\s+\d+(?:am|pm)", re.IGNORECASE),
]


def is_quota_error(error_msg: str) -> bool:
    """Check whether an error message indicates provider quota exhaustion.

    Args:
        error_msg: The error string to check.

    Returns:
        True if the message matches a known quota/rate-limit pattern.
    """
    return any(p.search(error_msg) for p in _QUOTA_PATTERNS)


def parse_quota_reset(error_msg: str) -> str | None:
    """Extract the reset time from a quota error message.

    Args:
        error_msg: The error string to parse.

    Returns:
        The reset time string (e.g., "6am", "3pm UTC") or None.
    """
    match = re.search(r"resets\s+(\d+(?:am|pm)\s*(?:\([^)]*\)|\S*))", error_msg, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


class ProviderQuotaError(AgentError):
    """Provider usage quota or rate limit exhausted.

    This error is **non-retryable** — retrying against the same provider
    will fail immediately. The workflow should either abort cleanly or
    switch to a different provider.

    Attributes:
        reset_time: Human-readable reset time extracted from the error
            (e.g., "6am UTC"), or None if not parseable.
    """

    def __init__(
        self,
        message: str,
        agent_name: str | None = None,
        reset_time: str | None = None,
    ) -> None:
        self.reset_time = reset_time or parse_quota_reset(message)
        super().__init__(message, agent_name=agent_name)
