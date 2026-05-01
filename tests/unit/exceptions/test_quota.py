"""Tests for provider quota error detection."""

from __future__ import annotations

import pytest

from maverick.exceptions.quota import (
    ProviderQuotaError,
    is_quota_error,
    is_transient_error,
    parse_quota_reset,
)


class TestIsQuotaError:
    """Test quota pattern matching against real-world error strings."""

    @pytest.mark.parametrize(
        "error_msg",
        [
            # Claude quota messages
            "Internal error: You've hit your limit · resets 6am (undefined)",
            "You've hit your limit · resets 3pm UTC",
            "You're out of extra usage · resets 3pm UTC",
            "You're out of extra usage · resets 8pm (undefined)",
            # Copilot quota messages
            "402 You have no quota (Request ID: abc123)",
            "You have no quota",
            # Generic patterns
            "Rate limit exceeded",
            "Usage limit reached",
            "Plan limit exceeded for this billing period",
            "Quota exhausted",
            "quota exceeded",
            # ACP-wrapped versions
            (
                "ACP prompt failed on session 'abc': Internal error: "
                "You've hit your limit · resets 6am (undefined)"
            ),
        ],
    )
    def test_detects_quota_errors(self, error_msg: str) -> None:
        assert is_quota_error(error_msg) is True

    @pytest.mark.parametrize(
        "error_msg",
        [
            "Connection refused",
            "Timeout after 1200 seconds",
            "Internal server error",
            "no JSON block found in response",
            "Agent not found in registry",
            "Invalid tool 'submit_outline'",
            "",
        ],
    )
    def test_ignores_non_quota_errors(self, error_msg: str) -> None:
        assert is_quota_error(error_msg) is False


class TestParseQuotaReset:
    """Test extraction of reset time from error messages."""

    def test_parse_reset_time_am(self) -> None:
        msg = "You've hit your limit · resets 6am (undefined)"
        assert parse_quota_reset(msg) == "6am (undefined)"

    def test_parse_reset_time_pm_utc(self) -> None:
        msg = "You're out of extra usage · resets 3pm UTC"
        assert parse_quota_reset(msg) == "3pm UTC"

    def test_parse_reset_time_pm_undefined(self) -> None:
        msg = "You've hit your limit · resets 8pm (undefined)"
        assert parse_quota_reset(msg) == "8pm (undefined)"

    def test_no_reset_time(self) -> None:
        msg = "402 You have no quota (Request ID: abc123)"
        assert parse_quota_reset(msg) is None

    def test_no_match(self) -> None:
        assert parse_quota_reset("Connection refused") is None


class TestProviderQuotaError:
    """Test ProviderQuotaError exception class."""

    def test_basic_construction(self) -> None:
        err = ProviderQuotaError("You've hit your limit · resets 6am (undefined)")
        assert "hit your limit" in str(err)
        assert err.reset_time == "6am (undefined)"

    def test_explicit_reset_time(self) -> None:
        err = ProviderQuotaError("quota exhausted", reset_time="3pm UTC")
        assert err.reset_time == "3pm UTC"

    def test_agent_name(self) -> None:
        err = ProviderQuotaError("quota exhausted", agent_name="briefing_navigator")
        assert err.agent_name == "briefing_navigator"

    def test_inherits_from_agent_error(self) -> None:
        from maverick.exceptions import AgentError

        err = ProviderQuotaError("quota exhausted")
        assert isinstance(err, AgentError)


class TestIsTransientError:
    """Pattern matching for retryable / escalation-eligible failures."""

    @pytest.mark.parametrize(
        "error_msg",
        [
            # Real-world capacity errors observed against gemini --acp
            "ACP prompt failed on session 'abc': No capacity available "
            "for model gemini-3.1-pro-preview on the server (code=500)",
            "No capacity available for model X",
            "capacity exhausted for this region",
            "Service unavailable",
            "service unavailable, please retry",
            "Internal server error",
            "Bad gateway",
            "Gateway timeout",
            "code=500 boom",
            "code=503",
            "HTTP 502 Bad Gateway",
            "503 server error",
            "Connection reset by peer",
            "Resource temporarily unavailable",
        ],
    )
    def test_detects_transient_errors(self, error_msg: str) -> None:
        assert is_transient_error(error_msg) is True

    @pytest.mark.parametrize(
        "error_msg",
        [
            # Quota errors are NOT transient — must be excluded.
            "You've hit your limit · resets 6am",
            "402 You have no quota",
            "Rate limit exceeded",
            # Generic non-transient failures
            "Agent not found in registry",
            "Invalid tool 'submit_review'",
            "no JSON block found in response",
            "",
        ],
    )
    def test_ignores_non_transient_errors(self, error_msg: str) -> None:
        assert is_transient_error(error_msg) is False

    def test_quota_and_transient_are_mutually_exclusive(self) -> None:
        """A quota message must never read as transient."""
        msg = "You've hit your limit · resets 6am"
        assert is_quota_error(msg) is True
        assert is_transient_error(msg) is False

    def test_capacity_error_is_transient_not_quota(self) -> None:
        """The earlybird-rn0.16 failure mode: capacity is transient, not quota."""
        msg = (
            "ACP prompt failed on session 'a8dc8098': No capacity "
            "available for model gemini-3.1-pro-preview on the server "
            "(code=500)"
        )
        assert is_transient_error(msg) is True
        assert is_quota_error(msg) is False
