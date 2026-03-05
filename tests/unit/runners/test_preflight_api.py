"""Unit tests for AnthropicAPIValidator.

Tests for T035: AnthropicAPIValidator unit tests.

This module tests the Anthropic API validation functionality used
by maverick fly and maverick refuel workflows for preflight checks.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import patch

import pytest

from maverick.constants import CLAUDE_HAIKU_LATEST
from maverick.runners.preflight import AnthropicAPIValidator
from maverick.tools._sdk_stubs import ClaudeAgentOptions as _ClaudeAgentOptionsStub


def _make_sdk_module(query_fn: object) -> ModuleType:
    """Create a fake claude_agent_sdk module for sys.modules injection.

    The AnthropicAPIValidator does ``from claude_agent_sdk import
    ClaudeAgentOptions, query`` inside a try block at runtime.  Since the real
    SDK is not installed we inject a lightweight fake module so that the
    ``with patch("claude_agent_sdk.query", ...)`` pattern works correctly.

    Args:
        query_fn: The callable to use as the ``query`` attribute.

    Returns:
        A synthetic module object with ``ClaudeAgentOptions`` and ``query``.
    """
    mod = ModuleType("claude_agent_sdk")
    mod.ClaudeAgentOptions = _ClaudeAgentOptionsStub  # type: ignore[attr-defined]
    mod.query = query_fn  # type: ignore[attr-defined]
    return mod


class TestAnthropicAPIValidator:
    """Unit tests for AnthropicAPIValidator."""

    @pytest.mark.asyncio
    async def test_validate_no_api_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test validation fails when no credentials are set."""
        # Ensure neither credential is set
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

        validator = AnthropicAPIValidator()
        result = await validator.validate()

        assert result.success is False
        assert result.component == "AnthropicAPI"
        assert len(result.errors) == 1
        assert "ANTHROPIC_API_KEY" in result.errors[0]
        assert "CLAUDE_CODE_OAUTH_TOKEN" in result.errors[0]
        assert "is set" in result.errors[0]  # "Neither X nor Y is set"

    @pytest.mark.asyncio
    async def test_validate_oauth_token_set(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test validation passes when OAuth token is set (no API key)."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-token-12345")

        validator = AnthropicAPIValidator(validate_access=False)
        result = await validator.validate()

        assert result.success is True
        assert result.component == "AnthropicAPI"
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_validate_key_set_no_access_check(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test validation passes when key is set and access check is disabled."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")

        validator = AnthropicAPIValidator(validate_access=False)
        result = await validator.validate()

        assert result.success is True
        assert result.component == "AnthropicAPI"
        assert len(result.errors) == 0
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_validate_api_access_success(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test validation passes when API access is successful."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")

        # Mock the query function to return an async iterator
        async def mock_query(*args: object, **kwargs: object) -> object:
            yield "mock response"

        sdk_mod = _make_sdk_module(mock_query)
        with patch.dict(sys.modules, {"claude_agent_sdk": sdk_mod}):
            validator = AnthropicAPIValidator(validate_access=True, timeout=5.0)
            result = await validator.validate()

        assert result.success is True
        assert result.component == "AnthropicAPI"

    @pytest.mark.asyncio
    async def test_validate_api_timeout(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test validation fails on timeout."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")

        # Mock query that never completes
        async def mock_slow_query(*args: object, **kwargs: object) -> object:
            import asyncio

            await asyncio.sleep(10)  # Sleep longer than timeout
            yield "never reached"

        sdk_mod = _make_sdk_module(mock_slow_query)
        with patch.dict(sys.modules, {"claude_agent_sdk": sdk_mod}):
            validator = AnthropicAPIValidator(
                validate_access=True,
                timeout=0.1,  # Very short timeout
            )
            result = await validator.validate()

        assert result.success is False
        assert result.component == "AnthropicAPI"
        assert len(result.errors) == 1
        assert "timed out" in result.errors[0]

    @pytest.mark.asyncio
    async def test_validate_api_401_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test validation fails with clear message on 401 error."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-invalid-key")

        def failing_query(*args: object, **kwargs: object) -> object:
            raise Exception("401 Unauthorized")

        sdk_mod = _make_sdk_module(failing_query)
        with patch.dict(sys.modules, {"claude_agent_sdk": sdk_mod}):
            validator = AnthropicAPIValidator(validate_access=True)
            result = await validator.validate()

        assert result.success is False
        assert result.component == "AnthropicAPI"
        assert len(result.errors) == 1
        assert "Invalid credentials" in result.errors[0]

    @pytest.mark.asyncio
    async def test_validate_api_403_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test validation fails with clear message on 403 error."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")

        def failing_query(*args: object, **kwargs: object) -> object:
            raise Exception("403 Permission denied for model")

        sdk_mod = _make_sdk_module(failing_query)
        with patch.dict(sys.modules, {"claude_agent_sdk": sdk_mod}):
            validator = AnthropicAPIValidator(validate_access=True)
            result = await validator.validate()

        assert result.success is False
        assert result.component == "AnthropicAPI"
        assert len(result.errors) == 1
        assert "access" in result.errors[0].lower()

    @pytest.mark.asyncio
    async def test_validate_api_429_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test validation fails with clear message on 429 rate limit error."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")

        def failing_query(*args: object, **kwargs: object) -> object:
            raise Exception("429 Rate limit exceeded")

        sdk_mod = _make_sdk_module(failing_query)
        with patch.dict(sys.modules, {"claude_agent_sdk": sdk_mod}):
            validator = AnthropicAPIValidator(validate_access=True)
            result = await validator.validate()

        assert result.success is False
        assert result.component == "AnthropicAPI"
        assert len(result.errors) == 1
        assert "Rate limit" in result.errors[0]

    @pytest.mark.asyncio
    async def test_validate_import_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test validation fails gracefully when SDK is not installed."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")

        # Ensure claude_agent_sdk is NOT in sys.modules so the local import
        # inside AnthropicAPIValidator.validate() raises ImportError.
        with patch.dict(sys.modules, {"claude_agent_sdk": None}):  # type: ignore[dict-item]
            validator = AnthropicAPIValidator(validate_access=True)
            result = await validator.validate()

        assert result.success is False
        assert "not installed" in result.errors[0]

    @pytest.mark.asyncio
    async def test_validate_generic_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test validation handles generic errors gracefully."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")

        def failing_query(*args: object, **kwargs: object) -> object:
            raise Exception("Some unexpected error")

        sdk_mod = _make_sdk_module(failing_query)
        with patch.dict(sys.modules, {"claude_agent_sdk": sdk_mod}):
            validator = AnthropicAPIValidator(validate_access=True)
            result = await validator.validate()

        assert result.success is False
        assert result.component == "AnthropicAPI"
        assert len(result.errors) == 1
        assert "Anthropic API error" in result.errors[0]
        assert "Some unexpected error" in result.errors[0]

    def test_validator_default_values(self) -> None:
        """Test AnthropicAPIValidator has correct default values."""
        validator = AnthropicAPIValidator()

        assert validator.validate_access is True
        assert validator.timeout == 10.0
        assert validator.model == CLAUDE_HAIKU_LATEST

    def test_validator_custom_values(self) -> None:
        """Test AnthropicAPIValidator accepts custom values."""
        validator = AnthropicAPIValidator(
            validate_access=False,
            timeout=30.0,
            model="claude-sonnet-4-5-20250929",
        )

        assert validator.validate_access is False
        assert validator.timeout == 30.0
        assert validator.model == "claude-sonnet-4-5-20250929"

    def test_validator_is_frozen(self) -> None:
        """Test AnthropicAPIValidator is immutable (frozen dataclass)."""
        validator = AnthropicAPIValidator()

        with pytest.raises(AttributeError):
            validator.timeout = 20.0  # type: ignore[misc]


