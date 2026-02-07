"""Secret detection and scrubbing utilities for Maverick.

This is the canonical module for all secret/sensitive-data handling. It provides:

1. **Regex-based output scrubbing** -- ``SENSITIVE_PATTERNS`` and the helper
   functions ``scrub_secrets`` / ``is_potentially_secret`` replace sensitive
   values in log output, command stderr, and hook payloads.

2. **File-scanning via detect-secrets** -- ``DEFAULT_DETECTORS`` and
   ``detect_secrets()`` use Yelp's detect-secrets library for robust,
   plugin-based secret detection in file content.

All other modules that need secret patterns MUST import from here.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from detect_secrets.core.plugins.util import get_mapping_from_secret_type_to_class

from maverick.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from detect_secrets.plugins.base import BasePlugin

__all__ = [
    # Regex-based scrubbing
    "SENSITIVE_PATTERNS",
    "scrub_secrets",
    "is_potentially_secret",
    # detect-secrets plugin scanning
    "detect_secrets",
    "load_baseline",
    "DEFAULT_DETECTORS",
]

# ---------------------------------------------------------------------------
# 1. Consolidated regex patterns for output scrubbing
# ---------------------------------------------------------------------------
# Each entry is ``(raw_pattern, replacement)``.  Patterns are applied in order
# so more specific patterns (GitHub PATs, AWS keys) come before generic ones
# (password=, token=).  All patterns are case-insensitive.
#
# The tuple is the single source of truth -- every consumer should reference
# ``SENSITIVE_PATTERNS`` (or the pre-compiled helpers below) instead of
# defining its own copy.

SENSITIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    # --- Specific token formats (order matters: most specific first) ---
    # GitHub PATs  (ghp_, ghs_, gho_, ghu_, gh_)
    (r"\b(gh[opsu]_[A-Za-z0-9_]{36,})\b", "***GITHUB_TOKEN***"),
    (r"\b(gh_[A-Za-z0-9_]{36,})\b", "***GITHUB_TOKEN***"),
    # OpenAI / Anthropic API keys  (sk-...)
    (r"sk-[a-zA-Z0-9]{32,}", "***API_KEY***"),
    # AWS access keys  (AKIA...)
    (r"AKIA[0-9A-Z]{16}", "***AWS_KEY***"),
    # --- Auth headers ---
    (r"(bearer|authorization)\s+\S+", r"\1 ***REDACTED***"),
    # --- Generic credential assignments  (key=value / key: value) ---
    (r"(password|passwd|pwd)\s*[=:]\s*\S+", r"\1=***REDACTED***"),
    (r"(api[_\-]?key|apikey)\s*[=:]\s*\S+", r"\1=***REDACTED***"),
    (r"(secret|token)\s*[=:]\s*\S+", r"\1=***REDACTED***"),
    (r"(credentials)\s*[=:]\s*\S+", r"\1=***REDACTED***"),
    # --- Broad catch-all (Base64 blobs) -- intentionally last ---
    (r"[a-zA-Z0-9+/]{40,}={0,2}", "***BASE64_REDACTED***"),
)

# Pre-compiled versions for callers that iterate many times.
_COMPILED_SENSITIVE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), replacement)
    for pattern, replacement in SENSITIVE_PATTERNS
)

# Convenience partition used by hooks/logging for its two-phase approach:
# "specific" patterns (first 4 entries) never use group back-references in
# the replacement, while "generic" patterns (the rest) may.
_COMPILED_SPECIFIC_PATTERNS: list[tuple[re.Pattern[str], str]] = list(
    _COMPILED_SENSITIVE_PATTERNS[:4]
)
_COMPILED_GENERIC_PATTERNS: list[tuple[re.Pattern[str], str]] = list(
    _COMPILED_SENSITIVE_PATTERNS[4:]
)


# ---------------------------------------------------------------------------
# 2. scrub_secrets / is_potentially_secret  (regex-based helpers)
# ---------------------------------------------------------------------------


def _make_safe_replacer(replacement: str) -> Callable[[re.Match[str]], str]:
    """Create a replacer that skips already-redacted text.

    Generic patterns (password=, token=, etc.) might re-match output that
    was already redacted by a more specific pattern.  This factory returns
    a ``re.sub`` callable that leaves such matches untouched.

    Args:
        replacement: The replacement template string (may contain group
            back-references such as ``\\1``).

    Returns:
        A function suitable for ``re.sub``.
    """

    def _replacer(match: re.Match[str]) -> str:
        if "***" in match.group(0):
            return match.group(0)
        return match.expand(replacement)

    return _replacer


def scrub_secrets(text: str) -> str:
    """Remove potential secrets from text.

    Replaces various types of secrets with redaction markers:

    - GitHub PATs (ghp_, ghs_, gho_, ghu_, gh_) -> ``***GITHUB_TOKEN***``
    - OpenAI/Anthropic API keys (sk-...) -> ``***API_KEY***``
    - AWS access keys (AKIA...) -> ``***AWS_KEY***``
    - Generic credentials (api_key=, password=, etc.) -> ``***REDACTED***``
    - Bearer / Authorization tokens -> ``***REDACTED***``
    - Long Base64-encoded blobs -> ``***BASE64_REDACTED***``

    Args:
        text: The text to scrub.

    Returns:
        The text with secrets replaced by redaction markers.

    Example:
        >>> scrub_secrets("token=ghp_1234567890abcdefghijklmnopqrstuvwxyz")
        'token=***GITHUB_TOKEN***'
        >>> scrub_secrets("api_key=sk-test123456789abcdefghijk")
        'api_key=***API_KEY***'
    """
    if not text:
        return text

    result = text
    for compiled_pattern, replacement in _COMPILED_SENSITIVE_PATTERNS:
        result = compiled_pattern.sub(_make_safe_replacer(replacement), result)
    return result


def is_potentially_secret(text: str) -> bool:
    """Detect if text contains potential secrets.

    Checks if the text matches any known secret pattern from
    ``SENSITIVE_PATTERNS``.

    Args:
        text: The text to check.

    Returns:
        True if the text appears to contain secrets, False otherwise.

    Example:
        >>> is_potentially_secret("ghp_1234567890abcdefghijklmnopqrstuvwxyz")
        True
        >>> is_potentially_secret("This is a normal description")
        False
    """
    if not text:
        return False

    return any(
        compiled_pattern.search(text)
        for compiled_pattern, _replacement in _COMPILED_SENSITIVE_PATTERNS
    )


# ---------------------------------------------------------------------------
# 3. detect-secrets plugin-based file scanning
# ---------------------------------------------------------------------------

# Default detectors to use for secret scanning.
# These cover the most common secret types with low false positive rates.
DEFAULT_DETECTORS: tuple[str, ...] = (
    "AWS Access Key",
    "GitHub Token",
    "GitLab Token",
    "Private Key",
    "JSON Web Token",
    "Secret Keyword",
    "Slack Token",
    "Stripe Access Key",
    "Twilio API Key",
    "Basic Auth Credentials",
    "OpenAI Token",
    "Telegram Bot Token",
    "Discord Bot Token",
    "SendGrid API Key",
    "NPM tokens",
    "PyPI Token",
)


@lru_cache(maxsize=1)
def _get_detectors() -> dict[str, BasePlugin]:
    """Get or initialize the detector instances.

    Returns:
        Dictionary mapping secret type names to detector instances.
    """
    # get_mapping_from_secret_type_to_class() returns a complex union type
    # that mypy cannot properly infer. We use Any to work around this.
    type_to_class: dict[str, Any] = get_mapping_from_secret_type_to_class()
    return {
        name: type_to_class[name]()
        for name in DEFAULT_DETECTORS
        if name in type_to_class
    }


def load_baseline(baseline_path: Path | str | None = None) -> set[str]:
    """Load a detect-secrets baseline file to get known false positives.

    Args:
        baseline_path: Path to the .secrets.baseline file. If None, attempts
            to find it in common locations (cwd, project root).

    Returns:
        Set of secret hashes that should be ignored (known false positives).
    """
    if baseline_path is None:
        # Try common locations
        candidates = [
            Path.cwd() / ".secrets.baseline",
            Path.cwd().parent / ".secrets.baseline",
        ]
        for candidate in candidates:
            if candidate.exists():
                baseline_path = candidate
                break
        else:
            return set()
    else:
        baseline_path = Path(baseline_path)
        if not baseline_path.exists():
            return set()

    try:
        with open(baseline_path) as f:
            baseline = json.load(f)
        # Extract hashes of known false positives
        hashes: set[str] = set()
        for file_results in baseline.get("results", {}).values():
            for result in file_results:
                if "hashed_secret" in result:
                    hashes.add(result["hashed_secret"])
        return hashes
    except (json.JSONDecodeError, OSError):
        return set()


def detect_secrets(content: str) -> list[tuple[int, str]]:
    """Detect potential secrets in content.

    Scans content for common secret patterns like API keys, tokens,
    and passwords using Yelp's detect-secrets library. Returns line
    numbers and secret type names for logging.

    Args:
        content: Text content to scan for secrets.

    Returns:
        List of (line_number, secret_type) tuples for each detected secret.
        Line numbers are 1-indexed.

    Note:
        Baseline filtering for known false positives is planned for a future
        release. Use load_baseline() to prepare baseline data.

    Example:
        >>> detect_secrets("AKIAIOSFODNN7EXAMPLE")
        [(1, 'AWS Access Key')]
        >>> detect_secrets("ghp_1234567890abcdefghijklmnopqrstuvwxyz")
        [(1, 'GitHub Token')]
    """
    if not content:
        return []

    findings: list[tuple[int, str]] = []
    lines = content.splitlines()
    detectors = _get_detectors()

    for line_num, line in enumerate(lines, start=1):
        line_findings: set[str] = set()

        for secret_type, detector in detectors.items():
            try:
                for _secret_value in detector.analyze_string(line):
                    # Record the finding
                    line_findings.add(secret_type)
                    break  # One match per detector per line is enough
            except Exception as e:
                logger.debug("Detector %s failed on input: %s", secret_type, e)
                continue

        # Add all unique findings for this line
        for secret_type in sorted(line_findings):
            findings.append((line_num, secret_type))

    return findings
