"""Unit tests for secret detection utilities.

Tests the detect_secrets function that uses Yelp's detect-secrets library
to identify potential secrets in text content.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from maverick.utils.secrets import (
    DEFAULT_DETECTORS,
    detect_secrets,
    load_baseline,
)


class TestDetectSecrets:
    """Tests for the detect_secrets function."""

    def test_empty_content(self) -> None:
        """Empty content returns empty list."""
        assert detect_secrets("") == []

    def test_no_secrets(self) -> None:
        """Content without secrets returns empty list."""
        content = "def hello():\n    return 'world'\n"
        assert detect_secrets(content) == []

    def test_aws_access_key(self) -> None:
        """Detects AWS access key IDs."""
        content = "AWS_ACCESS_KEY_ID = 'AKIAIOSFODNN7EXAMPLE'"
        findings = detect_secrets(content)
        assert len(findings) >= 1
        secret_types = [f[1] for f in findings]
        assert "AWS Access Key" in secret_types

    def test_github_token_ghp(self) -> None:
        """Detects GitHub classic PATs (ghp_)."""
        content = "GITHUB_TOKEN = 'ghp_1234567890abcdefghijklmnopqrstuvwxyz'"
        findings = detect_secrets(content)
        assert len(findings) >= 1
        secret_types = [f[1] for f in findings]
        assert "GitHub Token" in secret_types

    def test_github_token_ghs(self) -> None:
        """Detects GitHub server tokens (ghs_)."""
        content = "token = 'ghs_1234567890abcdefghijklmnopqrstuvwxyz'"
        findings = detect_secrets(content)
        assert len(findings) >= 1
        secret_types = [f[1] for f in findings]
        assert "GitHub Token" in secret_types

    def test_private_key(self) -> None:
        """Detects PEM private key headers."""
        content = "-----BEGIN RSA PRIVATE KEY-----"
        findings = detect_secrets(content)
        assert len(findings) == 1
        assert findings[0] == (1, "Private Key")

    def test_private_key_generic(self) -> None:
        """Detects generic private key headers."""
        content = "-----BEGIN PRIVATE KEY-----"
        findings = detect_secrets(content)
        assert len(findings) == 1
        assert findings[0] == (1, "Private Key")

    def test_password_keyword(self) -> None:
        """Detects password assignments via Secret Keyword detector."""
        content = "password = 'mysecretpassword'"
        findings = detect_secrets(content)
        assert len(findings) == 1
        assert findings[0] == (1, "Secret Keyword")

    def test_secret_keyword(self) -> None:
        """Detects secret assignments via Secret Keyword detector."""
        content = "secret = 'topsecretvalue123'"
        findings = detect_secrets(content)
        assert len(findings) == 1
        assert findings[0] == (1, "Secret Keyword")

    def test_api_key_keyword(self) -> None:
        """Detects api_key assignments via Secret Keyword detector."""
        content = "api_key = 'sk-12345678901234567890123456'"
        findings = detect_secrets(content)
        assert len(findings) == 1
        assert findings[0] == (1, "Secret Keyword")

    def test_jwt_token(self) -> None:
        """Detects JSON Web Tokens."""
        # A valid JWT structure (header.payload.signature)
        jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
            "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        )
        content = f"token = '{jwt}'"
        findings = detect_secrets(content)
        assert len(findings) >= 1
        secret_types = [f[1] for f in findings]
        assert "JSON Web Token" in secret_types

    def test_multiple_secrets_same_line(self) -> None:
        """Detects multiple different secret types on the same line."""
        content = "keys: AKIAIOSFODNN7EXAMPLE, ghp_1234567890abcdefghijklmnopqrstuvwxyz"
        findings = detect_secrets(content)
        # Should detect both AWS and GitHub tokens
        secret_types = [f[1] for f in findings]
        assert "AWS Access Key" in secret_types
        assert "GitHub Token" in secret_types

    def test_multiple_secrets_different_lines(self) -> None:
        """Detects secrets on multiple lines with correct line numbers."""
        content = (
            "line1\n"
            "api_key = 'sk-12345678901234567890'\n"
            "line3\n"
            "password = 'secret123456'"
        )
        findings = detect_secrets(content)
        assert len(findings) == 2
        # Both should be Secret Keyword type
        assert findings[0] == (2, "Secret Keyword")
        assert findings[1] == (4, "Secret Keyword")

    def test_line_numbers_are_1_indexed(self) -> None:
        """Verifies line numbers start at 1, not 0."""
        content = "AKIAIOSFODNN7EXAMPLE"
        findings = detect_secrets(content)
        assert len(findings) == 1
        assert findings[0][0] == 1  # Line number should be 1

    def test_multiline_content_correct_line_numbers(self) -> None:
        """Verifies correct line numbers in multiline content."""
        content = "\n\n\nAKIAIOSFODNN7EXAMPLE"  # AWS key on line 4
        findings = detect_secrets(content)
        assert len(findings) == 1
        assert findings[0][0] == 4

    def test_findings_sorted_alphabetically_per_line(self) -> None:
        """Multiple findings on same line are sorted alphabetically by type."""
        content = "keys: ghp_1234567890abcdefghijklmnopqrstuvwxyz AKIAIOSFODNN7EXAMPLE"
        findings = detect_secrets(content)
        line_1_types = [f[1] for f in findings if f[0] == 1]
        assert line_1_types == sorted(line_1_types)

    def test_no_false_positive_on_normal_code(self) -> None:
        """Normal code without secrets returns empty list."""
        content = """
