"""Secret detection utilities for Maverick.

This module provides secret detection functionality to scan text content
for potential secrets like API keys, tokens, and passwords.

Uses Yelp's detect-secrets library for robust, well-maintained secret detection
with support for many secret types including AWS keys, GitHub tokens, private keys,
JWT tokens, and various other API keys.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from detect_secrets.core.plugins.util import get_mapping_from_secret_type_to_class

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


# Module-level cache for detector instances
_detector_cache: dict[str, BasePlugin] | None = None


def _get_detectors() -> dict[str, BasePlugin]:
    """Get or initialize the detector instances.

    Returns:
        Dictionary mapping secret type names to detector instances.
    """
    global _detector_cache
    if _detector_cache is None:
        type_to_class = get_mapping_from_secret_type_to_class()
        _detector_cache = {}
        for detector_name in DEFAULT_DETECTORS:
            if detector_name in type_to_class:
                detector_cls = type_to_class[detector_name]
                # type_to_class returns type[BasePlugin], instantiate it
                _detector_cache[detector_name] = detector_cls()  # type: ignore[misc]
    return _detector_cache


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


def detect_secrets(
    content: str,
    baseline_path: Path | str | None = None,
) -> list[tuple[int, str]]:
    """Detect potential secrets in content.

    Scans content for common secret patterns like API keys, tokens,
    and passwords using Yelp's detect-secrets library. Returns line
    numbers and secret type names for logging.

    Args:
        content: Text content to scan for secrets.
        baseline_path: Optional path to a .secrets.baseline file for
            ignoring known false positives.

    Returns:
        List of (line_number, secret_type) tuples for each detected secret.
        Line numbers are 1-indexed.

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

    # Load baseline for false positive filtering if provided
    # Note: Baseline filtering is available but not yet implemented
    # ignored_hashes = load_baseline(baseline_path) if baseline_path else set()
    _ = baseline_path  # Reserved for future baseline filtering support

    for line_num, line in enumerate(lines, start=1):
        line_findings: set[str] = set()

        for secret_type, detector in detectors.items():
            try:
                for _secret_value in detector.analyze_string(line):
                    # If we have a baseline, we could filter by hash here
                    # For now, just record the finding
                    line_findings.add(secret_type)
                    break  # One match per detector per line is enough
            except Exception:
                # Some detectors may fail on certain input; skip gracefully
                continue

        # Add all unique findings for this line
        for secret_type in sorted(line_findings):
            findings.append((line_num, secret_type))

    return findings
