"""Tests for RetryPolicy, StepExecutorConfig, and DEFAULT_EXECUTOR_CONFIG."""

from __future__ import annotations

import pytest

from maverick.dsl.executor.config import (
    DEFAULT_EXECUTOR_CONFIG,
    RetryPolicy,
    StepExecutorConfig,
)


class TestRetryPolicy:
    """Tests for RetryPolicy frozen dataclass."""

    def test_default_values(self) -> None:
        """RetryPolicy has correct defaults."""
        policy = RetryPolicy()
        assert policy.max_attempts == 3
        assert policy.wait_min == 1.0
        assert policy.wait_max == 10.0

    def test_custom_values(self) -> None:
        """RetryPolicy accepts custom values."""
        policy = RetryPolicy(max_attempts=5, wait_min=0.5, wait_max=30.0)
        assert policy.max_attempts == 5
        assert policy.wait_min == 0.5
        assert policy.wait_max == 30.0

    def test_to_dict_roundtrip(self) -> None:
        """RetryPolicy.to_dict() produces JSON-compatible dict."""
        policy = RetryPolicy(max_attempts=5, wait_min=2.0, wait_max=20.0)
        d = policy.to_dict()
        assert d == {"max_attempts": 5, "wait_min": 2.0, "wait_max": 20.0}

    def test_to_dict_default(self) -> None:
        """RetryPolicy.to_dict() works with defaults."""
        policy = RetryPolicy()
        d = policy.to_dict()
        assert d["max_attempts"] == 3
        assert d["wait_min"] == 1.0
        assert d["wait_max"] == 10.0

    def test_frozen_immutable(self) -> None:
        """RetryPolicy is frozen (cannot be mutated)."""
        policy = RetryPolicy()
        with pytest.raises((AttributeError, TypeError)):
            policy.max_attempts = 10  # type: ignore[misc]


class TestStepExecutorConfig:
    """Tests for StepExecutorConfig frozen dataclass."""

    def test_all_none_defaults(self) -> None:
        """StepExecutorConfig defaults all fields to None."""
        config = StepExecutorConfig()
        assert config.timeout is None
        assert config.retry_policy is None
        assert config.model is None
        assert config.temperature is None
        assert config.max_tokens is None

    def test_partial_config(self) -> None:
        """StepExecutorConfig accepts partial configuration."""
        config = StepExecutorConfig(timeout=60, model="claude-opus-4-6")
        assert config.timeout == 60
        assert config.model == "claude-opus-4-6"
        assert config.retry_policy is None
        assert config.temperature is None

    def test_to_dict_all_none(self) -> None:
        """StepExecutorConfig.to_dict() with all-None values."""
        config = StepExecutorConfig()
        d = config.to_dict()
        assert d == {
            "timeout": None,
            "retry_policy": None,
            "model": None,
            "temperature": None,
            "max_tokens": None,
        }

    def test_to_dict_with_retry_policy(self) -> None:
        """StepExecutorConfig.to_dict() includes nested RetryPolicy."""
        policy = RetryPolicy(max_attempts=5)
        config = StepExecutorConfig(timeout=300, retry_policy=policy)
        d = config.to_dict()
        assert d["timeout"] == 300
        assert d["retry_policy"] == {
            "max_attempts": 5,
            "wait_min": 1.0,
            "wait_max": 10.0,
        }

    def test_to_dict_full_config(self) -> None:
        """StepExecutorConfig.to_dict() roundtrip with all fields."""
        config = StepExecutorConfig(
            timeout=600,
            retry_policy=RetryPolicy(max_attempts=2),
            model="claude-opus-4-6",
            temperature=0.5,
            max_tokens=4096,
        )
        d = config.to_dict()
        assert d["timeout"] == 600
        assert d["model"] == "claude-opus-4-6"
        assert d["temperature"] == 0.5
        assert d["max_tokens"] == 4096

    def test_frozen_immutable(self) -> None:
        """StepExecutorConfig is frozen (cannot be mutated)."""
        config = StepExecutorConfig()
        with pytest.raises((AttributeError, TypeError)):
            config.timeout = 300  # type: ignore[misc]


class TestDefaultExecutorConfig:
    """Tests for DEFAULT_EXECUTOR_CONFIG module constant."""

    def test_timeout_300(self) -> None:
        """DEFAULT_EXECUTOR_CONFIG has timeout=300."""
        assert DEFAULT_EXECUTOR_CONFIG.timeout == 300

    def test_no_retry_policy(self) -> None:
        """DEFAULT_EXECUTOR_CONFIG has no retry policy."""
        assert DEFAULT_EXECUTOR_CONFIG.retry_policy is None

    def test_no_model_override(self) -> None:
        """DEFAULT_EXECUTOR_CONFIG has no model override."""
        assert DEFAULT_EXECUTOR_CONFIG.model is None

    def test_is_step_executor_config(self) -> None:
        """DEFAULT_EXECUTOR_CONFIG is a StepExecutorConfig instance."""
        assert isinstance(DEFAULT_EXECUTOR_CONFIG, StepExecutorConfig)
