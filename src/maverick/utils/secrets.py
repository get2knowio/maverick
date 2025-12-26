"""Secret detection utilities for Maverick.

This module provides secret detection functionality to scan text content
for potential secrets like API keys, tokens, and passwords.

Uses Yelp's detect-secrets library for robust, well-maintained secret detection
with support for many secret types including AWS keys, GitHub tokens, private keys,
JWT tokens, and various other API keys.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from detect_secrets.core.plugins.util import get_mapping_from_secret_type_to_class

from maverick.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from detect_secrets.plugins.base import BasePlugin

__all__ = [
    "detect_secrets",
    "load_baseline",
    "DEFAULT_DETECTORS",
]


# Default detectors to use for secret scanning
# These cover the most common secret types with low false positive rates
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