class TestAnthropicAPIValidatorWithPreflight:
    """Integration tests with PreflightValidator."""

    @pytest.mark.asyncio
    async def test_validator_works_with_preflight_validator(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test AnthropicAPIValidator can be used with PreflightValidator."""
        from maverick.runners.preflight import PreflightConfig, PreflightValidator

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")

        # Create validators
        api_validator = AnthropicAPIValidator(validate_access=False)

        # Run through PreflightValidator
        preflight = PreflightValidator(
            runners=[api_validator],  # type: ignore[list-item]
            config=PreflightConfig(timeout_per_check=5.0),
        )

        result = await preflight.run()

        assert result.success is True
        assert len(result.results) == 1
        assert result.results[0].component == "AnthropicAPI"

    @pytest.mark.asyncio
    async def test_validator_failure_blocks_preflight(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test AnthropicAPIValidator failure blocks preflight."""
        from maverick.runners.preflight import PreflightConfig, PreflightValidator

        # Remove both credentials to cause failure
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

        api_validator = AnthropicAPIValidator()

        preflight = PreflightValidator(
            runners=[api_validator],  # type: ignore[list-item]
            config=PreflightConfig(timeout_per_check=5.0),
        )

        result = await preflight.run()

        assert result.success is False
        assert "AnthropicAPI" in result.failed_components
        assert len(result.all_errors) >= 1