def calculate_sum(a, b):
    \"\"\"Calculate the sum of two numbers.\"\"\"
    result = a + b
    return result

class MyClass:
    def __init__(self, name: str):
        self.name = name
"""
        assert detect_secrets(content) == []


class TestLoadBaseline:
    """Tests for the load_baseline function."""

    def test_nonexistent_file_returns_empty_set(self) -> None:
        """Nonexistent baseline file returns empty set."""
        result = load_baseline(Path("/nonexistent/.secrets.baseline"))
        assert result == set()

    def test_none_path_with_no_baseline_returns_empty_set(self) -> None:
        """None path with no baseline in common locations returns empty set."""
        # This should search common locations and return empty if not found
        result = load_baseline(None)
        assert isinstance(result, set)

    def test_valid_baseline_file(self) -> None:
        """Valid baseline file returns set of hashed secrets."""
        baseline_content = {
            "version": "1.4.0",
            "results": {
                "test.py": [
                    {
                        "hashed_secret": "abc123def456",
                        "is_secret": False,
                        "line_number": 10,
                        "type": "Secret Keyword",
                    },
                    {
                        "hashed_secret": "xyz789uvw012",
                        "is_secret": False,
                        "line_number": 20,
                        "type": "AWS Access Key",
                    },
                ]
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(baseline_content, f)
            temp_path = Path(f.name)

        try:
            result = load_baseline(temp_path)
            assert result == {"abc123def456", "xyz789uvw012"}
        finally:
            temp_path.unlink()

    def test_invalid_json_returns_empty_set(self) -> None:
        """Invalid JSON in baseline file returns empty set."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json {{{")
            temp_path = Path(f.name)

        try:
            result = load_baseline(temp_path)
            assert result == set()
        finally:
            temp_path.unlink()

    def test_empty_results_returns_empty_set(self) -> None:
        """Baseline with empty results returns empty set."""
        baseline_content = {"version": "1.4.0", "results": {}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(baseline_content, f)
            temp_path = Path(f.name)

        try:
            result = load_baseline(temp_path)
            assert result == set()
        finally:
            temp_path.unlink()


class TestDefaultDetectors:
    """Tests for the DEFAULT_DETECTORS configuration."""

    def test_default_detectors_is_tuple(self) -> None:
        """DEFAULT_DETECTORS is an immutable tuple."""
        assert isinstance(DEFAULT_DETECTORS, tuple)

    def test_includes_common_detectors(self) -> None:
        """Includes essential secret detectors."""
        assert "AWS Access Key" in DEFAULT_DETECTORS
        assert "GitHub Token" in DEFAULT_DETECTORS
        assert "Private Key" in DEFAULT_DETECTORS
        assert "Secret Keyword" in DEFAULT_DETECTORS
        assert "JSON Web Token" in DEFAULT_DETECTORS

    def test_includes_modern_service_detectors(self) -> None:
        """Includes modern SaaS service detectors."""
        assert "Slack Token" in DEFAULT_DETECTORS
        assert "Stripe Access Key" in DEFAULT_DETECTORS
        assert "OpenAI Token" in DEFAULT_DETECTORS
        assert "Discord Bot Token" in DEFAULT_DETECTORS
        assert "SendGrid API Key" in DEFAULT_DETECTORS


class TestEdgeCases:
    """Edge case tests for detect_secrets."""

    def test_whitespace_only_content(self) -> None:
        """Whitespace-only content returns empty list."""
        assert detect_secrets("   \n\t\n   ") == []

    def test_binary_like_content(self) -> None:
        """Content with binary-like patterns doesn't crash."""
        content = "\\x00\\x01\\x02\\xff\\xfe"
        # Should not raise, may or may not find secrets
        result = detect_secrets(content)
        assert isinstance(result, list)

    def test_very_long_line(self) -> None:
        """Very long lines are handled gracefully."""
        long_content = "a" * 10000 + "AKIAIOSFODNN7EXAMPLE" + "b" * 10000
        findings = detect_secrets(long_content)
        assert len(findings) == 1
        assert findings[0][1] == "AWS Access Key"

    def test_unicode_content(self) -> None:
        """Unicode content is handled correctly."""
        content = "password = 'contraseña秘密пароль123'"
        findings = detect_secrets(content)
        # Secret Keyword detector should catch this
        assert len(findings) == 1
        assert findings[0][1] == "Secret Keyword"

    def test_special_characters_in_secret(self) -> None:
        """Secrets with special characters are detected."""
        content = "password = 'p@$$w0rd!#%^&*()'"
        findings = detect_secrets(content)
        assert len(findings) == 1
        assert findings[0][1] == "Secret Keyword"
