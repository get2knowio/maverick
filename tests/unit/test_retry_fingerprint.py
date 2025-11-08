"""Unit tests for retry fingerprint generation and validation.

Tests verify deterministic fingerprint computation and retry short-circuiting
logic to support idempotent review/fix loop retries.
"""

from src.utils.retry_fingerprint import (
    compute_findings_hash,
    compute_review_fingerprint,
)


def test_compute_findings_hash_deterministic():
    """Test that findings hash is deterministic for same input."""
    prompt = "Issue found: missing error handling in parser.rs"

    hash1 = compute_findings_hash(prompt)
    hash2 = compute_findings_hash(prompt)

    assert hash1 == hash2
    assert len(hash1) == 64
    assert all(c in "0123456789abcdef" for c in hash1)


def test_compute_findings_hash_different_inputs():
    """Test that different prompts produce different hashes."""
    prompt1 = "Issue found: memory leak"
    prompt2 = "Issue found: type error"

    hash1 = compute_findings_hash(prompt1)
    hash2 = compute_findings_hash(prompt2)

    assert hash1 != hash2
    assert len(hash1) == 64
    assert len(hash2) == 64


def test_compute_findings_hash_empty_string():
    """Test findings hash computation with empty string."""
    hash_val = compute_findings_hash("")

    assert len(hash_val) == 64
    assert all(c in "0123456789abcdef" for c in hash_val)


def test_compute_review_fingerprint_deterministic():
    """Test that review fingerprint is deterministic for same inputs."""
    commits = ["abc1234", "def5678"]
    findings_hash = "a" * 64

    fp1 = compute_review_fingerprint(commits, findings_hash)
    fp2 = compute_review_fingerprint(commits, findings_hash)

    assert fp1 == fp2
    assert len(fp1) == 64
    assert all(c in "0123456789abcdef" for c in fp1)


def test_compute_review_fingerprint_order_independent():
    """Test that commit order doesn't affect fingerprint (sorted internally)."""
    commits_order1 = ["abc1234", "def5678", "ghi9012"]
    commits_order2 = ["ghi9012", "abc1234", "def5678"]
    findings_hash = "b" * 64

    fp1 = compute_review_fingerprint(commits_order1, findings_hash)
    fp2 = compute_review_fingerprint(commits_order2, findings_hash)

    assert fp1 == fp2


def test_compute_review_fingerprint_different_commits():
    """Test that different commit ranges produce different fingerprints."""
    commits1 = ["abc1234"]
    commits2 = ["def5678"]
    findings_hash = "c" * 64

    fp1 = compute_review_fingerprint(commits1, findings_hash)
    fp2 = compute_review_fingerprint(commits2, findings_hash)

    assert fp1 != fp2


def test_compute_review_fingerprint_different_findings():
    """Test that different findings hashes produce different fingerprints."""
    commits = ["abc1234"]
    findings_hash1 = "d" * 64
    findings_hash2 = "e" * 64

    fp1 = compute_review_fingerprint(commits, findings_hash1)
    fp2 = compute_review_fingerprint(commits, findings_hash2)

    assert fp1 != fp2


def test_compute_review_fingerprint_empty_commits():
    """Test fingerprint computation with empty commit list."""
    commits = []
    findings_hash = "f" * 64

    fp = compute_review_fingerprint(commits, findings_hash)

    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)


def test_compute_review_fingerprint_single_commit():
    """Test fingerprint computation with single commit."""
    commits = ["abc1234"]
    findings_hash = "1" * 64

    fp = compute_review_fingerprint(commits, findings_hash)

    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)


def test_compute_review_fingerprint_many_commits():
    """Test fingerprint computation with many commits."""
    commits = [f"commit{i:03d}" for i in range(100)]
    findings_hash = "2" * 64

    fp = compute_review_fingerprint(commits, findings_hash)

    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)


def test_fingerprint_stability_across_calls():
    """Test that fingerprints remain stable across multiple function calls.

    This ensures retry detection will work correctly when activity is invoked
    multiple times with the same inputs.
    """
    commits = ["abc1234", "def5678"]
    prompt = "Issue: memory leak in parser.rs"

    # Simulate multiple activity invocations
    findings_hash1 = compute_findings_hash(prompt)
    fp1 = compute_review_fingerprint(commits, findings_hash1)

    findings_hash2 = compute_findings_hash(prompt)
    fp2 = compute_review_fingerprint(commits, findings_hash2)

    findings_hash3 = compute_findings_hash(prompt)
    fp3 = compute_review_fingerprint(commits, findings_hash3)

    # All fingerprints should be identical
    assert fp1 == fp2 == fp3
    assert findings_hash1 == findings_hash2 == findings_hash3


def test_fingerprint_changes_with_new_commit():
    """Test that adding a new commit changes the fingerprint.

    This ensures retries detect new commits and don't skip review.
    """
    commits_initial = ["abc1234"]
    commits_with_new = ["abc1234", "def5678"]
    findings_hash = "3" * 64

    fp_initial = compute_review_fingerprint(commits_initial, findings_hash)
    fp_with_new = compute_review_fingerprint(commits_with_new, findings_hash)

    assert fp_initial != fp_with_new


def test_fingerprint_changes_with_new_findings():
    """Test that different findings change the fingerprint.

    This ensures retries detect new CodeRabbit findings and don't skip review.
    """
    commits = ["abc1234"]
    prompt1 = "Issue: memory leak"
    prompt2 = "Issue: type error"

    findings_hash1 = compute_findings_hash(prompt1)
    findings_hash2 = compute_findings_hash(prompt2)

    fp1 = compute_review_fingerprint(commits, findings_hash1)
    fp2 = compute_review_fingerprint(commits, findings_hash2)

    assert fp1 != fp2
