"""Unit tests for security utilities.

Tests the secret scrubbing functionality to ensure sensitive information
is properly redacted from logs and outputs.
"""

from __future__ import annotations

import pytest

from maverick.utils.security import is_potentially_secret, scrub_secrets


class TestScrubSecrets:
    """Tests for scrub_secrets function."""

    def test_scrub_github_pat_classic(self) -> None:
        """Test scrubbing of GitHub classic PATs (ghp_)."""
        text = "My token is ghp_1234567890abcdefghijklmnopqrstuvwxyz"
        result = scrub_secrets(text)
        assert "ghp_" not in result
        assert "***GITHUB_TOKEN***" in result
        assert "My token is" in result

    def test_scrub_github_pat_server(self) -> None:
        """Test scrubbing of GitHub server PATs (ghs_)."""
        text = "Server token: ghs_abcdefghijklmnopqrstuvwxyz1234567890"
        result = scrub_secrets(text)
        assert "ghs_" not in result
        assert "***GITHUB_TOKEN***" in result

    def test_scrub_api_key_pattern(self) -> None:
        """Test scrubbing of API key patterns."""
        test_cases = [
            ("api_key=sk_test_1234567890abcdef", "api_key=***REDACTED***"),
            ("apikey: mykey123456789", "apikey=***REDACTED***"),
            ("API-KEY=secret123456", "API-KEY=***REDACTED***"),
        ]
        for input_text, _expected_pattern in test_cases:
            result = scrub_secrets(input_text)
            assert "***REDACTED***" in result, f"Failed to scrub: {input_text}"
            # The actual key should not be present
            if "=" in input_text or ":" in input_text:
                key_value = input_text.split("=")[-1].split(":")[-1].strip()
                assert key_value not in result, f"Key still present in: {result}"

    def test_scrub_secret_pattern(self) -> None:
        """Test scrubbing of secret/token/password patterns."""
        test_cases = [
            "secret=mysecret123",
            "token: abc123def456",
            "password=p@ssw0rd123",
            "passwd: secretpass123",
            "pwd=mypassword",
            "credentials=cred123456789",
        ]
        for text in test_cases:
            result = scrub_secrets(text)
            assert "***REDACTED***" in result, f"Failed to scrub: {text}"

    def test_scrub_aws_key(self) -> None:
        """Test scrubbing of AWS access keys."""
        text = "AWS_KEY=AKIAIOSFODNN7EXAMPLE"
        result = scrub_secrets(text)
        assert "AKIA" not in result or "***AWS_KEY***" in result
        assert "AKIAIOSFODNN7EXAMPLE" not in result

    def test_scrub_openai_key(self) -> None:
        """Test scrubbing of OpenAI/Anthropic API keys."""
        text = "api_key=sk-1234567890abcdefghijklmnopqrstuvwxyz1234567890AB"
        result = scrub_secrets(text)
        assert "sk-1234567890" not in result
        assert "***API_KEY***" in result

    def test_scrub_auth_header(self) -> None:
        """Test scrubbing of authorization headers."""
        test_cases = [
            "Authorization: Bearer abc123def456",
            "bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        ]
        for text in test_cases:
            result = scrub_secrets(text)
            assert "***REDACTED***" in result, f"Failed to scrub: {text}"

    def test_scrub_multiple_secrets(self) -> None:
        """Test scrubbing multiple secrets in one string."""
        text = (
            "My config: api_key=secret123 and "
            "token=ghp_1234567890abcdefghijklmnopqrstuvwxyz and "
            "password=mypass123"
        )
        result = scrub_secrets(text)
        assert "secret123" not in result
        assert "ghp_" not in result
        assert "mypass123" not in result
        assert "***REDACTED***" in result or "***GITHUB_TOKEN***" in result

    def test_scrub_preserves_safe_content(self) -> None:
        """Test that non-sensitive content is preserved."""
        text = "This is a normal PR description with no secrets"
        result = scrub_secrets(text)
        assert result == text

    def test_scrub_empty_string(self) -> None:
        """Test scrubbing empty string."""
        assert scrub_secrets("") == ""

    def test_scrub_case_insensitive(self) -> None:
        """Test that scrubbing is case-insensitive for generic patterns."""
        test_cases = [
            "API_KEY=secret123",
            "api_key=secret123",
            "Api_Key=secret123",
            "PASSWORD=pass123456",
            "password=pass123456",
        ]
        for text in test_cases:
            result = scrub_secrets(text)
            assert "***REDACTED***" in result, f"Failed to scrub: {text}"

    def test_scrub_in_pr_body(self) -> None:
        """Test scrubbing secrets in a realistic PR body."""
        pr_body = """
        ## Changes
        This PR adds authentication using token=ghp_1234567890abcdefghijklmnopqrstuvwxyz

        ## Testing
        Set API_KEY=sk-test1234567890abcdefghijklmnopqrstuvwxyz123456 and run tests
        """
        result = scrub_secrets(pr_body)
        assert "ghp_" not in result
        assert "sk-test" not in result
        assert "***GITHUB_TOKEN***" in result or "***REDACTED***" in result

    def test_scrub_in_issue_description(self) -> None:
        """Test scrubbing secrets in a realistic issue description."""
        issue = """
        Bug: Cannot connect to API

        When using password=supersecret123 I get an error.
        My credentials are: user=admin, pwd=adminpass123
        """
        result = scrub_secrets(issue)
        assert "supersecret123" not in result
        assert "adminpass123" not in result
        assert "***REDACTED***" in result


class TestIsPotentiallySecret:
    """Tests for is_potentially_secret function."""

    def test_detects_github_pat(self) -> None:
        """Test detection of GitHub PAT."""
        assert is_potentially_secret("ghp_1234567890abcdefghijklmnopqrstuvwxyz")
        assert is_potentially_secret("ghs_1234567890abcdefghijklmnopqrstuvwxyz")

    def test_detects_api_key(self) -> None:
        """Test detection of API key patterns."""
        assert is_potentially_secret("api_key=secret123456789")
        assert is_potentially_secret("apikey: mysecretkey123")

    def test_detects_password(self) -> None:
        """Test detection of password patterns."""
        assert is_potentially_secret("password=mypassword123")
        assert is_potentially_secret("pwd=secretpass")

    def test_no_false_positive_on_safe_text(self) -> None:
        """Test that safe text is not flagged."""
        assert not is_potentially_secret("This is a normal description")
        assert not is_potentially_secret("No secrets here!")

    def test_empty_string(self) -> None:
        """Test empty string returns False."""
        assert not is_potentially_secret("")


class TestSecretPatternsComprehensive:
    """Comprehensive tests for all secret patterns."""

    @pytest.mark.parametrize(
        "secret_text,should_be_scrubbed",
        [
            # GitHub PATs
            ("ghp_1234567890123456789012345678901234AB", True),
            ("ghs_1234567890123456789012345678901234AB", True),
            # API keys
            ("sk-1234567890abcdefghijklmnopqrstuvwxyz1234567890AB", True),
            ("AKIAIOSFODNN7EXAMPLE", True),
            # Credentials
            ("api_key=abc1234567890123", True),
            ("apikey: xyz9876543210987", True),
            ("secret=topsecret12345", True),
            ("token=bearer123456789", True),
            ("password=pass12345678", True),
            ("credentials=mycreds123", True),
            # Safe text
            ("Just a normal description", False),
            ("PR #123: Add feature", False),
            ("User: john.doe@example.com", False),
        ],
    )
    def test_pattern_detection(
        self, secret_text: str, should_be_scrubbed: bool
    ) -> None:
        """Test that patterns are correctly detected and scrubbed."""
        result = scrub_secrets(secret_text)
        if should_be_scrubbed:
            # Should contain a redaction marker
            assert "***" in result, (
                f"Expected scrubbing in '{secret_text}' but got '{result}'"
            )
        else:
            # Should be unchanged
            assert result == secret_text, (
                f"Unexpected scrubbing in '{secret_text}' -> '{result}'"
            )
