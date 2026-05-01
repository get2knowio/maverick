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

# Patterns that indicate a *transient* provider failure: the model is
# probably fine in general but the specific request couldn't be served.
# These are worth a single retry on the same tier and, if still failing,
# escalation to a different tier (typically a different model).
#
# Distinct from quota errors — those are non-retryable on the same
# provider until the limit resets. Transient errors are short-lived
# capacity / network / 5xx blips.
_TRANSIENT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"no capacity available", re.IGNORECASE),
    re.compile(r"capacity\s+(?:exhausted|exceeded|unavailable)", re.IGNORECASE),
    re.compile(r"service\s+unavailable", re.IGNORECASE),
    re.compile(r"internal\s+server\s+error", re.IGNORECASE),
    re.compile(r"bad\s+gateway", re.IGNORECASE),
    re.compile(r"gateway\s+timeout", re.IGNORECASE),
    re.compile(r"\bcode\s*=\s*5\d\d\b", re.IGNORECASE),
    re.compile(r"\bhttp\s*5\d\d\b", re.IGNORECASE),
    re.compile(r"\b5\d\d\s+(?:server|error)\b", re.IGNORECASE),
    re.compile(r"connection\s+reset", re.IGNORECASE),
    re.compile(r"temporarily\s+unavailable", re.IGNORECASE),
]


def is_quota_error(error_msg: str) -> bool:
    """Check whether an error message indicates provider quota exhaustion.

    Args:
        error_msg: The error string to check.

    Returns:
        True if the message matches a known quota/rate-limit pattern.
    """
    return any(p.search(error_msg) for p in _QUOTA_PATTERNS)


def is_transient_error(error_msg: str) -> bool:
    """Check whether an error message indicates a transient provider failure.

    Transient = retryable on the same tier (one retry, brief backoff)
    AND escalation-worthy if the retry also fails. Examples: "No
    capacity available for model X", HTTP 5xx, "service unavailable",
    "connection reset". Distinct from quota errors (which are
    non-retryable until reset) and prompt-content errors (which retry
    won't help).

    Quota errors are explicitly excluded — :func:`is_quota_error` and
    this function are mutually exclusive in their intended handling.

    Args:
        error_msg: The error string to check.

    Returns:
        True if the message matches a known transient-failure pattern
        AND is not a quota error.
    """
    if is_quota_error(error_msg):
        return False
    return any(p.search(error_msg) for p in _TRANSIENT_PATTERNS)


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
