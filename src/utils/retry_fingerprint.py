"""Deterministic fingerprinting for retry detection.

Computes stable SHA-256 fingerprints from commit ranges and code review findings
to support idempotent retry detection in the review/fix automation loop.
"""

import hashlib


def compute_review_fingerprint(
    commit_range: list[str],
    findings_hash: str,
) -> str:
    """Compute deterministic fingerprint for review loop retry detection.

    Args:
        commit_range: List of commit SHAs in sorted order
        findings_hash: SHA-256 hash of sanitized CodeRabbit findings

    Returns:
        64-character hex string (SHA-256 hash)

    Example:
        >>> commits = ["abc1234", "def5678"]
        >>> findings = "a" * 64  # Example hash
        >>> fp = compute_review_fingerprint(commits, findings)
        >>> len(fp)
        64
    """
    # Sort commits to ensure deterministic ordering
    sorted_commits = sorted(commit_range)

    # Build fingerprint input: commits + findings hash
    fingerprint_input = "|".join(sorted_commits) + "|" + findings_hash

    # Compute SHA-256 hash
    fingerprint = hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()

    return fingerprint


def compute_findings_hash(sanitized_prompt: str) -> str:
    """Compute SHA-256 hash of sanitized CodeRabbit findings.

    Args:
        sanitized_prompt: Sanitized CodeRabbit transcript

    Returns:
        64-character hex string (SHA-256 hash)

    Example:
        >>> prompt = "Issue found: missing error handling"
        >>> hash_val = compute_findings_hash(prompt)
        >>> len(hash_val)
        64
    """
    return hashlib.sha256(sanitized_prompt.encode("utf-8")).hexdigest()
